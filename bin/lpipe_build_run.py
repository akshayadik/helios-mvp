"""Run L-pipe on the build cases and report aggregates (S2.3 design §5.8).

Usage:
    set -a; source .env; set +a
    poetry run python bin/lpipe_build_run.py --round N              # dev half
    poetry run python bin/lpipe_build_run.py --round N --split both --final

Per case, one at a time: the frozen trigger, then ``run_lpipe`` (HELIOS-Full)
with the local model and the response cache. Scores L-pipe and each worker
alone (HR@3) per corpus and split. Writes
``docs/sprints/s2-reasoning/calibration/lpipe_round<N>.json`` — aggregates
only, never an incident ID. Prompt revisions are judged on dev only; held-out
cases run only in the final round (``--final``), so they never steer a revision.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bin.log_deviation import load_key
from helios.evaluation.lpipe_calibration import (
    CaseOutcome,
    LPipeCase,
    load_lpipe_cases,
    split_cases,
    summarise,
)
from helios.evaluation.scoring import score_ranking
from helios.pipelines.l_pipe.cache import ResponseCache
from helios.pipelines.l_pipe.lpipe_config import MODEL_NAME, OLLAMA_BASE_URL
from helios.pipelines.l_pipe.ollama_client import OllamaClient
from helios.pipelines.l_pipe.pipeline import run_lpipe
from helios.telemetry.trigger import detect, detector_hash, load_detector_params
from helios.vcl import get_variant, set_current_manifest
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance
from helios.vcl.utils import canonical_json

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = REPO_ROOT / "docs/sprints/s2-reasoning/calibration"
CACHE_PATH = REPO_ROOT / "data/cache/lpipe_cache.sqlite"
VARIANT = "HELIOS-Full"
_STREAMS = ("p1_metrics_path", "p2_traces_path", "p3_logs_path")
_PROGRESS_EVERY = 25
_MS_PER_S = 1_000


def make_client() -> OllamaClient:
    return OllamaClient(OLLAMA_BASE_URL, MODEL_NAME)


def _absolute(case: LPipeCase) -> Any:
    window = case.window
    for attr in _STREAMS:
        value = getattr(window, attr)
        if value is not None and not Path(value).is_absolute():
            window = window.model_copy(update={attr: str(REPO_ROOT / value)})
    return window


def _hit(ranked: list[str], root: str) -> int:
    return score_ranking(ranked, root).hr_at_3 if ranked else 0


def _outcome(
    case: LPipeCase, split: Any, out: dict[str, Any]
) -> tuple[CaseOutcome, dict[str, Any] | None]:
    evidence = out.get("evidence")
    workers = (evidence or {}).get("workers", {})
    hits = {
        name: None if w["dropped"] else _hit(list(w["ranked"]), case.root_cause)
        for name, w in workers.items()
    }
    drops = {name: str(w["dropped"]) for name, w in workers.items() if w["dropped"]}
    if evidence is None:
        drops = {"pipeline": str(out["status"])}
    outcome = CaseOutcome(
        corpus=case.corpus,
        split=split,
        fault=case.fault,
        lpipe_hit=_hit(list(out["ranked_candidates"]), case.root_cause),
        worker_hits=hits,
        k=int((evidence or {}).get("k", 0)),
        drops=drops,
        seconds=float(out["latency_ms"]) / _MS_PER_S,
        cache_hit=bool(out.get("cache_hit")),
    )
    return outcome, evidence


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Dev by default; held-out numbers only with --final (design §5.8)."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--split", choices=("dev", "heldout", "both"), default="dev")
    parser.add_argument(
        "--final",
        action="store_true",
        help="the last round, after the prompts are settled: held-out may be run",
    )
    parser.add_argument("--corpus", choices=("build", "pool"), default="build")
    args = parser.parse_args(argv)
    if args.split != "dev" and not args.final:
        parser.error("held-out cases run only in the final round (--final)")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.corpus == "pool":
        print("[lpipe] the pool is locked until tag build-freeze", file=sys.stderr)
        return 2
    detector = load_detector_params()
    if detector.provisional:
        print("[lpipe] detector parameters are provisional", file=sys.stderr)
        return 2
    cases = load_lpipe_cases(root=REPO_ROOT, key=load_key())
    splits: dict[str, Any] = {}
    for corpus in sorted({c.corpus for c in cases}):
        splits.update(split_cases([c.incident_id for c in cases if c.corpus == corpus]))
    chosen = [c for c in cases if args.split in ("both", splits[c.incident_id])]
    client = make_client()
    cache = ResponseCache(CACHE_PATH)
    manifest = get_variant(VARIANT)
    outcomes: list[CaseOutcome] = []
    pinned: dict[str, Any] = {}
    for n, case in enumerate(chosen, start=1):
        set_current_manifest(manifest)
        window = _absolute(case)
        trigger = detect(window, detector, root=REPO_ROOT)
        out = run_lpipe(
            incident_id=window.incident_id,
            snapshot_hash=window.compute_window_hash(),
            evaluation_phase=window.evaluation_phase.value,
            run_id=f"lpipe-round{args.round}",
            window=window,
            trigger=trigger,
            root=REPO_ROOT,
            client=client,
            cache=cache,
        )
        outcome, evidence = _outcome(case, splits[case.incident_id], out)
        outcomes.append(outcome)
        if evidence and not pinned:
            pinned = {
                "model_digest": evidence["model_digest"],
                "prompt_shas": evidence["prompt_shas"],
            }
        if n % _PROGRESS_EVERY == 0:
            print(f"[lpipe] {n}/{len(chosen)} cases", flush=True)
    report: dict[str, Any] = {
        "round": args.round,
        "split": args.split,
        "variant": VARIANT,
        "detector_hash": detector_hash(detector),
        **pinned,
        "summary": summarise(outcomes),
    }
    text = json.dumps(json.loads(canonical_json(report)), indent=2, sort_keys=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / f"lpipe_round{args.round}.json").write_text(text + "\n", "utf-8")
    for corpus, groups in report["summary"].items():
        for split, g in groups.items():
            print(
                f"[lpipe] {corpus} {split}: {g['cases']} cases, "
                f"HR@3 hits {g['lpipe_hr3_hits']}, workers {g['worker_hr3_hits']}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
