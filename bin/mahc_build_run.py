"""Fit and check MAHC on the build cases (S2.5 design §5.2-5.4; M-a, M-c, M-e).

Usage (from the repository root; the runner reads repo-relative stream paths):
    set -a; source .env; set +a
    poetry run python bin/mahc_build_run.py --run N

Runs the real orchestrator (HELIOS-Full, frozen detector, D-, G- and L-pipe,
provisional MAHC parameters) over the sealed build corpora into a scratch
store. L-pipe answers come only from the response cache: a cache miss aborts
the run rather than calling the model. Then priors and calibration are
nested cross-fitted, the floor is chosen, and the parameters are refitted on
all build cases. Writes ``docs/sprints/s2-reasoning/calibration/mahc_run<N>.json``
(aggregates only, never an incident ID). Exit 3 when a corpus cannot reach the
floor target: the owner decides (M-e). Never writes ``data/frozen/``.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bin.log_deviation import load_key
from helios.adapters.rcaeval import verify_ground_truth
from helios.consensus.mahc import Vote
from helios.consensus.params import (
    MAHCParams,
    load_mahc_params,
    mahc_params_hash,
)
from helios.evaluation.mahc_calibration import (
    BuildCase,
    evaluate,
    fit_priors,
    inner_calibrator,
    prior_case,
)
from helios.evaluation.scoring import _ranked
from helios.evaluation.trigger_calibration import CORPORA
from helios.orchestrator.runner import RunOrchestrator
from helios.pipelines.l_pipe.cache import ResponseCache
from helios.pipelines.l_pipe.lpipe_config import (
    EXPECTED_MODEL_DIGEST,
    MODEL_NAME,
    OLLAMA_BASE_URL,
)
from helios.pipelines.l_pipe.ollama_client import (
    OllamaClient,
    OllamaGenerateResult,
)
from helios.store.result_store import ResultStore
from helios.telemetry.scope import in_scope
from helios.telemetry.signal_type import SignalType
from helios.vcl import get_variant, set_current_manifest
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance
from helios.vcl.utils import canonical_json

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = REPO_ROOT / "docs/sprints/s2-reasoning/calibration"
CACHE_PATH = REPO_ROOT / "data/cache/lpipe_cache.sqlite"
BUILD_CORPORA = ("otel_build_v3", "rcaeval_build")
VARIANT = "HELIOS-Full"


class CacheMissError(RuntimeError):
    """The build run needed a model call the cache did not hold."""


class LPipeFailedError(RuntimeError):
    """An L-pipe verdict failed in the build run; MAHC must not be fitted without it."""


class _CacheOnlyClient(OllamaClient):
    """Answers only from the response cache; never contacts the model server."""

    def model_digest(self, timeout_s: float) -> str:
        del timeout_s
        if EXPECTED_MODEL_DIGEST is None:
            raise CacheMissError("the model digest is not pinned (entry 58)")
        return EXPECTED_MODEL_DIGEST

    def generate(self, prompt: str, timeout_s: float) -> OllamaGenerateResult:
        raise CacheMissError(
            "an L-pipe answer is not in the cache; rerun the L-pipe build runs"
        )


class _CountingLedger:
    def __init__(self) -> None:
        self.count = 0

    def append(self, fields: dict[str, str]) -> None:
        del fields
        self.count += 1


def _cases_from_store(
    store: ResultStore, corpus: str, labels: dict[str, Any]
) -> list[BuildCase]:
    fusion = {str(f["run_id"]): f for f in store.fetch_all_fusion_rows()}
    by_run: dict[str, list[dict[str, Any]]] = {}
    for row in store.fetch_all():
        by_run.setdefault(str(row["run_id"]), []).append(row)
    cases = []
    failed = [
        r
        for rows in by_run.values()
        for r in rows
        if r["pipeline"] == "lpipe" and r["status"] == "failed"
    ]
    if failed:
        raise LPipeFailedError(
            f"{len(failed)} L-pipe verdict(s) failed in the build run"
        )
    for run_id, rows in sorted(
        by_run.items(), key=lambda kv: (str(kv[1][0]["incident_id"]), kv[0])
    ):
        incident = str(rows[0]["incident_id"])
        label = labels[incident]
        votes = []
        for r in sorted(rows, key=lambda r: str(r["pipeline"])):
            ranked = tuple(s for s in _ranked(r["ranked_candidates"]) if in_scope(s))
            if r["status"] == "ranked" and ranked:
                sigma = r.get("sigma")
                votes.append(
                    Vote(
                        str(r["pipeline"]), ranked, 1 if sigma is None else float(sigma)
                    )
                )
        signal = SignalType(fusion[run_id]["evidence"].get("signal", "unclassified"))
        group = str(label.get("system") or label["root_cause_service"])
        cases.append(
            BuildCase(
                incident,
                corpus,
                group,
                signal,
                tuple(votes),
                str(label["root_cause_service"]),
            )
        )
    return cases


def collect_cases(*, key: bytes) -> tuple[list[BuildCase], dict[str, int]]:
    """Run HELIOS-Full over both build corpora; the cases and the exclusion count."""
    manifest = get_variant(VARIANT)
    cases: list[BuildCase] = []
    excluded = 0
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for corpus in BUILD_CORPORA:
            captures, _manifest, truth = (REPO_ROOT / p for p in CORPORA[corpus])
            labels = verify_ground_truth(truth, key)
            ledger = _CountingLedger()
            set_current_manifest(manifest)
            RunOrchestrator(
                manifest=manifest,
                captures_dir=captures,
                db_path=work / f"{corpus}.duckdb",
                registry_path=work / f"{corpus}.registry.jsonl",
                reconciliation_path=work / f"{corpus}.reconciliation.jsonl",
                exclusion_ledger=ledger,
                hmac_key=key,
                lpipe_client=_CacheOnlyClient(OLLAMA_BASE_URL, MODEL_NAME),
                lpipe_cache=ResponseCache(CACHE_PATH),
                mahc_params=load_mahc_params(),
            ).run(captures)
            store = ResultStore(work / f"{corpus}.duckdb")
            cases.extend(_cases_from_store(store, corpus, labels))
            store.close()
            excluded += ledger.count
            print(f"[mahc] {corpus}: {len(cases)} cases so far", flush=True)
    return cases, {"excluded": excluded}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", choices=("build", "pool"), default="build")
    parser.add_argument(
        "--run", type=int, default=1, help="names the report mahc_run<N>.json"
    )
    args = parser.parse_args(argv)
    if args.corpus == "pool":
        print("[mahc] the pool is locked until tag build-freeze", file=sys.stderr)
        return 2
    if Path.cwd().resolve() != REPO_ROOT:
        print(
            "[mahc] run from the repository root (stream paths are relative)",
            file=sys.stderr,
        )
        return 2
    cases, counts = collect_cases(key=load_key())
    report = evaluate(cases)
    idx = list(range(len(cases)))
    refit = MAHCParams(
        priors=fit_priors([prior_case(c) for c in cases]),
        calibrator=inner_calibrator(cases, idx),
        floor=report["floor"],
        provisional=False,
    )
    report.update(
        {
            "variant": VARIANT,
            "cases": len(cases),
            **counts,
            "refit": refit.as_dict(),
            "refit_hash": mahc_params_hash(refit),
        }
    )
    text = json.dumps(json.loads(canonical_json(report)), indent=2, sort_keys=True)
    report_path = REPORT_DIR / f"mahc_run{args.run}.json"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text + "\n", encoding="utf-8")
    for name, g in report["by_corpus"].items():
        print(
            f"[mahc] {name}: {g['cases']} cases, MAHC HR@3 {g['mahc_hr3']}, "
            f"vote-only {g['vote_only_hr3']}, confirmed {g['confirmed']} "
            f"(HR@3 {g['hr3_confirmed']})"
        )
    if report["floor"] is None:
        print(
            "[mahc] a corpus cannot reach HR@3 0.8 at any confidence: stop (M-e)",
            file=sys.stderr,
        )
        return 3
    print(f"[mahc] floor {report['floor']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
