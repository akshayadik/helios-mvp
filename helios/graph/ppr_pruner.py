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
    pruner_threshold: float = 0.01,
) -> tuple[UEGCSnapshot, PruneResult]:
    graph: nx.DiGraph = nx.DiGraph()
    for node in snapshot.nodes:
        graph.add_node(node.service_name)
    for edge in snapshot.edges:
        graph.add_edge(edge.source, edge.target, weight=edge.weight)

    # Entry points: services with structural in-degree == 0 AND structural out-degree > 0.
    # Purely isolated nodes (no structural edges) are orphans, not roots.
    structural_in: dict[str, int] = dict.fromkeys(graph.nodes, 0)
    structural_out: dict[str, int] = dict.fromkeys(graph.nodes, 0)
    for edge in snapshot.edges:
        if edge.edge_type == EdgeType.STRUCTURAL:
            structural_in[edge.target] = structural_in.get(edge.target, 0) + 1
            structural_out[edge.source] = structural_out.get(edge.source, 0) + 1
    entry_points = [
        n for n in graph.nodes if structural_in[n] == 0 and structural_out[n] > 0
    ]
    if not entry_points:
        entry_points = list(graph.nodes)

    n_entry = len(entry_points)
    personalization = {
        n: (1 / n_entry if n in entry_points else 0.00) for n in graph.nodes
    }

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
