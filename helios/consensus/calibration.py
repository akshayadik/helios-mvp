"""Calibrated confidence, the floor and the state (S2.5 design §5.4; M-b, M-c, M-e).

IN2: the fused list carries P(root cause in its top 3), from observable
features of the fusion only: top-1 share, normalised entropy, fused sigma,
contributing pipelines, whether their top-1s agree. A logistic score of the
standardised features is mapped through isotonic regression (pool-adjacent-
violators) to a probability. The floor is the lowest confidence at which the
held-out cases of each corpus reach the target HR@3; the stricter corpus
wins; a corpus that cannot reach it gives no floor (stop and report, M-e).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING

import numpy as np
from scipy.optimize import minimize

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Sequence

    from helios.consensus.mahc import Fusion

__all__ = [
    "FLOOR_TARGET",
    "Calibrator",
    "State",
    "choose_floor",
    "features",
    "state",
]

HELIOS_ENABLE_MAHC_CALIBRATION: bool = True

FLOOR_TARGET: float = 0.8  # owner decision M-c
L2_STRENGTH: float = 1
_DIGITS = 6
_MIN_SCALE = 1e-6

Features = tuple[float, float, float, float]


class State(StrEnum):
    """What MAHC publishes."""

    CONFIRMED = "confirmed"
    PROVISIONAL = "provisional"
    NON_CONVERGED = "non_converged"


def features(f: Fusion) -> Features:
    """(top-1 share, entropy / log n, fused sigma, agree).

    The number of contributing pipelines is not a feature (entry 61): on build
    data three pipelines occur only on OTel, so it would stand for the dataset.
    """
    sigma = 1 if f.fused_sigma is None else f.fused_sigma
    agree = 1 if f.top1s_agree else 0
    total = sum(f.scores.values())
    if not f.ranked or total <= 0:
        return (0, 0, sigma, agree)
    p = [f.scores[s] / total for s in f.ranked]
    n = len(p)
    entropy = -sum(x * math.log(x) for x in p if x > 0) / math.log(n) if n > 1 else 0
    return (
        round(p[0], _DIGITS),
        round(entropy, _DIGITS),
        sigma,
        agree,
    )


def _pav(
    scores: Sequence[float], ys: Sequence[float]
) -> tuple[tuple[float, float], ...]:
    """Isotonic fit: equal scores pooled first, then pool-adjacent-violators.

    Returns (lowest score, value) per block, in increasing score.
    """
    groups: dict[float, list[float]] = {}
    for sc, y in zip(scores, ys, strict=True):
        g = groups.setdefault(sc, [0, 0])
        g[0] += y
        g[1] += 1
    blocks: list[list[float]] = []  # [start score, sum y, count]
    for sc in sorted(groups):
        blocks.append([sc, groups[sc][0], groups[sc][1]])
        while (
            len(blocks) > 1
            and blocks[-2][1] / blocks[-2][2] > blocks[-1][1] / blocks[-1][2]
        ):
            last = blocks.pop()
            blocks[-1][1] += last[1]
            blocks[-1][2] += last[2]
    return tuple((b[0], round(b[1] / b[2], _DIGITS)) for b in blocks)


@dataclass(frozen=True)
class Calibrator:
    """Logistic score of standardised features, then an isotonic step map."""

    coef: tuple[float, ...]
    intercept: float
    mean: tuple[float, ...]
    scale: tuple[float, ...]
    knots: tuple[tuple[float, float], ...]

    def _score(self, x: Sequence[float]) -> float:
        z = (np.asarray(x, dtype=float) - np.asarray(self.mean)) / np.asarray(
            self.scale
        )
        return float(z @ np.asarray(self.coef) + self.intercept)

    def predict(self, x: Sequence[float]) -> float:
        """P(root in fused top 3): the value of the last knot at or below the score."""
        s = round(self._score(x), _DIGITS)
        value = self.knots[0][1]
        for start, v in self.knots:
            if start <= s:
                value = v
            else:
                break
        return value

    @classmethod
    def fit(cls, xs: Sequence[Sequence[float]], ys: Sequence[int]) -> Calibrator:
        """Deterministic fit: L-BFGS-B from zero, then pool-adjacent-violators."""
        x = np.asarray(xs, dtype=float)
        y = np.asarray(ys, dtype=float)
        mean = x.mean(axis=0)
        scale = x.std(axis=0)
        scale[scale < _MIN_SCALE] = 1  # a constant column (float noise, not exactly 0)
        z = (x - mean) / scale

        def loss(w: np.ndarray) -> tuple[float, np.ndarray]:
            margin = z @ w[:-1] + w[-1]
            p = 1 / (1 + np.exp(-margin))
            value = np.logaddexp(0, margin).mean() - (y * margin).mean()
            value += L2_STRENGTH * (w[:-1] @ w[:-1]) / 2
            grad_w = z.T @ (p - y) / len(y) + L2_STRENGTH * w[:-1]
            grad_b = (p - y).mean()
            return float(value), np.append(grad_w, grad_b)

        result = minimize(loss, np.zeros(z.shape[1] + 1), jac=True, method="L-BFGS-B")
        w = result.x
        draft = cls(
            coef=tuple(round(float(v), _DIGITS) for v in w[:-1]),
            intercept=round(float(w[-1]), _DIGITS),
            mean=tuple(round(float(v), _DIGITS) for v in mean),
            scale=tuple(round(float(v), _DIGITS) for v in scale),
            knots=((0, 0),),
        )
        # Knots on exactly the score predict computes (rounded parameters).
        scores = [round(draft._score(row), _DIGITS) for row in x]
        return replace(draft, knots=_pav(scores, list(y)))


def choose_floor(
    conf: Sequence[float],
    hit: Sequence[int],
    corpus: Sequence[str],
    target: float = FLOOR_TARGET,
) -> float | None:
    """The stricter corpus's lowest c with mean hit >= target over conf >= c."""
    floors = []
    for name in sorted(set(corpus)):
        pairs = [(c, h) for c, h, k in zip(conf, hit, corpus, strict=True) if k == name]
        found = None
        for c in sorted({c for c, _ in pairs}):
            kept = [h for v, h in pairs if v >= c]
            if sum(kept) / len(kept) >= target:
                found = c
                break
        if found is None:
            return None
        floors.append(found)
    return max(floors) if floors else None


def state(conf: float | None, floor: float | None, *, all_in: bool) -> State:
    """CONFIRMED only with every pipeline in and the confidence at or above the floor."""
    if not all_in or conf is None or floor is None:
        return State.PROVISIONAL
    return State.CONFIRMED if conf >= floor else State.PROVISIONAL
