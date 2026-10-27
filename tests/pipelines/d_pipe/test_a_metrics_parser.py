"""TDD for Stage A MetricsParser."""

from __future__ import annotations

import json
import math

import pandas as pd
import pytest

from helios.pipelines.d_pipe.stages.a_metrics_parser import MetricsParser, ParsedMetrics
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance for test module


def _make_http_row(
    ts: float, svc: str, status: str, le: str, value: float
) -> dict[str, object]:
    labels = json.dumps(
        {"job": svc, "http_response_status_code": status, "le": le}, sort_keys=True
    )
    return {
        "timestamp": ts,
        "metric_name": "http_server_duration_milliseconds_bucket",
        "value": value,
        "labels": labels,
    }


def _make_df(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_parsed_metrics_has_expected_fields() -> None:
    rows = [_make_http_row(1.00, "svc-a", "200", "+Inf", 10.0)]
    df = _make_df(rows)
    result = MetricsParser().parse(df)
    assert isinstance(result, ParsedMetrics)
    assert hasattr(result, "error_deltas")
    assert hasattr(result, "latency_means")
    assert hasattr(result, "steps")
    assert hasattr(result, "p1_services")


def test_error_delta_single_step() -> None:
    # t=1: cumulative count=5; t=2: count=8 -> delta=3
    rows = [
        _make_http_row(1.00, "svc-a", "500", "+Inf", 5.0),
        _make_http_row(2.0, "svc-a", "500", "+Inf", 8.0),
    ]
    df = _make_df(rows)
    result = MetricsParser().parse(df)
    assert "svc-a" in result.error_deltas
    deltas = [d for d in result.error_deltas["svc-a"] if not math.isnan(d)]
    assert len(deltas) == 1
    assert deltas[0] == pytest.approx(3.0)


def test_counter_reset_produces_nan() -> None:
    # Counter goes down at t=2 -- should produce NaN
    rows = [
        _make_http_row(1.00, "svc-a", "500", "+Inf", 10.0),
        _make_http_row(2.0, "svc-a", "500", "+Inf", 3.0),
        _make_http_row(3.0, "svc-a", "500", "+Inf", 6.0),
    ]
    df = _make_df(rows)
    result = MetricsParser().parse(df)
    assert math.isnan(result.error_deltas["svc-a"][0])  # t=2 reset
    assert result.error_deltas["svc-a"][1] == pytest.approx(3.0)  # t=3: 6-3=3


def test_non_error_status_not_counted() -> None:
    rows = [
        _make_http_row(1.00, "svc-a", "200", "+Inf", 5.0),
        _make_http_row(2.0, "svc-a", "200", "+Inf", 10.0),
    ]
    df = _make_df(rows)
    result = MetricsParser().parse(df)
    # No error status codes -> error_deltas should not include svc-a
    assert "svc-a" not in result.error_deltas


# ── format-neutral parsing (S2.1, S2-M7-ENG09) ──────────────────────────────


def _plain(ts: float, svc: str, metric: str, value: float) -> dict[str, object]:
    return {
        "timestamp": ts,
        "metric_name": metric,
        "value": value,
        "labels": json.dumps({"service_name": svc}),
    }


def test_rcaeval_metrics_give_services() -> None:
    rows = [
        _plain(t, svc, m, v)
        for t in (1, 2, 3)
        for svc in ("cart", "ad")
        for m, v in (
            ("latency-90", 40 + t),
            ("latency-50", 9),
            ("error", t),
            ("cpu", 7),
        )
    ]
    parsed = MetricsParser().parse(_make_df(rows))
    assert parsed.p1_services == ["ad", "cart"]
    assert parsed.steps == [2, 3]
    assert parsed.latency_means["cart"] == [42, 43]  # latency-90 wins
    assert parsed.error_deltas["cart"] == [2, 3]  # per-step values, not differenced
    assert parsed.resource_values["cart"] == {"cpu": [7, 7]}


def test_latency_falls_back_to_median_then_plain() -> None:
    rows = [_plain(t, "cart", "latency-50", 11) for t in (1, 2)] + [
        _plain(t, "ad", "latency", 13) for t in (1, 2)
    ]
    parsed = MetricsParser().parse(_make_df(rows))
    assert parsed.latency_means == {"ad": [13], "cart": [11]}


def test_otel_container_metrics_fill_resource_channel() -> None:
    rows = [
        _plain(t, "cart", "container_cpu_utilization_ratio", 3) for t in (1, 2, 3)
    ] + [_plain(t, "cart", "container_memory_usage_total_bytes", 64) for t in (1, 2, 3)]
    parsed = MetricsParser().parse(_make_df(rows))
    assert parsed.resource_values["cart"] == {
        "container_cpu_utilization_ratio": [3, 3],
        "container_memory_usage_total_bytes": [64, 64],
    }
    assert parsed.p1_services == ["cart"]


def test_otel_histogram_parsing_unchanged_with_resource_rows_present() -> None:
    hist = [
        _make_http_row(1, "svc-a", "500", "+Inf", 5),
        _make_http_row(2, "svc-a", "500", "+Inf", 8),
    ]
    alone = MetricsParser().parse(_make_df(hist))
    mixed = MetricsParser().parse(
        _make_df(
            hist
            + [_plain(t, "svc-a", "container_cpu_utilization_ratio", 2) for t in (1, 2)]
        )
    )
    assert mixed.error_deltas == alone.error_deltas
    assert mixed.steps == alone.steps
    assert mixed.resource_values == {"svc-a": {"container_cpu_utilization_ratio": [2]}}
