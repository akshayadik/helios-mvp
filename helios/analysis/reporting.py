"""S5 reporting rules over the analysis case tables (deviation entries 93-96).

None of these rules changes a hypothesis, a test or a Holm decision; each adds
what the report must show beside a result:

- entry 93 (CR-09): comparisons that need the incident graph are untestable
  on a system whose captures carry no traces;
- entry 94 (CR-10): the censored share and run-to-run timing noise beside
  every timing-derived result;
- entry 95 (CR-11): HR@1 and MRR as exploratory columns beside each HR@3 test;
- entry 96 (CR-23): the determinism rerun of a baseline (Multi-source RCD
  beside B-H5 and, when it is the best baseline, B-H8).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from helios.analysis.stats import bca_mean
from helios.research.seeds import bca_seed
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "EXPLORATORY_HR_KEYS",
    "GRAPH_HYPOTHESES",
    "NO_TRACES_REASON",
    "RERUN_METRICS",
    "S54_TIMING_P_MOVEMENT",
    "TIMING_KEYS",
    "TIMING_NOISE_STATEMENT",
    "apps_without_traces",
    "censored_share",
    "hr_exploratory_columns",
    "noise_reading",
    "rerun_determinism",
    "substitute_reruns",
    "trace_coverage",
]

HELIOS_ENABLE_ANALYSIS_REPORTING: bool = True

# Entry 93: comparisons whose two variants differ only in mechanisms that read
# the incident graph (G-pipe, l2b_graph, ueg_structural).
GRAPH_HYPOTHESES = frozenset({"A-H6", "A-H8", "E-H10"})
NO_TRACES_REASON = "no traces, no incident graph (entry 93)"

# Entry 94: case-table fields of timing-derived results (CpR's opportunity
# term is priced on TTCD).
TIMING_KEYS = frozenset({"log_cpr", "log_ttcd", "ttt_ms"})
# S5.4 replication on build data, OTel B-H7: p about 0.038 -> about 0.099.
S54_TIMING_P_MOVEMENT = 0.061
TIMING_NOISE_STATEMENT = (
    "Timing-derived results carry run-to-run noise: in the S5.4 replication "
    "(identical code, data and seeds) every accuracy result was identical while "
    "timing-derived p-values moved by up to about 0.06 (OTel B-H7, about 0.038 "
    "to about 0.099). The censored share is the fraction of runs whose TTCD hit "
    "the 1,800 s cap."
)

# Entry 95: exploratory columns beside each HR@3 test.
EXPLORATORY_HR_KEYS = ("hr_at_1", "mrr")

# Entry 96: what a determinism rerun is compared on.
RERUN_METRICS = ("hr_at_1", "hr_at_3", "avg_at_5", "mrr")

CaseRows = dict[str, dict[str, Any]]  # case -> fields


def _share(flags: Sequence[bool]) -> float | None:
    return sum(flags) / len(flags) if flags else None


# ── entry 93 ────────────────────────────────────────────────────────────────


def trace_coverage(
    apps: Mapping[str, str], traced: Mapping[str, bool]
) -> dict[str, dict[str, int]]:
    """Per system: cases, cases whose capture carries traces, cases with no
    capture read. ``traced`` maps case -> whether its sealed capture has spans."""
    out: dict[str, dict[str, int]] = {}
    for case, app in apps.items():
        row = out.setdefault(app, {"cases": 0, "with_traces": 0, "capture_missing": 0})
        row["cases"] += 1
        if case not in traced:
            row["capture_missing"] += 1
        elif traced[case]:
            row["with_traces"] += 1
    return dict(sorted(out.items()))


def apps_without_traces(coverage: Mapping[str, Mapping[str, int]]) -> set[str]:
    """Systems none of whose captures carries traces (entry 93 item 1).

    Only a system whose every capture was read qualifies: an unread capture
    leaves trace presence unknown, which is never taken as "no traces"."""
    return {
        app
        for app, row in coverage.items()
        if row["with_traces"] == 0 and row["capture_missing"] == 0
    }


# ── entry 94 ────────────────────────────────────────────────────────────────


def censored_share(
    rows: Mapping[str, Mapping[str, Any]],
    cases: Sequence[str],
    apps: Mapping[str, str],
) -> dict[str, Any]:
    """Share of ``cases`` whose run hit the TTCD cap, overall and per system."""
    flags = {c: bool(rows[c].get("ttcd_censored")) for c in cases if c in rows}
    by_app: dict[str, list[bool]] = {}
    for c, f in flags.items():
        by_app.setdefault(apps.get(c, "?"), []).append(f)
    return {
        "n": len(flags),
        "share": _share(list(flags.values())),
        "by_system": {a: _share(v) for a, v in sorted(by_app.items())},
    }


def substitute_reruns(
    key: str,
    a_vals: Mapping[str, float],
    b_vals: Mapping[str, float],
    cases: Sequence[str],
    rerun_a: Mapping[str, Mapping[str, Any]],
    rerun_b: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, float], dict[str, float], int]:
    """The pairs with each side's rerun value in place of its first run where
    a rerun exists; returns both sides and how many cases changed source."""
    a2, b2, n = dict(a_vals), dict(b_vals), 0
    for c in cases:
        hit = False
        for src, dst in ((rerun_a, a2), (rerun_b, b2)):
            value = src.get(c, {}).get(key)
            if value is not None:
                dst[c] = float(value)
                hit = True
        n += hit
    return a2, b2, n


def noise_reading(
    p_value: float | None,
    threshold: float | None,
    p_with_reruns: float | None,
) -> dict[str, Any]:
    """Entry 94 item 4: is the p-value within the observed movement of its
    threshold? The movement is the larger of the S5.4 build figure and, when
    reruns exist, this result's own movement with rerun values substituted."""
    own = (
        abs(p_value - p_with_reruns)
        if p_value is not None and p_with_reruns is not None
        else None
    )
    movement = max(S54_TIMING_P_MOVEMENT, own or float(0))
    out: dict[str, Any] = {
        "p_with_reruns": p_with_reruns,
        "rerun_p_movement": own,
        "build_p_movement": S54_TIMING_P_MOVEMENT,
        "threshold": threshold,
        "sensitive_to_timing_noise": None,
    }
    if p_value is not None and threshold is not None:
        out["sensitive_to_timing_noise"] = abs(p_value - threshold) <= movement
        if p_with_reruns is not None:
            out["crosses_threshold_with_reruns"] = (p_value <= threshold) != (
                p_with_reruns <= threshold
            )
    return out


