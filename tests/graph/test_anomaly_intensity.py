"""Per-service anomaly intensity (S1.5) and the pruner/G-pipe changes for v0.2 graphs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from helios.graph.anomaly_intensity import (
    bucket_count,
    combine,
    log_intensity,
    metric_intensity,
    robust_z,
    service_of,
)
from helios.graph.ppr_pruner import prune_graph
from helios.pipelines.g_pipe.pipeline import _ppr_traverse
from helios.schemas.ueg_c import (
    TENANT_SELF,
    EdgeType,
    NodeType,
    UEGCEdge,
    UEGCNode,
    UEGCSnapshot,
)
from helios.telemetry.log_templates import extract_templates
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Sequence

START = "2026-10-25T10:00:00Z"
T0 = 1_792_922_400


def test_bucket_count_covers_the_window() -> None:
    assert bucket_count(START, "2026-10-25T10:20:00Z", 30) == 40
    assert bucket_count(START, "2026-10-25T10:20:01Z", 30) == 41
    assert bucket_count(START, START, 30) == 1


def test_robust_z_uses_mad_then_std_then_zero() -> None:
    z = robust_z(np.array([1, 1, 1, 1, 9, np.nan], dtype="float64"))
    assert np.isnan(z[-1])
    assert z[4] > z[0] >= 0  # MAD is zero here, so std is the scale
    assert robust_z(np.array([2, 2, 2], dtype="float64")).tolist() == [0, 0, 0]
    assert np.isnan(robust_z(np.array([np.nan, np.nan]))).all()


def test_service_of_prefers_service_name_then_job() -> None:
    assert service_of({"service_name": "cart", "job": "x/y"}) == "cart"
    assert service_of({"job": "opentelemetry-demo/adservice"}) == "adservice"
    assert service_of({}) == ""


def _metrics(rows: Sequence[tuple[int, str, float, dict[str, str]]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [float(T0 + r[0]) for r in rows],
            "metric_name": [r[1] for r in rows],
            "value": [r[2] for r in rows],
            "labels": [json.dumps(r[3]) for r in rows],
        }
    )


def test_metric_intensity_peaks_where_a_series_departs() -> None:
    rows = [
        (t, "cpu", 9 if t == 300 else 1 + t % 2, {"service_name": "a"})
        for t in range(0, 600, 30)
    ]
    out = metric_intensity(_metrics(rows), START, 20, 30)
    assert set(out) == {"a"}
    assert int(np.argmax(out["a"])) == 10


def test_counters_are_differenced_before_scoring() -> None:
    steady = [
        (t, "req_total", float(t * 5), {"service_name": "a"}) for t in range(0, 600, 30)
    ]
    out = metric_intensity(_metrics(steady), START, 20, 30)
    # A steadily rising counter has a constant rate: no anomaly anywhere.
    assert float(np.max(out["a"])) == 0


def test_metric_rows_outside_the_window_or_without_service_are_ignored() -> None:
    rows = [
        (-60, "cpu", 5, {"service_name": "a"}),
        (30, "cpu", 5, {"pod": "x"}),
        (30, "cpu", float("nan"), {"service_name": "b"}),
    ]
    assert metric_intensity(_metrics(rows), START, 20, 30) == {}
    assert metric_intensity(_metrics([]).iloc[0:0], START, 20, 30) == {}


def test_log_intensity_uses_line_counts_and_novelty() -> None:
    rows = [
        (f"2026-10-25T10:0{m}:05Z", "cart", "GET /cart took 3 ms") for m in range(6)
    ]
    rows += [
        (f"2026-10-25T10:04:{s:02d}Z", "cart", f"connection {s} refused")
        for s in range(10, 40)
    ]
    logs = pd.DataFrame(rows, columns=["timestamp", "service_name", "body"])
    features = extract_templates(logs, START, bucket_seconds=30)
    out = log_intensity(features, START, 20, 30)
    assert set(out) == {"cart"}
    assert int(np.argmax(out["cart"])) == 8  # 10:04:00 bucket
    empty = extract_templates(logs.iloc[0:0], START)
    assert log_intensity(empty, START, 20, 30) == {}


def test_combine_takes_the_bucket_wise_max() -> None:
    a = {"x": np.array([1, 5, 2], dtype="float64")}
    b = {
        "x": np.array([3, 1, 2], dtype="float64"),
        "y": np.array([7, 7, 7], dtype="float64"),
    }
    out = combine(a, b)
    assert out["x"].tolist() == [3, 5, 2]
    assert out["y"].tolist() == [7, 7, 7]
    assert combine() == {}


# -- pruner and G-pipe on v0.2 graphs ----------------------------------------


def _node(nid: str, kind: NodeType = NodeType.SERVICE, **kw: object) -> UEGCNode:
    return UEGCNode(node_id=nid, node_type=kind, service_name=kw.pop("svc", nid), **kw)


def _graph() -> UEGCSnapshot:
    nodes = [
        _node("frontend", metadata={"modalities": "traces"}),
        _node("cart", metadata={"modalities": "metrics,traces"}),
        _node("kafka", metadata={"modalities": "metrics"}),
        _node("kpi:frontend", NodeType.TRANSACTION_KPI, svc="frontend"),
        _node("ars:s1", NodeType.AGENT_REASONING_STEP, svc="agent", tenant=TENANT_SELF),
    ]
    edges = [
        UEGCEdge(
            source="frontend", target="cart", edge_type=EdgeType.STRUCTURAL, weight=1
        ),
        UEGCEdge(source="frontend", target="cart", edge_type=EdgeType.CALL, weight=1),
        UEGCEdge(
            source="kafka", target="cart", edge_type=EdgeType.ANOMALY_LEADS, weight=0.9
        ),
        UEGCEdge(
            source="cart",
            target="kpi:frontend",
            edge_type=EdgeType.SERVES_KPI,
            weight=1,
        ),
        UEGCEdge(source="ars:s1", target="cart", edge_type=EdgeType.INVOKES, weight=1),
    ]
    return UEGCSnapshot(
        incident_id="inc",
        variant_config_hash="h",
        nodes=nodes,
        edges=edges,
        captured_at_iso="2026-10-25T10:20:00Z",
    )


def test_pruner_keeps_traceless_services_kpis_and_self_tenant_nodes() -> None:
    pruned, result = prune_graph(_graph(), pruner_threshold=0.2)
    kept = {n.node_id for n in pruned.nodes}
    assert {"frontend", "cart", "kafka", "kpi:frontend", "ars:s1"} == kept
    assert result.nodes_after == len(kept)
    assert any(e.edge_type == EdgeType.ANOMALY_LEADS for e in pruned.edges)


def test_gpipe_ranks_only_production_services() -> None:
    ranked, scores = _ppr_traverse(_graph(), {"kafka": 1})
    assert set(ranked) == {"frontend", "cart", "kafka"}
    assert set(scores) == set(ranked)
    assert ranked[0] in {"cart", "kafka"}
