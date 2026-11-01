"""Keep signed CoE ledgers of the build cases for rater training (S2.9 §5.7).

Usage (from the repository root; Ollama serving the frozen model):
    set -a; source .env; set +a
    poetry run python bin/labelling_runs.py --out data/labelling/build

Runs HELIOS-Full (the frozen narrator on the local model; L-pipe answers from
the response cache only) and HELIOS-noLLM over both build corpora through the
real orchestrator, and keeps each run's signed CoE ledger in
``<out>/<corpus>-<variant>.coe/``. The pool is refused, an existing output
directory is refused, and no ground-truth file is opened. Prints counts only.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bin.log_deviation import load_ed25519_private, load_key, load_public_key_file
from bin.narrator_build_run import (
    BUILD_CORPORA,
    CACHE_PATH,
    _CountingLedger,
    make_client,
)
from helios.evaluation.trigger_calibration import CORPORA
from helios.narrative.params import load_narrator_params
from helios.orchestrator.runner import RunOrchestrator
from helios.pipelines.l_pipe.cache import ResponseCache
from helios.vcl import VCLFlag, get_variant, set_current_manifest  # noqa: F401

__all__ = [
    "BUILD_CORPORA",
    "CACHE_PATH",
    "CORPORA",
    "load_signer",
    "main",
    "make_client",
]

REPO_ROOT = Path(__file__).resolve().parent.parent
VARIANTS = ("HELIOS-Full", "HELIOS-noLLM")


def load_signer() -> Any:
    """The Ed25519 key that signs CoE anchors (as the orchestrator's CoE ledger
    uses it, S2.7); checked against the committed public key."""
    return load_ed25519_private(load_public_key_file())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--corpus", choices=("build", "pool"), default="build")
    args = parser.parse_args(argv)
    if args.corpus == "pool":
        print("[labelling] the pool is locked until tag build-freeze", file=sys.stderr)
        return 2
    if args.out.exists():
        print(f"[labelling] refused: {args.out} exists", file=sys.stderr)
        return 2
    key, signer = load_key(), load_signer()
    client = make_client()
    params = load_narrator_params()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for corpus in BUILD_CORPORA:
            captures = REPO_ROOT / CORPORA[corpus][0]
            for variant in VARIANTS:
                manifest = get_variant(variant)
                set_current_manifest(manifest)
                name = f"{corpus}-{variant}"
                ledger = _CountingLedger()
                orch = RunOrchestrator(
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
                    coe_path=args.out / f"{name}.coe" / f"{name}.coe.jsonl",
                    coe_signer=signer,
                )
                orch.run(captures)
                print(f"[labelling] {name}: excluded {ledger.count}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
