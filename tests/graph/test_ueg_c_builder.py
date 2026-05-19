"""TDD for UEGCBuilder structural + call edge construction.

VCLFlag.L2B_GRAPH gates the UEGCBuilder — imported for flag-guard compliance.
"""

from __future__ import annotations

import warnings

import pytest

from helios.graph.ueg_c_builder import SpanRecord, UEGCBuilder
from helios.schemas.ueg_c import EdgeType
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def _builder_structural() -> UEGCBuilder:
    return UEGCBuilder(enable_structural=True)


def _span(
    trace: str,
    svc: str,
    start: int,
    dur: int,
    span_id: str = "",
    parent_span_id: str | None = None,
) -> SpanRecord:
    return SpanRecord(
        trace_id=trace,
        span_id=span_id,
        service_name=svc,
        parent_span_id=parent_span_id,
        start_us=start,
        end_us=start + dur,
    )


_HASH = "a" * 64
_AT = "2026-01-01T00:00:00+00:00"


def test_structural_edge_parent_encloses_child() -> None:
    spans = [
        _span("t1", "frontend", 0, 1000),
        _span("t1", "checkout", 1_00, 800),
    ]
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
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
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
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
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        snap = _builder_structural().build(
            spans, incident_id="inc", variant_config_hash=_HASH, captured_at_iso=_AT
        )
    assert {n.service_name for n in snap.nodes} == {"a", "b"}


def test_structural_root_span_has_no_incoming_edge() -> None:
    spans = [
        _span("t1", "frontend", 0, 1000, span_id="s1", parent_span_id=None),
        _span("t1", "checkout", 1_00, 800, span_id="s2", parent_span_id="s1"),
    ]
    snap = UEGCBuilder(enable_structural=True).build(
        spans,
        incident_id="inc",
        variant_config_hash=_HASH,
        captured_at_iso=_AT,
        parent_span_id_col_present=True,
    )
    s_edges = [e for e in snap.edges if e.edge_type == EdgeType.STRUCTURAL]
    assert len(s_edges) == 1
    assert s_edges[0].source == "frontend"
    assert s_edges[0].target == "checkout"


def test_structural_cross_service_edge() -> None:
    spans = [
        _span("t1", "api", 0, 1000, span_id="A", parent_span_id=None),
        _span("t1", "db", 1_00, 200, span_id="B", parent_span_id="A"),
    ]
    snap = UEGCBuilder(enable_structural=True).build(
        spans,
        incident_id="inc",
        variant_config_hash=_HASH,
        captured_at_iso=_AT,
        parent_span_id_col_present=True,
    )
    s_edges = [e for e in snap.edges if e.edge_type == EdgeType.STRUCTURAL]
    assert any(e.source == "api" and e.target == "db" for e in s_edges)


def test_structural_same_service_skipped() -> None:
    spans = [
        _span("t1", "svc", 0, 1000, span_id="A", parent_span_id=None),
        _span("t1", "svc", 1_00, 200, span_id="B", parent_span_id="A"),
    ]
    snap = UEGCBuilder(enable_structural=True).build(
        spans,
        incident_id="inc",
        variant_config_hash=_HASH,
        captured_at_iso=_AT,
        parent_span_id_col_present=True,
    )
    s_edges = [e for e in snap.edges if e.edge_type == EdgeType.STRUCTURAL]
    assert len(s_edges) == 0


def test_structural_multi_level_chain() -> None:
    spans = [
        _span("t1", "A", 0, 1000, span_id="s1", parent_span_id=None),
        _span("t1", "B", 1_00, 500, span_id="s2", parent_span_id="s1"),
        _span("t1", "C", 200, 200, span_id="s3", parent_span_id="s2"),
    ]
    snap = UEGCBuilder(enable_structural=True).build(
        spans,
        incident_id="inc",
        variant_config_hash=_HASH,
        captured_at_iso=_AT,
        parent_span_id_col_present=True,
    )
    s_edges = [e for e in snap.edges if e.edge_type == EdgeType.STRUCTURAL]
    pairs = {(e.source, e.target) for e in s_edges}
    assert ("A", "B") in pairs
    assert ("B", "C") in pairs


def test_structural_fallback_on_missing_column() -> None:
    spans = [
        _span("t1", "frontend", 0, 1000, span_id="s1"),
        _span("t1", "checkout", 1_00, 800, span_id="s2"),
    ]
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        snap = UEGCBuilder(enable_structural=True).build(
            spans,
            incident_id="inc",
            variant_config_hash=_HASH,
            captured_at_iso=_AT,
            parent_span_id_col_present=False,
        )
    assert any("parent_span_id absent" in str(warning.message) for warning in w)
    s_edges = [e for e in snap.edges if e.edge_type == EdgeType.STRUCTURAL]
    assert len(s_edges) >= 1


def test_structural_root_only_v2_no_temporal_fallback() -> None:
    spans = [
        _span("t1", "svc_a", 0, 1000, span_id="s1", parent_span_id=""),
        _span("t1", "svc_b", 1_00, 800, span_id="s2", parent_span_id=""),
    ]
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        snap = UEGCBuilder(enable_structural=True).build(
            spans,
            incident_id="inc",
            variant_config_hash=_HASH,
            captured_at_iso=_AT,
            parent_span_id_col_present=True,
        )
    assert not any("parent_span_id absent" in str(warning.message) for warning in w)
    s_edges = [e for e in snap.edges if e.edge_type == EdgeType.STRUCTURAL]
    assert len(s_edges) == 0


def test_structural_empty_spans_returns_empty_edges() -> None:
    snap = UEGCBuilder(enable_structural=True).build(
        [],
        incident_id="inc",
        variant_config_hash=_HASH,
        captured_at_iso=_AT,
        parent_span_id_col_present=True,
    )
    assert not any(e.edge_type == EdgeType.STRUCTURAL for e in snap.edges)


def test_structural_no_cross_trace_contamination() -> None:
    # Traces t1 and t2 both use span IDs "s1"/"s2" — structural edges must not bleed.
    spans = [
        _span("t1", "frontend", 0, 1000, span_id="s1", parent_span_id=None),
        _span("t1", "checkout", 100, 800, span_id="s2", parent_span_id="s1"),
        _span("t2", "payment", 0, 1000, span_id="s1", parent_span_id=None),
        _span("t2", "fraud", 100, 800, span_id="s2", parent_span_id="s1"),
    ]
    snap = UEGCBuilder(enable_structural=True).build(
        spans,
        incident_id="inc",
        variant_config_hash=_HASH,
        captured_at_iso=_AT,
        parent_span_id_col_present=True,
    )
    s_edges = [e for e in snap.edges if e.edge_type == EdgeType.STRUCTURAL]
    pairs = {(e.source, e.target) for e in s_edges}
    assert ("frontend", "checkout") in pairs
    assert ("payment", "fraud") in pairs
    assert len(pairs) == 2


def test_structural_parquet_null_variants() -> None:
    import math

    import pandas as pd

    from helios.graph.ueg_c_builder import _psid

    assert _psid(None) == ""
    assert _psid(float("nan")) == ""
    assert _psid(pd.NA) == ""
    assert _psid(pd.NaT) == ""
    assert _psid(math.nan) == ""
    assert _psid("abc123") == "abc123"
    assert _psid("") == ""
