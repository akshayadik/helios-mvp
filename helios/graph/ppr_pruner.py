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

    # Entry points: services with structural in-degree == 0 (spec §2.4).
    structural_in: dict[str, int] = dict.fromkeys(graph.nodes, 0)
    for edge in snapshot.edges:
        if edge.edge_type == EdgeType.STRUCTURAL:
            structural_in[edge.target] = structural_in.get(edge.target, 0) + 1
    entry_points = [n for n in graph.nodes if structural_in[n] == 0]

    if entry_points:
        # If all entry points are isolated in the full graph (no outgoing edges of any type),
        # PPR seeded from them cannot propagate — fall back to uniform PageRank.
        all_isolated = all(graph.out_degree(ep) == 0 for ep in entry_points)
        if all_isolated:
            print(
                f"WARNING: all {len(entry_points)} structural entry point(s) are isolated "
                "(no outgoing edges) — falling back to uniform PageRank"
            )
            personalization = None
        else:
            # Only seed from entry points that have outgoing edges; isolated structural
            # roots cannot drive PPR propagation and would dilute scores unfairly.
            seeded = [ep for ep in entry_points if graph.out_degree(ep) > 0]
            n_seed = len(seeded)
            personalization = {
                n: (1 / n_seed if n in seeded else 0) for n in graph.nodes
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
