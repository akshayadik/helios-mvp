#!/usr/bin/env python3
"""Subprocess entry point: run RunOrchestrator for a single named variant.

Called by run_ablation.py via subprocess.run(). Accepts CLI args for the
variant name, DB output path, and data directory.

Usage:
    python scripts/run_one_variant.py --variant HELIOS-Full \\
        --db-path /tmp/helios/HELIOS-Full.duckdb \\
        --captures-dir data/captures \\
        --registry-path data/snapshot_registry.jsonl \\
        --reconciliation-path data/reconciliation_ledger.jsonl \\
        --exclusion-ledger exclusion_ledger.jsonl
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from helios.vcl.config import VCLManifest  # noqa: F401 — flag-guard compliance

HELIOS_ENABLE_RUN_ONE_VARIANT: bool = True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one HELIOS variant.")
    parser.add_argument("--variant", required=True)
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--captures-dir", type=Path, required=True)
    parser.add_argument("--registry-path", type=Path, required=True)
    parser.add_argument("--reconciliation-path", type=Path, required=True)
    parser.add_argument("--exclusion-ledger", type=Path, required=True)
    args = parser.parse_args(argv)

    hmac_secret = os.environ.get("DEVIATION_HMAC_SECRET", "")
    hmac_key: bytes = hmac_secret.encode("utf-8")

    from typing import cast

    from bin.log_exclusion import ExclusionLedger
    from helios.integrity_gate import AppendOnlyLedger
    from helios.orchestrator.runner import RunOrchestrator
    from helios.vcl import get_variant, set_current_manifest

    manifest = get_variant(args.variant)
    set_current_manifest(manifest)

    # ExclusionLedger.append() has a broader signature than the AppendOnlyLedger
    # Protocol (it returns the signed entry dict rather than None).  It satisfies
    # the protocol structurally at runtime; cast() informs mypy.
    exclusion_ledger: AppendOnlyLedger = cast(
        AppendOnlyLedger, ExclusionLedger(key=hmac_key, log_path=args.exclusion_ledger)
    )

    orchestrator = RunOrchestrator(
        manifest=manifest,
        captures_dir=args.captures_dir,
        db_path=args.db_path,
        registry_path=args.registry_path,
        reconciliation_path=args.reconciliation_path,
        exclusion_ledger=exclusion_ledger,
        hmac_key=hmac_key,
    )
    orchestrator.run(corpus=args.captures_dir)
    print(f"[run_one_variant] {args.variant} complete → {args.db_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
