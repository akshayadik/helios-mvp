"""Request and response models of API v1 (S4.1 A-b2, A-g).

The OpenAPI spec is generated from these models and committed as
``docs/api/openapi.json``; a test fails when the two differ. No model has a
field for ground truth, a case name, an injection time or a scored metric.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

__all__ = [
    "Claim",
    "CoEOut",
    "DecisionIn",
    "DecisionOut",
    "DecisionsOut",
    "Health",
    "IncidentDetail",
    "IncidentPage",
    "IncidentSummary",
    "Narrative",
    "Problem",
    "QueueItem",
    "QueueOut",
    "RankedService",
    "RunSummary",
    "TriggerOut",
    "Verdict",
    "ViewOut",
]


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Problem(_Out):
    """RFC 9457 problem details (``application/problem+json``)."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None


class Health(_Out):
    status: Literal["ok", "degraded"]
    api_version: str
    schema_tags: list[str]
    build_frozen: bool
    incidents: int
    keys_configured: int
    decisions_ledger: str
    coe_ledgers: dict[str, str]


class IncidentSummary(_Out):
    incident_id: str
    runs: int
    confirmed: int
    needs_review: int


class IncidentPage(_Out):
    items: list[IncidentSummary]
    total: int
    limit: int
    offset: int


class RunSummary(_Out):
    run_id: str
    variant: str | None
    state: str
    needs_review: bool
    confidence: float | None
    top3: list[str]


class IncidentDetail(_Out):
    incident_id: str
    runs: list[RunSummary]


class RankedService(_Out):
    rank: int
    service: str
    score: float | None


class Claim(_Out):
    slot: str
    kind: str
    sentence: str
    cites: list[str]


class Narrative(_Out):
    narrator: str
    rendered: str
    claims: list[Claim]
    template_fallbacks: int


class TriggerOut(_Out):
    time_s: float
    suspects: list[str]
    source: str


class Verdict(_Out):
    run_id: str
    incident_id: str
    variant: str | None = Field(description="Null for a blind (participant) key.")
    state: str
    needs_review: bool
    non_converged: bool
    confidence: float | None
    ranked: list[RankedService]
    first_ranked: list[str]
    first_published_ms: float | None
    terminal_published_ms: float | None
    escalated: bool | None
    trigger: TriggerOut | None
    narrative: Narrative | None = Field(
        description="Null when the run's variant has no narrative (HELIOS-noExpl)."
    )


class CoEOut(_Out):
    run_id: str
    ledger: str
    verified: bool
    verification: str
    entry: dict[str, Any]


class ViewOut(_Out):
    run_id: str
    view_token: str
    issued_at: float
    expires_at: float


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["accept", "escalate", "reject"]
    view_token: str = Field(min_length=16, max_length=1024)
    note: str | None = Field(default=None, max_length=2000)
    client_ms: float | None = Field(
        default=None,
        ge=0,
        description="The client's own timing, kept beside the server's.",
    )
    client_hidden_ms: float | None = Field(
        default=None,
        ge=0,
        description="How long the page was hidden while the case was shown (K-d).",
    )
    chosen_service: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "On reject: the service the reviewer believes is the root cause, "
            "from the ranked list, or 'none'. Set by the server on accept."
        ),
    )


class DecisionOut(_Out):
    run_id: str
    incident_id: str
    key_id: str
    decision: str
    note: str | None
    shown_at: float
    decided_at: float
    decision_ms: float
    client_ms: float | None
    client_hidden_ms: float | None
    chosen_service: str | None
    simulated: bool
    signature: str


class DecisionsOut(_Out):
    run_id: str
    decisions: list[DecisionOut]
    latest: str | None


class QueueItem(_Out):
    position: int
    run_id: str
    decided: bool


class QueueOut(_Out):
    """The cases assigned to the calling key, in order (S4.2 K-e)."""

    key_id: str
    items: list[QueueItem]
    next_position: int | None = Field(description="First undecided case, if any.")
