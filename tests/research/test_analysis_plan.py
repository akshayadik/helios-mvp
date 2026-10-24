"""Tests for helios.research.analysis_plan — hypothesis tables against the approved Chapter 3.

The expected tables below are transcribed from Ch3 Table 18 (p.169-189) and the
Holm order (p.192), with the owner's decisions D1/D6 (deviation 24), D10
(deviation 29) and D11 (deviation 25) applied. A change to the plan that does
not match them fails here first.
"""

from __future__ import annotations

from helios.research.analysis_plan import (
    ANALYSIS_SETTINGS,
    FAMILY_A_HYPOTHESES,
    FAMILY_B_HYPOTHESES,
    FAMILY_E_HYPOTHESES,
    _hypothesis_for_variant,
    _status_for_variant,
)
from helios.vcl import (
    CONFIRMATORY_VARIANTS,
    EXPLORATORY_VARIANTS,
    VCLFlag,  # noqa: F401 — flag-guard compliance
)

# (id, Holm rank, comparison, primary metric, test, stratum, asymmetric rule)
CH3_FAMILY_A = [
    ("A-H3", 1, "HELIOS-Full vs HELIOS-D", "HR@3", "wilcoxon_signed_rank", None, False),
    (
        "A-H7",
        2,
        "HELIOS-Full vs HELIOS-noLLM",
        "H_fact, H_struct",
        "sign_test",
        None,
        False,
    ),
    (
        "A-H1",
        3,
        "HELIOS-Full vs HELIOS-noLLM",
        "HR@3",
        "wilcoxon_signed_rank",
        None,
        False,
    ),
    (
        "A-H2",
        4,
        "HELIOS-Full vs HELIOS-LLM-only",
        "HR@3",
        "wilcoxon_signed_rank",
        None,
        False,
    ),
    (
        "A-H6",
        5,
        "HELIOS-Full vs HELIOS-G",
        "HR@3",
        "wilcoxon_signed_rank",
        "narrative_heavy",
        False,
    ),
    (
        "A-H5",
        6,
        "HELIOS-noRouter vs HELIOS-Full",
        "log-CpR at matched HR@3",
        "wilcoxon_signed_rank",
        None,
        False,
    ),
    (
        "A-H4",
        7,
        "HELIOS-Full vs HELIOS-noConsensus",
        "HR@3",
        "wilcoxon_signed_rank",
        "ambiguous",
        True,
    ),
    (
        "A-H8",
        8,
        "HELIOS-Full vs HELIOS-noStructural",
        "HR@3",
        "wilcoxon_signed_rank",
        None,
        True,
    ),
]

# (id, Holm rank, primary metric, test)
CH3_FAMILY_B = [
    ("B-H1", 1, "HR@3 (paired binary)", "mcnemar_exact_mid_p"),
    ("B-H2", 2, "HR@3 (paired binary)", "mcnemar_exact_mid_p"),
    ("B-H3", 3, "HR@3 (paired binary)", "mcnemar_exact_mid_p"),
    ("B-H4", 4, "HR@3 (paired binary)", "mcnemar_exact_mid_p"),
    ("B-H5", 5, "HR@3 (paired binary)", "mcnemar_exact_mid_p"),
    ("B-H7", 6, "log-CpR", "wilcoxon_signed_rank"),
    ("B-H6", 7, "log time to correct diagnosis", "wilcoxon_signed_rank"),
    ("B-H8", 8, "Avg@5", "wilcoxon_signed_rank"),
]

ALPHA_BY_RANK = {
    1: 0.00625,
    2: 0.007143,
    3: 0.008333,
    4: 0.01,
    5: 0.0125,
    6: 0.016667,
    7: 0.025,
    8: 0.05,
}


