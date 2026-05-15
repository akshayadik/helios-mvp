#!/usr/bin/env python3
"""CLI entry point for snapshot verification of HELIOS telemetry captures.

Usage (from repo root):
    poetry run python bin/verify_captures.py
    poetry run python bin/verify_captures.py --incident-id s0-cart-001
    poetry run python bin/verify_captures.py --captures-dir data/captures

Exits 0 if all verified captures have matching hashes; exits 1 if any are
tampered, missing streams, or unreadable.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helios.telemetry.reader import CaptureReader
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify HELIOS telemetry capture snapshots (hash + schema check).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Verify all 5 known incidents:
    poetry run python bin/verify_captures.py

  Verify a single incident:
    poetry run python bin/verify_captures.py --incident-id s0-cart-001

  Use a non-default captures directory:
    poetry run python bin/verify_captures.py --captures-dir /mnt/archive/captures
        """,
    )
    parser.add_argument(
        "--incident-id",
        default=None,
        help="Verify only this incident (default: all 5 known incidents).",
    )
    parser.add_argument(
        "--captures-dir",
        default="data/captures",
        help="Root captures directory (default: data/captures).",
    )
    args = parser.parse_args()

    captures_dir = Path(args.captures_dir)
    incident_ids = [args.incident_id] if args.incident_id else _ALL_INCIDENT_IDS
    reader = CaptureReader(captures_dir)

    print(f"[verify] captures_dir : {captures_dir}")
    print(f"[verify] incidents     : {', '.join(incident_ids)}")
    print()

    all_ok = True
    for iid in incident_ids:
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

        rows = result.stream_row_counts
        status = "OK      " if result.hash_matches else "TAMPERED"
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
            all_ok = False

    print()
    if all_ok:
        print("[verify] All snapshots verified OK")
    else:
        print("[verify] VERIFICATION FAILED — see TAMPERED / MISSING rows above")
        sys.exit(1)


if __name__ == "__main__":
    main()
