"""Frozen hypothesis tables — single source of truth for OSF pre-registration.

Changes require a deviation log entry.
FAMILY_A_HYPOTHESES and FAMILY_B_HYPOTHESES are consumed by
verify_osf_freeze.py --generate to produce analysis_plan.json.
"""

from __future__ import annotations

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

HELIOS_ENABLE_RESEARCH_ANALYSIS_PLAN: bool = True

# Holm-Bonferroni ranks: rank 1 is most critical (strictest threshold).
# alpha(rank) = family_alpha / (n_hypotheses - rank + 1) = 0.05 / (9 - rank).
# Exact per-rank alphas: rank1=0.00625, rank2=0.007143, rank3=0.008333,
# rank4=0.01, rank5=0.0125, rank6=0.016667, rank7=0.025, rank8=0.05
FAMILY_A_HYPOTHESES: list[dict[str, str | int | float | None]] = [
    {
        "id": "A-H3",
        "rank": 1,
        "comparison": "HELIOS-Full vs HELIOS-D",
        "primary_metric": "HR@3",
        "alpha": 0.00625,
        "filter": None,
        "status": "confirmatory",
    },
    {
        "id": "A-H7",
        "rank": 2,
        "comparison": "HELIOS-Full vs HELIOS-noLLM",
        "primary_metric": "HR@3",
        "alpha": 0.007143,
        "filter": None,
        "status": "confirmatory",
    },
    {
        "id": "A-H1",
        "rank": 3,
        "comparison": "HELIOS-Full vs baseline (fixed threshold)",
        "primary_metric": "HR@3",
        "alpha": 0.008333,
        "filter": None,
        "status": "confirmatory",
    },
    {
        "id": "A-H2",
        "rank": 4,
        "comparison": "HELIOS-Full vs HELIOS-noGraph",
        "primary_metric": "CpR",
        "alpha": 0.01,
        "filter": None,
        "status": "confirmatory",
    },
    {
        "id": "A-H6",
        "rank": 5,
        "comparison": "HELIOS-G vs HELIOS-D (gate-conditional)",
        "primary_metric": "HR@3",
        "alpha": 0.0125,
        "filter": "narrative != 'gpipe-gated-or-skipped'",
        "status": "confirmatory",
    },
    {
        "id": "A-H5",
        "rank": 6,
        "comparison": "HELIOS-Full vs HELIOS-noRouter",
        "primary_metric": "HR@3",
        "alpha": 0.016667,
        "filter": None,
        "status": "confirmatory",
    },
    {
        "id": "A-H4",
        "rank": 7,
        "comparison": "HELIOS-Full vs HELIOS-noConsensus",
        "primary_metric": "HR@3",
        "alpha": 0.025,
        "filter": None,
        "status": "exploratory",
    },
    {
        "id": "A-H8",
        "rank": 8,
        "comparison": "HELIOS-Full vs HELIOS-noStructural",
        "primary_metric": "HR@3",
        "alpha": 0.05,
        "filter": None,
        "status": "exploratory",
    },
]

# B-family: external baseline comparisons. Not derived from _VARIANT_HYPOTHESIS_MAP.
# B-H2 and B-H4 use RCACopilot as baseline; all others use CHASE.
# B-H7 primary_metric is "CoE score" (§2.2 Primary metric column, not "CoE quality").
FAMILY_B_HYPOTHESES: list[dict[str, str | int]] = [
    {
        "id": "B-H1",
        "rank": 1,
        "comparison": "HELIOS-Full vs CHASE",
        "primary_metric": "HR@3",
        "status": "deferred",
        "baseline": "CHASE",
        "note": "AIOpsLab corpus pending",
    },
    {
        "id": "B-H2",
        "rank": 2,
        "comparison": "HELIOS-Full vs RCACopilot",
        "primary_metric": "HR@3",
        "status": "deferred",
        "baseline": "RCACopilot",
        "note": "AIOpsLab corpus pending",
    },
    {
        "id": "B-H3",
        "rank": 3,
        "comparison": "HELIOS-Full vs CHASE",
        "primary_metric": "CpR",
        "status": "deferred",
        "baseline": "CHASE",
        "note": "AIOpsLab corpus pending",
    },
    {
        "id": "B-H4",
        "rank": 4,
        "comparison": "HELIOS-Full vs RCACopilot",
        "primary_metric": "CpR",
        "status": "deferred",
        "baseline": "RCACopilot",
        "note": "AIOpsLab corpus pending",
    },
    {
        "id": "B-H5",
        "rank": 5,
        "comparison": "HELIOS-Full vs CHASE",
        "primary_metric": "log-MTTR delta",
        "status": "deferred",
        "baseline": "CHASE",
        "note": "AIOpsLab corpus pending",
    },
    {
        "id": "B-H6",
        "rank": 6,
        "comparison": "HELIOS-Full vs CHASE",
        "primary_metric": "hallucination rate",
        "status": "deferred",
        "baseline": "CHASE",
        "note": "AIOpsLab corpus pending",
    },
    {
        "id": "B-H7",
        "rank": 7,
        "comparison": "HELIOS-Full vs CHASE",
        "primary_metric": "CoE score",
        "status": "deferred",
        "baseline": "CHASE",
        "note": "AIOpsLab corpus pending",
    },
    {
        "id": "B-H8",
        "rank": 8,
        "comparison": "HELIOS-Full vs CHASE",
        "primary_metric": "macro-F1",
        "status": "deferred",
        "baseline": "CHASE",
        "note": "AIOpsLab corpus pending",
    },
]

_VARIANT_HYPOTHESIS_MAP: dict[str, str] = {
    "HELIOS-Full": "A-H1, A-H2, A-H3, A-H4, A-H5, A-H7, A-H8",
    "HELIOS-noLLM": "A-H7",
    "HELIOS-noGraph": "A-H2",
    "HELIOS-D": "A-H3, A-H6",
    "HELIOS-G": "A-H6",
    "HELIOS-noConsensus": "A-H4",
    "HELIOS-noRouter": "A-H5",
    "HELIOS-noStructural": "A-H8",
}

_VARIANT_STATUS_MAP: dict[str, str] = {
    "HELIOS-Full": "confirmatory",
    "HELIOS-noLLM": "confirmatory",
    "HELIOS-noGraph": "confirmatory",
    "HELIOS-D": "confirmatory",
    "HELIOS-G": "cond. confirmatory",
    "HELIOS-noConsensus": "exploratory",
    "HELIOS-noRouter": "exploratory",
    "HELIOS-noStructural": "exploratory",
}


def _hypothesis_for_variant(name: str) -> str:
    return _VARIANT_HYPOTHESIS_MAP.get(name, "")


def _status_for_variant(name: str) -> str:
    return _VARIANT_STATUS_MAP.get(name, "exploratory")
