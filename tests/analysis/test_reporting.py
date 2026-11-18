"""S5 reporting rules in the analysis (deviation entries 93-96), hand-built tables."""

from __future__ import annotations

from typing import Any

import pytest

from helios.analysis.reporting import (
    NO_TRACES_REASON,
    S54_TIMING_P_MOVEMENT,
    apps_without_traces,
    noise_reading,
    rerun_determinism,
    trace_coverage,
)
from helios.analysis.run import analyse
from helios.research.analysis_plan import BASELINES
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from tests.analysis.test_run import APPS, CASES, N, _by_id, _merge, _rows

RCD = BASELINES[4]  # BASELINE-5, Multi-source RCD
OB_TT = {c: ("OB" if i < 5 else "TT") for i, c in enumerate(CASES)}


def _baseline(
    name: str, hr3: list[int], cases: list[str] = CASES, **run_fields: list[Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    scores, runs = [], []
    for i, case in enumerate(cases):
        run_id = f"{name}-{case}"
        scores.append(
            {
                "run_id": run_id,
                "incident_id": case,
                "variant_config_hash": None,
                "list_kind": "fused",
                "source": name,
                "hr_at_1": hr3[i],
                "hr_at_3": hr3[i],
                "hr_at_10": hr3[i],
                "avg_at_5": float(hr3[i]),
                "mrr": float(hr3[i]),
                "corpus": "build",
                "scoring_version": "x",
            }
        )
        run = {
            "run_id": run_id,
            "incident_id": case,
            "variant_config_hash": "BASELINE",
            "corpus": "build",
            "metrics_version": "x",
            "ttcd_s": 30,
        }
        run.update({k: v[i] for k, v in run_fields.items()})
        runs.append(run)
    return scores, runs


def _run(scores: Any, runs: Any, **kwargs: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "apps": APPS,
        "groups": {},
        "n_services": {},
        "frozen": lambda: False,
    }
    return analyse(scores, runs, **{**base, **kwargs})


# ── entry 93 ────────────────────────────────────────────────────────────────


def test_trace_coverage_counts_missing_captures() -> None:
    cov = trace_coverage(OB_TT, dict.fromkeys(CASES[:4], True) | {CASES[5]: False})
    assert cov["OB"] == {"cases": 5, "with_traces": 4, "capture_missing": 1}
    assert cov["TT"] == {"cases": 5, "with_traces": 0, "capture_missing": 4}
    # TT's unread captures leave its trace presence unknown: never "no traces".
    assert apps_without_traces(cov) == set()
    full = trace_coverage(OB_TT, {c: OB_TT[c] == "OB" for c in CASES})
    assert apps_without_traces(full) == {"TT"}


def test_unread_captures_block_the_confirmatory_label() -> None:
    scores, runs = _merge(
        _rows("HELIOS-Full", [1] * N, corpus="pool"),
        _rows("HELIOS-noStructural", [0] * N, corpus="pool"),
    )
    traced = dict.fromkeys(CASES[:8], True)  # 2 captures not read
    out = _run(scores, runs, traced=traced, frozen=lambda: True)
    assert out["label"] == "exploratory"
    assert any("2 captures not read" in r for r in out["guard_reasons"])
    # Coverage incomplete but OB has traces: A-H8 is still tested on it.
    assert _by_id(out["family_a"])["A-H8"]["apps_tested"] == {"hr_at_3": ["OB"]}


def test_graph_comparisons_are_untestable_on_systems_without_traces() -> None:
    # Full hits all; noStructural misses all. OB has traces, TT none.
    scores, runs = _merge(
        _rows("HELIOS-Full", [1] * N), _rows("HELIOS-noStructural", [0] * N)
    )
    traced = {c: OB_TT[c] == "OB" for c in CASES}
    out = _run(scores, runs, apps=OB_TT, traced=traced)
    a8 = _by_id(out["family_a"])["A-H8"]
    assert a8["apps_tested"] == {"hr_at_3": ["OB"]}
    assert a8["apps_untestable_no_traces"] == ["TT"]
    assert a8["p_value"] == pytest.approx(2**-5)  # 5 discordant pairs on OB
    e10 = {h["id"]: h for h in out["family_e"]}["E-H10"]
    assert e10["n_pairs"] == 5
    assert out["trace_coverage"]["TT"]["with_traces"] == 0
    # A comparison that needs no graph (A-H3 shape) is not narrowed: not run here.
    # No traces anywhere: untestable with the entry 93 reason, not a non-rejection.
    none = _run(scores, runs, apps=OB_TT, traced=dict.fromkeys(CASES, False))
    a8 = _by_id(none["family_a"])["A-H8"]
    assert a8["p_value"] is None
    assert a8["untestable"] == NO_TRACES_REASON
    e10 = {h["id"]: h for h in none["family_e"]}["E-H10"]
    assert (e10["available"], e10["untestable"]) == (False, NO_TRACES_REASON)
    # Trace presence not supplied: rule not applied, both systems tested.
    blind = _by_id(_run(scores, runs, apps=OB_TT)["family_a"])["A-H8"]
    assert blind["apps_tested"] == {"hr_at_3": ["OB", "TT"]}
    assert blind["trace_rule"].startswith("not applied")


def test_non_graph_comparison_keeps_untraced_systems() -> None:
    scores, runs = _merge(_rows("HELIOS-Full", [1] * N), _rows("HELIOS-D", [0] * N))
    out = _run(scores, runs, apps=OB_TT, traced=dict.fromkeys(CASES, False))
    a3 = _by_id(out["family_a"])["A-H3"]
    assert a3["apps_tested"] == {"hr_at_3": ["OB", "TT"]}
    assert "apps_untestable_no_traces" not in a3


# ── entry 94 ────────────────────────────────────────────────────────────────


def test_noise_reading_uses_the_larger_movement() -> None:
    small = noise_reading(1e-4, 2e-2, 2e-4)
    assert small["rerun_p_movement"] == pytest.approx(1e-4)
    assert small["sensitive_to_timing_noise"] is True  # within the build movement
    assert small["crosses_threshold_with_reruns"] is False
    far = noise_reading(2e-1, 1e-2, 2e-1)
    assert far["sensitive_to_timing_noise"] is False
    big = noise_reading(1e-3, 1e-2, 3e-1)  # own movement beyond the build figure
    assert big["sensitive_to_timing_noise"] is True
    assert big["crosses_threshold_with_reruns"] is True
    assert noise_reading(None, None, None)["sensitive_to_timing_noise"] is None
    assert small["build_p_movement"] == S54_TIMING_P_MOVEMENT


def _timing_fixture() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return _merge(
        _rows(
            "HELIOS-Full",
            [1] * N,
            log_cpr=[5] * N,
            ttt_ms=[1000] * N,
            ttcd_censored=[True] * 2 + [False] * 8,
        ),
        _rows(
            "HELIOS-noRouter",
            [1] * N,
            log_cpr=[9] * N,
            ttt_ms=[3000] * N,
            ttcd_censored=[False] * N,
        ),
    )


def test_timing_results_carry_censored_share_and_rerun_movement() -> None:
    scores, runs = _timing_fixture()
    # Full rerun on 3 cases at log-CpR 12: those differences become 9 - 12 = -3.
    reruns = _rows("HELIOS-Full", [1] * 3, cases=CASES[:3], log_cpr=[12] * 3)
    out = _run(scores, runs, reruns=reruns)
    a5 = _by_id(out["family_a"])["A-H5"]
    t = a5["timing"]
    assert t["censored_share"]["b"]["share"] == pytest.approx(2 / 10)
    assert t["censored_share"]["a"]["share"] == 0
    assert t["censored_share"]["b"]["by_system"] == {"OB": pytest.approx(2 / 10)}
    assert t["reruns"] == {"n_substituted": 3}
    assert t["p_with_reruns"] > a5["p_value"]
    assert t["rerun_p_movement"] == pytest.approx(t["p_with_reruns"] - a5["p_value"])
    holm = {r["id"]: r for r in out["family_a"]["holm_binding"]}
    assert t["threshold"] == holm["A-H5"]["threshold"]
    movement = max(S54_TIMING_P_MOVEMENT, t["rerun_p_movement"])
    assert t["sensitive_to_timing_noise"] is (
        abs(a5["p_value"] - t["threshold"]) <= movement
    )
    assert "S5.4" in t["statement"]
    assert a5["p_value"] == pytest.approx(2**-10)  # the decision is unchanged
    e2 = {h["id"]: h for h in out["family_e"]}["E-H2"]
    assert e2["timing"]["censored_share"]["b"]["share"] == pytest.approx(2 / 10)
    assert e2["timing"]["reruns"] == {"n_substituted": 0}
    assert "S5.4" in out["timing_noise_statement"]


def test_timing_without_reruns_says_so() -> None:
    scores, runs = _timing_fixture()
    t = _by_id(_run(scores, runs)["family_a"])["A-H5"]["timing"]
    assert t["reruns"] == "not supplied"
    assert t["p_with_reruns"] is None
    assert t["sensitive_to_timing_noise"] is not None  # build movement still applies


# ── entry 95 ────────────────────────────────────────────────────────────────


def test_hr_at_3_tests_get_hr_at_1_and_mrr_columns() -> None:
    scores, runs = _merge(_rows("HELIOS-Full", [1] * N), _rows("HELIOS-D", [0] * N))
    a3 = _by_id(_run(scores, runs)["family_a"])["A-H3"]
    cols = a3["exploratory_hr"]
    assert cols["hr_at_3_discordant_pairs"] == N
    assert cols["status"].startswith("exploratory")
    for key in ("hr_at_1", "mrr"):
        assert cols[key]["n"] == N
        assert (cols[key]["mean_a"], cols[key]["mean_b"]) == (1, 0)
        assert cols[key]["mean_difference"] == pytest.approx(1)
        assert cols[key]["by_system"]["OB"]["n"] == N
        assert "p_value" not in cols[key]
    assert a3["p_value"] == pytest.approx(2**-10)  # HR@3 stays the binding test


# ── entry 96 ────────────────────────────────────────────────────────────────


def test_rcd_rerun_figures_sit_beside_b_h5_and_b_h8() -> None:
    nd = [True, False] + [None] * (N - 2)
    scores, runs = _merge(
        _rows("HELIOS-Full", [1] * N), _baseline(RCD, [0] * N, nondeterministic=nd)
    )
    # Rerun of the first two cases: case 0's MRR moves, case 1's does not.
    r_scores, r_runs = _baseline(RCD, [0, 0], cases=CASES[:2])
    r_scores[0]["mrr"] = 1 / 3
    out = _run(scores, runs, reruns=(r_scores, r_runs))
    b = _by_id(out["family_b"])
    det = b["B-H5"]["rerun_determinism"]
    assert (det["pairs"], det["compared"]) == (2, 2)
    assert det["identical_share"] == pytest.approx(1 / 2)
    assert det["mrr"] == {"n": 2, "changed": 1, "mean_abs_change": pytest.approx(1 / 6)}
    assert det["hr_at_3"]["changed"] == 0
    # RCD is the only, hence best, baseline: B-H8 carries the same figures.
    assert b["B-H8"]["rerun_determinism"] == det
    assert "rerun_determinism" not in b["B-H1"]
    assert out["rerun_determinism"][RCD] == det
    blind = _by_id(_run(scores, runs)["family_b"])
    assert blind["B-H5"]["rerun_determinism"] == "not supplied"


def test_rerun_determinism_skips_systems_without_pairs() -> None:
    first = {"A": {"c0": {"hr_at_1": 1}}}
    assert rerun_determinism(first, {"A": {"c9": {"hr_at_1": 1}}, "B": {}}) == {}
