"""S4.11 statistics: every expected value is computed by hand in the comments."""

from __future__ import annotations

import math

import pytest

from helios.analysis.sensitivity import group_differences, icc, rank_mixed_model
from helios.analysis.stats import (
    bca_mean,
    benjamini_hochberg,
    cliffs_delta,
    cohens_h,
    hodges_lehmann,
    holm_fixed_sequence,
    holm_step_down,
    mcnemar_mid_p,
    paired_t,
    sign_test,
    wilcoxon_exact,
)
from helios.research.analysis_plan import FAMILY_A_HYPOTHESES
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

# ── Wilcoxon (T-b) ───────────────────────────────────────────────────────────


def test_wilcoxon_exact_without_ties() -> None:
    # |d| ranks 1, 2, 3, 4; T+ = 1 + 2 + 3 = 6. Of the 16 subsets of {1,2,3,4},
    # seven sum to at least 6 ({2,4} {3,4} {1,2,3} {1,2,4} {1,3,4} {2,3,4} all).
    res = wilcoxon_exact([1, 2, 3, -4])
    assert res.statistic == 6
    assert res.p_value == pytest.approx(7 / 16)
    assert (res.n_pairs, res.n_informative) == (4, 4)


def test_wilcoxon_exact_with_ties_and_zero() -> None:
    # Zero dropped; |d| = 1, 1, 2 -> midranks 1.5, 1.5, 3; T+ = 3.
    # Subset sums of {1.5, 1.5, 3}: 0, 1.5, 1.5, 3, 3, 4.5, 4.5, 6 -> 5 of 8 >= 3.
    res = wilcoxon_exact([1, 1, -2, 0])
    assert res.statistic == 3
    assert res.p_value == pytest.approx(5 / 8)
    assert (res.n_pairs, res.n_informative) == (4, 3)


def test_wilcoxon_on_binary_differences_equals_the_sign_test() -> None:
    # 0/1 outcomes: d in {-1, 0, 1}; 3 positive of 4 non-zero -> P(X >= 3) = 5/16.
    diffs = [1, 1, 1, -1, 0]
    assert wilcoxon_exact(diffs).p_value == pytest.approx(5 / 16)
    assert sign_test(diffs).p_value == pytest.approx(5 / 16)


def test_wilcoxon_with_no_informative_pair_is_not_significant() -> None:
    res = wilcoxon_exact([0, 0])
    assert res.p_value == 1
    assert res.n_informative == 0


def test_wilcoxon_rejects_non_finite_differences() -> None:
    with pytest.raises(ValueError, match="finite"):
        wilcoxon_exact([1, math.nan])


# ── sign test and McNemar (T-c, T-e) ─────────────────────────────────────────


def test_sign_test_exact() -> None:
    # Non-zero: 0.2, 0.1, -0.3, 0.4 -> 3 positive of 4: P(X >= 3) = (4 + 1) / 16.
    res = sign_test([0.2, 0.1, -0.3, 0.4, 0])
    assert res.statistic == 3
    assert res.p_value == pytest.approx(5 / 16)
    assert sign_test([0, 0]).p_value == 1


def test_mcnemar_mid_p() -> None:
    # b = 3 (a hits, b misses), c = 1, n = 4.
    # mid-p = P(X > 3) + P(X = 3) / 2 = 1/16 + (4/16) / 2 = 3/16.
    res = mcnemar_mid_p([1, 1, 1, 0, 1, 0], [0, 0, 0, 1, 1, 0])
    assert res.statistic == 3
    assert res.n_informative == 4
    assert res.p_value == pytest.approx(3 / 16)


def test_mcnemar_edge_cases() -> None:
    assert mcnemar_mid_p([1, 0], [1, 0]).p_value == 1
    with pytest.raises(ValueError, match="0/1"):
        mcnemar_mid_p([2], [0])
    with pytest.raises(ValueError, match="equal length"):
        mcnemar_mid_p([1], [1, 0])


def test_paired_t() -> None:
    # d = 1, 2, 3: mean 2, sd 1, t = 2 / (1 / sqrt 3) = 2 sqrt 3.
    res = paired_t([1, 2, 3])
    assert res.statistic == pytest.approx(2 * math.sqrt(3))
    assert res.p_value < 0.05
    assert paired_t([2, 2]).p_value == 1


# ── multiplicity (T-a) ───────────────────────────────────────────────────────

P = {"H1": 0.001, "H2": 0.04, "H3": None, "H4": 0.012}
RANKS = {"H2": 1, "H1": 2, "H3": 3, "H4": 4}


def test_holm_data_order() -> None:
    # m = 4. Sorted: H1 0.001 <= 0.05/4 (yes); H4 0.012 <= 0.05/3 (yes);
    # H2 0.04 <= 0.05/2 (no, stop); H3 untestable, last, not rejected.
    # Adjusted: H1 4 x 0.001; H4 max(., 3 x 0.012); H2 max(., 2 x 0.04).
    rows = {r.hypothesis_id: r for r in holm_step_down(P, RANKS, 0.05)}
    assert [h for h, r in rows.items() if r.rejected] == ["H1", "H4"]
    assert rows["H1"].adjusted_p == pytest.approx(0.004)
    assert rows["H4"].adjusted_p == pytest.approx(0.036)
    assert rows["H2"].adjusted_p == pytest.approx(0.08)
    assert rows["H3"].p_value is None
    assert rows["H3"].rejected is False


