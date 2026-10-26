"""Structural bundle — ueg_structural ON vs OFF (S1.6, HELIOS-Full vs HELIOS-noStructural)."""

from __future__ import annotations

import itertools

import pytest

from helios.graph.composition import CLASS_ORDER, compose, typed_paths
from helios.graph.ppr_pruner import prune_graph
from helios.graph.structural_bundle import (
    StructuralView,
    TrainingScope,
    apply_structural_bundle,
    flatten,
    typed_view,
)
from helios.graph.ueg_c_builder import ReasoningStep, SpanRecord, UEGCBuilder
from helios.pipelines.d_pipe.stages.c_propagation_engine import PropagationEngine
from helios.schemas.ueg_c import EdgeClass, EdgeType, NodeType, UEGCSnapshot
from helios.vcl import VCLFlag, set_current_manifest
from helios.vcl.decorators import GatedComponentInactiveError
from helios.vcl.variants import get_variant


def _span(trace: str, sid: str, svc: str, parent: str, start: int) -> SpanRecord:
    return SpanRecord(
        trace_id=trace,
        span_id=sid,
        service_name=svc,
        parent_span_id=parent,
        start_us=start,
        end_us=start + 400,
    )


def _structural_fixture() -> UEGCSnapshot:
    """frontend -> cart -> redis (structural + call), KPI node, two reasoning steps."""
    spans = [
        _span("t1", "a", "frontend", "", 0),
        _span("t1", "b", "cart", "a", 10),
        _span("t1", "c", "redis", "b", 20),
        _span("t2", "d", "frontend", "", 0),
        _span("t2", "e", "cart", "d", 10),
    ]
    steps = [
        ReasoningStep("s1", "trace-agent", "inspect cart spans", "cart"),
        ReasoningStep("s2", "trace-agent", "rank candidates"),
    ]
    return UEGCBuilder().build(
        spans,
        incident_id="inc",
        variant_config_hash="h",
        captured_at_iso="2026-10-25T10:20:00Z",
        parent_span_id_col_present=True,
        reasoning_steps=steps,
    )


def _view_for(variant: str, snapshot: UEGCSnapshot) -> StructuralView:
    set_current_manifest(get_variant(variant))
    return apply_structural_bundle(snapshot)


def test_no_structural_changes_the_snapshot_hash() -> None:
    snap = _structural_fixture()
    full = _view_for("HELIOS-Full", snap)
    off = _view_for("HELIOS-noStructural", snap)
    assert full.typed and not off.typed
    assert full.snapshot.compute_snapshot_hash() == snap.compute_snapshot_hash()
    assert off.snapshot.compute_snapshot_hash() != full.snapshot.compute_snapshot_hash()


def test_every_other_variant_keeps_the_typed_graph() -> None:
    snap = _structural_fixture()
    for name in ("HELIOS-noLLM", "HELIOS-noRouter", "HELIOS-noConsensus"):
        assert _view_for(name, snap).typed


def test_off_is_one_untyped_edge_kind_with_parallel_edges_merged() -> None:
    snap = _structural_fixture()
    off = flatten(snap)
    assert {e.edge_type for e in off.snapshot.edges} == {EdgeType.UNTYPED}
    assert {e.edge_class for e in off.snapshot.edges} == {EdgeClass.UNTYPED}
    pairs = [(e.source, e.target) for e in off.snapshot.edges]
    assert len(pairs) == len(set(pairs))
    # frontend -> cart had a structural edge (weight 1) and a call edge (2/2)
    merged = {(e.source, e.target): e.weight for e in off.snapshot.edges}
    assert merged["frontend", "cart"] == pytest.approx(1)
    assert merged["cart", "redis"] == pytest.approx(1)
    assert all(
        e.correlation is None and e.lag_seconds is None for e in off.snapshot.edges
    )


def test_off_turns_reasoning_steps_into_flat_text() -> None:
    off = flatten(_structural_fixture())
    assert not any(
        n.node_type == NodeType.AGENT_REASONING_STEP for n in off.snapshot.nodes
    )
    assert not any(e.source.startswith("ars:") for e in off.snapshot.edges)
    assert off.reasoning_text == (
        "step 0 (trace-agent) -> cart: inspect cart spans",
        "step 1 (trace-agent): rank candidates",
    )
    kpis = [n for n in off.snapshot.nodes if n.node_type == NodeType.TRANSACTION_KPI]
    assert [n.node_id for n in kpis] == ["kpi:frontend"]


def test_training_scope_follows_the_flag() -> None:
    snap = _structural_fixture()
    assert (
        _view_for("HELIOS-Full", snap).training_scope == TrainingScope.PRUNED_SUBGRAPH
    )
    assert (
        _view_for("HELIOS-noStructural", snap).training_scope
        == TrainingScope.FULL_GRAPH
    )
    assert _view_for("HELIOS-Full", snap).reasoning_text == ()


def test_typed_view_is_the_gated_component() -> None:
    assert typed_view.__gated_by__ == VCLFlag.UEG_STRUCTURAL  # type: ignore[attr-defined]
    set_current_manifest(get_variant("HELIOS-noStructural"))
    with pytest.raises(GatedComponentInactiveError):
        typed_view(_structural_fixture())


def test_untyped_edges_compose_only_with_each_other() -> None:
    u = EdgeClass.UNTYPED
    assert compose(u, u) == u
    for k in CLASS_ORDER:
        assert compose(u, k) is None
        assert compose(k, u) is None
    values = [*CLASS_ORDER, u, None]
    for a, b, c in itertools.product(values, repeat=3):
        assert compose(compose(a, b), c) == compose(a, compose(b, c))
    off = flatten(_structural_fixture()).snapshot
    (path,) = typed_paths(off, "frontend", "redis", max_hops=3)
    assert path.edge_class == u


def test_pruner_uses_untyped_edges_and_falls_back_to_the_hub() -> None:
    off = flatten(_structural_fixture()).snapshot
    pruned, result = prune_graph(off, pruner_threshold=0.05)
    kept = {n.node_id for n in pruned.nodes}
    assert {"frontend", "cart", "redis"} <= kept
    assert result.edges_after > 0


def test_propagation_accepts_untyped_edges() -> None:
    off = flatten(_structural_fixture()).snapshot
    engine = PropagationEngine(rho_threshold=0.6, topology_boost_factor=0.3)
    out = engine.propagate(
        {"frontend": 2, "cart": 0, "redis": 0},
        {},
        [e for e in off.edges if e.target != "kpi:frontend"],
        p1_services=["frontend"],
    )
    assert out["cart"] > 0
