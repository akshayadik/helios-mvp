#!/usr/bin/env python3
"""Verify every HMAC-chained ledger in the repo root, head anchors required.

    verify_ledgers.py                 verify all three ledgers (exit 1 on any failure)
    verify_ledgers.py --init-anchors  create missing anchors for valid logs, then verify
    verify_ledgers.py --coe DIR       verify every *.coe.jsonl in DIR (S2.7) instead
    verify_ledgers.py --coe DIR --public-only   the same with the public key alone
    verify_ledgers.py --annotations DIR [--public-only]   every *.annotations.jsonl
                                      in DIR (S2.9), against the annotations key

A ledger passes only if its chain verifies, every entry has the fields of its
kind, and its signed head anchor matches the entry count and head signature.
A missing anchor is a failure even for an empty log: deleting a log together
with its anchor would otherwise read as a fresh, valid log.

--coe checks each Chain-of-Evidence file's HMAC chain and its Ed25519-signed
anchor (whole-file digest) against the public key; an unsigned anchor fails.
With --public-only no HMAC secret is needed: the signed digest covers every byte.
CoE files live beside a run's results database, not in the repository.

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

from bin.log_deviation import (
    PUBLIC_KEY_FILE,
    DeviationLog,
    load_key,
    load_public_key_file,
)
from bin.log_exclusion import ExclusionLedger
from helios.labelling.annotations import (
    ANNOTATIONS_HMAC_ENV_VAR,
    ANNOTATIONS_PUBLIC_KEY_FILE,
    AnnotationLedger,
    load_annotations_hmac,
)
from helios.orchestrator.coe import CoELedger
from helios.orchestrator.ledger import ReconciliationLedger
from helios.vcl.hmac_chain import verify_public

if TYPE_CHECKING:
    from helios.vcl.hmac_chain import HMACChainedLog

HELIOS_ENABLE_LEDGER_VERIFY: bool = True  # always-on C1 audit infrastructure

LEDGERS: tuple[tuple[type[HMACChainedLog], Path], ...] = (
    (DeviationLog, Path("deviation_log.jsonl")),
    (ExclusionLedger, Path("exclusion_ledger.jsonl")),
    (ReconciliationLedger, Path("reconciliation_ledger.jsonl")),
)


def _verify_anchored_dir(
    directory: Path,
    key: bytes | None,
    public_path: Path,
    cls: type[CoELedger] | type[AnnotationLedger],
) -> int:
    """Verify every ``*.<kind>.jsonl`` in ``directory``; 1 if any fails or none
    is found. Without ``key`` only the Ed25519 anchor and file digest are checked."""
    public = load_public_key_file(public_path)
    pattern = f"*.{cls.LOG_KIND}.jsonl"
    paths = sorted(directory.glob(pattern))
    if public is None or not paths:
        what = f"public key {public_path}" if public is None else pattern
        print(f"❌ {directory}: no {what} found.")
        return 1
    failed = False
    for path in paths:
        anchor = path.with_name(path.name.removesuffix(".jsonl") + ".anchor.json")
        ok, msg = True, ""
        if key is not None:
            ok, msg = cls(key, path, ed25519_public=public).verify()
        if ok:
            ok, msg = verify_public(
                path, anchor, public, from_entry=None, log_kind=cls.LOG_KIND
            )
        print(f"{'✅' if ok else '❌'} {path}: {msg}")
        failed |= not ok
    return 1 if failed else 0


def verify_coe_dir(directory: Path, key: bytes | None, public_path: Path) -> int:
    """Verify every CoE file in ``directory`` (S2.7)."""
    return _verify_anchored_dir(directory, key, public_path, CoELedger)


def verify_annotations_dir(
    directory: Path, key: bytes | None, public_path: Path
) -> int:
    """Verify every annotations ledger in ``directory`` (S2.9, R-n)."""
    return _verify_anchored_dir(directory, key, public_path, AnnotationLedger)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--init-anchors", action="store_true")
    parser.add_argument("--coe", type=Path, metavar="DIR")
    parser.add_argument("--annotations", type=Path, metavar="DIR")
    parser.add_argument("--public-key", type=Path, default=None)
    parser.add_argument("--public-only", action="store_true")
    args = parser.parse_args(argv)

    if args.coe is not None:
        key = None if args.public_only else load_key()
        return verify_coe_dir(args.coe, key, args.public_key or PUBLIC_KEY_FILE)
    if args.annotations is not None:
        key = None if args.public_only else load_annotations_hmac()
        if key is None and not args.public_only:
            print(f"❌ {ANNOTATIONS_HMAC_ENV_VAR} not set (or use --public-only).")
            return 1
        public = args.public_key or ANNOTATIONS_PUBLIC_KEY_FILE
        return verify_annotations_dir(args.annotations, key, public)
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
