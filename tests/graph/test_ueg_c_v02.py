"""UEG-C v0.2 builder: four edge classes, KPI and reasoning-step nodes,
metric/log-only services, partial traces, deterministic snapshots (S1.5)."""

from __future__ import annotations

import inspect
import json
from typing import TYPE_CHECKING

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from helios.graph.ueg_c_builder import (
    BUCKET_SECONDS,
    ReasoningStep,
    SpanRecord,
    UEGCBuilder,
    build_ueg_c,
    kpi_node_id,
)
from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.schemas.ueg_c import TENANT_SELF, EdgeClass, EdgeType, NodeType
from helios.telemetry.pool_lock import PoolLockedError
from helios.vcl import VCLFlag, set_current_manifest
from helios.vcl.variants import get_variant

if TYPE_CHECKING:
    from pathlib import Path

    from helios.schemas.ueg_c import UEGCSnapshot

_HASH = "a" * 64
_AT = "2026-10-25T10:05:00Z"


def _span(
    trace: str, sid: str, svc: str, parent: str, start: int, dur: int
) -> SpanRecord:
    return SpanRecord(
        trace_id=trace,
        span_id=sid,
        service_name=svc,
        parent_span_id=parent,
        start_us=start,
        end_us=start + dur,
    )


def _shop_spans() -> list[SpanRecord]:
    """t1: frontend -> cart -> redis; t2: frontend -> cart; t3: batch (own root)."""
    return [
        _span("t1", "a", "frontend", "", 0, 900),
        _span("t1", "b", "cart", "a", 10, 500),
        _span("t1", "c", "redis", "b", 20, 120),
        _span("t2", "d", "frontend", "", 0, 900),
        _span("t2", "e", "cart", "d", 10, 500),
        _span("t3", "f", "batch", "", 0, 300),
    ]


def _build(**kwargs: object) -> UEGCSnapshot:
    return UEGCBuilder().build(
        _shop_spans(),
        incident_id="inc",
        variant_config_hash=_HASH,
        captured_at_iso=_AT,
        parent_span_id_col_present=True,
        **kwargs,  # type: ignore[arg-type]
    )


def _edges(snap: UEGCSnapshot, kind: EdgeType) -> dict[tuple[str, str], float]:
    return {(e.source, e.target): e.weight for e in snap.edges if e.edge_type == kind}


def test_structural_and_behavioural_edges_from_parent_links() -> None:
    snap = _build()
    assert set(_edges(snap, EdgeType.STRUCTURAL)) == {
        ("frontend", "cart"),
        ("cart", "redis"),
    }
    calls = _edges(snap, EdgeType.CALL)
    assert calls["frontend", "cart"] == pytest.approx(2 / 3)
    assert calls["cart", "redis"] == pytest.approx(1 / 3)


def test_kpi_node_per_entry_service_with_traffic_share() -> None:
    snap = _build()
    kpis = {n.node_id: n for n in snap.nodes if n.node_type == NodeType.TRANSACTION_KPI}
    assert set(kpis) == {kpi_node_id("frontend"), kpi_node_id("batch")}
    assert kpis[kpi_node_id("frontend")].metadata["traces"] == "2"
    economic = _edges(snap, EdgeType.SERVES_KPI)
    assert economic["frontend", "kpi:frontend"] == pytest.approx(1)
    assert economic["cart", "kpi:frontend"] == pytest.approx(1)
    assert economic["redis", "kpi:frontend"] == pytest.approx(1 / 2)
    assert economic["batch", "kpi:batch"] == pytest.approx(1)


def test_partial_traces_keep_services_but_add_no_dangling_edges() -> None:
    spans = [
        _span("t1", "a", "frontend", "", 0, 900),
        _span("t1", "b", "cart", "a", 10, 500),
        # parent span "zz" was not recorded: no edge, and t2 has no root
        _span("t2", "c", "payment", "zz", 20, 120),
    ]
    snap = UEGCBuilder().build(
        spans,
        incident_id="inc",
        variant_config_hash=_HASH,
        captured_at_iso=_AT,
        parent_span_id_col_present=True,
    )
    assert "payment" in snap.candidate_ids()
    assert not any("payment" in (e.source, e.target) for e in snap.edges)
    kpis = {n.node_id for n in snap.nodes if n.node_type == NodeType.TRANSACTION_KPI}
    assert kpis == {"kpi:frontend"}


