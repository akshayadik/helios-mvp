#!/usr/bin/env python3
"""Append a signed deviation log entry to deviation_log.jsonl.

Each entry is HMAC-SHA256 chained: every entry's signature signs both its own
fields AND the previous entry's signature, so any tampering anywhere in the
chain invalidates every subsequent signature. The first entry's prev_signature
is the literal string "GENESIS".

Schema:
    timestamp_utc:        ISO-8601 with Z suffix (UTC)
    commit_sha:           Git commit SHA (from $GITHUB_SHA in CI, else "LOCAL")
    prev_signature:       Hex signature of the immediately preceding entry, or "GENESIS"
    stage:                Stage 0..8
    clause:               Section reference (e.g., "§3.6.6 / Execution Plan §6")
    change:               Concrete description of what changed
    reason:               Justification
    analytic_consequence: Typically: which hypothesis/variant moves status
    signature:            HMAC-SHA256 hex over canonical JSON of all above fields
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path
from typing import Any

LOG_FILE = Path("deviation_log.jsonl")
ENV_KEY = "DEVIATION_HMAC_SECRET"
GENESIS = "GENESIS"


def load_key() -> bytes:
    """Read the HMAC secret from $DEVIATION_HMAC_SECRET. Exit on failure."""
    key = os.getenv(ENV_KEY)
    if not key:
        sys.stderr.write(f"ERROR: {ENV_KEY} not set. Copy .env.example to .env and set a secret.\n")
        sys.exit(2)
    if len(key) < 32:
        sys.stderr.write(f"ERROR: {ENV_KEY} must be at least 32 characters (got {len(key)}).\n")
        sys.exit(2)
    return key.encode("utf-8")


def previous_signature(log_path: Path) -> str:
    """Return signature of the last entry, or GENESIS if file is empty/missing."""
    if not log_path.exists() or log_path.stat().st_size == 0:
        return GENESIS
    last = ""
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                last = stripped
    if not last:
        return GENESIS
    return json.loads(last)["signature"]


def compute_signature(key: bytes, entry: dict[str, Any]) -> str:
    """HMAC-SHA256 over canonical JSON of entry, excluding the signature field itself."""
    payload_dict = {k: v for k, v in entry.items() if k != "signature"}
    payload = json.dumps(payload_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def append_entry(log_path: Path, fields: dict[str, Any]) -> dict[str, Any]:
    """Build, sign, and append a new entry. Returns the full entry dict."""
    key = load_key()
    prev_sig = previous_signature(log_path)
    entry: dict[str, Any] = {
        "timestamp_utc": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
        "commit_sha": os.getenv("GITHUB_SHA", "LOCAL"),
        "prev_signature": prev_sig,
        **fields,
    }
    entry["signature"] = compute_signature(key, entry)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def verify_chain(log_path: Path) -> tuple[bool, str]:
    """Walk the chain from genesis; return (ok, message)."""
    if not log_path.exists() or log_path.stat().st_size == 0:
        return True, "Empty log — vacuously valid."
    key = load_key()
    expected_prev = GENESIS
    with log_path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            entry = json.loads(stripped)
            if entry.get("prev_signature") != expected_prev:
                got = entry.get("prev_signature", "")[:12]
                return False, (
                    f"Line {lineno}: prev_signature mismatch "
                    f"(expected {expected_prev[:12]}..., got {got}...)"
                )
            recomputed = compute_signature(key, entry)
            if recomputed != entry.get("signature"):
                return False, f"Line {lineno}: signature does not verify (entry tampered)."
            expected_prev = entry["signature"]
    return True, "Chain verified."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd")

    # Default behaviour: append (kept compatible with bare invocation)
    parser.add_argument("--stage")
    parser.add_argument("--clause")
    parser.add_argument("--change")
    parser.add_argument("--reason")
    parser.add_argument("--analytic-consequence")

    # `verify` subcommand
    sub.add_parser("verify", help="Verify the entire HMAC chain.")

    args = parser.parse_args()

    if args.cmd == "verify":
        ok, msg = verify_chain(LOG_FILE)
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
    entry = append_entry(LOG_FILE, fields)
    print(f"✅ Deviation logged: {entry['clause']} | sig={entry['signature'][:12]}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
