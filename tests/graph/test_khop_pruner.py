"""K-hop pruner — Algorithm 5 (S1.7)."""

from __future__ import annotations

from itertools import pairwise

import numpy as np
import pytest

from helios.graph.khop_pruner import (
    EDGE_BUDGET,
    MIN_NODES,
    PEARSON_MIN_R,
    SeedSource,
    khop_prune,
    seed_nodes,
)
from helios.graph.structural_bundle import flatten
from helios.graph.ueg_c_builder import ANOMALY_PEAK_KEY, SpanRecord, UEGCBuilder
from helios.schemas.ueg_c import (
    TENANT_SELF,
    EdgeType,
    NodeType,
    UEGCEdge,
    UEGCNode,
    UEGCSnapshot,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

CHAIN = ("a", "b", "c", "d", "e")


def _service(name: str, peak: float | None = None) -> UEGCNode:
    meta = {} if peak is None else {ANOMALY_PEAK_KEY: f"{peak:.6f}"}
    return UEGCNode(
        node_id=name, node_type=NodeType.SERVICE, service_name=name, metadata=meta
    )


def _edge(
    a: str, b: str, kind: EdgeType, w: float = 1, r: float | None = None
) -> UEGCEdge:
    return UEGCEdge(source=a, target=b, edge_type=kind, weight=w, correlation=r)


def _snap(nodes: list[UEGCNode], edges: list[UEGCEdge]) -> UEGCSnapshot:
    return UEGCSnapshot(
        incident_id="inc",
        variant_config_hash="h",
        nodes=nodes,
        edges=edges,
        captured_at_iso="2026-10-26T10:00:00Z",
    )


def _chain(peaks: dict[str, float] | None = None) -> UEGCSnapshot:
    peaks = peaks or {}
    nodes = [_service(n, peaks.get(n)) for n in CHAIN]
    edges = [_edge(x, y, EdgeType.CALL) for x, y in pairwise(CHAIN)]
    return _snap(nodes, edges)


def _kept(snapshot: UEGCSnapshot) -> list[str]:
    return snapshot.candidate_ids()


def test_chapter_3_values() -> None:
    assert pytest.approx(0.7) == PEARSON_MIN_R
    assert EDGE_BUDGET == 10_000
    assert MIN_NODES == 50


def test_seeds_are_the_highest_peak_anomaly_services() -> None:
    snap = _chain({"a": 2, "b": 9, "c": 4, "d": 4, "e": 3})
    assert seed_nodes(snap) == (("b", "c", "d"), SeedSource.ANOMALY)
    assert seed_nodes(snap, count=1) == (("b",), SeedSource.ANOMALY)


def test_seeds_fall_back_to_entry_points_then_to_every_service() -> None:
    snap = _chain()
    structural = snap.model_copy(
        update={"edges": [*snap.edges, _edge("a", "b", EdgeType.STRUCTURAL)]}
    )
    assert seed_nodes(structural) == (("a", "c", "d"), SeedSource.ENTRY_POINTS)
    bare = _snap([_service(n, 0) for n in CHAIN], [])
    assert seed_nodes(bare) == (CHAIN, SeedSource.ALL)


def test_k_hops_bound_the_neighbourhood() -> None:
    snap = _chain()
    for k, expected in ((0, ["a"]), (1, ["a", "b"]), (2, ["a", "b", "c"])):
        pruned, result = khop_prune(snap, seeds=["a"], k=k, min_nodes=0)
        assert _kept(pruned) == expected
        assert result.services_in_reach == len(expected)
        assert result.seed_source == SeedSource.GIVEN


def test_only_strong_causal_edges_expand_the_seeds() -> None:
    nodes = [_service(n) for n in ("a", "b", "c")]
    edges = [
        _edge("a", "b", EdgeType.ANOMALY_LEADS, 0.9, 0.9),
        _edge("a", "c", EdgeType.ANOMALY_CO_MOVES, 0.65, 0.65),
    ]
    pruned, result = khop_prune(_snap(nodes, edges), seeds=["a"], k=2, min_nodes=0)
    assert _kept(pruned) == ["a", "b"]
    assert result.edges_below_r == 0  # the weak edge left with its node


def test_the_floor_fills_from_the_nearest_services_by_pagerank() -> None:
    pruned, result = khop_prune(_chain(), seeds=["a"], k=0, min_nodes=3)
    assert _kept(pruned) == ["a", "b", "c"]
    assert result.services_after == 3
    small, _ = khop_prune(_chain(), seeds=["a"], k=0)
    assert _kept(small) == list(CHAIN)  # graph below the floor: nothing removed


def test_top_n_caps_the_neighbourhood_and_seeds_always_stay() -> None:
    pruned, _ = khop_prune(_chain(), seeds=["a"], k=4, top_n=2, min_nodes=0)
    assert _kept(pruned) == ["a", "b"]
    pruned, _ = khop_prune(_chain(), seeds=["a", "e"], k=4, top_n=1, min_nodes=0)
    assert _kept(pruned) == ["a", "e"]


def test_weak_correlated_edges_are_dropped_others_stay() -> None:
    nodes = [_service(n) for n in ("a", "b", "c")]
    edges = [
        _edge("a", "b", EdgeType.CALL, 0.8, 0.4),  # behavioural, weak
        _edge("a", "b", EdgeType.STRUCTURAL),  # structural, no correlation
        _edge("b", "c", EdgeType.CALL, 0.8),  # behavioural without correlation
        _edge("b", "c", EdgeType.ANOMALY_LEADS, 0.65, 0.65),  # causal, weak
        _edge("c", "a", EdgeType.ANOMALY_LEADS, 0.8, -0.8),  # causal, strong
    ]
    pruned, result = khop_prune(_snap(nodes, edges), seeds=["a"], k=2)
    kinds = sorted((e.edge_type.value, e.source, e.target) for e in pruned.edges)
    assert kinds == [
        ("anomaly_leads", "c", "a"),
        ("call", "b", "c"),
        ("structural", "a", "b"),
    ]
    assert result.edges_below_r == 2


def test_edge_budget_keeps_the_strongest_edges() -> None:
    nodes = [_service(n) for n in CHAIN]
    edges = [
        _edge(x, y, EdgeType.CALL, w)
        for (x, y), w in zip(pairwise(CHAIN), (0.2, 0.9, 0.4, 0.7), strict=True)
    ]
    pruned, result = khop_prune(_snap(nodes, edges), seeds=["a"], k=4, edge_budget=2)
    assert sorted(e.weight for e in pruned.edges) == pytest.approx([0.7, 0.9])
    assert result.edges_over_budget == 2
    assert [e.source for e in pruned.edges] == sorted(e.source for e in pruned.edges)


def test_kpi_and_self_tenant_nodes_follow_the_services() -> None:
    snap = _chain()
    extra = [
        UEGCNode(node_id=f"kpi:{s}", node_type=NodeType.TRANSACTION_KPI, service_name=s)
        for s in ("a", "e")
    ]
    extra.append(
        UEGCNode(
            node_id="ars:s1",
            node_type=NodeType.AGENT_REASONING_STEP,
            service_name="agent",
            tenant=TENANT_SELF,
        )
    )
    edges = [
        *snap.edges,
        _edge("a", "kpi:a", EdgeType.SERVES_KPI),
        _edge("ars:s1", "a", EdgeType.INVOKES),
    ]
    full = snap.model_copy(update={"nodes": [*snap.nodes, *extra], "edges": edges})
    pruned, _ = khop_prune(full, seeds=["a"], k=1, min_nodes=0)
    ids = {n.node_id for n in pruned.nodes}
    assert {"kpi:a", "ars:s1"} <= ids
    assert "kpi:e" not in ids
    assert ("ars:s1", "a") in {(e.source, e.target) for e in pruned.edges}


def test_output_is_deterministic_and_hashed() -> None:
    snap = _chain({"a": 3, "c": 5})
    first, r1 = khop_prune(snap, k=1, min_nodes=0)
    again, r2 = khop_prune(snap, k=1, min_nodes=0)
    assert r1 == r2
    assert r1.snapshot_hash == first.compute_snapshot_hash()
    assert first == again
    assert r1.seeds == ("a", "c")  # only services with a peak are ranked


def test_untyped_edges_expand_like_topology() -> None:
    off = flatten(_chain()).snapshot
    pruned, _ = khop_prune(off, seeds=["c"], k=1, min_nodes=0)
    assert _kept(pruned) == ["b", "c", "d"]


def test_bad_arguments_are_refused() -> None:
    with pytest.raises(ValueError, match="not production services"):
        khop_prune(_chain(), seeds=["zz"])
    with pytest.raises(ValueError, match="top_n"):
        khop_prune(_chain(), top_n=0)
    with pytest.raises(ValueError, match="top_n"):
        khop_prune(_chain(), k=-1)


def test_empty_graph() -> None:
    pruned, result = khop_prune(_snap([], []))
    assert pruned.nodes == []
    assert result.seed_source == SeedSource.ALL
    assert result.services_after == 0


def test_builder_records_the_peak_anomaly_intensity() -> None:
    spans = [
        SpanRecord(
            trace_id="t",
            span_id="s",
            service_name="a",
            parent_span_id="",
            start_us=0,
            end_us=10,
        )
    ]
    snap = UEGCBuilder().build(
        spans,
        incident_id="inc",
        variant_config_hash="h",
        captured_at_iso="2026-10-26T10:00:00Z",
        parent_span_id_col_present=True,
        intensity={"a": np.array([1, 4.25, 2]), "b": np.array([])},
    )
    meta = {n.node_id: n.metadata for n in snap.nodes}
    assert meta["a"][ANOMALY_PEAK_KEY] == "4.250000"
    assert ANOMALY_PEAK_KEY not in meta["b"]
