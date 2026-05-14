#!/usr/bin/env python3
"""helios run — orchestrate a corpus through the full C1 pipeline (§3.6.8).

Usage:
    poetry run python bin/helios_run.py --variant HELIOS-Full --corpus data/captures/
    poetry run python bin/helios_run.py --variant HELIOS-Full --corpus corpus.json

Requires DEVIATION_HMAC_SECRET in environment (same secret as deviation log).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from helios.orchestrator.runner import RunOrchestrator
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance
from helios.vcl.hmac_chain import HMACChainedLog
from helios.vcl.variants import get_variant

HELIOS_ENABLE_ORCHESTRATOR: bool = True

_ENV_KEY = "DEVIATION_HMAC_SECRET"


class _ExclusionLedger(HMACChainedLog):
    """Inline exclusion ledger for the CLI — mirrors bin/log_exclusion.py ExclusionLedger."""

    REQUIRED_FIELDS: tuple[str, ...] = (
        "variant_config_hash",
        "snapshot_hash",
        "run_id",
        "incident_id",
        "gate_check",
        "reason",
        "analytic_consequence",
    )

    def append(self, fields: dict[str, str]) -> None:  # type: ignore[override]
        """Satisfy AppendOnlyLedger protocol — delegates to HMACChainedLog.append."""
        super().append(fields)


def _load_key() -> bytes:
    key = os.environ.get(_ENV_KEY, "")
    if not key or len(key) < 32:
        sys.stderr.write(f"ERROR: {_ENV_KEY} must be set and at least 32 characters.\n")
        sys.exit(2)
    return key.encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="helios run",
        description="Run a corpus of incidents through the full C1 pipeline.",
    )
    parser.add_argument(
        "--variant",
        required=True,
        help="Variant name, e.g. HELIOS-Full",
    )
    parser.add_argument(
        "--corpus",
        required=True,
        type=Path,
        help="Path to captures directory or corpus.json manifest",
    )
    parser.add_argument(
        "--captures-dir",
        type=Path,
        default=Path("data/captures"),
        help="Root directory of Parquet captures (default: data/captures/)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/results.duckdb"),
        help="DuckDB result store path (default: data/results.duckdb)",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("data/snapshot_registry.jsonl"),
        help="SnapshotRegistry path (default: data/snapshot_registry.jsonl)",
    )
    parser.add_argument(
        "--reconciliation",
        type=Path,
        default=Path("reconciliation_ledger.jsonl"),
        help="ReconciliationLedger output path",
    )
    args = parser.parse_args()

    key = _load_key()
    manifest = get_variant(args.variant)
    exclusion_ledger = _ExclusionLedger(
        key=key, log_path=Path("exclusion_ledger.jsonl")
    )

    orchestrator = RunOrchestrator(
        manifest=manifest,
        captures_dir=args.captures_dir,
        db_path=args.db,
        registry_path=args.registry,
        reconciliation_path=args.reconciliation,
        exclusion_ledger=exclusion_ledger,
        hmac_key=key,
    )

    print(f"[helios run] variant={args.variant} corpus={args.corpus}")
    orchestrator.run(args.corpus)
    print("[helios run] done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
