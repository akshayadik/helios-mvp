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
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Ensure helios/ is importable when run as a script from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helios.graph.ueg_c_builder import build_ueg_c
from helios.telemetry.otel_demo_capture import build_default_capture
from helios.vcl import set_current_manifest
from helios.vcl.config import VCLManifest
from helios.vcl.decorators import GatedComponentInactiveError
from helios.vcl.variants import CONFIRMATORY_VARIANTS

MANIFEST_SCHEMA_VERSION = "schema-draft-v0.2"


def _write_snapshot_hash(window: Any, manifest_path: Path) -> None:
    """Compute UEGCSnapshot hash and patch manifest with snapshot_hash + schema_version.

    build_ueg_c() may return None when l2b_graph flag is off — snapshot_hash is
    omitted in that case. Requires set_current_manifest() to have been called.
    """
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    try:
        snapshot = build_ueg_c(window, manifest_data["variant_config_hash"])
    except GatedComponentInactiveError:
        snapshot = None
    if snapshot is not None:
        manifest_data["snapshot_hash"] = snapshot.compute_snapshot_hash()
    manifest_data["schema_version"] = MANIFEST_SCHEMA_VERSION
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")


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

    set_current_manifest(manifest)
    if window.p1_metrics_path is None:
        print("[capture] WARNING: p1_metrics_path is None, skipping snapshot_hash")
        incident_dir = None
    else:
        incident_dir = Path(window.p1_metrics_path).parent
        _write_snapshot_hash(window, incident_dir / "manifest.json")

    print("[capture] DONE")
    print(f"[capture] window_hash   : {window.compute_window_hash()[:16]}...")
    print(f"[capture] p1_metrics    : {window.p1_metrics_path}")
    print(f"[capture] p2_traces     : {window.p2_traces_path}")
    print(f"[capture] p3_logs       : {window.p3_logs_path}")
    if incident_dir is not None:
        print(f"[capture] manifest.json : {incident_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()
