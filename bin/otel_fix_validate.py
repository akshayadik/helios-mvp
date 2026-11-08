"""OTel fix validation: old chain against the candidate chain, once (entry 76, O-f).

Usage (from the repository root):
    set -a; source .env; set +a
    poetry run python bin/otel_fix_validate.py

Runs HELIOS-Full (the decision) and HELIOS-noRouter (reported) with the
current frozen chain (*old*, ``data/frozen/``) and the candidate chain (*new*,
``data/candidate/otel_fix/``) over the held-out OTel v4 corpus (36 cases) and
RCAEval build (495), and scores each run's published fused list (HR@3,
signed labels, exact service names).

- v4 is read here and nowhere else, once: the tool refuses to run when its
  report exists.
- L-pipe: RCAEval build answers come from the response cache only (as every
  build run). v4 answers are new: the pinned model is called (its digest is
  checked) and the answers cached, so both chains and both variants read the
  same answers. The narrator never runs (it does not change fusion).
- Adoption rule (fixed in entry 76): *new* is adopted if its HELIOS-Full v4
  hits are at least *old*'s + ``MARGIN_V4`` AND its HELIOS-Full RCAEval build
  HR@3 is at least *old*'s. The tool reports the decision; it never writes
  ``data/frozen/``.

Writes ``docs/sprints/s3-routing/calibration/otel_fix_validation.json``
(aggregates and per-fault counts, no incident ID).
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
from bin.mahc_build_run import CACHE_PATH, _CacheOnlyClient, _CountingLedger
from helios.adapters.rcaeval import verify_ground_truth
from helios.consensus.router_params import (
    ROUTER_PARAMS_PATH,
    RouterParams,
    load_router_params,
    router_params_hash,
)
from helios.evaluation.candidate_set import CANDIDATE_ROOT, ChainParams, load_chain
from helios.evaluation.scoring import score_ranking
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
    OllamaConnectionError,
    OllamaGenerateResult,
)
from helios.store.result_store import ResultStore
from helios.vcl import get_variant, set_current_manifest
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance
from helios.vcl.utils import canonical_json

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT = Path("docs/sprints/s3-routing/calibration/otel_fix_validation.json")
CANDIDATE = CANDIDATE_ROOT / "otel_fix"
HELDOUT = "otel_heldout_v4"
RCAEVAL = "rcaeval_build"
CORPUS_FILES: dict[str, tuple[str, str, str]] = {
    HELDOUT: (
        "data/otel/heldout_v4",
        "data/otel/heldout_v4_manifest.json",
        "data/otel/ground_truth_heldout_v4.json",
    ),
    RCAEVAL: CORPORA[RCAEVAL],
}
DECISION = "HELIOS-Full"
VARIANTS = (DECISION, "HELIOS-noRouter")
MARGIN_V4 = 2
_DIGITS = 6


class _LiveNoNarrator(OllamaClient):
    """The pinned model for L-pipe workers; the narrator falls back to its template."""

    def generate(
        self, prompt: str, timeout_s: float, schema: dict[str, Any] | None = None
    ) -> OllamaGenerateResult:
        if prompt.startswith("HELIOS-NARRATOR"):
            raise OllamaConnectionError("validation run: no narrator model")
        return super().generate(prompt, timeout_s, schema)


def chains(candidate: Path = CANDIDATE) -> dict[str, tuple[ChainParams, RouterParams]]:
    """*old* (frozen) and *new* (candidate); the candidate must hold every refit."""
    for name in ("gpipe_params.json", "mahc_params.json", "router_params.json"):
        if not (candidate / name).is_file():
            raise FileNotFoundError(f"candidate {candidate} lacks {name}")
    return {
        "old": (load_chain(), load_router_params(ROUTER_PARAMS_PATH)),
        "new": (
            load_chain(candidate),
            load_router_params(candidate / "router_params.json"),
        ),
    }


def decide(hits: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    """Entry 76's rule on the HELIOS-Full results of both chains."""
    old, new = hits["old"][DECISION], hits["new"][DECISION]
    v4 = new[HELDOUT]["hits"] >= old[HELDOUT]["hits"] + MARGIN_V4
    rca = new[RCAEVAL]["hr_at_3"] >= old[RCAEVAL]["hr_at_3"]
    return {
        "rule": (
            f"new HELIOS-Full v4 hits >= old + {MARGIN_V4} AND new HELIOS-Full "
            "rcaeval_build HR@3 >= old"
        ),
        "v4_holds": v4,
        "rcaeval_holds": rca,
        "adopted": v4 and rca,
    }


