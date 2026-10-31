"""Calibrated confidence, the floor and the state (S2.5 §5.4; M-b, M-c, M-e)."""

from __future__ import annotations

import math
from itertools import pairwise

import pytest

from helios.consensus.calibration import (
    MIN_BLOCK,
    Calibrator,
    State,
    choose_floor,
    features,
    state,
)
from helios.consensus.mahc import Fusion
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def _fusion(
    scores: dict[str, float], sigma: float | None, agree: bool = True
) -> Fusion:
    ranked = tuple(sorted(scores, key=lambda s: (-scores[s], s)))
    return Fusion(ranked, scores, {"dpipe": 1}, sigma, ("dpipe", "gpipe"), agree)


def test_features_two_candidates() -> None:
    share, entropy, sigma, agree = features(_fusion({"a": 3, "b": 1}, 0.2))
    assert share == pytest.approx(0.75)
    p = (0.75, 0.25)
    assert entropy == pytest.approx(-sum(x * math.log(x) for x in p) / math.log(2))
    assert (sigma, agree) == (0.2, 1)


def test_features_single_candidate_and_empty() -> None:
    assert features(_fusion({"a": 1}, None))[:3] == (1, 0, 1)
    empty = Fusion((), {}, {}, None, (), True)
    assert features(empty) == (0, 0, 1, 1)


def _toy() -> tuple[list[tuple[float, ...]], list[int]]:
    xs: list[tuple[float, ...]] = []
    for s in range(1, 10):
        xs.append((s / 10, 1 - s / 10, 0.2, float(1)))
    xs = xs * 4
    ys = [1 if x[0] > 0.45 else 0 for x in xs]
    return xs, ys


def test_isotonic_is_monotone_in_the_score() -> None:
    xs, ys = _toy()
    cal = Calibrator.fit(xs, ys)
    preds = [cal.predict(x) for x in sorted(xs, key=lambda x: x[0])]
    assert all(a <= b + 1e-12 for a, b in pairwise(preds))
    assert min(preds) >= 0 and max(preds) <= 1


def test_fit_deterministic() -> None:
    xs, ys = _toy()
    assert Calibrator.fit(xs, ys) == Calibrator.fit(xs, ys)


def test_floor_exact_is_the_stricter_corpus() -> None:
    conf = [0.9, 0.8, 0.7, 0.6, 0.95, 0.85, 0.75]
    hit = [1, 1, 1, 0, 1, 0, 1]
    corpus = ["a"] * 4 + ["b"] * 3
    assert choose_floor(conf, hit, corpus) == pytest.approx(0.95)


def test_floor_none_when_a_corpus_cannot_reach_target() -> None:
    assert choose_floor([0.9, 0.8, 0.7], [1, 0, 0], ["a", "b", "b"]) is None


def test_floor_with_tied_confidences() -> None:
    assert choose_floor([0.6] * 5, [1, 1, 1, 1, 0], ["a"] * 5) == pytest.approx(0.6)
    assert choose_floor([0.6] * 5, [1, 1, 1, 0, 0], ["a"] * 5) is None


def test_state_rules() -> None:
    assert state(0.9, 0.8, all_in=True) == State.CONFIRMED
    assert state(0.8, 0.8, all_in=True) == State.CONFIRMED
    assert state(0.7, 0.8, all_in=True) == State.PROVISIONAL
    assert state(0.9, 0.8, all_in=False) == State.PROVISIONAL
    assert state(None, 0.8, all_in=True) == State.PROVISIONAL
    assert state(0.9, None, all_in=True) == State.PROVISIONAL


def test_tied_scores_are_pooled() -> None:
    # Review I1: tied groups keep their own rate; groups of 25 (>= MIN_BLOCK).
    a = (0.9, 0.1, 0.2, float(1))
    b = (0.6, 0.6, 0.5 + 0.2, float(0))
    xs = [a] * 25 + [b] * 25
    ys = [1] * 20 + [0] * 5 + [1] * 10 + [0] * 15
    cal = Calibrator.fit(xs, ys)
    assert cal.predict(a) == pytest.approx(0.8)
    assert cal.predict(b) == pytest.approx(0.4)


def test_l2_is_relative_to_the_summed_loss() -> None:
    # Entry 62: L2 strength 1 on the summed log-loss; a clear signal keeps its weight.
    xs = [(s / 100, 0.5 + 0.1, 0.2, float(1)) for s in range(200)]
    ys = [1 if x[0] >= 1 else 0 for x in xs]
    assert abs(Calibrator.fit(xs, ys).coef[0]) > 1


def test_isotonic_blocks_hold_at_least_min_block_cases() -> None:
    # Entry 62: a lone extreme miss cannot make a step of value 0.
    xs = [(s / 100, 0.6, 0.2, float(1)) for s in range(100)]
    ys = [0] + [1] * 99
    cal = Calibrator.fit(xs, ys)
    assert len(cal.knots) <= 100 // MIN_BLOCK
    assert cal.predict((-5.0 + 4, 0.6, 0.2, float(1))) >= 0.9


def test_training_points_predict_their_own_block() -> None:
    xs, ys = _toy()
    cal = Calibrator.fit(xs, ys)
    once = [cal.predict(x) for x in xs]
    assert once == [cal.predict(x) for x in xs]
    assert all(0 <= p <= 1 for p in once)


def test_features_do_not_count_pipelines() -> None:
    # Entry 61: the pipeline count is a dataset proxy on build data (3 only on OTel).
    two = Fusion(("a", "b"), {"a": 3, "b": 1}, {}, 0.2, ("dpipe", "lpipe"), True)
    three = Fusion(
        ("a", "b"), {"a": 3, "b": 1}, {}, 0.2, ("dpipe", "gpipe", "lpipe"), True
    )
    assert features(two) == features(three)
    assert len(features(two)) == 4
