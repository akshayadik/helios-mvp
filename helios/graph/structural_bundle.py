"""Structural bundle — what `ueg_structural` switches (S1.6, Chapter 3 p. 51).

ON (HELIOS-Full): the four typed edge classes with their composition rules,
subgraph-aware training (pipelines are trained on the same pruned subgraph
they see at inference), and structured Agent-Reasoning-Step nodes.

OFF (HELIOS-noStructural), all three together as one bundle (A-H8):
- every edge loses its relation and class: parallel edges between the same
  two nodes become one `untyped` edge with the largest weight;
- training scope is the full graph rather than the pruned subgraph;
- reasoning steps are removed from the graph and handed to the L-pipe as flat
  text lines instead.

`typed_view` is the gated component; `apply_structural_bundle` is the only
place the OFF behaviour lives.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from helios.schemas.ueg_c import (
    EdgeType,
    NodeType,
    UEGCEdge,
    UEGCSnapshot,
)
from helios.vcl import GatedComponentInactiveError, VCLFlag, gated_by

__all__ = [
    "StructuralView",
    "TrainingScope",
    "apply_structural_bundle",
    "flatten",
    "typed_view",
]


class TrainingScope(StrEnum):
    """Graph a pipeline is trained or calibrated on (subgraph-aware training)."""

    PRUNED_SUBGRAPH = "pruned_subgraph"
    FULL_GRAPH = "full_graph"


@dataclass(frozen=True)
class StructuralView:
    """The graph the pipelines consume, plus what the bundle decides with it."""

    snapshot: UEGCSnapshot
    training_scope: TrainingScope
    reasoning_text: tuple[str, ...]  # empty when reasoning steps are graph nodes
    typed: bool


@gated_by(VCLFlag.UEG_STRUCTURAL)
def typed_view(snapshot: UEGCSnapshot) -> StructuralView:
    """ON: typed edges, structured reasoning-step nodes, subgraph-aware training."""
    return StructuralView(
        snapshot=snapshot,
        training_scope=TrainingScope.PRUNED_SUBGRAPH,
        reasoning_text=(),
        typed=True,
    )


def _step_line(order: str, agent: str, text: str, target: str | None) -> str:
    on = f" -> {target}" if target else ""
    return f"step {order} ({agent}){on}: {text}"


def flatten(snapshot: UEGCSnapshot) -> StructuralView:
    """OFF: one untyped edge kind, full-graph training, reasoning steps as text."""
    steps = {
        n.node_id: n
        for n in snapshot.nodes
        if n.node_type == NodeType.AGENT_REASONING_STEP
    }
    targets = {
        e.source: e.target
        for e in snapshot.edges
        if e.edge_type == EdgeType.INVOKES and e.source in steps
    }
    ordered = sorted(steps.values(), key=lambda n: int(n.metadata.get("order", "0")))
    text = tuple(
        _step_line(
            n.metadata.get("order", "0"),
            n.service_name,
            n.metadata.get("text", ""),
            targets.get(n.node_id),
        )
        for n in ordered
    )
    merged: dict[tuple[str, str], float] = {}
    for e in snapshot.edges:
        if e.source in steps or e.target in steps:
            continue
        key = (e.source, e.target)
        merged[key] = max(merged.get(key, 0), e.weight)
    flat = snapshot.model_copy(
        update={
            "nodes": [n for n in snapshot.nodes if n.node_id not in steps],
            "edges": [
                UEGCEdge(source=a, target=b, edge_type=EdgeType.UNTYPED, weight=w)
                for (a, b), w in sorted(merged.items())
            ],
        }
    )
    return StructuralView(
        snapshot=flat,
        training_scope=TrainingScope.FULL_GRAPH,
        reasoning_text=text,
        typed=False,
    )


def apply_structural_bundle(snapshot: UEGCSnapshot) -> StructuralView:
    """The view of ``snapshot`` for the current manifest's ``ueg_structural``."""
    try:
        return typed_view(snapshot)
    except GatedComponentInactiveError:
        return flatten(snapshot)
