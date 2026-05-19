"""PipelineVerdict — Pydantic model for per-pipeline evaluation result rows (§6.3)."""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict, Field

from helios.schemas.telemetry import (
    EvaluationPhase,  # noqa: TCH001 — Pydantic field type, needed at runtime
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.utils import canonical_json

__all__ = ["VERDICT_SCHEMA_VERSION", "PipelineVerdict"]

VERDICT_SCHEMA_VERSION: str = "schema-draft-v0.2"


class PipelineVerdict(BaseModel):
    """Single pipeline result row — all semantic fields required for metric integrity gate (§5.1).

    Stores pre-computed hr_at_3/cpr alongside raw ranked_candidates for downstream audit.
    pipeline must be one of: dpipe | gpipe | lpipe.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    incident_id: str
    variant_config_hash: str
    snapshot_hash: str
    pipeline: str
    evaluation_phase: EvaluationPhase
    ranked_candidates: list[str]
    hr_at_3: float = Field(default=0.00, ge=0, le=1)
    cpr: float = Field(default=0.00, ge=0, le=1)
    latency_ms: float = Field(ge=0)
    token_count: int = Field(ge=0)
    narrative: str
    ppr_scores: dict[str, float] = Field(default_factory=dict)
    prompt_version: str | None = None
    schema_version: str = VERDICT_SCHEMA_VERSION

    def compute_verdict_hash(self) -> str:
        """SHA-256 of canonical JSON — row identity for deduplication and auditing."""
        return hashlib.sha256(
            canonical_json(self.model_dump()).encode("utf-8")
        ).hexdigest()
