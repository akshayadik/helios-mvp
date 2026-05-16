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
