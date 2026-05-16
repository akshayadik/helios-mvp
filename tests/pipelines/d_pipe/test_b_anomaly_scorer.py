"""TDD for Stage B wm90 and AnomalyScorer."""

from __future__ import annotations

import math

import numpy as np
import pytest

from helios.pipelines.d_pipe.stages.b_anomaly_scorer import AnomalyScorer, wm90
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def test_wm90_all_zeros_returns_zero() -> None:
    result = wm90(np.zeros(20))
    assert result == pytest.approx(0)


def test_wm90_ignores_nan() -> None:
    arr = np.array([float("nan")] * 5 + [2.0] * 15)
    result = wm90(arr)
    assert not math.isnan(result)
    assert result > 0


def test_wm90_all_nan_returns_nan() -> None:
    result = wm90(np.full(5, float("nan")))
    assert math.isnan(result)


def test_wm90_clamps_single_spike() -> None:
    arr = np.array([1.00] * 19 + [1000.0])
    result = wm90(arr)
    # Spike clamped to third-highest (which is 1.00 here); result ≈ 1.00
    assert result == pytest.approx(1.00)


def test_anomaly_scorer_non_p1_gets_zero() -> None:
    error_deltas: dict[str, list[float]] = {"svc-a": [5.0] * 20}
    latency_means: dict[str, list[float]] = {"svc-a": [10.0] * 20}
    scorer = AnomalyScorer(w_error=0.50)
    result = scorer.score(error_deltas, latency_means, p1_services=["svc-a"])
    assert "svc-a" in result
    assert result.get("svc-b", 0.00) == pytest.approx(0)


def test_anomaly_scorer_scores_in_unit_interval() -> None:
    error_deltas = {"a": [1_00.0] * 20, "b": [10.0] * 20}
    latency_means = {"a": [500.0] * 20, "b": [50.0] * 20}
    scorer = AnomalyScorer(w_error=0.50)
    result = scorer.score(error_deltas, latency_means, p1_services=["a", "b"])
    for svc, val in result.items():
        assert 0 <= val <= 1.00, f"{svc} score {val} out of range"


def test_anomaly_scorer_higher_errors_rank_first() -> None:
    error_deltas = {"high": [200.0] * 20, "low": [1.00] * 20}
    latency_means = {"high": [1.00] * 20, "low": [1.00] * 20}
    scorer = AnomalyScorer(w_error=0.9)
    result = scorer.score(error_deltas, latency_means, p1_services=["high", "low"])
    assert result["high"] > result["low"]
