"""L-pipe null stub — gated by VCLFlag.L2C_LLM (§3.6.7).

Returns a minimal verdict dict when active. Full LLM explanation pipeline
follows at Stage 5. VCLManifest provides variant_config_hash via context.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from helios.vcl.decorators import gated_by, get_current_manifest
from helios.vcl.registry import VCLFlag

__all__ = ["run_lpipe"]


@gated_by(VCLFlag.L2C_LLM)
def run_lpipe(incident_id: str, snapshot_hash: str) -> dict[str, Any]:
    """Return a stub PipelineVerdict dict for l_pipe (Stage 5 implementation pending)."""
    manifest = get_current_manifest()
    assert manifest is not None
    return {
        "pipeline": "lpipe",
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
