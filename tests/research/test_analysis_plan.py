"""Tests for helios.research.analysis_plan — frozen hypothesis tables."""

from __future__ import annotations

import pytest

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def test_family_a_hypotheses_has_eight_entries() -> None:
    from helios.research.analysis_plan import FAMILY_A_HYPOTHESES

    assert len(FAMILY_A_HYPOTHESES) == 8


def test_family_b_hypotheses_has_eight_entries() -> None:
    from helios.research.analysis_plan import FAMILY_B_HYPOTHESES

    assert len(FAMILY_B_HYPOTHESES) == 8


def test_a_h3_is_rank_1_with_correct_alpha() -> None:
    from helios.research.analysis_plan import FAMILY_A_HYPOTHESES

    a_h3 = next(h for h in FAMILY_A_HYPOTHESES if h["id"] == "A-H3")
    assert a_h3["rank"] == 1
    assert a_h3["alpha"] == pytest.approx(0.00625)


def test_a_h6_is_rank_5_with_filter_and_correct_alpha() -> None:
    from helios.research.analysis_plan import FAMILY_A_HYPOTHESES

    a_h6 = next(h for h in FAMILY_A_HYPOTHESES if h["id"] == "A-H6")
    assert a_h6["rank"] == 5
    assert a_h6["alpha"] == pytest.approx(0.0125)
    assert a_h6["filter"] == "narrative != 'gpipe-gated-or-skipped'"


def test_non_a_h6_entries_have_null_filter() -> None:
    from helios.research.analysis_plan import FAMILY_A_HYPOTHESES

    for h in FAMILY_A_HYPOTHESES:
        if h["id"] != "A-H6":
            assert h["filter"] is None, f"{h['id']} must have filter=None"


def test_family_a_ranks_are_unique_and_sequential() -> None:
    from helios.research.analysis_plan import FAMILY_A_HYPOTHESES

    ranks = sorted(int(h["rank"]) for h in FAMILY_A_HYPOTHESES)  # type: ignore[arg-type]
    assert ranks == list(range(1, 9))


def test_family_b_all_deferred() -> None:
    from helios.research.analysis_plan import FAMILY_B_HYPOTHESES

    for h in FAMILY_B_HYPOTHESES:
        assert h["status"] == "deferred"


def test_family_b_b_h2_and_b_h4_use_rcacopilot_baseline() -> None:
    from helios.research.analysis_plan import FAMILY_B_HYPOTHESES

    b_h2 = next(h for h in FAMILY_B_HYPOTHESES if h["id"] == "B-H2")
    b_h4 = next(h for h in FAMILY_B_HYPOTHESES if h["id"] == "B-H4")
    assert b_h2["baseline"] == "RCACopilot"
    assert b_h4["baseline"] == "RCACopilot"


def test_b_h7_primary_metric_is_coe_score() -> None:
    from helios.research.analysis_plan import FAMILY_B_HYPOTHESES

    b_h7 = next(h for h in FAMILY_B_HYPOTHESES if h["id"] == "B-H7")
    assert b_h7["primary_metric"] == "CoE score"


def test_hypothesis_for_variant_helios_full() -> None:
    from helios.research.analysis_plan import _hypothesis_for_variant

    result = _hypothesis_for_variant("HELIOS-Full")
    assert "A-H1" in result
    assert "A-H3" in result


def test_hypothesis_for_variant_helios_nollm() -> None:
    from helios.research.analysis_plan import _hypothesis_for_variant

    assert _hypothesis_for_variant("HELIOS-noLLM") == "A-H7"


def test_hypothesis_for_unknown_variant_returns_empty() -> None:
    from helios.research.analysis_plan import _hypothesis_for_variant

    assert _hypothesis_for_variant("HELIOS-Unknown") == ""


def test_status_for_variant_confirmatory() -> None:
    from helios.research.analysis_plan import _status_for_variant

    assert _status_for_variant("HELIOS-Full") == "confirmatory"
    assert _status_for_variant("HELIOS-D") == "confirmatory"


def test_status_for_variant_exploratory() -> None:
    from helios.research.analysis_plan import _status_for_variant

    assert _status_for_variant("HELIOS-noConsensus") == "exploratory"
    assert _status_for_variant("HELIOS-noRouter") == "exploratory"
    assert _status_for_variant("HELIOS-noStructural") == "exploratory"


def test_status_for_variant_conditional_confirmatory() -> None:
    from helios.research.analysis_plan import _status_for_variant

    assert _status_for_variant("HELIOS-G") == "cond. confirmatory"
