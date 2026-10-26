"""PipelineVerdict — the typed verdict every reasoning pipeline emits (S1.8).

Chapter 3 (L2): each peer pipeline consumes the same content-hashed UEG-C
snapshot and emits ``(ranked_RCA_list, mu, sigma, cost, latency)``; MAHC
(Algorithm 3) weights each pipeline's vote down as its sigma grows.

schema-draft-v0.5 (S1.8):

- ``status`` says whether the pipeline produced a ranking; a skipped, failed
  or abstaining pipeline has an empty list (never a placeholder candidate).
- ``mu`` is the pipeline's confidence that its top-1 is the root cause, in
  [0, 1]; ``sigma`` is the standard deviation of that estimate. Either may be
  ``None`` while a pipeline has no estimator (D-pipe sigma is S2.1, L-pipe
  workers S2.3); consensus treats ``None`` as unknown, never as certain.
- ``cost`` is the resource usage of the call (tokens, CPU and GPU time); the
  price book turns it into money afterwards (S1.10), so a verdict never
  depends on prices.
- ``candidate_scores`` replaces ``ppr_scores`` (every pipeline's own score).
- Scores against ground truth (HR@k, MRR) are no longer verdict fields: a
  pipeline never sees ground truth, and scores are computed after dispatch
  (S1.9 scoring path).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping  # noqa: TCH003 — used at runtime by from_output
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from helios.schemas.telemetry import (
    EvaluationPhase,  # noqa: TCH001 — Pydantic field type, needed at runtime
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.utils import canonical_json

__all__ = [
    "MU_DIGITS",
    "VERDICT_SCHEMA_VERSION",
    "PipelineName",
    "PipelineVerdict",
    "VerdictCost",
    "VerdictStatus",
    "top1_share",
]

VERDICT_SCHEMA_VERSION: str = "schema-draft-v0.5"
MU_DIGITS = 6  # mu is rounded like canonical_json floats, so reruns are bitwise equal


class PipelineName(StrEnum):
    """The three peer reasoning pipelines."""

    DPIPE = "dpipe"
    GPIPE = "gpipe"
    LPIPE = "lpipe"


class VerdictStatus(StrEnum):
    """What the pipeline did for this incident."""

    RANKED = "ranked"  # produced a ranked list
    ABSTAINED = "abstained"  # ran, found nothing to rank
    SKIPPED = "skipped"  # gated off by its flag or not routed
    FAILED = "failed"  # ran and errored (e.g. the model endpoint was unreachable)


class VerdictCost(BaseModel):
    """Resource usage of one pipeline call; priced later by the price book (S1.10)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    cpu_ms: float = Field(default=0, ge=0)
    gpu_ms: float = Field(default=0, ge=0)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class PipelineVerdict(BaseModel):
    """One pipeline's verdict for one incident run (one result row)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    incident_id: str
    variant_config_hash: str
    snapshot_hash: str
    pipeline: PipelineName
    evaluation_phase: EvaluationPhase
    status: VerdictStatus
    ranked_candidates: list[str] = Field(default_factory=list)
    candidate_scores: dict[str, float] = Field(default_factory=dict)
    mu: float | None = Field(default=None, ge=0, le=1)
    sigma: float | None = Field(default=None, ge=0)
    cost: VerdictCost = Field(default_factory=VerdictCost)
    latency_ms: float = Field(ge=0)
    narrative: str = ""
    prompt_version: str | None = None
    schema_version: str = VERDICT_SCHEMA_VERSION

    @model_validator(mode="after")
    def _consistent(self) -> PipelineVerdict:
        if len(set(self.ranked_candidates)) != len(self.ranked_candidates):
            raise ValueError("ranked_candidates must not repeat a candidate")
        unranked = sorted(set(self.candidate_scores) - set(self.ranked_candidates))
        if unranked:
            raise ValueError(f"{len(unranked)} scored candidate(s) are not ranked")
        if self.status == VerdictStatus.RANKED:
            if not self.ranked_candidates:
                raise ValueError("a ranked verdict needs at least one candidate")
        elif self.ranked_candidates or self.mu is not None or self.sigma is not None:
            raise ValueError(
                f"a {self.status.value} verdict carries no candidates, mu or sigma"
            )
        return self

    @classmethod
    def from_output(
        cls,
        out: Mapping[str, Any],
        *,
        latency_ms: float | None = None,
        cpu_ms: float = 0,
    ) -> PipelineVerdict:
        """Build the verdict from a pipeline's output dict.

        The orchestrator passes the latency and CPU time it measured; without
        them the pipeline's own ``latency_ms`` is used. Keys outside the
        contract (e.g. the D-pipe calibration fields) are ignored.
        """
        return cls(
            run_id=str(out["run_id"]),
            incident_id=str(out["incident_id"]),
            variant_config_hash=str(out["variant_config_hash"]),
            snapshot_hash=str(out["snapshot_hash"]),
            pipeline=out["pipeline"],
            evaluation_phase=out["evaluation_phase"],
            status=out["status"],
            ranked_candidates=list(out.get("ranked_candidates", [])),
            candidate_scores=dict(out.get("candidate_scores", {})),
            mu=out.get("mu"),
            sigma=out.get("sigma"),
            cost=VerdictCost(
                prompt_tokens=int(out.get("prompt_tokens", 0)),
                completion_tokens=int(out.get("completion_tokens", 0)),
                cpu_ms=cpu_ms,
            ),
            latency_ms=(
                float(out.get("latency_ms", 0)) if latency_ms is None else latency_ms
            ),
            narrative=str(out.get("narrative") or ""),
            prompt_version=out.get("prompt_version"),
        )

    @property
    def top1(self) -> str | None:
        return self.ranked_candidates[0] if self.ranked_candidates else None

    def compute_verdict_hash(self) -> str:
        """SHA-256 of canonical JSON — row identity for deduplication and auditing."""
        return _sha256(self.model_dump(mode="json"))

    def compute_decision_hash(self) -> str:
        """SHA-256 of what the pipeline decided, without run_id and measured time.

        Two runs of the same pipeline on the same snapshot under the same
        variant must give the same decision hash (rerun equality, S2.1);
        latency and CPU/GPU time are measurements and vary between runs.
        """
        payload = self.model_dump(mode="json", exclude={"run_id", "latency_ms"})
        payload["cost"] = {
            k: v for k, v in payload["cost"].items() if k not in _MEASURED_COST
        }
        return _sha256(payload)


_MEASURED_COST = frozenset({"cpu_ms", "gpu_ms"})


def _sha256(payload: dict[str, object]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def top1_share(scores: dict[str, float]) -> float | None:
    """Label-free mu from non-negative candidate scores: the top-1 share of the total.

    ``None`` when there is nothing to share (no scores, a negative score or a
    zero total). Rounded to MU_DIGITS so reruns are bitwise equal.
    """
    if not scores or any(v < 0 for v in scores.values()):
        return None
    total = sum(scores.values())
    if total <= 0:
        return None
    return round(max(scores.values()) / total, MU_DIGITS)