def _score(
    store: ResultStore, labels: dict[str, Any]
) -> tuple[int, int, dict[str, list[int]]]:
    """(hits, cases scored, per-fault [hits, cases]) of the published lists."""
    hits = n = 0
    by_fault: dict[str, list[int]] = {}
    for row in store.fetch_all_fusion_rows():
        label = labels[str(row["incident_id"])]
        hit = score_ranking(list(row["ranked"]), str(label["root_cause_service"]))
        fault = str(label.get("fault") or "unknown")
        cell = by_fault.setdefault(fault, [0, 0])
        cell[0] += hit.hr_at_3
        cell[1] += 1
        hits += hit.hr_at_3
        n += 1
    return hits, n, by_fault


def run_one(
    corpus: str,
    variant: str,
    chain: ChainParams,
    router: RouterParams,
    *,
    key: bytes,
    work: Path,
    tag: str,
) -> dict[str, Any]:
    """Run one variant and chain over one corpus; its scores."""
    captures, _manifest, truth = (REPO_ROOT / p for p in CORPUS_FILES[corpus])
    labels = verify_ground_truth(truth, key)
    manifest = get_variant(variant)
    set_current_manifest(manifest)
    client = (
        _LiveNoNarrator(OLLAMA_BASE_URL, MODEL_NAME)
        if corpus == HELDOUT
        else _CacheOnlyClient(OLLAMA_BASE_URL, MODEL_NAME)
    )
    ledger = _CountingLedger()
    db = work / f"{tag}.duckdb"
    RunOrchestrator(
        manifest=manifest,
        captures_dir=captures,
        db_path=db,
        registry_path=work / f"{tag}.registry.jsonl",
        reconciliation_path=work / f"{tag}.reconciliation.jsonl",
        exclusion_ledger=ledger,
        hmac_key=key,
        lpipe_client=client,
        lpipe_cache=ResponseCache(CACHE_PATH),
        dpipe_params=chain.dpipe,
        gpipe_params=chain.gpipe,
        mahc_params=chain.mahc,
        router_params=router,
    ).run(captures)
    store = ResultStore(db)
    hits, n, by_fault = _score(store, labels)
    store.close()
    out: dict[str, Any] = {
        "hits": hits,
        "cases": n,
        "labelled": len(labels),
        "excluded": ledger.count,
        "hr_at_3": round(hits / n, _DIGITS) if n else None,
    }
    if corpus == HELDOUT:
        out["by_fault"] = {
            f: {"hits": h, "cases": c} for f, (h, c) in sorted(by_fault.items())
        }
    print(f"[validate] {tag}: HR@3 {hits}/{n}", flush=True)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)
    path = REPO_ROOT / REPORT
    if path.exists():
        print(f"[validate] {REPORT} exists: v4 is read once", file=sys.stderr)
        return 2
    if Path.cwd().resolve() != REPO_ROOT:
        print("[validate] run from the repository root", file=sys.stderr)
        return 2
    if EXPECTED_MODEL_DIGEST is None:
        print("[validate] the model digest is not pinned", file=sys.stderr)
        return 2
    live = OllamaClient(OLLAMA_BASE_URL, MODEL_NAME)
    if live.model_digest(timeout_s=10) != EXPECTED_MODEL_DIGEST:
        print("[validate] the served model is not the pinned one", file=sys.stderr)
        return 2
    key = load_key()
    sets = chains()
    results: dict[str, dict[str, dict[str, Any]]] = {}
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        # v4 with the old chain first: it fills the cache every later run reads.
        for corpus in (HELDOUT, RCAEVAL):
            for name in ("old", "new"):
                chain, router = sets[name]
                for variant in VARIANTS:
                    tag = f"{corpus}.{name}.{variant}"
                    results.setdefault(name, {}).setdefault(variant, {})[corpus] = (
                        run_one(
                            corpus, variant, chain, router, key=key, work=work, tag=tag
                        )
                    )
    d = decide(results)
    report: dict[str, Any] = {
        "deviation_entries": [76, 77, 78, 79, 80],
        "chains": {
            name: {
                **chain.hashes(),
                "router": router_params_hash(router),
                "sources": chain.sources,
            }
            for name, (chain, router) in sets.items()
        },
        "model_digest": EXPECTED_MODEL_DIGEST,
        "results": results,
        "decision": d,
    }
    text = json.dumps(json.loads(canonical_json(report)), indent=2, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8")
    print(
        f"[validate] v4 rule {d['v4_holds']}, RCAEval rule {d['rcaeval_holds']}: "
        f"{'ADOPT new' if d['adopted'] else 'KEEP old'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