def test_family_a_matches_ch3_table_18_and_holm_order() -> None:
    actual = [
        (
            h["id"],
            h["rank"],
            h["comparison"],
            h["primary_metric"],
            h["test"],
            h["stratum"],
            h["asymmetric_rule"],
        )
        for h in FAMILY_A_HYPOTHESES
    ]
    assert actual == CH3_FAMILY_A


def test_family_b_matches_ch3_with_d10() -> None:
    actual = [
        (h["id"], h["rank"], h["primary_metric"], h["test"])
        for h in FAMILY_B_HYPOTHESES
    ]
    assert actual == CH3_FAMILY_B


def test_every_confirmatory_hypothesis_is_one_sided_with_rank_alpha() -> None:
    for h in [*FAMILY_A_HYPOTHESES, *FAMILY_B_HYPOTHESES]:
        assert h["status"] == "confirmatory", h["id"]
        assert h["direction"] == "a > b", h["id"]
        assert h["alpha"] == ALPHA_BY_RANK[int(h["rank"])], h["id"]  # type: ignore[arg-type]


def test_asymmetric_rule_covers_underpowered_and_mcnemar_hypotheses() -> None:
    flagged = {
        h["id"]
        for h in [*FAMILY_A_HYPOTHESES, *FAMILY_B_HYPOTHESES]
        if h["asymmetric_rule"]
    }
    assert flagged == {"A-H4", "A-H8", "B-H1", "B-H2", "B-H3", "B-H4", "B-H5"}


def test_family_e_has_ten_entries_with_e_h3_retired() -> None:
    assert [h["id"] for h in FAMILY_E_HYPOTHESES] == [f"E-H{i}" for i in range(1, 11)]
    status = {h["id"]: h["status"] for h in FAMILY_E_HYPOTHESES}
    assert status["E-H3"] == "retired"
    assert all(s == "exploratory" for i, s in status.items() if i != "E-H3")


def test_every_comparison_names_a_defined_variant() -> None:
    known = {*CONFIRMATORY_VARIANTS, *EXPLORATORY_VARIANTS, "BEST-BASELINE"} | {
        f"BASELINE-{k}" for k in range(1, 6)
    }
    for h in [*FAMILY_A_HYPOTHESES, *FAMILY_B_HYPOTHESES, *FAMILY_E_HYPOTHESES]:
        a, b = (side.strip() for side in str(h["comparison"]).split(" vs "))
        assert a in known and b in known, h["id"]


def test_family_a_uses_only_confirmatory_variants() -> None:
    for h in FAMILY_A_HYPOTHESES:
        for side in str(h["comparison"]).split(" vs "):
            assert side.strip() in CONFIRMATORY_VARIANTS, h["id"]


def test_settings_carry_d11_floors_and_clustering_sensitivity() -> None:
    floors = " ".join(ANALYSIS_SETTINGS["sanity_floors"])  # type: ignore[arg-type]
    sensitivity = " ".join(ANALYSIS_SETTINGS["sensitivity_analyses"])  # type: ignore[arg-type]
    assert "prior-only" in floors
    assert "group-level" in sensitivity
    assert "mixed model" in sensitivity
    assert ANALYSIS_SETTINGS["alpha_at_rank_1"] == ALPHA_BY_RANK[1]


def test_variant_maps_cover_all_confirmatory_variants() -> None:
    for name in CONFIRMATORY_VARIANTS:
        assert _hypothesis_for_variant(name), name
        assert _status_for_variant(name) == "confirmatory", name


def test_variant_map_points_each_ablation_at_its_hypothesis() -> None:
    assert _hypothesis_for_variant("HELIOS-noLLM") == "A-H1, A-H7"
    assert _hypothesis_for_variant("HELIOS-LLM-only") == "A-H2"
    assert _hypothesis_for_variant("HELIOS-G") == "A-H6"


def test_unknown_variant_defaults() -> None:
    assert _hypothesis_for_variant("HELIOS-Unknown") == ""
    assert _status_for_variant("HELIOS-Unknown") == "exploratory"
