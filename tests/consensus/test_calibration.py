"""Calibrated confidence, the floor and the state (S2.5 §5.4; M-b, M-c, M-e)."""

from __future__ import annotations

import math
from itertools import pairwise

import pytest

from helios.consensus.calibration import (
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
    share, entropy, sigma, n, agree = features(_fusion({"a": 3, "b": 1}, 0.2))
    assert share == pytest.approx(0.75)
    p = (0.75, 0.25)
    assert entropy == pytest.approx(-sum(x * math.log(x) for x in p) / math.log(2))
    assert (sigma, n, agree) == (0.2, 2, 1)


def test_features_single_candidate_and_empty() -> None:
    assert features(_fusion({"a": 1}, None))[:3] == (1, 0, 1)
    empty = Fusion((), {}, {}, None, (), True)
    assert features(empty) == (0, 0, 1, 0, 1)


def _toy() -> tuple[list[tuple[float, ...]], list[int]]:
    xs: list[tuple[float, ...]] = []
    for s in range(1, 10):
        xs.append((s / 10, 1 - s / 10, 0.2, float(2), float(1)))
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
