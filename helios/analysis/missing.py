"""MCAR test and inverse-probability weighting (S4.10 O-f; entry 87).

Both are sensitivity analyses (analysis plan ``sensitivity_analyses``); neither
changes a binding result.

Unit: the case pair of a hypothesis. A pair is missing when either compared
run is excluded or its cell fails for the hypothesis's metric.

MCAR: with at least ``MIN_MISSING_FOR_LR`` missing pairs, a logistic
regression of "pair missing" on the case covariates, likelihood-ratio test
against the intercept-only model. Below that, descriptive per-covariate
comparisons: per-level counts, Fisher's exact test for two-level covariates,
the exact rank-sum test for continuous ones (asymptotic when tied, stated).
With no missing pair: complete, not applicable.

IPW: the same model for "pair complete"; stabilised weights (marginal
completion share / fitted probability), truncated at the 1st and 99th
percentiles; the weighted mean paired difference with a weighted BCa interval
(paired case resampling, ``bca_seed`` of the hypothesis). No weighted p-value.
"""

from __future__ import annotations

import math
import warnings
from typing import TYPE_CHECKING, Any

import numpy as np
import scipy.stats as sps
import statsmodels.api as sm

from helios.analysis.stats import BCA_CONFIDENCE, BCA_RESAMPLES
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "MIN_MISSING_FOR_LR",
    "WEIGHT_PERCENTILES",
    "design_matrix",
    "ipw_effect",
    "mcar_test",
]

HELIOS_ENABLE_MISSING_DATA: bool = True

MIN_MISSING_FOR_LR = 10
WEIGHT_PERCENTILES = (1, 99)


def _categorical(values: Sequence[Any]) -> bool:
    return any(isinstance(v, str | bool) for v in values)


def design_matrix(
    cases: Sequence[str], covariates: Mapping[str, Mapping[str, Any]]
) -> tuple[np.ndarray, list[str]]:
    """Columns: one-hot categoricals (first level dropped), standardised
    continuous covariates. Constant and incomplete covariates are left out."""
    names = sorted({k for c in cases for k in covariates.get(c, {})})
    cols: list[np.ndarray] = []
    labels: list[str] = []
    for name in names:
        values = [covariates.get(c, {}).get(name) for c in cases]
        if any(v is None for v in values):
            continue
        if _categorical(values):
            levels = sorted({str(v) for v in values})
            for level in levels[1:]:
                cols.append(np.array([str(v) == level for v in values], dtype=float))
                labels.append(f"{name}={level}")
        else:
            x = np.array(values, dtype=float)
            sd = float(x.std())
            if sd > 0:
                cols.append((x - x.mean()) / sd)
                labels.append(name)
    matrix = np.column_stack(cols) if cols else np.empty((len(cases), 0))
    return matrix, labels


def _fit(y: np.ndarray, x: np.ndarray) -> Any | None:
    """Logit fit, or None when it does not converge or separates perfectly."""
    exog = sm.add_constant(x, has_constant="add")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = sm.Logit(y, exog).fit(disp=0, maxiter=200)
    except Exception:  # perfect separation, singular matrix
        return None
    if not res.mle_retvals.get("converged", False):
        return None
    if not np.all(np.isfinite(res.params)):
        return None
    return res