def _pulse(n: int, at: list[int], shift: int = 0) -> np.ndarray:
    x = np.zeros(n)
    for i, k in enumerate(at):
        x[k + shift] = 3 + i
    return x


def test_causal_edges_lead_and_co_move_from_intensity() -> None:
    n = 40
    intensity = {
        "redis": _pulse(n, [8, 20, 31]),
        "cart": _pulse(n, [8, 20, 31], shift=2),  # follows redis by two buckets
        "kafka": _pulse(n, [8, 20, 31]),  # metric-only service, moves with redis
        "batch": _pulse(n, [1, 15, 26]),  # unrelated at every lag tried
    }
    snap = _build(
        intensity=intensity,
        service_modalities={"kafka": ["metrics"], "redis": ["metrics", "logs"]},
    )
    leads = {
        (e.source, e.target): e
        for e in snap.edges
        if e.edge_type == EdgeType.ANOMALY_LEADS
    }
    assert ("redis", "cart") in leads
    assert leads["redis", "cart"].lag_seconds == 2 * BUCKET_SECONDS
    assert leads["redis", "cart"].correlation == pytest.approx(1)
    co = _edges(snap, EdgeType.ANOMALY_CO_MOVES)
    assert {("kafka", "redis"), ("redis", "kafka")} <= set(co)
    assert not any("batch" in pair for pair in [*leads, *co])
    kafka = next(n for n in snap.nodes if n.node_id == "kafka")
    assert kafka.metadata["modalities"] == "metrics"
    assert "kafka" in snap.candidate_ids()
    redis = next(n for n in snap.nodes if n.node_id == "redis")
    assert redis.metadata["modalities"] == "logs,metrics,traces"


def test_flat_or_short_intensity_gives_no_causal_edges() -> None:
    snap = _build(intensity={"a": np.zeros(40), "b": np.zeros(40), "c": np.ones(4)})
    assert not any(e.edge_class == EdgeClass.CAUSAL for e in snap.edges)


def test_reasoning_steps_become_self_tenant_nodes() -> None:
    steps = [
        ReasoningStep("s1", "metric-agent", "check cart latency", "cart"),
        ReasoningStep("s2", "metric-agent", "summarise"),
    ]
    snap = _build(reasoning_steps=steps)
    ars = [n for n in snap.nodes if n.node_type == NodeType.AGENT_REASONING_STEP]
    assert [n.node_id for n in ars] == ["ars:s1", "ars:s2"]
    assert all(n.tenant == TENANT_SELF for n in ars)
    assert ars[0].metadata == {"order": "0", "text": "check cart latency"}
    assert _edges(snap, EdgeType.PRECEDES) == {("ars:s1", "ars:s2"): 1}
    assert _edges(snap, EdgeType.INVOKES) == {("ars:s1", "cart"): 1}
    assert "ars:s1" not in snap.candidate_ids()


def test_structural_off_keeps_the_other_classes() -> None:
    snap = UEGCBuilder(enable_structural=False).build(
        _shop_spans(),
        incident_id="inc",
        variant_config_hash=_HASH,
        captured_at_iso=_AT,
        parent_span_id_col_present=True,
    )
    classes = {e.edge_class for e in snap.edges}
    assert EdgeClass.STRUCTURAL not in classes
    assert {EdgeClass.BEHAVIOURAL, EdgeClass.ECONOMIC} <= classes


def test_snapshot_does_not_depend_on_span_order() -> None:
    forward = _build()
    backward = UEGCBuilder().build(
        list(reversed(_shop_spans())),
        incident_id="inc",
        variant_config_hash=_HASH,
        captured_at_iso=_AT,
        parent_span_id_col_present=True,
    )
    assert forward.compute_snapshot_hash() == backward.compute_snapshot_hash()


# -- end to end on a written window ------------------------------------------

START = "2026-10-25T10:00:00Z"
END = "2026-10-25T10:20:00Z"
T0 = 1_792_922_400  # START as epoch seconds


