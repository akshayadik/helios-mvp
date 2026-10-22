#!/usr/bin/env python3
"""CLI entry point for snapshot + content-seal verification of HELIOS captures.

Usage (from repo root; the seal check needs the ledger key):
    set -a; source .env; set +a
    poetry run python bin/verify_captures.py
    poetry run python bin/verify_captures.py --incident-id s0-cart-001
    poetry run python bin/verify_captures.py --captures-dir data/captures
    poetry run python bin/verify_captures.py --init-seals   # one-time bootstrap

A capture passes only if its manifest window_hash matches AND its signed
content_seal.json matches the manifest bytes and every Parquet stream.
Exits 0 if every listed capture passes; 1 if any is tampered, unsealed,
missing or unreadable.

--init-seals seals captures that have no seal yet, and only when every file
of the capture is tracked by git and identical to HEAD: the committed blobs
are the independent record that the bytes being sealed are the recorded ones.
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bin.log_deviation import load_key
from helios.telemetry.reader import CaptureReader
from helios.telemetry.seal import SEAL_FILENAME, write_seal
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance

_ALL_INCIDENT_IDS = [
    "s0-adhc-001",
    "s0-adhc-002",
    "s0-adhc-003",
    "s0-cart-001",
    "s0-cart-002",
    "s0-cart-003",
    "s0-imgsl-001",
    "s0-imgsl-002",
    "s0-imgsl-003",
    "s0-imgsl-004",
    "s0-pcat-001",
    "s0-pcat-002",
    "s0-pcat-003",
    "s0-pcat-004",
    "s0-pcat-005",
    "s0-rcf-001",
    "s0-rcf-002",
    "s0-rcf-003",
    "s0-rcf-004",
    "s0-rcf-005",
]


def _unclean_vs_head(paths: list[Path]) -> list[str]:
    """Return the paths that are untracked or differ from HEAD (index or worktree)."""
    bad = []
    for p in paths:
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(p)], capture_output=True
        )
        clean = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", str(p)], capture_output=True
        )
        if tracked.returncode != 0 or clean.returncode != 0:
            bad.append(str(p))
    return bad


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify HELIOS telemetry captures (window hash + content seal).",
    )
    parser.add_argument(
        "--incident-id",
        default=None,
        help="Verify only this incident (default: all known incidents).",
    )
    parser.add_argument(
        "--captures-dir",
        default="data/captures",
        help="Root captures directory (default: data/captures).",
    )
    parser.add_argument(
        "--init-seals",
        action="store_true",
        help="Seal unsealed captures whose files are tracked and identical to HEAD.",
    )
    args = parser.parse_args(argv)

    key = load_key()
    captures_dir = Path(args.captures_dir)
    incident_ids = [args.incident_id] if args.incident_id else _ALL_INCIDENT_IDS
    reader = CaptureReader(captures_dir, seal_key=key)

    print(f"[verify] captures_dir : {captures_dir}")
    print(f"[verify] incidents     : {len(incident_ids)}")
    print()

    all_ok = True
    for iid in incident_ids:
        incident_dir = captures_dir / iid
        try:
            result = reader.read(iid)
        except FileNotFoundError as exc:
            print(f"[MISSING ] {iid}  — {exc}")
            all_ok = False
            continue
        except Exception as exc:
            print(f"[ERROR   ] {iid}  — {exc}")
            all_ok = False
            continue

        if args.init_seals and not (incident_dir / SEAL_FILENAME).exists():
            if not result.hash_matches:
                print(f"[REFUSED ] {iid}  — window_hash mismatch; not sealing")
                all_ok = False
                continue
            files = sorted(p for p in incident_dir.iterdir() if p.is_file())
            if bad := _unclean_vs_head(files):
                print(f"[REFUSED ] {iid}  — not identical to git HEAD: {bad}")
                all_ok = False
                continue
            write_seal(incident_dir, result.window, key)
            print(f"[SEALED  ] {iid}  — {len(files)} files identical to HEAD")
            result = reader.read(iid)

        rows = result.stream_row_counts
        if not result.hash_matches:
            status = "TAMPERED"
        elif not result.content_intact:
            status = (
                "UNSEALED"
                if "no " + SEAL_FILENAME in str(result.seal_error)
                else "ALTERED "
            )
        else:
            status = "OK      "
        print(
            f"[{status}] {iid:20s}"
            f"  p1={rows.get('p1_metrics', 0):5d}"
            f"  p2={rows.get('p2_traces', 0):5d}"
            f"  p3={rows.get('p3_logs', 0):5d}"
            f"  hash={result.stored_hash[:12]}..."
        )
        if not result.hash_matches:
            print(
                f"           stored  : {result.stored_hash[:32]}..."
                f"\n           computed: {result.computed_hash[:32]}..."
            )
        if result.seal_error:
            print(f"           seal    : {result.seal_error}")
        all_ok &= result.intact

    print()
    if all_ok:
        print("[verify] All captures verified OK (window hash + content seal)")
        return 0
    print("[verify] VERIFICATION FAILED — see rows above")
    return 1


if __name__ == "__main__":
    sys.exit(main())
