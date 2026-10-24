"""Hypothesis tables and analysis settings — single source of truth for the OSF pre-registration.

Derived from the approved Chapter 3 (Table 18 p.169-189; Holm order p.192;
power p.198-200) with the owner's decisions applied: D1/D6 (deviation 24),
D10 (deviation 29), D11 (deviation 25). Changes require a deviation log entry.

Consumed by bin/verify_osf_freeze.py --generate (analysis_plan.json) and by
the analysis tooling. Family A and Family B are separate Holm-Bonferroni
families; Family E is exploratory (BCa intervals, no Holm correction).
"""

from __future__ import annotations

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

HELIOS_ENABLE_RESEARCH_ANALYSIS_PLAN: bool = True

Hypothesis = dict[str, str | int | float | bool | None]

# Per-rank alpha inside each confirmatory family: 0.05 / (9 - rank).
# rank1=0.00625, rank2=0.007143, rank3=0.008333, rank4=0.01,
# rank5=0.0125, rank6=0.016667, rank7=0.025, rank8=0.05
_ALPHA_BY_RANK: dict[int, float] = {
    1: 0.00625,
    2: 0.007143,
    3: 0.008333,
    4: 0.01,
    5: 0.0125,
    6: 0.016667,
    7: 0.025,
    8: 0.05,
}

# ---------------------------------------------------------------------------
# Family A — ablation (confirmatory). Direction "a > b": the first-named
# variant is expected to score higher on the primary metric.
# ---------------------------------------------------------------------------
FAMILY_A_HYPOTHESES: list[Hypothesis] = [
    {
        "id": "A-H3",
        "rank": 1,
        "alpha": _ALPHA_BY_RANK[1],
        "comparison": "HELIOS-Full vs HELIOS-D",
        "primary_metric": "HR@3",
        "test": "wilcoxon_signed_rank",
        "direction": "a > b",
        "stratum": None,
        "expected_effect": "delta HR@3 >= 0.15",
        "status": "confirmatory",
        "asymmetric_rule": False,
        "ch3_ref": "Table 18 p.171",
    },
    {
        "id": "A-H7",
        "rank": 2,
        "alpha": _ALPHA_BY_RANK[2],
        "comparison": "HELIOS-Full vs HELIOS-noLLM",
        "primary_metric": "H_fact, H_struct",
        "test": "sign_test",
        "direction": "a > b",
        "stratum": None,
        "expected_effect": "hallucination rates at or near zero without the L-pipe, above zero under Full",
        "status": "confirmatory",
        "asymmetric_rule": False,
        "ch3_ref": "Table 18 p.179; power p.200",
    },
    {
        "id": "A-H1",
        "rank": 3,
        "alpha": _ALPHA_BY_RANK[3],
        "comparison": "HELIOS-Full vs HELIOS-noLLM",
        "primary_metric": "HR@3",
        "test": "wilcoxon_signed_rank",
        "direction": "a > b",
        "stratum": None,
        "expected_effect": "delta HR@3 >= 0.10",
        "status": "confirmatory",
        "asymmetric_rule": False,
        "ch3_ref": "Table 18 p.169",
    },
    {
        "id": "A-H2",
        "rank": 4,
        "alpha": _ALPHA_BY_RANK[4],
        "comparison": "HELIOS-Full vs HELIOS-LLM-only",
        "primary_metric": "HR@3",
        "test": "wilcoxon_signed_rank",
        "direction": "a > b",
        "stratum": None,
        "expected_effect": "delta HR@3 >= 0.10",
        "status": "confirmatory",
        "asymmetric_rule": False,
        "ch3_ref": "Table 18 p.170",
    },
    {
        "id": "A-H6",
        "rank": 5,
        "alpha": _ALPHA_BY_RANK[5],
        "comparison": "HELIOS-Full vs HELIOS-G",
        "primary_metric": "HR@3",
        "test": "wilcoxon_signed_rank",
        "direction": "a > b",
        "stratum": "narrative_heavy",
        "expected_effect": "delta HR@3 >= 0.12",
        "status": "confirmatory",
        "asymmetric_rule": False,
        "ch3_ref": "Table 18 p.178",
    },
    {
        "id": "A-H5",
        "rank": 6,
        "alpha": _ALPHA_BY_RANK[6],
        "comparison": "HELIOS-noRouter vs HELIOS-Full",
        "primary_metric": "log-CpR at matched HR@3",
        "test": "wilcoxon_signed_rank",
        "direction": "a > b",
        "stratum": None,
        "expected_effect": "delta log-CpR >= 0.60 (uniform routing costs more)",
        "status": "confirmatory",
        "asymmetric_rule": False,
        "ch3_ref": "Table 18 p.172",
    },
    {
        "id": "A-H4",
        "rank": 7,
        "alpha": _ALPHA_BY_RANK[7],
        "comparison": "HELIOS-Full vs HELIOS-noConsensus",
        "primary_metric": "HR@3",
        "test": "wilcoxon_signed_rank",
        "direction": "a > b",
        "stratum": "ambiguous",
        "expected_effect": "delta HR@3 >= 0.05 (underpowered, disclosed)",
        "status": "confirmatory",
        "asymmetric_rule": True,
        "ch3_ref": "Table 18 p.177; p.191, p.195",
    },
    {
        "id": "A-H8",
        "rank": 8,
        "alpha": _ALPHA_BY_RANK[8],
        "comparison": "HELIOS-Full vs HELIOS-noStructural",
        "primary_metric": "HR@3",
        "test": "wilcoxon_signed_rank",
        "direction": "a > b",
        "stratum": None,
        "expected_effect": "delta HR@3 >= 0.08 (underpowered, disclosed)",
        "status": "confirmatory",
        "asymmetric_rule": True,
        "ch3_ref": "Table 18 p.180; p.191, p.195",
    },
]

