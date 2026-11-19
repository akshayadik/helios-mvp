"""S5.4 replication compare (design s5_4_replication_design.md R-e)."""

from __future__ import annotations

from typing import Any

from bin import replication_compare as rc
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def _run(sig: Any, event: str = "passed", gate: str | None = None) -> dict[str, Any]:
    return {"event": event, "gate_check": gate, "sig": sig}


def test_final_outcomes_keeps_last_first_run_event() -> None:
    log = [
        {"event": "started", "key": "confirmatory/c/H"},
        {"event": "excluded", "key": "confirmatory/c/H", "gate_check": "x"},
        {"event": "passed", "key": "confirmatory/c/H", "run_id": "r"},
        {"event": "passed", "key": "rerun/c/H", "run_id": "q"},
    ]
    assert rc.final_outcomes(log) == {"confirmatory/c/H": log[2]}


def test_helios_signature_and_live_calls() -> None:
    sig = rc.helios_signature(
        [("lpipe", "s", "[b]", "d2"), ("dpipe", "s", "[a]", "d1")], ("[a]", "[b]", "t")
    )
    assert sig["snapshot"] == ["s"]
    assert list(sig["pipelines"]) == ["dpipe", "lpipe"]
    assert sig["fused"] == {"ranked": "[a]", "first": "[b]", "state": "t"}
    ev = {"workers": {"log": {"cache_hit": True}, "metric": {"cache_hit": False}}}
    assert rc.live_calls(ev) == 1
    assert rc.live_calls(None) == 0
    dropped = {"workers": {"trace": {"cache_hit": False, "dropped": "no_digest"}}}
    assert rc.live_calls(dropped) == 0


def test_compare_runs_classes() -> None:
    ref = {
        "confirmatory/c1/H": _run("a"),
        "confirmatory/c2/H": _run("a"),
        "confirmatory/c3/H": _run("a"),
        "baseline/c1/B": _run(None, "excluded", "baseline_error"),
        "baseline/c2/B": _run("r"),
    }
    clone = {
        "confirmatory/c1/H": _run("a"),
        "confirmatory/c2/H": _run("b"),  # differs, cache hit: build defect
        "confirmatory/c3/H": _run("b"),  # differs after a live call
        "baseline/c1/B": _run("r"),  # outcome differs
        "baseline_trigger/c9/B": _run("r"),  # not in the reference
    }
    live = {"confirmatory/c3/H": 2}
    report = rc.compare_runs(ref, clone, live)
    assert report["counts"] == {
        "missing_in_clone": 1,
        "extra_in_clone": 1,
        "outcome_differs": 1,
        "differs_cache_hit": 1,
        "differs_live_call": 1,
    }
    assert report["equal_by_phase"] == {"confirmatory": 1}
    assert report["clone_runs_with_live_calls"] == 1
    assert not report["passes"]


def test_live_call_difference_alone_passes() -> None:
    ref = {"confirmatory/c/H": _run("a")}
    report = rc.compare_runs(
        ref, {"confirmatory/c/H": _run("b")}, {"confirmatory/c/H": 1}
    )
    assert report["passes"]
    assert report["counts"]["differs_live_call"] == 1


def test_analysis_diff_separates_timing_metrics() -> None:
    ref = {
        "tests": [
            {"metric": "log_cpr", "p_value": 2, "n": 5},
            {"metric": "hr_at_3", "p_value": 3, "n": 5},
        ],
        "label": "x",
    }
    timing_only = {
        "tests": [
            {"metric": "log_cpr", "p_value": 4, "n": 5},
            {"metric": "hr_at_3", "p_value": 3, "n": 5},
        ],
        "label": "x",
    }
    report = rc.compare_analysis(ref, timing_only)
    assert report["passes"]
    assert report["timing_derived"]["paths"] == ["/tests[0]/p_value"]
    exact = {**timing_only, "label": "y", "extra": 1}
    report = rc.compare_analysis(ref, exact)
    assert not report["passes"]
    assert report["other"]["paths"] == ["/extra", "/label"]
    assert rc.leaf_diff([1, 2], [1]) == [("[len]", None)]


def test_correction_table_entries_take_their_hypothesis_metric() -> None:
    ref = {
        "hypotheses": [
            {"id": "A-H5", "metric": "log-CpR", "p_value": 2},
            {"id": "A-H1", "metric": "HR@3", "p_value": 3},
        ],
        "holm": [{"id": "A-H5", "adjusted_p": 2}, {"id": "A-H1", "adjusted_p": 3}],
    }
    assert rc.hypothesis_metrics(ref) == {"A-H5": "log-CpR", "A-H1": "HR@3"}
    timing = {**ref, "holm": [{"id": "A-H5", "adjusted_p": 4}, ref["holm"][1]]}
    report = rc.compare_analysis(ref, timing)
    assert report["passes"]
    assert report["timing_derived"]["paths"] == ["/holm[0]/adjusted_p"]
    accuracy = {**ref, "holm": [ref["holm"][0], {"id": "A-H1", "adjusted_p": 4}]}
    report = rc.compare_analysis(ref, accuracy)
    assert not report["passes"]
    assert report["other"]["paths"] == ["/holm[1]/adjusted_p"]


