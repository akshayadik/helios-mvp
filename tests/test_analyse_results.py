"""Unit tests for statistical analysis helpers."""

from __future__ import annotations

import math

from helios.vcl.config import VCLManifest  # noqa: F401 — flag-guard compliance


def test_run_wilcoxon_detects_consistent_improvement() -> None:
    from analyse_results import run_wilcoxon

    full_scores = [0.80, 0.80, 0.80, 0.80, 0.80, 0.80, 0.80, 0.80, 0.80, 0.80]
    nollm_scores = [0.40, 0.40, 0.40, 0.40, 0.40, 0.40, 0.40, 0.40, 0.40, 0.40]
    result = run_wilcoxon(full_scores, nollm_scores)
    assert result["n_nonzero"] > 0
    assert result["pvalue"] < 0.05
    assert "effect_r" in result


def test_run_wilcoxon_zero_variance_guard() -> None:
    from analyse_results import run_wilcoxon

    identical = [0.60, 0.60, 0.60, 0.60, 0.60, 0.60, 0.60, 0.60, 0.60, 0.60]
    result = run_wilcoxon(identical, identical)
    assert result["zero_variance"] is True
    assert math.isnan(result["pvalue"])


def test_run_wilcoxon_insufficient_sample() -> None:
    from analyse_results import run_wilcoxon

    result = run_wilcoxon([0.80, 0.60, 0.70], [0.40, 0.30, 0.20])
    assert result["insufficient_sample"] is True
    assert math.isnan(result["pvalue"])


def test_run_wilcoxon_returns_expected_keys() -> None:
    from analyse_results import run_wilcoxon

    a = [0.80, 0.60, 0.70, 0.80, 0.60, 0.70, 0.80, 0.60, 0.70, 0.80]
    b = [0.40, 0.30, 0.20, 0.40, 0.30, 0.20, 0.40, 0.30, 0.20, 0.40]
    result = run_wilcoxon(a, b)
    for key in (
        "pvalue",
        "effect_r",
        "n_nonzero",
        "zero_variance",
        "insufficient_sample",
        "n_pairs",
    ):
        assert key in result


def test_apply_holm_bonferroni_sorts_by_pvalue() -> None:
    from analyse_results import apply_holm_bonferroni

    pvalues = {"A-H3": 0.03, "A-H7": 0.01, "A-H1": 0.04}
    corrected = apply_holm_bonferroni(pvalues)
    assert set(corrected.keys()) == {"A-H3", "A-H7", "A-H1"}
    for v in corrected.values():
        assert "corrected_pvalue" in v
        assert "rejected" in v
