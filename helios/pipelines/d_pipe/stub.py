"""D-pipe null stub — statistical anomaly detection (Milestone 2 implementation pending).

Gated by VCLFlag.DPIPE. Returns a sentinel verdict dict. Signature matches g_pipe/l_pipe
so RunOrchestrator can dispatch uniformly across all three pipelines.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from helios.vcl.decorators import gated_by, get_current_manifest
from helios.vcl.registry import VCLFlag

__all__ = ["run_dpipe"]


@gated_by(VCLFlag.DPIPE)
def run_dpipe(incident_id: str, snapshot_hash: str) -> dict[str, Any]:
    """Return a stub verdict dict for d_pipe (Milestone 2 implementation pending)."""
    manifest = get_current_manifest()
    assert manifest is not None
    return {
        "pipeline": "dpipe",
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
