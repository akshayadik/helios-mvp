"""Run the registered analysis over the harness-written eval tables (S4.11).

Inputs are ``eval_score`` (fused lists) and ``eval_run`` rows only (contract
§10, entry 84), joined by run_id and keyed by (variant, case): one run per case
and variant (D11). Hypotheses, ranks, alphas, directions, strata and settings
come from ``helios.research.analysis_plan`` and are never changed here.

Rules are those of the S4.11 design note (T-a to T-j). A run is confirmatory
only when the guard passes (T-i); otherwise every output is labelled
exploratory and carries no "rejected" wording.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from helios.analysis.missing import ipw_effect, mcar_test
from helios.analysis.sensitivity import group_differences, rank_mixed_model
from helios.analysis.stats import (
    MultiplicityRow,
    TestResult,
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
from helios.evaluation.cells import (
    CELL_METRICS,
    CellTable,
    cell_table,
    passing_apps,
)
from helios.evaluation.run_metrics import METRICS_VERSION
from helios.evaluation.scoring import SCORING_VERSION
from helios.orchestrator.schedule import TRIGGER_SUFFIX
from helios.research.analysis_plan import (
    ANALYSIS_SETTINGS,
    BASELINES,
    FAMILY_A_HYPOTHESES,
    FAMILY_B_HYPOTHESES,
    FAMILY_E_HYPOTHESES,
)
from helios.research.seeds import bca_seed
from helios.telemetry.pool_lock import build_frozen
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.variants import CONFIRMATORY_VARIANTS, EXPLORATORY_VARIANTS

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Mapping, Sequence

__all__ = [
    "ANALYSIS_VERSION",
    "A_H7_MODES",
    "HOLM_READINGS",
    "CaseTable",
    "Guard",
    "analyse",
    "build_case_table",
    "confirmatory_guard",
    "e_h5_forms",
    "sanity_floors",
    "variant_names",
]

HELIOS_ENABLE_ANALYSIS_RUN: bool = True

ANALYSIS_VERSION = "analysis-v1"
HOLM_READINGS = ("data_order", "fixed_sequence")  # T-a (a), (b)
A_H7_MODES = ("intersection_union", "h_fact_only", "sum")  # T-c (a), (b), (c)
PRIOR_SERVICES = 5  # prior-only floor: the 5 injected services (contract §8)
HR_KS = (1, 3, 10)

# primary_metric string in the plan -> (case-table field, test)
_METRICS: dict[str, tuple[str, str]] = {
    "HR@3": ("hr_at_3", "wilcoxon_signed_rank"),
    "HR@3 (paired binary)": ("hr_at_3", "mcnemar_exact_mid_p"),
    "log-CpR at matched HR@3": ("log_cpr", "wilcoxon_signed_rank"),
    "log-CpR": ("log_cpr", "wilcoxon_signed_rank"),
    "log time to correct diagnosis": ("log_ttcd", "wilcoxon_signed_rank"),
    "Avg@5": ("avg_at_5", "wilcoxon_signed_rank"),
    "H_fact, H_struct": ("h_fact", "sign_test"),
}
# Family E items that the eval tables can measure (others: not built / Stage B)
_E_METRICS: dict[str, str] = {"E-H2": "ttt_ms", "E-H10": "hr_at_3"}
_BINARY = frozenset({"hr_at_3"})
# S4.8 B-k: the published-score anchor (entry 36; 0.61 in the sensitivity band).
CHASE_HR_AT_3 = 0.60
CHASE_BAND = 0.61
TTCD_CENSOR_S = 1800  # metric contract §4 (Ch3's incident window)
_CELL_KEYS = frozenset(CELL_METRICS)
_SCORE_FIELDS = ("hr_at_1", "hr_at_3", "hr_at_10", "avg_at_5", "mrr", "corpus")
_LOG_T = frozenset({"B-H6", "B-H7"})  # paired t on log values (T-g)
_RAW_T = frozenset({"B-H8"})  # Avg@5 is not a log quantity

CaseTable = dict[str, dict[str, dict[str, Any]]]  # variant -> case -> fields


def variant_names() -> dict[str, str]:
    """variant_config_hash -> variant name, over all 15 variants."""
    out: dict[str, str] = {}
    for name, manifest in {**CONFIRMATORY_VARIANTS, **EXPLORATORY_VARIANTS}.items():
        out[manifest.compute_variant_config_hash()] = name
    return out


def build_case_table(
    scores: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    names: Mapping[str, str],
) -> CaseTable:
    """Join fused eval_score rows with eval_run rows by run_id.

    Baseline rows (S4.8) carry their baseline name as ``source`` and no
    variant hash. Two runs of one (variant, case) are an integrity error.
    """
    by_run = {str(r["run_id"]): r for r in runs}
    table: CaseTable = {}
    for s in scores:
        if s["list_kind"] != "fused":
            continue
        vhash = s.get("variant_config_hash")
        name = names.get(str(vhash)) if vhash else str(s["source"])
        if name is None:
            raise ValueError(f"unknown variant hash {str(vhash)[:12]}")
        case = str(s["incident_id"])
        if case in table.get(name, {}):
            raise ValueError(f"two runs of {name} on one case")
        row: dict[str, Any] = dict(by_run.get(str(s["run_id"]), {}))
        row.update({k: s[k] for k in _SCORE_FIELDS})
        ttcd = row.get("ttcd_s")
        row["log_ttcd"] = math.log(ttcd) if ttcd is not None and ttcd > 0 else None
        table.setdefault(name, {})[case] = row
    return table


@dataclass(frozen=True)
class Guard:
    """Whether a run may be labelled confirmatory, and why not."""

    confirmatory: bool
    reasons: tuple[str, ...]


def confirmatory_guard(
    scores: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    *,
    frozen: Callable[[], bool] = build_frozen,
) -> Guard:
    """T-i: pool corpus, build-freeze, known variant hashes, current versions."""
    reasons: list[str] = []
    corpora = {str(r["corpus"]) for r in [*scores, *runs]}
    if corpora != {"pool"}:
        reasons.append(f"corpus is {sorted(corpora)}, not the pool")
    if not frozen():
        reasons.append("tag build-freeze does not exist")
    known = {m.compute_variant_config_hash() for m in CONFIRMATORY_VARIANTS.values()}
    hashes = {str(r["variant_config_hash"]) for r in runs}
    if not hashes <= known:
        reasons.append("a run's variant hash is not a confirmatory variant")
    if {str(s["scoring_version"]) for s in scores} - {SCORING_VERSION}:
        reasons.append("scoring version differs from the frozen one")
    if {str(r["metrics_version"]) for r in runs} - {METRICS_VERSION}:
        reasons.append("metrics version differs from the frozen one")
    return Guard(not reasons, tuple(reasons))


# ── helpers ─────────────────────────────────────────────────────────────────


def _sides(comparison: str) -> tuple[str, str]:
    a, b = (part.strip() for part in comparison.split(" vs "))
    return a, b


def _resolve(side: str, table: CaseTable) -> str | None:
    if side.startswith("BASELINE-"):
        name = BASELINES[int(side.split("-")[1]) - 1]
        return name if name in table else None
    if side == "BEST-BASELINE":
        present = [b for b in BASELINES if b in table]
        if not present:
            return None
        return max(present, key=lambda b: (_mean(table[b], "hr_at_3"), b))
    return side if side in table else None


def _mean(rows: Mapping[str, Mapping[str, Any]], key: str) -> float:
    values = [float(r[key]) for r in rows.values() if r.get(key) is not None]
    return float(np.mean(values)) if values else float("-inf")


def _values(rows: Mapping[str, Mapping[str, Any]], key: str) -> dict[str, float]:
    return {c: float(r[key]) for c, r in rows.items() if r.get(key) is not None}


def _stratum_cases(table: CaseTable, stratum: str | None) -> set[str] | None:
    if stratum is None:
        return None
    full = table.get("HELIOS-Full", {})
    return {c for c, r in full.items() if r.get(stratum) is True}


def _effects(
    hid: str, a: Mapping[str, float], b: Mapping[str, float], cases: list[str]
) -> dict[str, Any]:
    diffs = [a[c] - b[c] for c in cases]
    bca = bca_mean(diffs, bca_seed(hid))
    out: dict[str, Any] = {
        "mean_a": float(np.mean([a[c] for c in cases])),
        "mean_b": float(np.mean([b[c] for c in cases])),
        "mean_difference": bca.estimate,
        "bca_low": bca.low,
        "bca_high": bca.high,
        "bca_note": bca.note,
        "bca_seed": bca.seed,
        "hodges_lehmann": hodges_lehmann(diffs),
        "cliffs_delta": cliffs_delta([a[c] for c in cases], [b[c] for c in cases]),
    }
    if all(a[c] in (0, 1) and b[c] in (0, 1) for c in cases):
        out["cohens_h"] = cohens_h(out["mean_a"], out["mean_b"])
    return out


def _test(
    test: str, a: Mapping[str, float], b: Mapping[str, float], cases: list[str]
) -> TestResult:
    if test == "mcnemar_exact_mid_p":
        return mcnemar_mid_p([int(a[c]) for c in cases], [int(b[c]) for c in cases])
    diffs = [a[c] - b[c] for c in cases]
    return sign_test(diffs) if test == "sign_test" else wilcoxon_exact(diffs)


@dataclass
class _Outcome:
    result: dict[str, Any]
    p_value: float | None
    pairs: dict[str, tuple[dict[str, float], dict[str, float], list[str]]] = field(
        default_factory=dict
    )


def _untestable(base: dict[str, Any], reason: str) -> _Outcome:
    base.update({"p_value": None, "untestable": reason})
    return _Outcome(base, None)


def _confirmatory_hypothesis(
    h: Mapping[str, Any],
    table: CaseTable,
    cells: CellTable,
    apps: Mapping[str, str],
    a_h7_mode: str,
) -> _Outcome:
    hid = str(h["id"])
    a_side, b_side = _sides(str(h["comparison"]))
    key, test = _METRICS[str(h["primary_metric"])]
    base: dict[str, Any] = {
        "id": hid,
        "rank": h["rank"],
        "comparison": h["comparison"],
        "metric": h["primary_metric"],
        "test": test,
        "stratum": h["stratum"],
        "asymmetric_rule": h["asymmetric_rule"],
    }
    a_name, b_name = _resolve(a_side, table), _resolve(b_side, table)
    base.update({"a": a_name, "b": b_name})
    if a_name is None or b_name is None:
        return _untestable(base, "a compared system has no runs")
    stratum = _stratum_cases(table, h["stratum"]) if h["stratum"] else None
    keys = ["h_fact", "h_struct"] if hid == "A-H7" else [key]
    if hid == "A-H7" and a_h7_mode == "h_fact_only":
        keys = ["h_fact"]
    per_key: dict[str, tuple[dict[str, float], dict[str, float], list[str]]] = {}
    for k in keys:
        a_vals, b_vals = _values(table[a_name], k), _values(table[b_name], k)
        cases = sorted(a_vals.keys() & b_vals.keys())
        if stratum is not None:
            cases = [c for c in cases if c in stratum]
        per_key[k] = (a_vals, b_vals, cases)
    # S4.10 O-e (a): only cases of the apps where both compared cells pass.
    ok_apps = {k: passing_apps(cells, a_name, b_name, k) for k in keys}
    base["apps_tested"] = dict(ok_apps)
    for k, (a_vals, b_vals, cases) in per_key.items():
        per_key[k] = (a_vals, b_vals, [c for c in cases if apps.get(c) in ok_apps[k]])
    if hid == "A-H7" and a_h7_mode == "sum":
        a_f, b_f, cf = per_key["h_fact"]
        a_s, b_s, cs = per_key["h_struct"]
        both = sorted(set(cf) & set(cs))
        per_key = {
            "h_fact+h_struct": (
                {c: a_f[c] + a_s[c] for c in both},
                {c: b_f[c] + b_s[c] for c in both},
                both,
            )
        }
    n_pairs = min(len(v[2]) for v in per_key.values())
    base["n_pairs"] = n_pairs
    if stratum is not None and not stratum:
        return _untestable(base, f"stratum {h['stratum']} is empty or not computed")
    missing = [
        k
        for k in keys
        if not _values(table[a_name], k) or not _values(table[b_name], k)
    ]
    if missing:
        return _untestable(base, f"no values for {', '.join(missing)} (not scored yet)")
    failed = [k for k in keys if not ok_apps[k]]
    if failed:
        return _untestable(
            base,
            f"cell rule: no system where both {a_name} and {b_name} have at "
            f"least 4/5 of their cases on {', '.join(failed)}",
        )
    if str(h["primary_metric"]).startswith("log-CpR at matched"):
        hr_a, hr_b = (
            _values(table[a_name], "hr_at_3"),
            _values(table[b_name], "hr_at_3"),
        )
        a_vals, b_vals, cases = per_key[key]
        matched = [c for c in cases if c in hr_a and c in hr_b and hr_a[c] == hr_b[c]]
        base["matched_share"] = len(matched) / len(cases) if cases else None
        base["n_matched"] = len(matched)
        per_key = {key: (a_vals, b_vals, matched)}
        if not matched:
            return _untestable(base, "no case with matched HR@3")
    tests: dict[str, dict[str, Any]] = {}
    for k, (a_vals, b_vals, cases) in per_key.items():
        res = _test(test, a_vals, b_vals, cases)
        tests[k] = {
            "statistic": res.statistic,
            "p_value": res.p_value,
            "n_pairs": res.n_pairs,
            "n_informative": res.n_informative,
            **(_effects(hid, a_vals, b_vals, cases) if cases else {}),
        }
    p = max(t["p_value"] for t in tests.values())  # IUT: the larger p (T-c a)
    base.update({"p_value": p, "by_measure": tests})
    if key in _BINARY and test == "wilcoxon_signed_rank":
        base["note"] = (
            "0/1 outcome: with zeros dropped the signed-rank test equals the exact "
            "sign test on discordant pairs (design T-b)"
        )
    if hid == "A-H7":
        base["a_h7_mode"] = a_h7_mode
    return _Outcome(base, p, per_key)


def _sensitivity(
    h: Mapping[str, Any],
    outcome: _Outcome,
    table: CaseTable,
    groups: Mapping[str, str],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if outcome.p_value is None or not outcome.pairs:
        return out
    hid = str(h["id"])
    _, (a_vals, b_vals, cases) = next(iter(outcome.pairs.items()))
    a_c = {c: a_vals[c] for c in cases}
    b_c = {c: b_vals[c] for c in cases}
    gdiffs = group_differences(a_c, b_c, groups)
    if gdiffs:
        g = wilcoxon_exact(gdiffs)
        out["group_level_wilcoxon"] = {"p_value": g.p_value, "n_groups": len(gdiffs)}
    mm = rank_mixed_model(a_c, b_c, groups)
    if mm is not None:
        out["rank_mixed_model"] = {
            "coefficient": mm.coefficient,
            "p_value": mm.p_value,
            "icc": mm.icc,
            "n_groups": mm.n_groups,
            "converged": mm.converged,
        }
    if hid in _LOG_T | _RAW_T:
        t = paired_t([a_c[c] - b_c[c] for c in cases])
        out["paired_t"] = {
            "p_value": t.p_value,
            "scale": "log" if hid in _LOG_T else "raw",
        }
    if str(h["primary_metric"]).startswith("log-CpR at matched"):
        a_name, b_name = outcome.result["a"], outcome.result["b"]
        av, bv = _values(table[a_name], "log_cpr"), _values(table[b_name], "log_cpr")
        all_cases = sorted(av.keys() & bv.keys())
        w = wilcoxon_exact([av[c] - bv[c] for c in all_cases])
        out["all_cases"] = {"p_value": w.p_value, "n_pairs": len(all_cases)}
    return out


def _missing_data(
    h: Mapping[str, Any],
    outcome: _Outcome,
    table: CaseTable,
    scheduled: Mapping[str, Collection[str]],
    covariates: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """S4.10 O-f: MCAR evidence and the IPW estimate over the scheduled pairs."""
    if outcome.p_value is None or not outcome.pairs:
        return {}
    hid = str(h["id"])
    a_name, b_name = outcome.result["a"], outcome.result["b"]
    key = next(iter(outcome.pairs))
    if key not in _CELL_KEYS:
        key = next(iter(outcome.result["apps_tested"]))
    a_vals, b_vals = _values(table[a_name], key), _values(table[b_name], key)
    ok = set(outcome.result["apps_tested"].get(key, []))
    sched = sorted(set(scheduled.get(a_name, ())) & set(scheduled.get(b_name, ())))
    stratum = _stratum_cases(table, h["stratum"]) if h["stratum"] else None
    if stratum is not None:
        sched = [c for c in sched if c in stratum]
    diffs = {
        c: a_vals[c] - b_vals[c]
        for c in sched
        if c in a_vals and c in b_vals and covariates.get(c, {}).get("app") in ok
    }
    missing = {c: c not in diffs for c in sched}
    return {
        "metric": key,
        "mcar": mcar_test(sched, missing, covariates),
        "ipw": ipw_effect(sched, diffs, covariates, bca_seed(hid)),
    }


def _splits(
    h: Mapping[str, Any], outcome: _Outcome, table: CaseTable
) -> dict[str, Any]:
    """Descriptive splits: A-H5 by stage, A-H1 by escalation, llm_unavailable."""
    out: dict[str, Any] = {}
    if outcome.p_value is None or not outcome.pairs:
        return out
    hid = str(h["id"])
    _, (a_vals, b_vals, cases) = next(iter(outcome.pairs.items()))
    full = table.get("HELIOS-Full", {})
    seed = bca_seed(hid)

    def describe(subset: list[str]) -> dict[str, Any]:
        if not subset:
            return {"n": 0}
        bca = bca_mean([a_vals[c] - b_vals[c] for c in subset], seed)
        return {
            "n": len(subset),
            "mean_difference": bca.estimate,
            "bca_low": bca.low,
            "bca_high": bca.high,
        }

    if hid in ("A-H5", "A-H1"):
        name = "by_stage" if hid == "A-H5" else "by_escalation"
        esc = [c for c in cases if full.get(c, {}).get("escalated") is True]
        stop = [c for c in cases if full.get(c, {}).get("escalated") is False]
        out[name] = {"escalated": describe(esc), "stopped": describe(stop)}
    a_name, b_name = outcome.result["a"], outcome.result["b"]
    affected = {
        c
        for c in cases
        if table[a_name].get(c, {}).get("llm_unavailable")
        or table[b_name].get(c, {}).get("llm_unavailable")
    }
    if affected:
        out["without_llm_unavailable"] = describe(
            [c for c in cases if c not in affected]
        )
    return out


def _family(
    hypotheses: Sequence[Mapping[str, Any]],
    table: CaseTable,
    cells: CellTable,
    apps: Mapping[str, str],
    groups: Mapping[str, str],
    *,
    a_h7_mode: str,
    holm: str,
    confirmatory: bool,
    scheduled: Mapping[str, Collection[str]],
    covariates: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Any]:
    outcomes = {
        str(h["id"]): _confirmatory_hypothesis(h, table, cells, apps, a_h7_mode)
        for h in hypotheses
    }
    ranks = {str(h["id"]): int(h["rank"]) for h in hypotheses}
    pvals = {hid: o.p_value for hid, o in outcomes.items()}
    alpha = float(str(ANALYSIS_SETTINGS["family_alpha"]))
    readings = {
        "data_order": holm_step_down(pvals, ranks, alpha),
        "fixed_sequence": holm_fixed_sequence(pvals, ranks, alpha),
    }
    binding = readings[holm]
    bh = benjamini_hochberg(pvals, ranks, alpha)
    verdict = "rejected" if confirmatory else "below_threshold_descriptive"

    def rows(mrows: list[MultiplicityRow]) -> list[dict[str, Any]]:
        return [
            {
                "id": r.hypothesis_id,
                "rank": r.rank,
                "p_value": r.p_value,
                "threshold": r.threshold,
                "adjusted_p": r.adjusted_p,
                verdict: r.rejected,
            }
            for r in mrows
        ]

    results = []
    decisions = {r.hypothesis_id: r.rejected for r in binding}
    for h in hypotheses:
        hid = str(h["id"])
        o = outcomes[hid]
        res = dict(o.result)
        res[verdict] = decisions[hid]
        if h["asymmetric_rule"] and not decisions[hid]:
            res["reading"] = "inconclusive at delivered power (asymmetric rule)"
        res["sensitivity"] = _sensitivity(h, o, table, groups)
        if covariates is not None:
            res["sensitivity"]["missing_data"] = _missing_data(
                h, o, table, scheduled, covariates
            )
        res["splits"] = _splits(h, o, table)
        results.append(res)
    return {
        "holm_reading": holm,
        "hypotheses": results,
        "holm_binding": rows(binding),
        "holm_other_reading": rows(
            readings[next(r for r in HOLM_READINGS if r != holm)]
        ),
        "benjamini_hochberg": rows(bh),
    }


def _family_e(table: CaseTable) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for h in FAMILY_E_HYPOTHESES:
        hid = str(h["id"])
        row: dict[str, Any] = {
            "id": hid,
            "comparison": h["comparison"],
            "metric": h["primary_metric"],
            "status": h["status"],
            "stage": h["stage"],
        }
        key = _E_METRICS.get(hid)
        a_side, b_side = _sides(str(h["comparison"]))
        if (
            h["status"] != "exploratory"
            or key is None
            or a_side not in table
            or b_side not in table
        ):
            row["available"] = False
            out.append(row)
            continue
        a_vals, b_vals = _values(table[a_side], key), _values(table[b_side], key)
        cases = sorted(a_vals.keys() & b_vals.keys())
        row["available"] = bool(cases)
        if cases:
            row.update({"n_pairs": len(cases), **_effects(hid, a_vals, b_vals, cases)})
        out.append(row)
    return out


def e_h5_forms(
    rre_full: Mapping[str, float], rre_no_reconcile: Mapping[str, float]
) -> dict[str, Any]:
    """E-H5 both forms (S3.3 design §6 item 3): registered (own case sets) and same-case."""
    seed = bca_seed("E-H5")
    a, b = list(rre_no_reconcile.values()), list(rre_full.values())
    registered = {
        "n_no_reconcile": len(a),
        "n_full": len(b),
        "mean_difference": float(np.mean(a) - np.mean(b)) if a and b else None,
    }
    common = sorted(rre_full.keys() & rre_no_reconcile.keys())
    same = (
        bca_mean([rre_no_reconcile[c] - rre_full[c] for c in common], seed)
        if common
        else None
    )
    return {
        "registered_form": registered,
        "same_case_form": (
            None
            if same is None
            else {
                "n": len(common),
                "mean_difference": same.estimate,
                "bca_low": same.low,
                "bca_high": same.high,
            }
        ),
    }


def sanity_floors(
    table: CaseTable, n_services: Mapping[str, int]
) -> dict[str, dict[str, float | None]]:
    """Contract §8 floors for HR@1, HR@3, HR@10 (T-h)."""
    out: dict[str, dict[str, float | None]] = {}
    d_rows = table.get("HELIOS-D", {})
    for k in HR_KS:
        cases = [c for c in n_services if n_services[c] > 0]
        random_floor = (
            float(np.mean([min(k, n_services[c]) / n_services[c] for c in cases]))
            if cases
            else None
        )
        d_vals = [
            float(r[f"hr_at_{k}"])
            for r in d_rows.values()
            if r.get(f"hr_at_{k}") is not None
        ]
        out[f"HR@{k}"] = {
            "random_all_services": random_floor,
            "prior_only": min(k, PRIOR_SERVICES) / PRIOR_SERVICES,
            "helios_d": float(np.mean(d_vals)) if d_vals else None,
        }
    return out


def _family_b_rows(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    verdict = next(
        k
        for k in ("rejected", "below_threshold_descriptive")
        if k in result["hypotheses"][0]
    )
    return [
        {
            "id": h["id"],
            "a": h.get("a"),
            "b": h.get("b"),
            "n_pairs": h.get("n_pairs"),
            "p_value": h.get("p_value"),
            verdict: h.get(verdict),
            **({"untestable": h["untestable"]} if "untestable" in h else {}),
        }
        for h in result["hypotheses"]
    ]


def family_b_sensitivity(
    table: CaseTable,
    apps: Mapping[str, str],
    groups: Mapping[str, str],
    scheduled: Mapping[str, Collection[str]],
    **kwargs: Any,
) -> dict[str, Any]:
    """S4.8 sensitivity rows for Family B (each reruns the whole family, so
    Holm applies as in the binding analysis), and the CHASE anchor (B-k).

    - ``trigger_time`` (B-b): every baseline replaced by its run with HELIOS's
      detection-trigger time instead of the injection time;
    - ``no_human_time`` (B-e): log-CpR without the human-review component on
      both sides (it changes only B-H7);
    - ``failures_as_misses`` (B-f): a scheduled baseline case with no run
      (excluded for a method error or timeout) counts as a miss: HR@3 and
      Avg@5 zero, TTCD censored; log-CpR stays missing.
    """
    kwargs = {**kwargs, "covariates": None}
    out: dict[str, Any] = {
        "chase_anchor": {
            "hr_at_3": CHASE_HR_AT_3,
            "sensitivity_band": CHASE_BAND,
            "baselines_hr_at_3": {
                b: _mean(table[b], "hr_at_3") for b in BASELINES if b in table
            },
        }
    }

    def run(alt: CaseTable, alt_scheduled: Mapping[str, Collection[str]]) -> Any:
        cells = cell_table(alt, apps, alt_scheduled)
        return _family_b_rows(
            _family(
                FAMILY_B_HYPOTHESES,
                alt,
                cells,
                apps,
                groups,
                **{**kwargs, "scheduled": alt_scheduled},
            )
        )

    suffix = TRIGGER_SUFFIX
    if any(b + suffix in table for b in BASELINES):
        alt = {k: v for k, v in table.items() if k not in BASELINES}
        alt_s = {k: v for k, v in scheduled.items() if k not in BASELINES}
        for b in BASELINES:
            if b + suffix in table:
                alt[b] = table[b + suffix]
                alt_s[b] = scheduled.get(b + suffix, list(apps))
        out["trigger_time"] = run(alt, alt_s)

    def no_human(rows: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
        res = {}
        for case, row in rows.items():
            r = dict(row)
            total, human = r.get("cpr_total"), r.get("cpr_human")
            if total is not None and human is not None and total - human > 0:
                r["log_cpr"] = math.log(total - human)
            res[case] = r
        return res

    out["no_human_time"] = [
        r
        for r in run({k: no_human(v) for k, v in table.items()}, scheduled)
        if r["id"] == "B-H7"
    ]

    censor = math.log(TTCD_CENSOR_S)
    alt = dict(table)
    filled = 0
    for b in BASELINES:
        if b not in table:
            continue
        rows = dict(table[b])
        for case in scheduled.get(b, []):
            if case not in rows:
                rows[case] = {"hr_at_3": 0, "avg_at_5": 0, "log_ttcd": censor}
                filled += 1
        alt[b] = rows
    if filled:
        out["failures_as_misses"] = {
            "filled": filled,
            "hypotheses": [r for r in run(alt, scheduled) if r["id"] != "B-H7"],
        }
    return out


def analyse(
    scores: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    *,
    apps: Mapping[str, str],
    groups: Mapping[str, str],
    n_services: Mapping[str, int],
    holm: str = "data_order",
    a_h7_mode: str = "intersection_union",
    frozen: Callable[[], bool] = build_frozen,
    scheduled: Mapping[str, Collection[str]] | None = None,
    covariates: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """The full analysis as one JSON-ready dict (no case IDs in it).

    ``apps`` maps every case of the corpus to its benchmark system.
    ``scheduled`` (the campaign schedule, system -> cases) sets each cell's
    denominator; without a campaign every system is taken as scheduled on
    every case of ``apps``. ``covariates`` (case -> app, fault, window
    bytes, ...) turn on the MCAR test and IPW of S4.10 O-f; they must include
    ``app``.
    """
    if holm not in HOLM_READINGS:
        raise ValueError(f"holm must be one of {HOLM_READINGS}")
    if a_h7_mode not in A_H7_MODES:
        raise ValueError(f"a_h7_mode must be one of {A_H7_MODES}")
    guard = confirmatory_guard(scores, runs, frozen=frozen)
    table = build_case_table(scores, runs, variant_names())
    if scheduled is None:
        scheduled = {name: list(apps) for name in table}
    cells = cell_table(table, apps, scheduled)
    kwargs: dict[str, Any] = {
        "scheduled": scheduled,
        "covariates": covariates,
        "a_h7_mode": a_h7_mode,
        "holm": holm,
        "confirmatory": guard.confirmatory,
    }
    return {
        "version": ANALYSIS_VERSION,
        "label": "confirmatory" if guard.confirmatory else "exploratory",
        "guard_reasons": list(guard.reasons),
        "systems": {name: len(rows) for name, rows in sorted(table.items())},
        "cases": len(apps),
        "cells": [c.as_dict() for c in cells.values()],
        "family_a": _family(FAMILY_A_HYPOTHESES, table, cells, apps, groups, **kwargs),
        "family_b": _family(FAMILY_B_HYPOTHESES, table, cells, apps, groups, **kwargs),
        "family_b_sensitivity": family_b_sensitivity(table, apps, groups, **kwargs),
        "family_e": _family_e(table),
        "sanity_floors": sanity_floors(table, n_services),
    }
