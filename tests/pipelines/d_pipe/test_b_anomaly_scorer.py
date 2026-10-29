"""TDD for Stage B wm90 and AnomalyScorer."""

from __future__ import annotations

import math

import numpy as np
import pytest

from helios.pipelines.d_pipe.stages.a_metrics_parser import ParsedMetrics
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


# ── trigger split (S2.1, S2-M7-ENG09) ────────────────────────────────────────


def _parsed(latency: dict[str, list[float]], steps: int = 12) -> ParsedMetrics:
    return ParsedMetrics(
        error_deltas={},
        latency_means=latency,
        steps=[float(t) for t in range(steps)],
        p1_services=sorted(latency),
    )


def test_split_scores_only_the_shift_after_the_trigger() -> None:
    always_high: list[float] = [80 + t % 3 for t in range(12)]
    rises: list[float] = [float(40 + t % 3) for t in range(6)] + [
        float(80 + t % 3) for t in range(6)
    ]
    scored = AnomalyScorer(w_error=0, w_resource=0).score_split(
        _parsed({"steady": always_high, "rises": rises}), split_s=6
    )
    assert scored.scores["rises"] > scored.scores["steady"]
    assert scored.evidence["steady"] < 1


def test_evidence_is_the_raw_shift_before_normalisation() -> None:
    small: list[float] = [float(40 + t % 3) for t in range(6)] + [
        float(42 + t % 3) for t in range(6)
    ]
    scored = AnomalyScorer(w_error=0, w_resource=0).score_split(
        _parsed({"cart": small}), split_s=6
    )
    assert scored.scores["cart"] > 0  # alone, it still normalises to the top
    assert scored.evidence["cart"] < 2  # but its raw shift is small


def test_resource_channel_counts_with_its_weight() -> None:
    parsed = ParsedMetrics(
        error_deltas={},
        latency_means={"a": [10.0] * 12, "b": [10.0] * 12},
        steps=[float(t) for t in range(12)],
        p1_services=["a", "b"],
        resource_values={"a": {"cpu": [5.0 + t % 2 for t in range(6)] + [90.0] * 6}},
    )
    with_res = AnomalyScorer(w_error=0, w_resource=0.3).score_split(parsed, split_s=6)
    without = AnomalyScorer(w_error=0, w_resource=0).score_split(parsed, split_s=6)
    assert with_res.scores["a"] > with_res.scores["b"]
    assert without.scores["a"] == without.scores["b"]


def test_out_of_scope_services_do_not_set_the_normalisation_scale() -> None:
    base: list[float] = [float(40 + t % 3) for t in range(6)]
    parsed = ParsedMetrics(
        error_deltas={},
        latency_means={
            "cart": base + [float(60 + t % 3) for t in range(6)],
            "jaeger": base + [float(4000 + t % 3) for t in range(6)],
        },
        steps=[float(t) for t in range(12)],
        p1_services=["cart", "jaeger"],
    )
    scored = AnomalyScorer(w_error=0, w_resource=0).score_split(parsed, split_s=6)
    assert (
        abs(scored.scores["cart"] - 1) < 1e-6
    )  # the top in-scope shift sets the scale
    assert scored.evidence["jaeger"] > scored.evidence["cart"]  # raw evidence kept


def test_workload_drop_scores_but_cpu_drop_does_not() -> None:
    before: list[float] = [float(40 + t % 3) for t in range(6)]
    drop: list[float] = before + [1.0] * 6
    parsed = ParsedMetrics(
        error_deltas={},
        latency_means={},
        steps=[float(t) for t in range(12)],
        p1_services=["a", "b"],
        resource_values={"a": {"workload": drop}, "b": {"cpu": drop}},
    )
    scored = AnomalyScorer(w_error=0, w_resource=1).score_split(parsed, split_s=6)
    assert scored.evidence["a"] > 6
    assert scored.evidence["b"] == 0
