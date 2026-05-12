#!/usr/bin/env python3
"""Append a signed deviation log entry to deviation_log.jsonl.

Each entry is HMAC-SHA256 chained: every entry's signature signs both its own
fields AND the previous entry's signature, so any tampering anywhere in the
chain invalidates every subsequent signature. The first entry's prev_signature
is the literal string "GENESIS".

Schema (§B.12):
    timestamp_utc:        ISO-8601 with Z suffix (UTC)
    commit_sha:           Git commit SHA ($GITHUB_SHA in CI, else "LOCAL")
    prev_signature:       Hex signature of preceding entry, or "GENESIS"
    stage:                Stage 0..8
    clause:               Section reference (e.g. "§3.6.6")
    change:               Concrete description of what changed
    reason:               Justification
    analytic_consequence: Which hypothesis/variant is affected
    signature:            HMAC-SHA256 hex over canonical JSON of all above fields
    deviation_id:         First 16 chars of signature (post-sign, not in payload)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from helios.vcl.hmac_chain import GENESIS as GENESIS  # re-export for tests
from helios.vcl.hmac_chain import HMACChainedLog

HELIOS_ENABLE_DEVIATION_LOG: bool = True  # always-on C1 audit infrastructure

LOG_FILE = Path("deviation_log.jsonl")
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


class DeviationLog(HMACChainedLog):
    """HMAC-chained log for research protocol deviations (§B.12)."""

    REQUIRED_FIELDS = ("stage", "clause", "change", "reason", "analytic_consequence")

    def _post_sign_fields(self, entry: dict[str, Any]) -> dict[str, Any]:
        entry["deviation_id"] = entry["signature"][:16]
        return entry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd")

    parser.add_argument("--stage")
    parser.add_argument("--clause")
    parser.add_argument("--change")
    parser.add_argument("--reason")
    parser.add_argument("--analytic-consequence")

    sub.add_parser("verify", help="Verify the entire HMAC chain.")

    args = parser.parse_args()

    if args.cmd == "verify":
        ledger = DeviationLog(key=load_key(), log_path=LOG_FILE)
        ok, msg = ledger.verify()
        print(("✅ " if ok else "❌ ") + msg)
        return 0 if ok else 1

    required = ["stage", "clause", "change", "reason", "analytic_consequence"]
    missing = [r for r in required if not getattr(args, r, None)]
    if missing:
        flags = ", ".join("--" + m.replace("_", "-") for m in missing)
        parser.error(f"Missing required arguments: {flags}")

    fields = {
        "stage": args.stage,
        "clause": args.clause,
        "change": args.change,
        "reason": args.reason,
        "analytic_consequence": args.analytic_consequence,
    }
    ledger = DeviationLog(key=load_key(), log_path=LOG_FILE)
    entry = ledger.append(fields)
    print(f"✅ Deviation logged: {entry['clause']} | sig={entry['signature'][:12]}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
