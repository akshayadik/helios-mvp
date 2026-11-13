"""Registered sensitivity analyses (S4.11 design T-g).

- Group-level differences: per-group means of each variant over the
  system x root-cause service x fault groups, then the same exact Wilcoxon.
- Rank-based mixed model: pooled ranks of the outcome over both variants,
  regressed on the variant indicator with a random intercept per group
  (statsmodels MixedLM, REML); the one-sided p of the variant coefficient and
  the ICC = group variance / (group + residual variance).
"""

from __future__ import annotations

import math
import warnings
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from scipy import stats as sps

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = ["MixedModelResult", "group_differences", "icc", "rank_mixed_model"]

HELIOS_ENABLE_ANALYSIS_SENSITIVITY: bool = True


def group_differences(
    a: Mapping[str, float], b: Mapping[str, float], groups: Mapping[str, str]
) -> list[float]:
    """Per-group mean(a) - mean(b) over the cases both variants have, sorted by group."""
    by_group: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for case in sorted(a.keys() & b.keys()):
        if case in groups:
            by_group[groups[case]].append((a[case], b[case]))
    out: list[float] = []
    for g in sorted(by_group):
        pairs = by_group[g]
        out.append(
            float(np.mean([x for x, _ in pairs]) - np.mean([y for _, y in pairs]))
        )
    return out


def icc(group_variance: float, residual_variance: float) -> float:
    """Intraclass correlation of a random-intercept model."""
    total = group_variance + residual_variance
    if total <= 0:
        raise ValueError("variances must sum to a positive value")
    return group_variance / total


@dataclass(frozen=True)
class MixedModelResult:
    """Variant effect on pooled ranks with a random group intercept."""

    coefficient: float
    p_value: float  # one-sided, coefficient > 0 (a ranks higher)
    group_variance: float
    residual_variance: float
    icc: float
    n_observations: int
    n_groups: int
    converged: bool


def rank_mixed_model(
    a: Mapping[str, float],
    b: Mapping[str, float],
    groups: Mapping[str, str],
) -> MixedModelResult | None:
    """Rank-based mixed model over the paired cases; None if it cannot be fitted."""
    import statsmodels.formula.api as smf

    cases: Sequence[str] = sorted((a.keys() & b.keys()) & groups.keys())
    if len({groups[c] for c in cases}) < 2:
        return None
    values = [a[c] for c in cases] + [b[c] for c in cases]
    frame = pd.DataFrame(
        {
            "rank": sps.rankdata(values),
            "variant_a": [1] * len(cases) + [0] * len(cases),
            "group": [groups[c] for c in cases] * 2,
        }
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            fit = smf.mixedlm("rank ~ variant_a", frame, groups=frame["group"]).fit(
                reml=True
            )
        except (np.linalg.LinAlgError, ValueError):
            # A singular design (e.g. one case per group) cannot be fitted;
            # whether the optimiser reaches it depends on the platform's BLAS.
            return None
    coefficient = float(fit.params["variant_a"])
    se = float(fit.bse["variant_a"])
    if not (math.isfinite(se) and se > 0):
        return None
    group_var = max(float(fit.cov_re.iloc[0, 0]), 0)
    resid = float(fit.scale)
    return MixedModelResult(
        coefficient=coefficient,
        p_value=float(sps.norm.sf(coefficient / se)),
        group_variance=group_var,
        residual_variance=resid,
        icc=icc(group_var, resid),
        n_observations=len(frame),
        n_groups=frame["group"].nunique(),
        converged=bool(fit.converged),
    )
