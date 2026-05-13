"""PipelineVerdict schema — L2/L3 per-pipeline result row (execution plan §3.6.3).

All fields required by the metric integrity gate and result store (schema.sql, §5.3).
VCLManifest provides variant_config_hash; compute_verdict_hash() yields row identity.
schema-draft-v0.1: stable until OSF Stage 5 freeze.
"""

import hashlib

from pydantic import BaseModel, ConfigDict, Field

from helios.schemas.telemetry import EvaluationPhase
from helios.vcl.utils import canonical_json


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
    pipeline: str  # dpipe | gpipe | lpipe
    evaluation_phase: EvaluationPhase
    ranked_candidates: list[str]  # ordered top-k service names (HR@3 source)
    hr_at_3: float = Field(ge=0, le=1)
    cpr: float = Field(ge=0, le=1)
    latency_ms: float = Field(ge=0)
    token_count: int = Field(ge=0)
    narrative: str  # Chain of Explanation (CoE) text
    schema_version: str = "schema-draft-v0.1"

    def compute_verdict_hash(self) -> str:
        """SHA-256 of canonical JSON — row identity for deduplication and auditing."""
        return hashlib.sha256(
            canonical_json(self.model_dump()).encode("utf-8")
        ).hexdigest()
