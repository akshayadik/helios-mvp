"""TDD for PPR pruner."""

from __future__ import annotations

from helios.graph.ppr_pruner import PruneResult, prune_graph
from helios.schemas.ueg_c import EdgeType, NodeType, UEGCEdge, UEGCNode, UEGCSnapshot

_HASH = "a" * 64
_AT = "2026-01-01T00:00:00+00:00"


def _snapshot(n_services: list[str], edges: list[UEGCEdge]) -> UEGCSnapshot:
    nodes = [
        UEGCNode(node_id=s, node_type=NodeType.SERVICE, service_name=s)
        for s in n_services
    ]
    return UEGCSnapshot(
        incident_id="t",
        variant_config_hash=_HASH,
        nodes=nodes,
        edges=edges,
        captured_at_iso=_AT,
    )


def test_prune_result_fields() -> None:
    snap = _snapshot(
        ["a", "b"],
        [UEGCEdge(source="a", target="b", edge_type=EdgeType.CALL, weight=0.80)],
    )
    _, result = prune_graph(snap, pruner_threshold=0.001)
    assert isinstance(result, PruneResult)
    assert result.nodes_before == 2
    assert result.edges_before == 1
    assert 0 < result.integrity_rate <= 1.00


def test_isolated_node_pruned_at_high_threshold() -> None:
    # a→b structural, c is isolated (not reachable from entry points)
    edges = [
        UEGCEdge(source="a", target="b", edge_type=EdgeType.STRUCTURAL, weight=1),
        UEGCEdge(source="a", target="b", edge_type=EdgeType.CALL, weight=0.80),
    ]
    snap = _snapshot(["a", "b", "c"], edges)
    pruned, result = prune_graph(snap, pruner_threshold=0.05)
    assert result.nodes_before == 3
    assert result.nodes_after <= 2
    pruned_svcs = {n.service_name for n in pruned.nodes}
    assert "c" not in pruned_svcs


def test_integrity_rate_computed_correctly() -> None:
    snap = _snapshot(
        ["a", "b"],
        [UEGCEdge(source="a", target="b", edge_type=EdgeType.CALL, weight=0.80)],
    )
    _, result = prune_graph(snap, pruner_threshold=0.001)
    assert result.integrity_rate == result.nodes_after / result.nodes_before


def test_prune_result_no_assert_caller_enforces_gate() -> None:
    snap = _snapshot(["x"], [])
    _, result = prune_graph(snap, pruner_threshold=0.99)
    # Must return PruneResult even if integrity_rate < INTEGRITY_RATE_GATE; no assert inside
    assert isinstance(result, PruneResult)


def test_isolated_structural_root_excluded_from_ppr_seed() -> None:
    # kafka_consumer: struct_in=0, out_degree=0 — async consumer, no outgoing edges.
    # frontend: struct_in=0, out_degree>0 — correct PPR seed.
    # backend: struct_in=1 — downstream service.
    # PPR seeded from frontend must score kafka_consumer near zero → pruned at 0.02.
    edges = [
        UEGCEdge(
            source="frontend", target="backend", edge_type=EdgeType.STRUCTURAL, weight=1
        ),
        UEGCEdge(
            source="frontend", target="backend", edge_type=EdgeType.CALL, weight=0.80
        ),
    ]
    snap = _snapshot(["backend", "frontend", "kafka_consumer"], edges)
    pruned_snap, result = prune_graph(snap, pruner_threshold=0.02)
    pruned_svcs = {n.service_name for n in pruned_snap.nodes}
    assert "kafka_consumer" not in pruned_svcs, "isolated async consumer must be pruned"
    assert "frontend" in pruned_svcs, "PPR seed (frontend) must be retained"
    assert result.nodes_before == 3
    assert result.nodes_after == 2


def test_hub_fallback_when_no_structural_edges() -> None:
    # Graph with only CALL edges — all nodes have struct_in=0.
    # hub has out_degree=2; leaf_a, leaf_b have out_degree=0.
    # Fallback seeds from hub; leaf nodes may be pruned at high threshold.
    edges = [
        UEGCEdge(source="hub", target="leaf_a", edge_type=EdgeType.CALL, weight=0.80),
        UEGCEdge(source="hub", target="leaf_b", edge_type=EdgeType.CALL, weight=0.40),
    ]
    snap = _snapshot(["hub", "leaf_a", "leaf_b"], edges)
    _, result = prune_graph(snap, pruner_threshold=0.001)
    # At very low threshold all nodes retained
    assert result.nodes_after == 3
    pruned_snap2, _ = prune_graph(snap, pruner_threshold=0.40)
    # hub should always be retained (highest PPR); leaves may be pruned
    hub_retained = any(n.service_name == "hub" for n in pruned_snap2.nodes)
    assert hub_retained