def _write_window(root: Path, phase: EvaluationPhase) -> TelemetryWindow:
    d = root / "w"
    d.mkdir()
    rows = []
    for t in range(0, 1200, 10):
        spike = 9 if 600 <= t < 660 else 1
        lagged = 9 if 660 <= t < 720 else 1
        rows += [
            (T0 + t, "cpu", spike + t % 3, {"service_name": "redis"}),
            (T0 + t, "cpu", lagged + t % 2, {"service_name": "cart"}),
            (T0 + t, "requests_total", t * 4, {"service_name": "kafka"}),
        ]
    pq.write_table(
        pa.table(
            {
                "timestamp": [float(r[0]) for r in rows],
                "metric_name": [r[1] for r in rows],
                "value": [float(r[2]) for r in rows],
                "labels": [json.dumps(r[3]) for r in rows],
            }
        ),
        d / "p1.parquet",
    )
    us = T0 * 1_000_000
    pq.write_table(
        pa.table(
            {
                "trace_id": ["t1", "t1", "t2"],
                "span_id": ["a", "b", "c"],
                "parent_span_id": ["", "a", ""],
                "service_name": ["frontend", "cart", "frontend"],
                "start_time_us": [us, us + 10, us + 5_000_000],
                "duration_us": [900, 500, 800],
            }
        ),
        d / "p2.parquet",
    )
    pq.write_table(
        pa.table(
            {
                "timestamp": ["2026-10-25T10:10:05Z", "2026-10-25T10:10:06Z"],
                "service_name": ["logger", "logger"],
                "body": ["disk 1 full", "disk 2 full"],
            }
        ),
        d / "p3.parquet",
    )
    return TelemetryWindow(
        incident_id="opaque",
        variant_config_hash=_HASH,
        window_start_iso=START,
        window_end_iso=END,
        evaluation_phase=phase,
        p1_metrics_path="w/p1.parquet",
        p2_traces_path="w/p2.parquet",
        p3_logs_path="w/p3.parquet",
    )


@pytest.fixture
def _full_manifest() -> None:
    set_current_manifest(get_variant("HELIOS-Full"))


@pytest.mark.usefixtures("_full_manifest")
def test_window_build_is_deterministic_and_uses_every_modality(
    tmp_path: Path,
) -> None:
    window = _write_window(tmp_path, EvaluationPhase.EXPLORATORY)
    first = build_ueg_c(window, _HASH, root=tmp_path)
    again = build_ueg_c(window, _HASH, root=tmp_path)
    assert first is not None and again is not None
    assert first.compute_snapshot_hash() == again.compute_snapshot_hash()
    assert first.captured_at_iso == END
    assert first.schema_version == "schema-draft-v0.2"
    modalities = {n.node_id: n.metadata.get("modalities") for n in first.nodes}
    assert modalities["kafka"] == "metrics"
    assert modalities["logger"] == "logs"
    assert modalities["cart"] == "metrics,traces"
    assert ("redis", "cart") in _edges(first, EdgeType.ANOMALY_LEADS)


@pytest.mark.usefixtures("_full_manifest")
def test_window_without_streams_gives_none(tmp_path: Path) -> None:
    window = TelemetryWindow(
        incident_id="x",
        variant_config_hash=_HASH,
        window_start_iso=START,
        window_end_iso=END,
        evaluation_phase=EvaluationPhase.EXPLORATORY,
    )
    assert build_ueg_c(window, _HASH, root=tmp_path) is None


@pytest.mark.usefixtures("_full_manifest")
def test_confirmatory_window_hits_the_pool_lock(tmp_path: Path) -> None:
    window = _write_window(tmp_path, EvaluationPhase.CONFIRMATORY)
    with pytest.raises(PoolLockedError):
        build_ueg_c(window, _HASH, root=tmp_path)


def test_builder_inputs_are_only_the_window_and_variant() -> None:
    # No labels, case names or injection time can reach the graph: the only
    # inputs are the window's own streams. Guard the signature.
    params = set(inspect.signature(build_ueg_c).parameters)
    assert params == {
        "window",
        "variant_config_hash",
        "root",
        "reasoning_steps",
    }
    assert VCLFlag.L2B_GRAPH in VCLFlag.bool_flags()
