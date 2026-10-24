#!/usr/bin/env python3
"""Verify every HMAC-chained ledger in the repo root, head anchors required.

    verify_ledgers.py                 verify all three ledgers (exit 1 on any failure)
    verify_ledgers.py --init-anchors  create missing anchors for valid logs, then verify

A ledger passes only if its chain verifies, every entry has the fields of its
kind, and its signed head anchor matches the entry count and head signature.
A missing anchor is a failure even for an empty log: deleting a log together
with its anchor would otherwise read as a fresh, valid log.

--init-anchors is a one-time bootstrap for logs written before anchors existed
(2026-10-22). It refuses to overwrite an existing anchor. Run it only after the
log content has been reviewed against an independent record (git history,
preregistration.md deviation table).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from bin.log_deviation import DeviationLog, load_key, load_public_key_file
from bin.log_exclusion import ExclusionLedger
from helios.orchestrator.ledger import ReconciliationLedger

if TYPE_CHECKING:
    from helios.vcl.hmac_chain import HMACChainedLog

HELIOS_ENABLE_LEDGER_VERIFY: bool = True  # always-on C1 audit infrastructure

LEDGERS: tuple[tuple[type[HMACChainedLog], Path], ...] = (
    (DeviationLog, Path("deviation_log.jsonl")),
    (ExclusionLedger, Path("exclusion_ledger.jsonl")),
    (ReconciliationLedger, Path("reconciliation_ledger.jsonl")),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--init-anchors", action="store_true")
    args = parser.parse_args(argv)

    key = load_key()
    failed = False
    for cls, path in LEDGERS:
        # The deviation log is also Ed25519-signed from entry 35 (D7).
        public = load_public_key_file() if cls is DeviationLog else None
        ledger = cls(key=key, log_path=path, ed25519_public=public)
        if args.init_anchors and not ledger.anchor_path.exists():
            print(f"⚓ {path}: {ledger.init_anchor()}")
        if not ledger.anchor_path.exists():
            ok, msg = False, f"anchor {ledger.anchor_path.name} missing."
        else:
            ok, msg = ledger.verify()
        print(f"{'✅' if ok else '❌'} {path}: {msg}")
        failed |= not ok
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