# ---------------------------------------------------------------------------
# Family B — baseline comparison (confirmatory, separate Holm family).
# Five baselines from the RCAEval suite (D5), in the priority order agreed with
# the dissertation chair (deviation entry 36). A baseline that cannot run on the
# pool is replaced by BASELINE_ALTERNATES in order, logged before the build
# freeze. "Best baseline" = the baseline with the highest HR@3 on the pool.
# ---------------------------------------------------------------------------
BASELINES: tuple[str, ...] = (
    "Multi-source BARO",
    "TraceRCA",
    "BARO (metrics only)",
    "PDiagnose",
    "Multi-source RCD",
)
BASELINE_ALTERNATES: tuple[str, ...] = ("CIRCA (metrics only)", "CausalRCA")

FAMILY_B_HYPOTHESES: list[Hypothesis] = [
    *[
        {
            "id": f"B-H{k}",
            "rank": k,
            "alpha": _ALPHA_BY_RANK[k],
            "comparison": f"HELIOS-Full vs BASELINE-{k}",
            "baseline": BASELINES[k - 1],
            "primary_metric": "HR@3 (paired binary)",
            "test": "mcnemar_exact_mid_p",
            "direction": "a > b",
            "stratum": None,
            "expected_effect": "powered region p_disc >= 0.30 with r >= 0.70",
            "status": "confirmatory",
            "asymmetric_rule": True,
            "ch3_ref": "Table 18 p.173; Panel D p.200-201; clarification D6 item 8",
        }
        for k in range(1, 6)
    ],
    {
        "id": "B-H7",
        "rank": 6,
        "alpha": _ALPHA_BY_RANK[6],
        "comparison": "BEST-BASELINE vs HELIOS-Full",
        "baseline": "best baseline",
        "primary_metric": "log-CpR",
        "test": "wilcoxon_signed_rank",
        "direction": "a > b",
        "stratum": None,
        "expected_effect": "delta = 0.80 (HELIOS costs less)",
        "status": "confirmatory",
        "asymmetric_rule": False,
        "ch3_ref": "Table 18 p.174",
    },
    {
        "id": "B-H6",
        "rank": 7,
        "alpha": _ALPHA_BY_RANK[7],
        "comparison": "BEST-BASELINE vs HELIOS-Full",
        "baseline": "best baseline",
        "primary_metric": "log time to correct diagnosis",
        "test": "wilcoxon_signed_rank",
        "direction": "a > b",
        "stratum": None,
        "expected_effect": "delta = 0.60 (HELIOS diagnoses faster)",
        "status": "confirmatory",
        "asymmetric_rule": False,
        "ch3_ref": "Table 18 p.174; D10 (deviation 29) replaces log-MTTR on recorded data",
    },
    {
        "id": "B-H8",
        "rank": 8,
        "alpha": _ALPHA_BY_RANK[8],
        "comparison": "HELIOS-Full vs BEST-BASELINE",
        "baseline": "best baseline",
        "primary_metric": "Avg@5",
        "test": "wilcoxon_signed_rank",
        "direction": "a > b",
        "stratum": None,
        "expected_effect": "delta Avg@5 >= 0.10",
        "status": "confirmatory",
        "asymmetric_rule": False,
        "ch3_ref": "Table 18 p.175; Avg@5 defined in the metric contract (D6 item 2)",
    },
]