# ── entry 95 ────────────────────────────────────────────────────────────────


def hr_exploratory_columns(
    hid: str,
    a_rows: Mapping[str, Mapping[str, Any]],
    b_rows: Mapping[str, Mapping[str, Any]],
    cases: Sequence[str],
    apps: Mapping[str, str],
) -> dict[str, Any]:
    """HR@1 and MRR beside an HR@3 test, on the test's own cases: each side's
    mean per system, and the paired difference with a BCa interval. Also the
    HR@3 discordant pairs. No p-value; outside every Holm family."""
    out: dict[str, Any] = {
        "status": "exploratory, descriptive (entry 95)",
        "hr_at_3_discordant_pairs": sum(
            1
            for c in cases
            if a_rows[c].get("hr_at_3") is not None
            and b_rows[c].get("hr_at_3") is not None
            and a_rows[c]["hr_at_3"] != b_rows[c]["hr_at_3"]
        ),
    }
    seed = bca_seed(hid)
    for key in EXPLORATORY_HR_KEYS:
        both = [
            c
            for c in cases
            if a_rows[c].get(key) is not None and b_rows[c].get(key) is not None
        ]
        if not both:
            out[key] = {"n": 0}
            continue
        a = {c: float(a_rows[c][key]) for c in both}
        b = {c: float(b_rows[c][key]) for c in both}
        by_app: dict[str, list[str]] = {}
        for c in both:
            by_app.setdefault(apps.get(c, "?"), []).append(c)
        bca = bca_mean([a[c] - b[c] for c in both], seed)
        out[key] = {
            "n": len(both),
            "mean_a": float(np.mean(list(a.values()))),
            "mean_b": float(np.mean(list(b.values()))),
            "by_system": {
                app: {
                    "n": len(cs),
                    "mean_a": float(np.mean([a[c] for c in cs])),
                    "mean_b": float(np.mean([b[c] for c in cs])),
                }
                for app, cs in sorted(by_app.items())
            },
            "mean_difference": bca.estimate,
            "bca_low": bca.low,
            "bca_high": bca.high,
            "bca_seed": bca.seed,
        }
    return out


# ── entry 96 ────────────────────────────────────────────────────────────────


def rerun_determinism(
    first: Mapping[str, Mapping[str, Mapping[str, Any]]],
    again: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> dict[str, dict[str, Any]]:
    """Per system with reruns: pairs compared, the share whose output was
    identical (the campaign's rerun compare, eval_run.nondeterministic), and
    per metric how many pairs changed and the mean absolute change."""
    out: dict[str, dict[str, Any]] = {}
    for system in sorted(again):
        rows = first.get(system, {})
        pairs = sorted(rows.keys() & again[system].keys())
        if not pairs:
            continue
        flags = [
            bool(rows[c]["nondeterministic"])
            for c in pairs
            if rows[c].get("nondeterministic") is not None
        ]
        share_nd = _share(flags)
        entry: dict[str, Any] = {
            "pairs": len(pairs),
            "compared": len(flags),
            "identical_share": None if share_nd is None else 1 - share_nd,
        }
        for key in RERUN_METRICS:
            diffs = [
                abs(float(again[system][c][key]) - float(rows[c][key]))
                for c in pairs
                if rows[c].get(key) is not None
                and again[system][c].get(key) is not None
            ]
            entry[key] = {
                "n": len(diffs),
                "changed": sum(d > 0 for d in diffs),
                "mean_abs_change": float(np.mean(diffs)) if diffs else None,
            }
        out[system] = entry
    return out
