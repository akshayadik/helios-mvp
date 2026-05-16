"""TDD for Stage D DVerdict."""

from __future__ import annotations

import math

import pytest

from helios.pipelines.d_pipe.stages.d_verdict import DVerdict


def test_ground_truth_ranked_first_gives_hr_and_cpr_one() -> None:
    scores = {"svc-a": 0.9, "svc-b": 0.50, "svc-c": 0.3}
    result = DVerdict.compute(scores, ground_truth_service="svc-a")
    assert result["hr_at_3"] == 1
    assert result["cpr"] == pytest.approx(1)


def test_ground_truth_ranked_second_gives_half_cpr() -> None:
    scores = {"svc-a": 0.9, "svc-b": 0.8, "svc-c": 0.3}
    result = DVerdict.compute(scores, ground_truth_service="svc-b")
    assert result["hr_at_3"] == 1
    assert result["cpr"] == pytest.approx(1 / 2)


def test_ground_truth_outside_top_3_gives_hr_zero() -> None:
    scores = {"a": 0.9, "b": 0.8, "c": 0.7, "d": 0.2}
    result = DVerdict.compute(scores, ground_truth_service="d")
    assert result["hr_at_3"] == 0
    assert result["cpr"] == pytest.approx(1 / 4)


def test_alphabetic_tiebreak_is_deterministic() -> None:
    scores = {"bravo": 0.50, "alpha": 0.50}
    r1 = DVerdict.compute(scores)
    r2 = DVerdict.compute(scores)
    assert r1["ranked_candidates"] == r2["ranked_candidates"]
    assert r1["ranked_candidates"][0] == "alpha"  # alphabetically first


def test_no_ground_truth_returns_nan_cpr() -> None:
    result = DVerdict.compute({"x": 0.50})
    assert math.isnan(result["cpr"])
    assert result["hr_at_3"] == 0


def test_ranked_candidates_limited_to_three() -> None:
    scores = {c: float(i) for i, c in enumerate("abcdefg")}
    result = DVerdict.compute(scores)
    assert len(result["ranked_candidates"]) == 3
