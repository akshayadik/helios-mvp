#!/usr/bin/env python3
"""CLI entry point for a single HELIOS telemetry capture session.

Usage (from repo root, after enabling a fault flag):
    set -a; source .env; set +a
    poetry run python bin/run_capture.py --incident-id s0-cart-001

The script computes window_end=now, window_start=now-5min, queries all three
telemetry backends, writes data/captures/{incident_id}/ Parquet files, and
prints the window hash for C1 snapshot verification.
"""

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Ensure helios/ is importable when run as a script from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helios.telemetry.otel_demo_capture import build_default_capture
from helios.vcl.config import VCLManifest
from helios.vcl.variants import CONFIRMATORY_VARIANTS


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a HELIOS 5-minute multi-modal telemetry capture.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Incident IDs (see docs/fault_catalogue_v0.md §3):
  s0-adhc-001   adHighCpu       [Resource]
  s0-cart-001   cartFailure     [Dependency]
  s0-imgsl-001  imageSlowLoad   [Network]
  s0-pcat-001   productCatalogFailure [Code]
  s0-rcf-001    recommendationCacheFailure [Dependency]
        """,
    )
    parser.add_argument(
        "--incident-id",
        required=True,
        help="Incident identifier from fault_catalogue_v0.md §3 (e.g. s0-cart-001).",
    )
    parser.add_argument(
        "--variant",
        default="HELIOS-Full",
        choices=list(CONFIRMATORY_VARIANTS.keys()),
        help="VCL variant to record against (default: HELIOS-Full).",
    )
    args = parser.parse_args()

    manifest = CONFIRMATORY_VARIANTS[args.variant]
    assert isinstance(manifest, VCLManifest), f"Unexpected type: {type(manifest)}"
    capture = build_default_capture(args.incident_id, manifest)

    end = datetime.now(UTC)
    start = end - timedelta(minutes=5)

    print(f"[capture] incident_id   : {args.incident_id}")
    print(f"[capture] variant       : {args.variant}")
    print(f"[capture] window_start  : {start.isoformat()}")
    print(f"[capture] window_end    : {end.isoformat()}")
    print(f"[capture] variant_hash  : {manifest.compute_variant_config_hash()[:16]}...")
    print("[capture] querying backends ...")

    window = capture.run(start, end)

    print("[capture] DONE")
    print(f"[capture] window_hash   : {window.compute_window_hash()[:16]}...")
    print(f"[capture] p1_metrics    : {window.p1_metrics_path}")
    print(f"[capture] p2_traces     : {window.p2_traces_path}")
    print(f"[capture] p3_logs       : {window.p3_logs_path}")
    incident_dir = Path(str(window.p1_metrics_path)).parent
    print(f"[capture] manifest.json : {incident_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()
