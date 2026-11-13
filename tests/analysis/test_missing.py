"""S4.10 O-f: MCAR test and IPW, with hand-computed expectations."""

from __future__ import annotations

import math

import pytest
from scipy import stats as sps

from helios.analysis.missing import (
    MIN_MISSING_FOR_LR,
    design_matrix,
    ipw_effect,
    mcar_test,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def _cases(n: int) -> list[str]:
    return [f"c{i:03d}" for i in range(n)]


def test_complete_data_needs_no_test() -> None:
    cases = _cases(4)
    out = mcar_test(
        cases, dict.fromkeys(cases, False), {c: {"app": "OB"} for c in cases}
    )
    assert out["status"].startswith("complete")
    assert ipw_effect(cases, dict.fromkeys(cases, 1), {}, 7)["status"].startswith(
        "complete"
    )


def test_few_missing_pairs_give_exact_descriptive_tests() -> None:
    # OB: 2 of 6 missing; TT: 0 of 6. Fisher 2x2 [[2, 4], [0, 6]].
    cases = _cases(12)
    cov = {c: {"app": "OB" if i < 6 else "TT", "bytes": i} for i, c in enumerate(cases)}
    missing = {c: i in (0, 1) for i, c in enumerate(cases)}
    out = mcar_test(cases, missing, cov)
    assert out["n_missing"] == 2
    assert out["status"].startswith("descriptive")
    app = out["covariates"]["app"]
    assert app["counts"]["OB"] == {"missing": 2, "total": 6}
    assert app["fisher_exact_p"] == pytest.approx(
        sps.fisher_exact([[2, 4], [0, 6]]).pvalue
    )
    # bytes 0, 1 missing vs 2..11 complete: the two smallest of 12 -> exact
    # two-sided rank-sum p = 2 / C(12, 2).
    assert out["covariates"]["bytes"]["method"] == "exact"
    assert out["covariates"]["bytes"]["rank_sum_p"] == pytest.approx(
        2 / math.comb(12, 2)
    )


def test_likelihood_ratio_branch_detects_dependence() -> None:
    # 40 cases; missing iff bytes is large, with some noise -> clear dependence.
    cases = _cases(40)
    cov = {c: {"bytes": i, "app": "OB" if i % 2 else "TT"} for i, c in enumerate(cases)}
    missing = {c: (i >= 25) != (i in (3, 30)) for i, c in enumerate(cases)}
    assert sum(missing.values()) >= MIN_MISSING_FOR_LR
    out = mcar_test(cases, missing, cov)
    assert out["status"] == "likelihood-ratio test"
    assert out["df"] == 2
    assert out["p_value"] < 1e-4


def test_separation_falls_back_to_descriptive() -> None:
    cases = _cases(30)
    cov = {c: {"app": "OB" if i < 15 else "TT"} for i, c in enumerate(cases)}
    missing = {c: i < 15 for i, c in enumerate(cases)}  # perfectly separated
    out = mcar_test(cases, missing, cov)
    assert out["status"].startswith("logistic model not estimable")
    assert (
        ipw_effect(cases, {c: 1 for c in cases if not missing[c]}, cov, 7)["status"]
        == "propensity model not estimable"
    )


def test_ipw_with_a_saturated_model_reweights_by_level() -> None:
    # A: 10 cases, 8 complete, diff 1; B: 10 cases, 5 complete, diff 0.
    # Completion share 13/20; weights A (13/20)/(8/10) = 13/16, B (13/20)/(5/10)
    # = 13/10. Weighted mean = 8 x 13/16 / (8 x 13/16 + 5 x 13/10) = 1/2.
    cases = _cases(20)
    cov = {c: {"app": "A" if i < 10 else "B"} for i, c in enumerate(cases)}
    diffs = dict.fromkeys(cases[:8], 1) | dict.fromkeys(cases[10:15], 0)
    out = ipw_effect(cases, diffs, cov, 7_328_001)
    assert out["status"] == "weighted"
    assert out["estimate"] == pytest.approx(1 / 2, abs=1e-6)
    assert out["unweighted_estimate"] == pytest.approx(8 / 13)
    assert out["weight_range"] == pytest.approx([13 / 16, 13 / 10], abs=1e-6)
    assert out["low"] is not None and out["low"] < out["estimate"] < out["high"]
    assert ipw_effect(cases, diffs, cov, 7_328_001) == out  # seeded


def test_design_matrix_drops_constant_and_incomplete_columns() -> None:
    cases = _cases(3)
    cov = {
        "c000": {"k": "x", "z": 5, "n": 1},
        "c001": {"k": "y", "z": 5, "n": None},
        "c002": {"k": "y", "z": 5, "n": 2},
    }
    x, labels = design_matrix(cases, cov)
    assert labels == ["k=y"]
    assert x.shape == (3, 1)


def test_ipw_too_few_complete_pairs() -> None:
    cases = _cases(5)
    assert ipw_effect(cases, {"c000": 1}, {}, 7)["status"] == "too few complete pairs"
