"""K-hop pruner — Algorithm 5 of Chapter 3 (p. 48; S1.7).

Given the UEG-C, seed nodes, a hop limit K, a Pearson threshold (r = 0.7,
pre-registered) and an edge budget of 10,000, the pruner

1. expands the seeds by K-hop traversal over structural and behavioural edges
   (untyped edges when ueg_structural is OFF) and, beyond Chapter 3, over
   causal edges with |r| >= the threshold, so services without traces (no
   call edges) are still reachable through anomaly propagation;
2. keeps the top-n services by personalized PageRank from the seeds — seeds
   first, then the K-hop neighbourhood, filled up to the floor of Chapter 3's
   50-200-node range from the rest of the graph when it is smaller, never more
   than top-n;
3. drops causal and behavioural edges whose |r| is below the threshold
   (edges without a correlation, such as agent-step edges, stay);
4. keeps at most the edge budget, strongest edges first;
5. returns the pruned snapshot and its content hash.

Seeds are label-free: the services with the highest peak anomaly intensity
(builder metadata), else the call-graph entry points, else every service.
The D-pipe anomaly trigger (S2.1) may pass its own seeds instead.
Design and calibration: docs/sprints/s1-data-graph/s1_7_khop_pruner.md.
The pruner serves every variant; ablation of the typed graph is
VCLFlag.UEG_STRUCTURAL (applied before pruning, structural_bundle).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

import networkx as nx

from helios.graph.ueg_c_builder import ANOMALY_PEAK_KEY
from helios.schemas.ueg_c import (
    TENANT_PROD,
    EdgeClass,
    EdgeType,
    NodeType,
    UEGCEdge,
    UEGCSnapshot,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "EDGE_BUDGET",
    "K_HOPS",
    "MIN_NODES",
    "PEARSON_MIN_R",
    "PPR_ALPHA",
    "SEED_COUNT",
    "TOP_N",
    "KHopResult",
    "SeedSource",
    "khop_prune",
    "seed_nodes",
]

# Chapter 3 values (Algorithm 5, p. 48 and p. 39: "a subgraph of 50 to 200 nodes").
PEARSON_MIN_R = 0.7
EDGE_BUDGET = 10_000
MIN_NODES = 50
# Calibrated on build data (S1.7 deviation entry; design note § Calibration).
K_HOPS = 3
TOP_N = 50
# A priori: three seeds (the HR@3 horizon); restart probability 0.15.
SEED_COUNT = 3
PPR_ALPHA = 0.85

_TOPOLOGY = frozenset({EdgeClass.STRUCTURAL, EdgeClass.BEHAVIOURAL, EdgeClass.UNTYPED})
_CORRELATED = frozenset({EdgeClass.BEHAVIOURAL, EdgeClass.CAUSAL})
_SCORE_DIGITS = 12  # PageRank scores are rounded before ranking (stable ties)


class SeedSource(StrEnum):
    """Where the seeds came from."""

    GIVEN = "given"
    ANOMALY = "anomaly"
    ENTRY_POINTS = "entry_points"
    ALL = "all"


@dataclass(frozen=True)
class KHopResult:
    """What the pruner did to one snapshot (counts only, no labels)."""

    seeds: tuple[str, ...]
    seed_source: SeedSource
    k: int
    top_n: int
    services_before: int
    services_in_reach: int
    services_after: int
    nodes_before: int
    nodes_after: int
    edges_before: int
    edges_after: int
    edges_below_r: int
    edges_over_budget: int
    snapshot_hash: str


def _services(snapshot: UEGCSnapshot) -> list[str]:
    return snapshot.candidate_ids()


def _peak(snapshot: UEGCSnapshot) -> dict[str, float]:
    return {
        n.node_id: float(n.metadata[ANOMALY_PEAK_KEY])
        for n in snapshot.nodes
        if n.node_type == NodeType.SERVICE
        and n.tenant == TENANT_PROD
        and ANOMALY_PEAK_KEY in n.metadata
    }


def seed_nodes(
    snapshot: UEGCSnapshot, count: int = SEED_COUNT
) -> tuple[tuple[str, ...], SeedSource]:
    """Label-free seeds: top peak anomaly intensity, else entry points, else all."""
    services = set(_services(snapshot))
    peak = _peak(snapshot)
    if any(v > 0 for v in peak.values()):
        ranked = sorted(peak, key=lambda s: (-peak[s], s))
        return tuple(sorted(ranked[:count])), SeedSource.ANOMALY
    structural_in = {
        e.target for e in snapshot.edges if e.edge_type == EdgeType.STRUCTURAL
    }
    calling = {
        e.source
        for e in snapshot.edges
        if e.edge_class in _TOPOLOGY and e.source in services and e.target in services
    }
    entry = sorted(s for s in calling if s not in structural_in)
    if entry:
        return tuple(entry), SeedSource.ENTRY_POINTS
    return tuple(sorted(services)), SeedSource.ALL


def _strong(edge: UEGCEdge, min_r: float) -> bool:
    return edge.correlation is not None and abs(edge.correlation) >= min_r


def _expansion_graph(
    snapshot: UEGCSnapshot, services: list[str], min_r: float
) -> nx.Graph:
    """Undirected service graph: topology edges plus strong causal edges."""
    graph = nx.Graph()
    graph.add_nodes_from(services)
    for e in snapshot.edges:
        if e.source == e.target or e.source not in graph or e.target not in graph:
            continue
        if e.edge_class in _TOPOLOGY or (
            e.edge_class == EdgeClass.CAUSAL and _strong(e, min_r)
        ):
            old = (
                graph.edges[e.source, e.target]["weight"]
                if graph.has_edge(e.source, e.target)
                else 0
            )
            graph.add_edge(e.source, e.target, weight=max(old, e.weight))
    return graph


def _reach(graph: nx.Graph, seeds: Sequence[str], k: int) -> set[str]:
    seen = set(seeds)
    frontier: deque[tuple[str, int]] = deque((s, 0) for s in sorted(seeds))
    while frontier:
        node, hops = frontier.popleft()
        if hops == k:
            continue
        for nxt in sorted(graph.neighbors(node)):
            if nxt not in seen:
                seen.add(nxt)
                frontier.append((nxt, hops + 1))
    return seen


def _ppr(graph: nx.Graph, seeds: Sequence[str]) -> dict[str, float]:
    personalization = {n: (1 if n in seeds else 0) for n in graph.nodes}
    scores: dict[str, float] = nx.pagerank(
        graph, alpha=PPR_ALPHA, personalization=personalization, weight="weight"
    )
    return {n: round(v, _SCORE_DIGITS) for n, v in scores.items()}


def _budget(edges: list[UEGCEdge], budget: int) -> list[UEGCEdge]:
    if len(edges) <= budget:
        return edges
    strongest = sorted(
        edges, key=lambda e: (-e.weight, e.edge_type.value, e.source, e.target)
    )[:budget]
    return sorted(strongest, key=lambda e: (e.edge_type.value, e.source, e.target))


def khop_prune(
    snapshot: UEGCSnapshot,
    *,
    seeds: Sequence[str] | None = None,
    k: int = K_HOPS,
    top_n: int = TOP_N,
    min_nodes: int = MIN_NODES,
    min_r: float = PEARSON_MIN_R,
    edge_budget: int = EDGE_BUDGET,
) -> tuple[UEGCSnapshot, KHopResult]:
    """Algorithm 5: the incident-local subgraph of ``snapshot`` and what was cut."""
    if k < 0 or top_n < 1 or min_nodes < 0 or edge_budget < 0:
        raise ValueError("k, min_nodes and edge_budget must be >= 0; top_n >= 1")
    services = _services(snapshot)
    if seeds is None:
        chosen, source = seed_nodes(snapshot)
    else:
        unknown = sorted(set(seeds) - set(services))
        if unknown:
            raise ValueError(f"{len(unknown)} seed(s) are not production services")
        chosen, source = tuple(sorted(set(seeds))), SeedSource.GIVEN

    graph = _expansion_graph(snapshot, services, min_r)
    reach = _reach(graph, chosen, k) if chosen else set(services)
    ppr = _ppr(graph, chosen) if chosen else dict.fromkeys(services, 0)
    peak = _peak(snapshot)
    order = sorted(
        services,
        key=lambda s: (
            s not in chosen,
            s not in reach,
            -ppr.get(s, 0),
            -peak.get(s, 0),
            s,
        ),
    )
    size = min(max(len(reach), min_nodes), top_n, len(services))
    kept_services = set(order[:size]) | set(chosen)

    kept = {
        n.node_id
        for n in snapshot.nodes
        if n.node_id in kept_services
        or n.tenant != TENANT_PROD
        or (n.node_type == NodeType.TRANSACTION_KPI and n.service_name in kept_services)
    }
    inside = [e for e in snapshot.edges if e.source in kept and e.target in kept]
    weak = [
        e
        for e in inside
        if e.edge_class in _CORRELATED
        and e.correlation is not None
        and not _strong(e, min_r)
    ]
    weak_ids = {id(e) for e in weak}
    edges = _budget([e for e in inside if id(e) not in weak_ids], edge_budget)

    pruned = snapshot.model_copy(
        update={
            "nodes": [n for n in snapshot.nodes if n.node_id in kept],
            "edges": edges,
        }
    )
    return pruned, KHopResult(
        seeds=chosen,
        seed_source=source,
        k=k,
        top_n=top_n,
        services_before=len(services),
        services_in_reach=len(reach),
        services_after=len(kept_services),
        nodes_before=len(snapshot.nodes),
        nodes_after=len(pruned.nodes),
        edges_before=len(snapshot.edges),
        edges_after=len(edges),
        edges_below_r=len(weak),
        edges_over_budget=len(inside) - len(weak) - len(edges),
        snapshot_hash=pruned.compute_snapshot_hash(),
    )
