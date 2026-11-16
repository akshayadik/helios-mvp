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
