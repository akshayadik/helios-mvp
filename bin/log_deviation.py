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
    ed25519_signature:    From entry 35 (D7): Ed25519 over every field above

Ed25519 (owner decision D7, S0.9): from entry ED25519_FROM_ENTRY on, entries
and the head anchor are also signed with an Ed25519 key. The private key lives
in $DEVIATION_ED25519_PRIVATE_KEY (.env); the public key is committed at
PUBLIC_KEY_FILE and deposited on OSF.

    log_deviation.py --stage ... --clause ...   append an entry (both keys needed)
    log_deviation.py verify                      HMAC chain + Ed25519 (HMAC secret)
    log_deviation.py verify-public               Ed25519 only, public key only
    log_deviation.py keygen                      one-time: print the private-key
                                                 .env line, write the public key
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from helios.vcl.ed25519 import (
    generate_private_key,
    load_private_key,
    load_public_key,
    private_key_to_env_value,
    public_key_pem,
)
from helios.vcl.hmac_chain import GENESIS as GENESIS  # re-export for tests
from helios.vcl.hmac_chain import HMACChainedLog, verify_public

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )

HELIOS_ENABLE_DEVIATION_LOG: bool = True  # always-on C1 audit infrastructure

LOG_FILE = Path("deviation_log.jsonl")
ENV_KEY = "DEVIATION_HMAC_SECRET"
ED25519_ENV_VAR = "DEVIATION_ED25519_PRIVATE_KEY"
PUBLIC_KEY_FILE = Path("keys/deviation_log_ed25519.pub.pem")
# Entries 1-34 predate D7 and stay HMAC-only; the signed anchor's log digest covers them.
ED25519_FROM_ENTRY = 35


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


def load_public_key_file(path: Path = PUBLIC_KEY_FILE) -> Ed25519PublicKey | None:
    """The committed Ed25519 public key, or None if it has not been created."""
    return load_public_key(path) if path.exists() else None


def load_ed25519_private(public: Ed25519PublicKey | None) -> Ed25519PrivateKey:
    """Read the Ed25519 private key from the environment; exit on any problem."""
    value = os.getenv(ED25519_ENV_VAR)
    if not value:
        sys.stderr.write(
            f"ERROR: {ED25519_ENV_VAR} not set. Entries from {ED25519_FROM_ENTRY} on "
            "must be Ed25519-signed (see CLAUDE.md, setup).\n"
        )
        sys.exit(2)
    try:
        private = load_private_key(value)
    except ValueError as exc:
        sys.stderr.write(f"ERROR: {ED25519_ENV_VAR}: {exc}\n")
        sys.exit(2)
    if public is None or public_key_pem(private) != public_key_pem(public):
        sys.stderr.write(
            f"ERROR: {ED25519_ENV_VAR} does not match the committed public key "
            f"{PUBLIC_KEY_FILE}.\n"
        )
        sys.exit(2)
    return private


class DeviationLog(HMACChainedLog):
    """HMAC-chained log for research protocol deviations (§B.12)."""

    REQUIRED_FIELDS = ("stage", "clause", "change", "reason", "analytic_consequence")
    LOG_KIND = "deviation"
    ED25519_FROM_ENTRY = ED25519_FROM_ENTRY

    def _post_sign_fields(self, entry: dict[str, Any]) -> dict[str, Any]:
        entry["deviation_id"] = entry["signature"][:16]
        return entry

    def _check_post_sign_fields(self, entry: dict[str, Any]) -> str | None:
        # Entries 1-3 predate deviation_id; when present it must match.
        dev_id = entry.get("deviation_id")
        if dev_id is not None and dev_id != entry["signature"][:16]:
            return f"deviation_id {dev_id!r} does not match signature prefix."
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd")

    parser.add_argument("--stage")
    parser.add_argument("--clause")
    parser.add_argument("--change")
    parser.add_argument("--reason")
    parser.add_argument("--analytic-consequence")

    sub.add_parser("verify", help="Verify the HMAC chain and Ed25519 signatures.")
    sub.add_parser("verify-public", help="Verify with the public key only.")
    sub.add_parser("keygen", help="One-time Ed25519 key generation.")

    args = parser.parse_args(argv)

    if args.cmd == "keygen":
        if PUBLIC_KEY_FILE.exists():
            sys.stderr.write(
                f"ERROR: {PUBLIC_KEY_FILE} exists; refusing to replace it.\n"
            )
            return 2
        private = generate_private_key()
        PUBLIC_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        PUBLIC_KEY_FILE.write_bytes(public_key_pem(private))
        print(f"{ED25519_ENV_VAR}={private_key_to_env_value(private)}")
        return 0

    if args.cmd == "verify-public":
        public = load_public_key_file()
        if public is None:
            print(f"❌ Public key {PUBLIC_KEY_FILE} missing.")
            return 1
        ok, msg = verify_public(
            LOG_FILE,
            LOG_FILE.with_name(f"{LOG_FILE.stem}.anchor.json"),
            public,
            from_entry=ED25519_FROM_ENTRY,
            log_kind=DeviationLog.LOG_KIND,
        )
        print(("✅ " if ok else "❌ ") + msg)
        return 0 if ok else 1

    if args.cmd == "verify":
        ledger = DeviationLog(
            key=load_key(), log_path=LOG_FILE, ed25519_public=load_public_key_file()
        )
        # Required even for an empty log: deleting log + anchor together
        # must not read as a fresh, valid log.
        if not ledger.anchor_path.exists():
            print(f"❌ Anchor {ledger.anchor_path.name} missing.")
            return 1
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
    public = load_public_key_file()
    ledger = DeviationLog(
        key=load_key(),
        log_path=LOG_FILE,
        ed25519_private=load_ed25519_private(public),
        ed25519_public=public,
    )
    entry = ledger.append(fields)
    print(f"✅ Deviation logged: {entry['clause']} | sig={entry['signature'][:12]}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