# ── moved by timing (S5.4 rerun report §4, owner 2026-11-19) ────────────────

_HYPS = [
    {"id": "B-H5", "metric": "HR@3", "p_value": 2e-24},
    {"id": "B-H6", "metric": "log time to correct diagnosis", "p_value": 2e-21},
    {"id": "B-H1", "metric": "HR@3", "p_value": 0.05},
]


def _row(hid: str, rank: int, p: float, threshold: float, adj: float) -> dict[str, Any]:
    return {
        "id": hid,
        "rank": rank,
        "p_value": p,
        "threshold": threshold,
        "adjusted_p": adj,
        "below_threshold_descriptive": p < threshold,
    }


def _analysis(b_h6_p: float, rows: list[dict[str, Any]]) -> dict[str, Any]:
    hyps = [{**h, "p_value": b_h6_p} if h["id"] == "B-H6" else h for h in _HYPS]
    return {"family_b": {"hypotheses": hyps, "holm_binding": rows}}


def test_a_row_moved_past_by_a_timing_hypothesis_is_moved_by_timing() -> None:
    # Reference order B-H5, B-H6, B-H1; in the clone B-H6 moves ahead of B-H5.
    ref = _analysis(
        2e-21,
        [
            _row("B-H1", 1, 0.05, 0.05, 0.05),
            _row("B-H5", 5, 2e-24, 0.0167, 6e-24),
            _row("B-H6", 6, 2e-21, 0.025, 4e-21),
        ],
    )
    clone = _analysis(
        6e-25,
        [
            _row("B-H1", 1, 0.05, 0.05, 0.05),
            _row("B-H5", 5, 2e-24, 0.025, 4e-24),
            _row("B-H6", 6, 6e-25, 0.0167, 1.8e-24),
        ],
    )
    report = rc.compare_analysis(ref, clone)
    assert report["passes"]
    assert report["other"]["count"] == 0
    assert report["moved_by_timing"]["count"] == 2
    leaf = report["moved_by_timing"]["leaves"][0]
    assert leaf["id"] == "B-H5"
    assert (leaf["position_ref"], leaf["position_clone"]) == (1, 2)
    assert leaf["swapped_with"] == ["B-H6"]
    # B-H6's own row is timing-derived, as before.
    assert report["timing_derived"]["count"] > 0


def test_a_row_whose_own_p_value_changed_is_not_moved_by_timing() -> None:
    ref = _analysis(2e-21, [_row("B-H5", 5, 2e-24, 0.0167, 6e-24)])
    clone = _analysis(2e-21, [_row("B-H5", 5, 3e-24, 0.0167, 9e-24)])
    report = rc.compare_analysis(ref, clone)
    assert not report["passes"]
    assert report["moved_by_timing"]["count"] == 0


def test_a_row_moved_past_by_an_accuracy_hypothesis_is_not_moved_by_timing() -> None:
    ref = _analysis(
        2e-21,
        [
            _row("B-H1", 1, 1e-30, 0.0167, 3e-30),
            _row("B-H5", 5, 2e-24, 0.025, 4e-24),
        ],
    )
    clone = _analysis(
        2e-21,
        [
            _row("B-H1", 1, 1e-20, 0.025, 2e-20),
            _row("B-H5", 5, 2e-24, 0.0167, 6e-24),
        ],
    )
    report = rc.compare_analysis(ref, clone)
    assert not report["passes"]
    assert "/family_b/holm_binding[1]/threshold" in report["other"]["paths"]
    assert report["moved_by_timing"]["count"] == 0


def test_a_decision_change_is_never_moved_by_timing() -> None:
    ref = _analysis(
        2e-21,
        [
            _row("B-H5", 5, 0.02, 0.0167, 0.04),
            _row("B-H6", 6, 2e-21, 0.025, 4e-21),
        ],
    )
    flipped = _row("B-H5", 5, 0.02, 0.025, 0.02)
    clone = _analysis(0.03, [flipped, _row("B-H6", 6, 0.03, 0.0167, 0.04)])
    report = rc.compare_analysis(ref, clone)
    assert not report["passes"]
    assert report["other"]["paths"] == [
        "/family_b/holm_binding[0]/below_threshold_descriptive"
    ]
    assert report["moved_by_timing"]["count"] == 2
