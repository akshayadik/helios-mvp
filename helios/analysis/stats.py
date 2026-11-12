"""Statistical tests, multiplicity and effect sizes for the analysis suite (S4.11).

Every test is one-sided in the registered direction: the differences passed in
are a - b, and the alternative is "a greater" (pre-registration §5). Rules are
those of the S4.11 design note (docs/sprints/s4-product-eval-tooling/
s4_11_analysis_design.md, T-a to T-f):

- Wilcoxon signed-rank: zeros dropped, ties get midranks, exact conditional
  null distribution over all sign patterns (T-b).
- Sign test and McNemar mid-p: exact binomial with rational arithmetic (T-e).
- Holm step-down in data order (standard) and in the registered rank order
  (fixed sequence); untestable hypotheses count as not rejected and are never
  dropped (T-a). Benjamini-Hochberg as a sensitivity row.
- BCa with the hypothesis' registered seed; Cliff's delta; Hodges-Lehmann;
  Cohen's h (T-f).
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING

import numpy as np
from scipy import stats as sps

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "BCA_CONFIDENCE",
    "BCA_RESAMPLES",
    "BcaInterval",
    "MultiplicityRow",
    "TestResult",
    "bca_mean",
    "benjamini_hochberg",
    "cliffs_delta",
    "cohens_h",
    "hodges_lehmann",
    "holm_fixed_sequence",
    "holm_step_down",
    "mcnemar_mid_p",
    "paired_t",
    "sign_test",
    "wilcoxon_exact",
]

HELIOS_ENABLE_ANALYSIS_STATS: bool = True

BCA_RESAMPLES = 10_000
BCA_CONFIDENCE = 0.95
_HALF = Fraction(1, 2)
_P_MAX = 1  # p-value of a tested hypothesis with no informative pair


@dataclass(frozen=True)
class TestResult:
    """One one-sided test: statistic, p-value and the pairs it used."""

    __test__ = False  # not a pytest class

    test: str
    statistic: float
    p_value: float
    n_pairs: int
    n_informative: int  # non-zero differences (Wilcoxon, sign) or discordant pairs


def _nonzero(diffs: Sequence[float]) -> np.ndarray:
    d = np.asarray(diffs, dtype=float)
    if not np.all(np.isfinite(d)):
        raise ValueError("differences must be finite")
    out: np.ndarray = d[d != 0]
    return out


def wilcoxon_exact(diffs: Sequence[float]) -> TestResult:
    """One-sided signed-rank test (a > b), exact under ties (T-b).

    The statistic is T+ = sum of the midranks of the positive differences.
    Midranks are doubled so every rank is an integer; the null distribution of
    2 T+ is built by convolution over the sign of each difference.
    """
    nz = _nonzero(diffs)
    n = len(nz)
    if n == 0:
        return TestResult("wilcoxon_signed_rank", 0, _P_MAX, len(diffs), 0)
    doubled = np.rint(2 * sps.rankdata(np.abs(nz))).astype(np.int64)
    observed = int(doubled[nz > 0].sum())
    dist = np.zeros(int(doubled.sum()) + 1)
    dist[0] = 1
    for r in doubled:
        shifted = np.zeros_like(dist)
        shifted[r:] = dist[: len(dist) - r]
        dist = (dist + shifted) / 2
    p = float(min(dist[observed:].sum(), _P_MAX))
    return TestResult("wilcoxon_signed_rank", observed / 2, p, len(diffs), n)


def _binomial_upper(k: int, n: int, *, mid: bool) -> Fraction:
    """P(X >= k) for X ~ Binomial(n, 1/2); with ``mid``, P(X > k) + P(X = k) / 2."""
    total = Fraction(sum(math.comb(n, j) for j in range(k, n + 1)), 2**n)
    if mid:
        total -= _HALF * Fraction(math.comb(n, k), 2**n)
    return total


def sign_test(diffs: Sequence[float]) -> TestResult:
    """Exact one-sided sign test (a > b); zeros dropped."""
    nz = _nonzero(diffs)
    n = len(nz)
    positive = int((nz > 0).sum())
    if n == 0:
        return TestResult("sign_test", 0, _P_MAX, len(diffs), 0)
    p = float(_binomial_upper(positive, n, mid=False))
    return TestResult("sign_test", positive, p, len(diffs), n)


def mcnemar_mid_p(hits_a: Sequence[int], hits_b: Sequence[int]) -> TestResult:
    """One-sided McNemar exact mid-p on paired 0/1 outcomes (a better), T-e.

    b = a hits and b misses, c = the reverse, n = b + c; the mid-p is
    P(X > b) + P(X = b) / 2 with X ~ Binomial(n, 1/2).
    """
    if len(hits_a) != len(hits_b):
        raise ValueError("paired outcomes must have equal length")
    pairs = list(zip(hits_a, hits_b, strict=True))
    if any(x not in (0, 1) or y not in (0, 1) for x, y in pairs):
        raise ValueError("McNemar needs 0/1 outcomes")
    b = sum(1 for x, y in pairs if x == 1 and y == 0)
    c = sum(1 for x, y in pairs if x == 0 and y == 1)
    n = b + c
    if n == 0:
        return TestResult("mcnemar_exact_mid_p", 0, _P_MAX, len(pairs), 0)
    p = float(_binomial_upper(b, n, mid=True))
    return TestResult("mcnemar_exact_mid_p", b, p, len(pairs), n)


def paired_t(diffs: Sequence[float]) -> TestResult:
    """One-sided paired t-test on the differences (sensitivity, T-g)."""
    d = np.asarray(diffs, dtype=float)
    if len(d) < 2 or float(np.std(d)) == 0:
        return TestResult("paired_t", 0, _P_MAX, len(d), len(d))
    res = sps.ttest_1samp(d, 0, alternative="greater")
    return TestResult(
        "paired_t", float(res.statistic), float(res.pvalue), len(d), len(d)
    )


# ── multiplicity ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MultiplicityRow:
    """One hypothesis in a family after correction."""

    hypothesis_id: str
    rank: int
    p_value: float | None  # None = untestable
    threshold: float | None  # the alpha it was compared with
    adjusted_p: float | None
    rejected: bool


def holm_step_down(
    p_values: Mapping[str, float | None],
    ranks: Mapping[str, int],
    alpha: float,
) -> list[MultiplicityRow]:
    """Standard Holm (T-a reading a): walk the p-values in ascending order.

    The k-th smallest is compared with alpha / (m - k + 1); the walk stops at
    the first failure. Ties go by registered rank. Untestable hypotheses (None)
    sort last, are never rejected and still count in m.
    """
    m = len(p_values)
    order = sorted(
        p_values,
        key=lambda h: (p_values[h] is None, p_values[h] or 0, ranks[h]),
    )
    rows: list[MultiplicityRow] = []
    running = float(0)
    stopped = False
    for k, h in enumerate(order, start=1):
        p = p_values[h]
        threshold = alpha / (m - k + 1)
        if p is None:
            rows.append(MultiplicityRow(h, ranks[h], None, None, None, False))
            stopped = True
            continue
        running = max(running, min(float(_P_MAX), (m - k + 1) * p))
        rejected = not stopped and p <= threshold
        if not rejected:
            stopped = True
        rows.append(MultiplicityRow(h, ranks[h], p, threshold, running, rejected))
    return sorted(rows, key=lambda r: r.rank)


def holm_fixed_sequence(
    p_values: Mapping[str, float | None],
    ranks: Mapping[str, int],
    alpha: float,
) -> list[MultiplicityRow]:
    """Fixed-sequence reading (T-a reading b): registered rank order.

    The hypothesis of rank r is compared with alpha / (m - r + 1) and the walk
    stops at the first failure or untestable hypothesis.
    """
    m = len(p_values)
    rows: list[MultiplicityRow] = []
    stopped = False
    for h in sorted(p_values, key=lambda x: ranks[x]):
        p = p_values[h]
        threshold = alpha / (m - ranks[h] + 1)
        rejected = not stopped and p is not None and p <= threshold
        if not rejected:
            stopped = True
        rows.append(MultiplicityRow(h, ranks[h], p, threshold, None, rejected))
    return rows


def benjamini_hochberg(
    p_values: Mapping[str, float | None],
    ranks: Mapping[str, int],
    q: float,
) -> list[MultiplicityRow]:
    """Benjamini-Hochberg step-up at level q; untestable counts as p = 1."""
    m = len(p_values)
    filled = {h: (float(_P_MAX) if p is None else p) for h, p in p_values.items()}
    order = sorted(filled, key=lambda h: (filled[h], ranks[h]))
    cutoff = 0
    for k, h in enumerate(order, start=1):
        if p_values[h] is not None and filled[h] <= q * k / m:
            cutoff = k
    adjusted: dict[str, float] = {}
    running = float(_P_MAX)
    for k in range(m, 0, -1):
        h = order[k - 1]
        running = min(running, filled[h] * m / k)
        adjusted[h] = running
    rows = [
        MultiplicityRow(
            h,
            ranks[h],
            p_values[h],
            q * k / m,
            adjusted[h],
            k <= cutoff and p_values[h] is not None,
        )
        for k, h in enumerate(order, start=1)
    ]
    return sorted(rows, key=lambda r: r.rank)


# ── effect sizes ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BcaInterval:
    """BCa interval of the mean paired difference; None bounds when degenerate."""

    estimate: float
    low: float | None
    high: float | None
    seed: int
    note: str | None = None


def bca_mean(diffs: Sequence[float], seed: int) -> BcaInterval:
    """BCa interval of the mean difference, 10,000 resamples, registered seed."""
    d = np.asarray(diffs, dtype=float)
    if len(d) == 0:
        raise ValueError("BCa needs at least one difference")
    estimate = float(d.mean())
    if len(d) < 2 or np.all(d == d[0]):
        return BcaInterval(
            estimate, None, None, seed, "degenerate: all differences equal"
        )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = sps.bootstrap(
            (d,),
            np.mean,
            n_resamples=BCA_RESAMPLES,
            confidence_level=BCA_CONFIDENCE,
            method="BCa",
            rng=np.random.default_rng(seed),
        )
    low = float(res.confidence_interval.low)
    high = float(res.confidence_interval.high)
    if not (math.isfinite(low) and math.isfinite(high)):
        return BcaInterval(estimate, None, None, seed, "degenerate: BCa undefined")
    return BcaInterval(estimate, low, high, seed)


def cliffs_delta(a: Sequence[float], b: Sequence[float]) -> float:
    """Cliff's delta over all cross pairs: (#a > b - #a < b) / (n_a n_b)."""
    x = np.asarray(a, dtype=float)[:, None]
    y = np.asarray(b, dtype=float)[None, :]
    if x.size == 0 or y.size == 0:
        raise ValueError("Cliff's delta needs two non-empty samples")
    return float(((x > y).sum() - (x < y).sum()) / (x.size * y.size))


def hodges_lehmann(diffs: Sequence[float]) -> float:
    """Median of the Walsh averages (d_i + d_j) / 2 over i <= j."""
    d = np.asarray(diffs, dtype=float)
    if len(d) == 0:
        raise ValueError("Hodges-Lehmann needs at least one difference")
    i, j = np.triu_indices(len(d))
    return float(np.median((d[i] + d[j]) / 2))


def cohens_h(p_a: float, p_b: float) -> float:
    """Cohen's h between two proportions: 2 asin(sqrt p_a) - 2 asin(sqrt p_b)."""
    for p in (p_a, p_b):
        if not 0 <= p <= _P_MAX:
            raise ValueError("proportions must lie in [0, 1]")
    return 2 * math.asin(math.sqrt(p_a)) - 2 * math.asin(math.sqrt(p_b))
