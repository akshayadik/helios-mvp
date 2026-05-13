"""UEG-C schema — L1/L2 graph snapshot (execution plan §3.6.4, §6.2).

NodeType + EdgeType define the 4-class edge taxonomy for the UEG-C graph.
UEGCSnapshot is the canonical container with SHA-256 content-addressable identity.
VCLManifest provides variant_config_hash; ueg_c_structural flag gates structural edges.
schema-draft-v0.1: stable until OSF Stage 5 freeze.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

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
