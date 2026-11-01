"""Narrate the build cases and write the machine report (S2.8 design §5.7, N-h).

Usage (from the repository root; the runner reads repo-relative stream paths):
    set -a; source .env; set +a
    poetry run python bin/narrator_build_run.py --round N              # dev split
    poetry run python bin/narrator_build_run.py --final --chosen N     # held-out

Runs the real orchestrator for HELIOS-Full (the LLM narrator on the local
model) and HELIOS-noLLM (the template narrator) over one split of each build
corpus, in a scratch store. L-pipe answers come only from the response cache:
an L-pipe prompt that reaches the model aborts the run. The split is L-pipe's
(``split_cases``, per corpus). Prompt rounds are judged on dev by the
verification report only; no ground truth is read. Held-out cases run once,
with ``--final`` for the round the owner chose, and only while the prompt and
parameters are those of that round. Writes
``docs/sprints/s2-reasoning/calibration/narrator_round<N>.json`` or
``narrator_final.json`` (aggregates only, never an incident ID).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bin.log_deviation import load_key
from bin.mahc_build_run import CacheMissError
from helios.evaluation.lpipe_calibration import split_cases
from helios.evaluation.narrative_report import narrative_report
from helios.evaluation.trigger_calibration import CORPORA
from helios.narrative.params import load_narrator_params, narrator_params_hash
from helios.narrative.prompt import NARRATOR_PROMPT_SHA
from helios.orchestrator.corpus import CorpusLoader
from helios.orchestrator.runner import RunOrchestrator
from helios.pipelines.l_pipe.cache import ResponseCache
from helios.pipelines.l_pipe.lpipe_config import MODEL_NAME, OLLAMA_BASE_URL
from helios.pipelines.l_pipe.ollama_client import OllamaClient, OllamaGenerateResult
from helios.store.result_store import ResultStore
from helios.vcl import get_variant, set_current_manifest
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance
from helios.vcl.utils import canonical_json

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = REPO_ROOT / "docs/sprints/s2-reasoning/calibration"
CACHE_PATH = REPO_ROOT / "data/cache/lpipe_cache.sqlite"
BUILD_CORPORA = ("otel_build_v3", "rcaeval_build")
VARIANTS = ("HELIOS-Full", "HELIOS-noLLM")  # LLM narrator, template narrator
_DIGEST_TIMEOUT_S = 10


class _NarratorClient(OllamaClient):
    """The local model for narrator prompts; any other prompt is a cache miss."""

    def generate(
        self, prompt: str, timeout_s: float, schema: dict[str, Any] | None = None
    ) -> OllamaGenerateResult:
        if not prompt.startswith("HELIOS-NARRATOR"):
            raise CacheMissError(
                "an L-pipe answer is not in the cache; rerun the L-pipe build runs"
            )
        return super().generate(prompt, timeout_s, schema)


def make_client() -> OllamaClient:
    return _NarratorClient(OLLAMA_BASE_URL, MODEL_NAME)


class _CountingLedger:
    def __init__(self) -> None:
        self.count = 0

    def append(self, fields: dict[str, str]) -> None:
        del fields
        self.count += 1


def _narrate(split: str, *, key: bytes, client: Any) -> dict[str, Any]:
    """Per corpus: the cases of ``split`` and the report per narrator."""
    params = load_narrator_params()
    out: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for corpus in BUILD_CORPORA:
            captures = REPO_ROOT / CORPORA[corpus][0]
            ids = list(CorpusLoader(captures).incident_ids())
            chosen = {i for i, s in split_cases(ids).items() if s == split}
            rows: list[dict[str, Any]] = []
            excluded = 0
            for variant in VARIANTS:
                manifest = get_variant(variant)
                set_current_manifest(manifest)
                name = f"{corpus}-{variant}"
                ledger = _CountingLedger()
                RunOrchestrator(
                    manifest=manifest,
                    captures_dir=captures,
                    db_path=work / f"{name}.duckdb",
                    registry_path=work / f"{name}.registry.jsonl",
                    reconciliation_path=work / f"{name}.reconciliation.jsonl",
                    exclusion_ledger=ledger,
                    hmac_key=key,
                    lpipe_client=client,
                    lpipe_cache=ResponseCache(CACHE_PATH),
                    narrator_params=params,
                ).run(captures, incidents=chosen)
                store = ResultStore(work / f"{name}.duckdb")
                rows.extend(store.fetch_all_narrative_rows())
                store.close()
                excluded += ledger.count
                print(f"[narrator] {corpus} {variant}: done", flush=True)
            out[corpus] = {
                "cases": len(chosen),
                "excluded": excluded,
                **narrative_report(rows),
            }
    return out


def _chosen_matches(n: int) -> str | None:
    """Why round ``n`` cannot be run on held-out, or None when it can."""
    path = REPORT_DIR / f"narrator_round{n}.json"
    if not path.is_file():
        return f"round {n} has no report"
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("narrator_prompt_sha") != NARRATOR_PROMPT_SHA:
        return f"the narrator prompt differs from round {n}'s"
    # The freeze flips only ``provisional``; any other difference is refused.
    params = load_narrator_params()
    as_run = {
        narrator_params_hash(dataclasses.replace(params, provisional=flag))
        for flag in (True, False)
    }
    if report.get("narrator_params_hash") not in as_run:
        return f"the narrator parameters differ from round {n}'s"
    return None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--round", type=int, help="a dev round; names the report")
    parser.add_argument(
        "--final", action="store_true", help="held-out, for the chosen round"
    )
    parser.add_argument("--chosen", type=int, help="the round the owner chose")
    parser.add_argument("--corpus", choices=("build", "pool"), default="build")
    args = parser.parse_args(argv)
    if args.final == (args.round is not None):
        parser.error("give either --round N or --final --chosen N")
    if args.final and args.chosen is None:
        parser.error("--final needs the chosen round (--chosen N)")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.corpus == "pool":
        print("[narrator] the pool is locked until tag build-freeze", file=sys.stderr)
        return 2
    if Path.cwd().resolve() != REPO_ROOT:
        print(
            "[narrator] run from the repository root (stream paths are relative)",
            file=sys.stderr,
        )
        return 2
    if args.final:
        why = _chosen_matches(args.chosen)
        if why is not None:
            print(f"[narrator] --final refused: {why}", file=sys.stderr)
            return 2
    split = "heldout" if args.final else "dev"
    client = make_client()
    report: dict[str, Any] = {
        "split": split,
        "narrator_prompt_sha": NARRATOR_PROMPT_SHA,
        "narrator_params_hash": narrator_params_hash(load_narrator_params()),
        "model_digest": client.model_digest(_DIGEST_TIMEOUT_S),
        "corpora": _narrate(split, key=load_key(), client=client),
    }
    if args.final:
        report["chosen_round"] = args.chosen
        name = "narrator_final.json"
    else:
        report["round"] = args.round
        name = f"narrator_round{args.round}.json"
    text = json.dumps(json.loads(canonical_json(report)), indent=2, sort_keys=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / name).write_text(text + "\n", encoding="utf-8")
    for corpus, r in report["corpora"].items():
        llm = r.get("llm", {})
        print(
            f"[narrator] {corpus}: {r['cases']} cases, first-pass claims "
            f"{llm.get('first_pass_claim_acceptance')}, slot fallback "
            f"{llm.get('slot_fallback_rate')}, retry success {llm.get('retry_success')}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
