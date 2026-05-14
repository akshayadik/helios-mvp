"""UEG-C schema — L1/L2 graph snapshot (execution plan §3.6.4, §6.2).

NodeType + EdgeType define the 4-class edge taxonomy for the UEG-C graph.
UEGCSnapshot is the canonical container with SHA-256 content-addressable identity.
VCLManifest provides variant_config_hash; ueg_c_structural flag gates structural edges.
schema-draft-v0.1: stable until OSF Stage 5 freeze.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from helios.vcl.utils import canonical_json


class NodeType(StrEnum):
    """UEG-C vertex taxonomy (proposal §3.6.4)."""

    SERVICE = "service"
    OPERATION = "operation"
    POD = "pod"
    DATABASE = "database"
    EXTERNAL = "external"


class EdgeType(StrEnum):
    """UEG-C directed-edge taxonomy — 4 classes (proposal §3.6.4).

    STRUCTURAL edges are gated by VCLFlag.UEG_C_STRUCTURAL in the G-pipe builder.
    """

    STRUCTURAL = "structural"
    CALL = "call"
    METRIC = "metric"
    LOG = "log"


class EdgeClass(StrEnum):
    """Semantic 4-class edge taxonomy (proposal §3.6.4) — maps onto EdgeType sub-types.

    STRUCTURAL → STRUCTURAL   (topology / dependency edges)
    CALL       → BEHAVIOURAL  (runtime invocation behaviour)
    METRIC     → CAUSAL       (metric-signal causation)
    LOG        → ECONOMIC     (log-evidenced cost / impact)
    """

    STRUCTURAL = "structural"
    BEHAVIOURAL = "behavioural"
    CAUSAL = "causal"
    ECONOMIC = "economic"


_EDGE_TYPE_TO_CLASS: dict[EdgeType, EdgeClass] = {
    EdgeType.STRUCTURAL: EdgeClass.STRUCTURAL,
    EdgeType.CALL: EdgeClass.BEHAVIOURAL,
    EdgeType.METRIC: EdgeClass.CAUSAL,
    EdgeType.LOG: EdgeClass.ECONOMIC,
}


class UEGCNode(BaseModel):
    """Single vertex in the UEG-C graph."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    node_type: NodeType
    service_name: str
    metadata: dict[str, str] = Field(default_factory=dict)


class UEGCEdge(BaseModel):
    """Directed weighted edge in the UEG-C graph."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str
    target: str
    edge_type: EdgeType
    weight: float = Field(ge=0, le=1)

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

    Nodes and edges capture the full UEG-C state at incident capture time.
    variant_config_hash is injected from VCLManifest at construction.
    snapshot_hash is computed externally and stored in result rows, not here.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    incident_id: str
    variant_config_hash: str
    nodes: list[UEGCNode]
    edges: list[UEGCEdge]
    captured_at_iso: str  # ISO 8601 UTC
    schema_version: str = "schema-draft-v0.1"

    def compute_snapshot_hash(self) -> str:
        """SHA-256 of canonical JSON — graph identity for C1 inclusion check (§5.1, §6.2)."""
        return hashlib.sha256(
            canonical_json(self.model_dump()).encode("utf-8")
        ).hexdigest()