def test_holm_fixed_sequence_stops_at_the_first_rank() -> None:
    # Rank 1 is H2: 0.04 > 0.05/4, so nothing after it is rejected either.
    rows = holm_fixed_sequence(P, RANKS, 0.05)
    assert [r.hypothesis_id for r in rows] == ["H2", "H1", "H3", "H4"]
    assert not any(r.rejected for r in rows)


def test_holm_thresholds_match_the_registered_alpha_by_rank() -> None:
    pvals = {str(h["id"]): None for h in FAMILY_A_HYPOTHESES}
    ranks = {str(h["id"]): int(str(h["rank"])) for h in FAMILY_A_HYPOTHESES}
    for row in holm_fixed_sequence(pvals, ranks, 0.05):
        registered = next(
            h["alpha"] for h in FAMILY_A_HYPOTHESES if h["id"] == row.hypothesis_id
        )
        assert row.threshold == pytest.approx(registered, abs=1e-6)


def test_benjamini_hochberg() -> None:
    # Thresholds k/4 x 0.05: 0.0125, 0.025, 0.0375, 0.05. Sorted p: 0.001, 0.012,
    # 0.04, (untestable as 1). Largest k with p_(k) <= threshold: k = 2.
    # Adjusted: k4 1; k3 min(1, 0.04 x 4/3); k2 min(., 0.012 x 2); k1 0.001 x 4.
    rows = {r.hypothesis_id: r for r in benjamini_hochberg(P, RANKS, 0.05)}
    assert sorted(h for h, r in rows.items() if r.rejected) == ["H1", "H4"]
    assert rows["H2"].adjusted_p == pytest.approx(0.04 * 4 / 3)
    assert rows["H4"].adjusted_p == pytest.approx(0.024)
    assert rows["H1"].adjusted_p == pytest.approx(0.004)


# ── effect sizes (T-f) ───────────────────────────────────────────────────────


def test_hodges_lehmann() -> None:
    # Walsh averages of 1, 3, 8: 1, 3, 8, 2, 4.5, 5.5 -> median (3 + 4.5) / 2.
    assert hodges_lehmann([1, 3, 8]) == pytest.approx(3.75)
    with pytest.raises(ValueError):
        hodges_lehmann([])


def test_cliffs_delta() -> None:
    # a = 3, 4; b = 1, 3, 5: wins 3 (3>1, 4>1, 4>3), losses 2 (3<5, 4<5) -> 1/6.
    assert cliffs_delta([3, 4], [1, 3, 5]) == pytest.approx(1 / 6)
    with pytest.raises(ValueError):
        cliffs_delta([], [1])


def test_cohens_h_reproduces_the_registered_commitment() -> None:
    # Ch3: target HR@3 0.73 against 0.60 gives h of about 0.276.
    h = cohens_h(0.73, 0.60)
    assert h == pytest.approx(0.2766, abs=1e-3)
    with pytest.raises(ValueError):
        cohens_h(1.2, 0.3)


def test_bca_is_reproducible_under_the_seed() -> None:
    diffs = [1, 0, 1, 1, 0, 1, -1, 1, 0, 1, 1, 0]
    first, again = bca_mean(diffs, 7_328_001), bca_mean(diffs, 7_328_001)
    assert first == again
    assert first.estimate == pytest.approx(sum(diffs) / len(diffs))
    assert first.low is not None and first.high is not None
    assert first.low < first.estimate < first.high


def test_bca_degenerate() -> None:
    res = bca_mean([1, 1, 1], 7)
    assert (res.low, res.high) == (None, None)
    assert res.note is not None
    with pytest.raises(ValueError):
        bca_mean([], 7)


# ── sensitivity (T-g) ────────────────────────────────────────────────────────


def test_group_differences() -> None:
    # g1 = c1..c3: mean a 1, mean b 1/3 -> 2/3; g2 = c4: 1 - 0 = 1.
    a = {"c1": 1, "c2": 1, "c3": 1, "c4": 1}
    b = {"c1": 0, "c2": 0, "c3": 1, "c4": 0}
    groups = {"c1": "g1", "c2": "g1", "c3": "g1", "c4": "g2"}
    assert group_differences(a, b, groups) == pytest.approx([2 / 3, 1])


def test_icc() -> None:
    assert icc(1, 3) == pytest.approx(1 / 4)
    with pytest.raises(ValueError):
        icc(0, 0)


def test_rank_mixed_model_detects_a_clear_effect() -> None:
    cases = [f"c{i}" for i in range(24)]
    groups = {c: f"g{i % 6}" for i, c in enumerate(cases)}
    a = {c: 10 + i % 3 + (i % 6) for i, c in enumerate(cases)}
    b = {c: 1 + i % 3 + (i % 6) for i, c in enumerate(cases)}
    res = rank_mixed_model(a, b, groups)
    assert res is not None
    assert res.coefficient > 0
    assert res.p_value < 0.01
    assert 0 <= res.icc <= 1
    assert (res.n_observations, res.n_groups) == (48, 6)


def test_rank_mixed_model_needs_two_groups() -> None:
    assert rank_mixed_model({"c": 1}, {"c": 0}, {"c": "g"}) is None
