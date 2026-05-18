"""K-hop PPR pruner — entry-point seeded Personalized PageRank graph reduction."""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from helios.schemas.ueg_c import EdgeType, UEGCSnapshot
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


@dataclass
class PruneResult:
    nodes_before: int
    nodes_after: int
    edges_before: int
    edges_after: int

    @property
    def integrity_rate(self) -> float:
        if self.nodes_before == 0:
            return 1.00
        return self.nodes_after / self.nodes_before


def prune_graph(
    snapshot: UEGCSnapshot,
    *,
    pruner_threshold: float = 0.02,
) -> tuple[UEGCSnapshot, PruneResult]:
    graph: nx.DiGraph = nx.DiGraph()
    for node in snapshot.nodes:
        graph.add_node(node.service_name)
    for edge in snapshot.edges:
        graph.add_edge(edge.source, edge.target, weight=edge.weight)

    # Entry points: structural in-degree == 0 AND at least one outgoing edge.
    # Nodes that are structurally unreachable AND have no outgoing edges (e.g., async
    # Kafka consumers) are isolated islands — seeding PPR from them prevents propagation
    # and forces a uniform-PageRank fallback that defeats pruning (spec §2.4).
    structural_in: dict[str, int] = dict.fromkeys(graph.nodes, 0)
    for edge in snapshot.edges:
        if edge.edge_type == EdgeType.STRUCTURAL:
            structural_in[edge.target] = structural_in.get(edge.target, 0) + 1
    entry_points = [
        n for n in graph.nodes if structural_in[n] == 0 and graph.out_degree(n) > 0
    ]

    if not entry_points:
        # No structural root has outgoing edges — fall back to the highest-degree hub.
        # This covers graphs where all structural entry points are async consumers, or
        # where the capture contains no structural edges at all.
        max_out = max((graph.out_degree(n) for n in graph.nodes), default=0)
        if max_out > 0:
            entry_points = [n for n in graph.nodes if graph.out_degree(n) == max_out]

    if entry_points:
        n_seed = len(entry_points)
        personalization: dict[str, float] | None = {
            n: (1 / n_seed if n in entry_points else 0) for n in graph.nodes
        }
    else:
        personalization = None

    # alpha=0.85 → restart_probability=0.15 (spec §2.4)
    ppr: dict[str, float] = nx.pagerank(
        graph, alpha=0.85, personalization=personalization
    )

    retained = {n for n, score in ppr.items() if score >= pruner_threshold}
    kept_nodes = [n for n in snapshot.nodes if n.service_name in retained]
    kept_edges = [
        e for e in snapshot.edges if e.source in retained and e.target in retained
    ]

    pruned = snapshot.model_copy(update={"nodes": kept_nodes, "edges": kept_edges})

    return pruned, PruneResult(
        nodes_before=len(snapshot.nodes),
        nodes_after=len(kept_nodes),
        edges_before=len(snapshot.edges),
        edges_after=len(kept_edges),
    )
