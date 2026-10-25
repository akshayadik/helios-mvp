"""Composition rules for typed UEG-C paths (S1.5)."""

from __future__ import annotations

import itertools

import pytest

from helios.graph.composition import CLASS_ORDER, compose, path_class, typed_paths
from helios.schemas.ueg_c import (
    EdgeClass,
    EdgeType,
    NodeType,
    UEGCEdge,
    UEGCNode,
    UEGCSnapshot,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

S, B, C, E = (
    EdgeClass.STRUCTURAL,
    EdgeClass.BEHAVIOURAL,
    EdgeClass.CAUSAL,
    EdgeClass.ECONOMIC,
)


def test_chapter_3_examples() -> None:
    assert compose(B, S) == B
    assert compose(S, B) == B
    assert compose(C, E) == E


def test_nothing_follows_an_economic_edge() -> None:
    for c in CLASS_ORDER:
        assert compose(E, c) is None
    assert compose(None, S) is None
    assert compose(S, None) is None


def test_composition_is_associative_over_every_triple() -> None:
    values = [*CLASS_ORDER, None]
    for a, b, c in itertools.product(values, repeat=3):
        assert compose(compose(a, b), c) == compose(a, compose(b, c))


def test_same_class_composes_to_itself() -> None:
    for c in (S, B, C):
        assert compose(c, c) == c


def test_path_class_folds_a_sequence() -> None:
    assert path_class([S, S, B]) == B
    assert path_class([C, S, E]) == E
    assert path_class([S, E, S]) is None
    assert path_class([]) is None


def _edge(a: str, b: str, kind: EdgeType, w: float) -> UEGCEdge:
    return UEGCEdge(source=a, target=b, edge_type=kind, weight=w)


def _snapshot() -> UEGCSnapshot:
    nodes = [
        UEGCNode(node_id=n, node_type=NodeType.SERVICE, service_name=n)
        for n in ("frontend", "cart", "redis")
    ]
    nodes.append(
        UEGCNode(
            node_id="kpi:frontend",
            node_type=NodeType.TRANSACTION_KPI,
            service_name="frontend",
        )
    )
    edges = [
        _edge("frontend", "cart", EdgeType.STRUCTURAL, 1),
        _edge("cart", "redis", EdgeType.CALL, 0.8),
        _edge("redis", "frontend", EdgeType.ANOMALY_LEADS, 0.9),
        _edge("frontend", "kpi:frontend", EdgeType.SERVES_KPI, 1),
        _edge("redis", "kpi:frontend", EdgeType.SERVES_KPI, 0.4),
        _edge("kpi:frontend", "cart", EdgeType.CALL, 1),  # invalid after economic
    ]
    return UEGCSnapshot(
        incident_id="inc",
        variant_config_hash="h",
        nodes=nodes,
        edges=edges,
        captured_at_iso="2026-10-25T10:05:00Z",
    )


def test_cross_domain_path_from_an_anomaly_to_a_kpi() -> None:
    paths = typed_paths(_snapshot(), "redis", "kpi:frontend", max_hops=3)
    assert [p.nodes for p in paths] == [
        ("redis", "frontend", "kpi:frontend"),
        ("redis", "kpi:frontend"),
    ]
    causal_then_economic = paths[0]
    assert causal_then_economic.edge_class == EdgeClass.ECONOMIC
    assert causal_then_economic.weight == pytest.approx(0.9)
    assert [e.edge_class for e in causal_then_economic.edges] == [C, E]


def test_behavioural_composed_with_structural() -> None:
    (path,) = typed_paths(_snapshot(), "frontend", "redis", max_hops=3)
    assert path.nodes == ("frontend", "cart", "redis")
    assert path.edge_class == EdgeClass.BEHAVIOURAL
    assert path.weight == pytest.approx(0.8)


def test_paths_never_continue_past_an_economic_edge() -> None:
    paths = typed_paths(_snapshot(), "frontend", "cart", max_hops=4)
    assert [p.nodes for p in paths] == [("frontend", "cart")]


def test_class_filter_and_hop_limit() -> None:
    snap = _snapshot()
    assert typed_paths(snap, "redis", "kpi:frontend", 1) == [
        p for p in typed_paths(snap, "redis", "kpi:frontend", 3) if len(p.edges) == 1
    ]
    only_topology = typed_paths(
        snap, "redis", "kpi:frontend", 3, classes=frozenset({S, B})
    )
    assert only_topology == []
    with pytest.raises(ValueError, match="max_hops"):
        typed_paths(snap, "redis", "cart", 0)