# ---------------------------------------------------------------------------
# Family E — exploratory (point estimates + BCa intervals; never Holm-corrected).
# "stage": A = in the evidence build if ready by the freeze; B = Stage B.
# ---------------------------------------------------------------------------
FAMILY_E_HYPOTHESES: list[Hypothesis] = [
    {
        "id": "E-H1",
        "comparison": "HELIOS-Full vs HELIOS-noCogni",
        "primary_metric": "HR@3 on Tier-4 cognitive faults",
        "method": "bca",
        "stage": "B",
        "status": "exploratory",
        "ch3_ref": "Table 18 p.181",
    },
    {
        "id": "E-H2",
        "comparison": "HELIOS-noRouter vs HELIOS-Full",
        "primary_metric": "time to triage",
        "method": "bca",
        "stage": "A",
        "status": "exploratory",
        "ch3_ref": "Table 18 p.182",
    },
    {
        "id": "E-H3",
        "comparison": "HELIOS-Full vs HELIOS-noACP",
        "primary_metric": "latency-constraint satisfaction",
        "method": "bca",
        "stage": None,
        "status": "retired",
        "ch3_ref": "Table 18 p.183; duplicate of E-H8 (D6 item 5)",
    },
    {
        "id": "E-H4",
        "comparison": "HELIOS-noFGSV vs HELIOS-Full",
        "primary_metric": "false-accept rate under fidelity-break perturbation",
        "method": "bca",
        "stage": "A (lite, if built) / B (full twin)",
        "status": "exploratory",
        "ch3_ref": "Table 18 p.184",
    },
    {
        "id": "E-H5",
        "comparison": "HELIOS-noReconcile vs HELIOS-Full",
        "primary_metric": "reward reconciliation error on the delayed-label subset",
        "method": "bca",
        "stage": "A",
        "status": "exploratory",
        "ch3_ref": "Table 18 p.185",
    },
    {
        "id": "E-H6",
        "comparison": "HELIOS-noIOL vs HELIOS-Full",
        "primary_metric": "detection latency under injected control-plane degradation",
        "method": "bca",
        "stage": "A (lite, if built) / B (full)",
        "status": "exploratory",
        "ch3_ref": "Table 18 p.176",
    },
    {
        "id": "E-H7",
        "comparison": "HELIOS-Full vs HELIOS-noExpl",
        "primary_metric": "correct interpretation; time to decision; trust (RQ4 user study)",
        "method": "wilcoxon_paired_with_bca",
        "stage": "A (if IRB approved)",
        "status": "exploratory",
        "ch3_ref": "Table 18 p.189; p.163-165; D6 items 10 and 12",
    },
    {
        "id": "E-H8",
        "comparison": "HELIOS-Full vs HELIOS-noACP",
        "primary_metric": "latency-constraint satisfaction",
        "method": "bca",
        "stage": "A",
        "status": "exploratory",
        "ch3_ref": "Table 18 p.186",
    },
    {
        "id": "E-H9",
        "comparison": "HELIOS-HIS3 vs HELIOS-Full",
        "primary_metric": "per-incident latency by isolation tier",
        "method": "bca",
        "stage": "B",
        "status": "exploratory",
        "ch3_ref": "Table 18 p.187",
    },
    {
        "id": "E-H10",
        "comparison": "HELIOS-Full vs HELIOS-noStructural",
        "primary_metric": "delta HR@3 attributed across the structural sub-mechanisms",
        "method": "descriptive_with_bca",
        "stage": "A",
        "status": "exploratory",
        "ch3_ref": "Table 18 p.188",
    },
]

