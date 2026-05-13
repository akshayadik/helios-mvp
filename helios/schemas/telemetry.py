"""TelemetryWindow schema — L0 5-minute observability window (execution plan §3.6.6).

Captures P1-P5 multi-modal streams and evaluation phase for C1 run-level inclusion (§5.1).
VCLManifest provides variant_config_hash; compute_window_hash() yields snapshot identity.
schema-draft-v0.1: stable until OSF Stage 5 freeze.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from helios.vcl.utils import canonical_json


class EvaluationPhase(StrEnum):
    """Evaluation context — separates exploratory calibration from confirmatory inference (§1.4)."""

    EXPLORATORY = "exploratory"
    CONFIRMATORY = "confirmatory"


class TelemetryWindow(BaseModel):
    """L0 5-minute multi-modal observability window (execution plan §3.6.6).

    P1-P5: Prometheus metrics, OTEL traces, structured logs, K8s events, profiling data.
    Parquet paths are optional — not every stream is available in all environments.
    evaluation_phase gates the two-environment firewall (§1.4).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    incident_id: str
    variant_config_hash: str
    window_start_iso: str  # ISO 8601 UTC
    window_end_iso: str  # ISO 8601 UTC
    evaluation_phase: EvaluationPhase

    # P1-P5 observability stream paths (Parquet; None if stream not captured)
    p1_metrics_path: str | None = None
    p2_traces_path: str | None = None
    p3_logs_path: str | None = None
    p4_events_path: str | None = None
    p5_profiles_path: str | None = None

    schema_version: str = "schema-draft-v0.1"

    def compute_window_hash(self) -> str:
        """SHA-256 of canonical JSON — snapshot identity for C1 inclusion check (§5.1)."""
        return hashlib.sha256(
            canonical_json(self.model_dump()).encode("utf-8")
        ).hexdigest()
