"""TDD for UEGCBuilder structural + call edge construction.

VCLFlag.L2B_GRAPH gates the UEGCBuilder — imported for flag-guard compliance.
"""

from __future__ import annotations

import pytest

from helios.graph.ueg_c_builder import SpanRecord, UEGCBuilder
from helios.schemas.ueg_c import EdgeType
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def _builder_structural() -> UEGCBuilder:
    return UEGCBuilder(enable_structural=True)


def _span(trace: str, svc: str, start: int, dur: int) -> SpanRecord:
    return SpanRecord(
        trace_id=trace, service_name=svc, start_us=start, end_us=start + dur
    )


_HASH = "a" * 64
_AT = "2026-01-01T00:00:00+00:00"


def test_structural_edge_parent_encloses_child() -> None:
    spans = [
        _span("t1", "frontend", 0, 1000),
        _span("t1", "checkout", 1_00, 800),
    ]
    snap = _builder_structural().build(
        spans, incident_id="inc", variant_config_hash=_HASH, captured_at_iso=_AT
    )
    s_edges = [e for e in snap.edges if e.edge_type == EdgeType.STRUCTURAL]
    assert len(s_edges) == 1
    assert s_edges[0].source == "frontend"
    assert s_edges[0].target == "checkout"
    assert s_edges[0].weight == 1


def test_structural_scan_skips_same_service_spans() -> None:
    spans = [
        _span("t1", "frontend", 0, 2000),
        _span("t1", "frontend", 1_00, 500),  # same service — skip
        _span("t1", "checkout", 200, 200),
    ]
    snap = _builder_structural().build(
        spans, incident_id="inc", variant_config_hash=_HASH, captured_at_iso=_AT
    )
    s_edges = [e for e in snap.edges if e.edge_type == EdgeType.STRUCTURAL]
    assert len(s_edges) == 1
    assert s_edges[0].source == "frontend"
    assert s_edges[0].target == "checkout"


def test_structural_disabled_emits_no_structural_edges() -> None:
    spans = [
        _span("t1", "a", 0, 1000),
        _span("t1", "b", 1_00, 800),
    ]
    snap = UEGCBuilder(enable_structural=False).build(
        spans, incident_id="inc", variant_config_hash=_HASH, captured_at_iso=_AT
    )
    assert not any(e.edge_type == EdgeType.STRUCTURAL for e in snap.edges)


def test_call_edge_weight_equals_fraction_of_traces() -> None:
    # Pair (frontend, checkout) observed in 2 of 2 traces
    spans = [
        _span("t1", "frontend", 0, 1000),
        _span("t1", "checkout", 1_00, 800),
        _span("t2", "frontend", 0, 1000),
        _span("t2", "checkout", 1_00, 800),
    ]
    snap = UEGCBuilder(enable_structural=False).build(
        spans, incident_id="inc", variant_config_hash=_HASH, captured_at_iso=_AT
    )
    c_edges = [e for e in snap.edges if e.edge_type == EdgeType.CALL]
    fe_co = next(
        e for e in c_edges if e.source == "frontend" and e.target == "checkout"
    )
    assert fe_co.weight == pytest.approx(2 / 2)


def test_call_edge_partial_trace_coverage() -> None:
    # Pair observed in 1 of 2 traces
    spans = [
        _span("t1", "frontend", 0, 1000),
        _span("t1", "checkout", 1_00, 800),
        _span("t2", "frontend", 0, 1000),
    ]
    snap = UEGCBuilder(enable_structural=False).build(
        spans, incident_id="inc", variant_config_hash=_HASH, captured_at_iso=_AT
    )
    c_edges = [e for e in snap.edges if e.edge_type == EdgeType.CALL]
    fe_co = next(
        (e for e in c_edges if e.source == "frontend" and e.target == "checkout"), None
    )
    assert fe_co is not None
    assert fe_co.weight == pytest.approx(1 / 2)


def test_nodes_one_per_service() -> None:
    spans = [
        _span("t1", "a", 0, 1000),
        _span("t1", "b", 1_00, 500),
        _span("t2", "a", 0, 800),
    ]
    snap = _builder_structural().build(
        spans, incident_id="inc", variant_config_hash=_HASH, captured_at_iso=_AT
    )
    assert {n.service_name for n in snap.nodes} == {"a", "b"}
