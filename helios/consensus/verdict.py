"""ConsensusVerdict schema and integrity gate.

schema-draft-v0.3 — not to be confused with PipelineVerdict schema-draft-v0.2.
CPR is a Stage 5 field; it is set to CPR_PENDING until cost data is available.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

HELIOS_ENABLE_CONSENSUS_VERDICT: bool = True

CPR_PENDING: float = float("0")

SCHEMA_VERSION: str = "schema-draft-v0.3"


class ConsensusVerdict(BaseModel, frozen=True):
    incident_id: str
    variant: str
    top_candidates: list[str] = Field(min_length=1)
    borda_scores: dict[str, float]
    # borda_scores are per-incident relative values (scored against the local
    # candidate union of size candidate_universe_size). They must not be compared
    # across incidents; downstream statistical analysis uses hr_at_3 (binary).
    # Store candidate_universe_size so future post-hoc normalization is possible
    # without reprocessing: normalised_score = borda_scores[c] / candidate_universe_size.
    candidate_universe_size: int = Field(ge=1)
    consensus_rank: int = Field(ge=1)
    fusion_algorithm: str
    fusion_algorithm_sha: str
    cpr: float = Field(default=CPR_PENDING)
    pipeline_row_count: int = Field(ge=1)
    run_id: str
    timestamp_utc: str

    @model_validator(mode="after")
    def _top_candidates_in_scores(self) -> ConsensusVerdict:
        missing = [c for c in self.top_candidates if c not in self.borda_scores]
        if missing:
            raise ValueError(f"top_candidates not in borda_scores: {missing}")
        return self


class ConsensusIntegrityGate:
    """Verifies that a ConsensusVerdict's fusion_algorithm_sha matches the expected value."""

    def __init__(self, *, expected_sha: str) -> None:
        self._expected_sha = expected_sha

    def check(self, cv: ConsensusVerdict) -> None:
        if cv.fusion_algorithm_sha != self._expected_sha:
            raise ValueError(
                f"fusion_algorithm_sha mismatch: stored={cv.fusion_algorithm_sha!r}, "
                f"expected={self._expected_sha!r}"
            )
