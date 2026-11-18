"""S5.4: cells keys trigger-time baseline runs under their own name.

Regression for S5.3 report section 3.4 (case c80ff7d1): a baseline whose
binding-time run was excluded and whose trigger-time run passed got
metric_missing entries against the trigger run.
"""

from __future__ import annotations

from typing import Any

from bin.helios_campaign import passed_runs
from helios.evaluation.cells import missing_metrics
from helios.orchestrator.schedule import TRIGGER_SUFFIX, spec_system_name, system_name
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

CASE = "c80ff7d1"
SLOT = "BASELINE-1"
NAME = system_name(SLOT)


def _body() -> dict[str, Any]:
    return {
        "specs": [
            {"phase": "baseline", "case": CASE, "system": SLOT},
            {"phase": "baseline_trigger", "case": CASE, "system": SLOT},
            {"phase": "rerun", "case": CASE, "system": SLOT},
        ]
    }


def _final(binding: str) -> dict[str, dict[str, Any]]:
    return {
        f"baseline/{CASE}/{SLOT}": {"event": binding, "run_id": "bind"},
        f"baseline_trigger/{CASE}/{SLOT}": {"event": "passed", "run_id": "trig"},
        f"rerun/{CASE}/{SLOT}": {"event": "passed", "run_id": "again"},
    }


def test_spec_names_carry_the_trigger_suffix() -> None:
    specs = _body()["specs"]
    assert spec_system_name(specs[0]) == NAME
    assert spec_system_name(specs[1]) == NAME + TRIGGER_SUFFIX


def test_binding_excluded_trigger_passed_is_not_missing() -> None:
    passed = passed_runs(_body(), _final("excluded"))
    assert passed == {(NAME + TRIGGER_SUFFIX, CASE): "trig"}
    # the trigger run is scored under its suffixed name: nothing is missing
    table = {NAME + TRIGGER_SUFFIX: {CASE: {"hr_at_3": 1, "log_cpr": 2}}}
    missing = missing_metrics(table, list(passed), labels_due=False)
    assert all(system == NAME + TRIGGER_SUFFIX for system, _, _ in missing)
    assert "hr_at_3" not in {m for _, _, m in missing}


def test_both_passed_keep_both_runs_and_an_unscored_trigger_is_caught() -> None:
    passed = passed_runs(_body(), _final("passed"))
    assert passed == {(NAME, CASE): "bind", (NAME + TRIGGER_SUFFIX, CASE): "trig"}
    table = {NAME: {CASE: {"hr_at_3": 1}}}  # trigger run left unscored
    missing = missing_metrics(table, list(passed), labels_due=False)
    assert (NAME + TRIGGER_SUFFIX, CASE, "hr_at_3") in missing
    assert (NAME, CASE, "hr_at_3") not in missing