def _descriptive(
    cases: Sequence[str],
    missing: Mapping[str, bool],
    covariates: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    names = sorted({k for c in cases for k in covariates.get(c, {})})
    for name in names:
        values = [covariates.get(c, {}).get(name) for c in cases]
        if any(v is None for v in values):
            continue
        miss = [missing[c] for c in cases]
        if _categorical(values):
            levels = sorted({str(v) for v in values})
            counts = {
                lv: {
                    "missing": sum(
                        m for v, m in zip(values, miss, strict=True) if str(v) == lv
                    ),
                    "total": sum(str(v) == lv for v in values),
                }
                for lv in levels
            }
            row: dict[str, Any] = {"kind": "categorical", "counts": counts}
            if len(levels) == 2:
                table = [
                    [counts[lv]["missing"], counts[lv]["total"] - counts[lv]["missing"]]
                    for lv in levels
                ]
                row["fisher_exact_p"] = float(sps.fisher_exact(table).pvalue)
            out[name] = row
        else:
            x = np.array(values, dtype=float)
            m = np.array(miss, dtype=bool)
            if m.all() or not m.any():
                continue
            tied = len(set(x.tolist())) < len(x)
            method = "asymptotic" if tied else "exact"
            res = sps.mannwhitneyu(x[m], x[~m], method=method)
            out[name] = {"kind": "continuous", "rank_sum_p": float(res.pvalue),
                         "method": method}  # fmt: skip
    return out


def mcar_test(
    cases: Sequence[str],
    missing: Mapping[str, bool],
    covariates: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """MCAR evidence for one hypothesis's case pairs (O-f)."""
    n_missing = sum(bool(missing[c]) for c in cases)
    base: dict[str, Any] = {"n_pairs_scheduled": len(cases), "n_missing": n_missing}
    if n_missing == 0:
        return {**base, "status": "complete; MCAR not applicable"}
    if n_missing < MIN_MISSING_FOR_LR or len(cases) - n_missing < MIN_MISSING_FOR_LR:
        return {
            **base,
            "status": f"descriptive (fewer than {MIN_MISSING_FOR_LR} missing or "
            "complete pairs)",
            "covariates": _descriptive(cases, missing, covariates),
        }
    x, labels = design_matrix(cases, covariates)
    y = np.array([float(missing[c]) for c in cases])
    res = _fit(y, x) if labels else None
    if res is None:
        return {
            **base,
            "status": "logistic model not estimable; descriptive",
            "covariates": _descriptive(cases, missing, covariates),
        }
    lr = float(2 * (res.llf - res.llnull))
    df = len(labels)
    return {
        **base,
        "status": "likelihood-ratio test",
        "covariates_in_model": labels,
        "lr_statistic": lr,
        "df": df,
        "p_value": float(sps.chi2.sf(lr, df)),
    }


def _weighted_mean(d: np.ndarray, w: np.ndarray, axis: int = -1) -> np.ndarray:
    out: np.ndarray = np.sum(d * w, axis=axis) / np.sum(w, axis=axis)
    return out


def ipw_effect(
    cases: Sequence[str],
    diffs: Mapping[str, float],
    covariates: Mapping[str, Mapping[str, Any]],
    seed: int,
) -> dict[str, Any]:
    """IPW-weighted mean paired difference over the complete pairs (O-f).

    ``cases`` are all scheduled pairs; ``diffs`` holds the complete ones.
    """
    complete = [c for c in cases if c in diffs]
    n_missing = len(cases) - len(complete)
    base: dict[str, Any] = {"n_complete": len(complete), "n_missing": n_missing}
    if n_missing == 0:
        return {**base, "status": "complete; no weighting needed"}
    if len(complete) < 2:
        return {**base, "status": "too few complete pairs"}
    x, labels = design_matrix(cases, covariates)
    y = np.array([float(c in diffs) for c in cases])
    res = _fit(y, x) if labels else None
    if res is None:
        return {**base, "status": "propensity model not estimable"}
    fitted = np.asarray(res.predict(sm.add_constant(x, has_constant="add")))
    share = float(y.mean())
    idx = [i for i, c in enumerate(cases) if c in diffs]
    w = share / fitted[idx]
    lo, hi = np.percentile(w, WEIGHT_PERCENTILES)
    w = np.clip(w, lo, hi)
    d = np.array([diffs[cases[i]] for i in idx], dtype=float)
    estimate = float(_weighted_mean(d, w))
    out = {
        **base,
        "status": "weighted",
        "covariates_in_model": labels,
        "estimate": estimate,
        "unweighted_estimate": float(d.mean()),
        "weight_range": [float(w.min()), float(w.max())],
        "seed": seed,
    }
    if np.all(d == d[0]):
        return {**out, "low": None, "high": None, "note": "degenerate: all equal"}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        boot = sps.bootstrap(
            (d, w),
            _weighted_mean,
            paired=True,
            n_resamples=BCA_RESAMPLES,
            confidence_level=BCA_CONFIDENCE,
            method="BCa",
            rng=np.random.default_rng(seed),
        )
    low = float(boot.confidence_interval.low)
    high = float(boot.confidence_interval.high)
    if not (math.isfinite(low) and math.isfinite(high)):
        return {**out, "low": None, "high": None, "note": "degenerate: BCa undefined"}
    return {**out, "low": low, "high": high}
