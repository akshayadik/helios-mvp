"""G-pipe null stub — gated by VCLFlag.L2B_GRAPH (§3.6.7).

Returns a minimal verdict dict when active. Full graph-based causal inference
follows at Stage 4. VCLManifest provides variant_config_hash via context.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from helios.vcl.decorators import gated_by, get_current_manifest
from helios.vcl.registry import VCLFlag

__all__ = ["run_gpipe"]


@gated_by(VCLFlag.L2B_GRAPH)
def run_gpipe(incident_id: str, snapshot_hash: str) -> dict[str, Any]:
    """Return a stub PipelineVerdict dict for g_pipe (Stage 4 implementation pending)."""
    manifest = get_current_manifest()
    assert manifest is not None
    return {
        "pipeline": "gpipe",
        "incident_id": incident_id,
        "variant_config_hash": manifest.compute_variant_config_hash(),
        "snapshot_hash": snapshot_hash,
        "ranked_candidates": [],
        "hr_at_3": 0,
        "cpr": 0,
        "latency_ms": 0,
        "token_count": 0,
        "narrative": "stub",
        "evaluation_phase": "exploratory",
        "created_at": dt.datetime.now(dt.UTC).isoformat(),
    }
