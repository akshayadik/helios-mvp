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
    # No error status codes -> error_deltas should be zero or absent
    if "svc-a" in result.error_deltas:
        assert all(
            d == pytest.approx(0) or math.isnan(d) for d in result.error_deltas["svc-a"]
        )
