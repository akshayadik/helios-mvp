#!/usr/bin/env python3
"""Append a signed exclusion ledger entry to exclusion_ledger.jsonl.

Records runtime metric-integrity-gate failures (§3.6.8). Each entry is
HMAC-SHA256 chained identically to the deviation log. Written by the
metric integrity gate (Stage 1+) or this CLI for manual entries.

Schema (§3.6.8):
    timestamp_utc:        ISO-8601 with Z suffix (UTC)
    commit_sha:           Git commit SHA ($GITHUB_SHA in CI, else "LOCAL")
    prev_signature:       Hex signature of preceding entry, or "GENESIS"
    variant_config_hash:  64-char SHA-256 of the VCLManifest
    snapshot_hash:        64-char SHA-256 of the telemetry snapshot
    run_id:               Unique run identifier
    incident_id:          Corpus incident reference (links to result store)
    gate_check:           Which integrity check failed (e.g. snapshot_hash_match)
    reason:               Human-readable explanation
    analytic_consequence: Which runs / hypothesis is affected
    signature:            HMAC-SHA256 hex over canonical JSON of all above fields
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from helios.vcl.hmac_chain import GENESIS as GENESIS  # re-export for tests
from helios.vcl.hmac_chain import HMACChainedLog

HELIOS_ENABLE_EXCLUSION_LEDGER: bool = True  # always-on C1 audit infrastructure

LOG_FILE = Path("exclusion_ledger.jsonl")
ENV_KEY = "DEVIATION_HMAC_SECRET"


def load_key() -> bytes:
    """Read the HMAC secret from $DEVIATION_HMAC_SECRET. Exit on failure."""
    key = os.getenv(ENV_KEY)
    if not key:
        sys.stderr.write(
            f"ERROR: {ENV_KEY} not set. Copy .env.example to .env and set a secret.\n"
        )
        sys.exit(2)
    if len(key) < 32:
        sys.stderr.write(
            f"ERROR: {ENV_KEY} must be at least 32 characters (got {len(key)}).\n"
        )
        sys.exit(2)
    return key.encode("utf-8")


class ExclusionLedger(HMACChainedLog):
    """HMAC-chained log for metric-integrity-gate exclusion events (§3.6.8)."""

    REQUIRED_FIELDS = (
        "variant_config_hash",
        "snapshot_hash",
        "run_id",
        "incident_id",
        "gate_check",
        "reason",
        "analytic_consequence",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd")

    parser.add_argument("--variant-config-hash")
    parser.add_argument("--snapshot-hash")
    parser.add_argument("--run-id")
    parser.add_argument("--incident-id")
    parser.add_argument("--gate-check")
    parser.add_argument("--reason")
    parser.add_argument("--analytic-consequence")

    sub.add_parser("verify", help="Verify the entire HMAC chain.")

    args = parser.parse_args()

    if args.cmd == "verify":
        ledger = ExclusionLedger(key=load_key(), log_path=LOG_FILE)
        ok, msg = ledger.verify()
        print(("✅ " if ok else "❌ ") + msg)
        return 0 if ok else 1

    required_args = [
        "variant_config_hash",
        "snapshot_hash",
        "run_id",
        "incident_id",
        "gate_check",
        "reason",
        "analytic_consequence",
    ]
    missing = [r for r in required_args if not getattr(args, r, None)]
    if missing:
        flags = ", ".join("--" + m.replace("_", "-") for m in missing)
        parser.error(f"Missing required arguments: {flags}")

    fields = {
        "variant_config_hash": args.variant_config_hash,
        "snapshot_hash": args.snapshot_hash,
        "run_id": args.run_id,
        "incident_id": args.incident_id,
        "gate_check": args.gate_check,
        "reason": args.reason,
        "analytic_consequence": args.analytic_consequence,
    }
    ledger = ExclusionLedger(key=load_key(), log_path=LOG_FILE)
    entry = ledger.append(fields)
    print(
        f"✅ Exclusion logged: {entry['run_id']} | gate={entry['gate_check']}"
        f" | sig={entry['signature'][:12]}..."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