# ---------------------------------------------------------------------------
# Analysis settings (pre-registered with the tables above)
# ---------------------------------------------------------------------------
ANALYSIS_SETTINGS: dict[str, str | int | float | list[str]] = {
    "family_alpha": 0.05,
    "alpha_at_rank_1": _ALPHA_BY_RANK[1],
    "multiplicity": (
        "Holm-Bonferroni step-down, applied separately to Family A and Family B "
        "over all 8 hypotheses each; a hypothesis that cannot be tested counts as "
        "not rejected and is never dropped from its family"
    ),
    "sidedness": "one-sided in the pre-registered direction",
    "asymmetric_rule": (
        "for hypotheses flagged asymmetric_rule, a non-rejection is reported as "
        "inconclusive at delivered power, not as evidence of no effect (p.191, p.195)"
    ),
    "unit_of_analysis": "case, paired across variants and baselines (D11)",
    "effect_size_commitment": "Cohen h >= 0.276 (n = 73 required, 84 with attrition)",
    "baseline_hr_at_3": (
        "CHASE adjusted to AIOpsLab: 0.60, agreed with the chair (D6 item 1); "
        "0.61 (sum of the stated components) reported in the sensitivity band"
    ),
    "target_hr_at_3": 0.73,
    "cell_inclusion_rule": "a variant x system x metric cell needs >= 80% of its cases included",
    "effect_reporting": [
        "BCa interval, 10,000 resamples, seeds from the seed register",
        "Cliff's delta with every Wilcoxon test",
        "Hodges-Lehmann estimate for every paired difference",
    ],
    "sensitivity_analyses": [
        "Wilcoxon on group-level means (78 service x fault groups)",
        "rank-based mixed model with a random intercept per group; ICC reported",
        "Benjamini-Hochberg at q = 0.05",
        "paired t-test on log values for B-H6, B-H7, B-H8",
        "MCAR test and inverse-probability weighting for exclusions",
    ],
    "sanity_floors": [
        "random ranking over all services of the system",
        "prior-only: random ranking of the 5 injected services (HR@3 = 0.60)",
        "HELIOS-D alone",
    ],
    "strata": [
        "ambiguous (A-H4) and narrative_heavy (A-H6): operational definitions in docs/tracking/metric_contract.md",
    ],
}

# ---------------------------------------------------------------------------
# Variant -> hypotheses (written into variant_hashes.json)
# ---------------------------------------------------------------------------
_VARIANT_HYPOTHESIS_MAP: dict[str, str] = {
    "HELIOS-Full": "A-H1, A-H2, A-H3, A-H4, A-H5, A-H6, A-H7, A-H8, B-H1..B-H8",
    "HELIOS-noLLM": "A-H1, A-H7",
    "HELIOS-LLM-only": "A-H2",
    "HELIOS-D": "A-H3",
    "HELIOS-noConsensus": "A-H4",
    "HELIOS-noRouter": "A-H5, E-H2",
    "HELIOS-G": "A-H6",
    "HELIOS-noStructural": "A-H8, E-H10",
}

_VARIANT_STATUS_MAP: dict[str, str] = dict.fromkeys(
    _VARIANT_HYPOTHESIS_MAP, "confirmatory"
)


def _hypothesis_for_variant(name: str) -> str:
    return _VARIANT_HYPOTHESIS_MAP.get(name, "")


def _status_for_variant(name: str) -> str:
    return _VARIANT_STATUS_MAP.get(name, "exploratory")
