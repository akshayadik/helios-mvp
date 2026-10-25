"""UEG-C schema — L1/L2 graph snapshot (execution plan §3.6.4, §6.2; C2).

Four edge classes (structural, behavioural, causal, economic); each edge's
class is derived from its relation (`edge_type`) and is never stored apart
from it. Agent-Reasoning-Step and Transaction/KPI nodes; `tenant` separates
production telemetry from HELIOS's own (C5, tenant=self).
UEGCSnapshot is the canonical container with SHA-256 content-addressable identity.
VCLManifest provides variant_config_hash; ueg_structural flag gates structural edges.

schema-draft-v0.2 (S1.5, 2026-10-25): design in
docs/sprints/s1-data-graph/s1_5_ueg_c_design.md.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from helios.vcl.utils import canonical_json

UEG_C_SCHEMA_VERSION = "schema-draft-v0.2"

TENANT_PROD = "prod"
TENANT_SELF = "self"


class NodeType(StrEnum):
    """UEG-C vertex taxonomy (proposal §3.6.4)."""

    SERVICE = "service"
    OPERATION = "operation"
    POD = "pod"
    DATABASE = "database"
    EXTERNAL = "external"
    TRANSACTION_KPI = "transaction_kpi"
    AGENT_REASONING_STEP = "agent_reasoning_step"


class EdgeClass(StrEnum):
    """The four typed edge classes of Chapter 3 (C2), in composition order."""

    STRUCTURAL = "structural"
    BEHAVIOURAL = "behavioural"
    CAUSAL = "causal"
    ECONOMIC = "economic"


class EdgeType(StrEnum):
    """Edge relation; its class follows from _EDGE_TYPE_TO_CLASS.

    STRUCTURAL edges are gated by VCLFlag.UEG_STRUCTURAL in the builder.
    """

    STRUCTURAL = "structural"  # parent -> child span, different services
    PRECEDES = "precedes"  # reasoning step -> next step
    CALL = "call"  # observed call traffic
    INVOKES = "invokes"  # reasoning step -> service it acted on
    ANOMALY_LEADS = "anomaly_leads"  # anomaly intensity of source leads target
    ANOMALY_CO_MOVES = "anomaly_co_moves"  # same, without a lead
    SERVES_KPI = "serves_kpi"  # service -> transaction/KPI node


_EDGE_TYPE_TO_CLASS: dict[EdgeType, EdgeClass] = {
    EdgeType.STRUCTURAL: EdgeClass.STRUCTURAL,
    EdgeType.PRECEDES: EdgeClass.STRUCTURAL,
    EdgeType.CALL: EdgeClass.BEHAVIOURAL,
    EdgeType.INVOKES: EdgeClass.BEHAVIOURAL,
    EdgeType.ANOMALY_LEADS: EdgeClass.CAUSAL,
    EdgeType.ANOMALY_CO_MOVES: EdgeClass.CAUSAL,
    EdgeType.SERVES_KPI: EdgeClass.ECONOMIC,
}


class UEGCNode(BaseModel):
    """Single vertex in the UEG-C graph."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    node_type: NodeType
    service_name: str
    tenant: str = TENANT_PROD
    metadata: dict[str, str] = Field(default_factory=dict)


class UEGCEdge(BaseModel):
    """Directed weighted edge in the UEG-C graph.

    correlation (Pearson r) and lag_seconds are evidence for behavioural and
    causal edges; None where they do not apply.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str
    target: str
    edge_type: EdgeType
    weight: float = Field(ge=0, le=1)
    correlation: float | None = Field(default=None, ge=-1, le=1)
    lag_seconds: int | None = Field(default=None, ge=0)

    @model_validator(mode="before")
    @classmethod
    def _strip_computed_fields(cls, data: object) -> object:
        """Remove edge_class from incoming data — it is a derived computed_field.

        Allows round-trip deserialization of model_dump() output without extra="ignore".
        Genuine unknown fields are still rejected by extra="forbid" after stripping.
        """
        if isinstance(data, dict):
            data = {k: v for k, v in data.items() if k != "edge_class"}
        return data

    @computed_field  # type: ignore[prop-decorator]
    @property
    def edge_class(self) -> EdgeClass:
        """Semantic class auto-derived from edge_type — always consistent, never stale."""
        return _EDGE_TYPE_TO_CLASS[self.edge_type]


class UEGCSnapshot(BaseModel):
    """Canonical L1/L2 graph snapshot — content-addressable via SHA-256 (§6.2).

    Nodes and edges capture the full UEG-C state for one incident window.
    variant_config_hash is injected from VCLManifest at construction.
    captured_at_iso is the window end (not the build time), so the same
    window always gives the same hash.
    snapshot_hash is computed externally and stored in result rows, not here.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    incident_id: str
    variant_config_hash: str
    nodes: list[UEGCNode]
    edges: list[UEGCEdge]
    captured_at_iso: str  # ISO 8601 UTC
    schema_version: str = UEG_C_SCHEMA_VERSION

    def compute_snapshot_hash(self) -> str:
        """SHA-256 of canonical JSON — graph identity for C1 inclusion check (§5.1, §6.2)."""
        return hashlib.sha256(
            canonical_json(self.model_dump()).encode("utf-8")
        ).hexdigest()

    def candidate_ids(self) -> list[str]:
        """Root-cause candidates: production service nodes, sorted."""
        return sorted(
            n.node_id
            for n in self.nodes
            if n.node_type == NodeType.SERVICE and n.tenant == TENANT_PROD
        )
