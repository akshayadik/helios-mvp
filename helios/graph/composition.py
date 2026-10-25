"""Composition rules for typed UEG-C paths (C2, S1.5).

Edge classes are ordered structural < behavioural < causal < economic.
Composing two adjacent edges gives the larger class, except that nothing may
follow an economic edge (Transaction/KPI nodes are sinks):

    compose(a, b) = None        if a is economic or either side is None
                  = max(a, b)   otherwise

Untyped edges (ueg_structural OFF) compose only with each other: there are
no typed rules to apply. The rule is associative, so a path's class does not
depend on grouping. A
path's weight is the product of its edge weights. Design:
docs/sprints/s1-data-graph/s1_5_ueg_c_design.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from helios.schemas.ueg_c import EdgeClass, UEGCEdge
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Iterable

    from helios.schemas.ueg_c import UEGCSnapshot

__all__ = ["CLASS_ORDER", "TypedPath", "compose", "path_class", "typed_paths"]

CLASS_ORDER: tuple[EdgeClass, ...] = (
    EdgeClass.STRUCTURAL,
    EdgeClass.BEHAVIOURAL,
    EdgeClass.CAUSAL,
    EdgeClass.ECONOMIC,
)
_RANK = {c: i for i, c in enumerate(CLASS_ORDER)}


def compose(a: EdgeClass | None, b: EdgeClass | None) -> EdgeClass | None:
    """Class of a path made of a path of class ``a`` followed by one of ``b``."""
    if a is None or b is None or a == EdgeClass.ECONOMIC:
        return None
    if EdgeClass.UNTYPED in (a, b):
        return a if a == b else None
    return a if _RANK[a] >= _RANK[b] else b


def path_class(classes: Iterable[EdgeClass]) -> EdgeClass | None:
    """Composed class of a sequence of edge classes; None if empty or invalid."""
    result: EdgeClass | None = None
    for i, c in enumerate(classes):
        result = c if i == 0 else compose(result, c)
        if result is None:
            return None
    return result


@dataclass(frozen=True)
class TypedPath:
    """A simple path through the graph with its composed class and weight."""

    nodes: tuple[str, ...]
    edges: tuple[UEGCEdge, ...]
    edge_class: EdgeClass
    weight: float


def typed_paths(
    snapshot: UEGCSnapshot,
    source: str,
    target: str,
    max_hops: int,
    classes: frozenset[EdgeClass] | None = None,
) -> list[TypedPath]:
    """Every valid simple path from source to target with at most max_hops edges.

    ``classes`` restricts the edge classes that may be used. Paths whose
    composition is undefined (an edge after an economic edge) are skipped.
    Sorted by weight (descending), then by node sequence.
    """
    if max_hops < 1:
        raise ValueError("max_hops must be at least 1")
    out_edges: dict[str, list[UEGCEdge]] = {}
    for edge in snapshot.edges:
        if classes is None or edge.edge_class in classes:
            out_edges.setdefault(edge.source, []).append(edge)
    found: list[TypedPath] = []

    def walk(node: str, nodes: list[str], edges: list[UEGCEdge]) -> None:
        for edge in out_edges.get(node, []):
            if edge.target in nodes:
                continue
            step = [*edges, edge]
            cls = path_class(e.edge_class for e in step)
            if cls is None:
                continue
            if edge.target == target:
                weight = 1.00
                for e in step:
                    weight *= e.weight
                found.append(TypedPath((*nodes, edge.target), tuple(step), cls, weight))
            elif len(step) < max_hops:
                walk(edge.target, [*nodes, edge.target], step)

    walk(source, [source], [])
    return sorted(found, key=lambda p: (-p.weight, p.nodes))
