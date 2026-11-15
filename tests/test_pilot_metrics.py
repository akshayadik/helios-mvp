"""S5.3 per-system readings (design s5_3_pilot_design.md §4)."""

from __future__ import annotations

from bin import pilot_metrics as pm
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

LOG = [
    {"event": "passed", "key": "confirmatory/c1/HELIOS-Full", "run_id": "f1"},
    {"event": "passed", "key": "confirmatory/c2/HELIOS-Full", "run_id": "f2"},
    {"event": "passed", "key": "baseline_trigger/c1/BASELINE-1", "run_id": "b1"},
    {"event": "passed", "key": "rerun/c1/HELIOS-Full", "run_id": "r1"},
    {"event": "excluded", "key": "baseline/c1/BASELINE-2", "run_id": "x1"},
]


def test_first_runs_only_and_trigger_time_named() -> None:
    assert pm.run_systems(LOG) == {
        "f1": "HELIOS-Full",
        "f2": "HELIOS-Full",
        "b1": "BASELINE-1 [trigger]",
    }


def test_readings_per_system_and_narratives() -> None:
    systems = pm.run_systems(LOG)
    scores = [("f1", 0, 1), ("f2", 1, 1), ("b1", 0, 0), ("r1", 1, 1)]
    runs = [
        ("f1", 30, 3, 200, 900, None),
        ("f2", 50, 4, 400, 1100, True),
        ("r1", 9, 9, 9, 9, False),
    ]
    narratives = [("f1", "llm", 600, 40), ("f2", "template", 0, 0)]
    out = pm.readings(systems, scores, runs, narratives)
    full = out["systems"]["HELIOS-Full"]
    assert full["runs"] == 2
    assert full["hr_at_3"] == 1
    assert full["cpr_total_median"] == 40
    assert full["nondeterministic"] == {"null": 1, "true": 1}
    assert out["systems"]["BASELINE-1 [trigger]"]["hr_at_3"] == 0
    l7 = out["l7_narratives"]["HELIOS-Full"]
    assert (l7["llm_narratives"], l7["template_narratives"]) == (1, 1)
    assert l7["tokens_llm_total"] == 640
