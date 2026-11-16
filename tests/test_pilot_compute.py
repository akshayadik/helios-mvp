"""S5.3 cold-cache campaign compute (design s5_3_pilot_design.md Q-e 2)."""

from __future__ import annotations

from typing import Any

import pytest

from bin import pilot_compute as pc
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

START = 10.0


def _log(runs: dict[str, float]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, (key, wall) in enumerate(runs.items()):
        rows.append({"event": "started", "key": key, "run_id": f"r{i}", "at": START})
        rows.append(
            {"event": "passed", "key": key, "run_id": f"r{i}", "at": START + wall}
        )
    return rows


RUNS = {
    "rerun/c1/HELIOS-noRouter": 20.0,  # every worker call live
    "rerun/c1/HELIOS-Full": 18.0,  # 14 s of it live worker calls
    "rerun/c1/BASELINE-1": 3.0,  # baseline reruns never count
    "confirmatory/c1/HELIOS-noRouter": 2.0,  # cached first run, ignored
    "confirmatory/c1/HELIOS-Full": 1.5,
    "confirmatory/c1/HELIOS-D": 4.0,  # no model call: first run counts
    "baseline/c1/BASELINE-1": 6.0,
    "baseline_trigger/c1/BASELINE-1": 5.0,
    "confirmatory/c2/HELIOS-Full": 1.25,  # c2 has no rerun: not a rerun case
}


def test_run_walls_pairs_started_and_passed() -> None:
    log = [*_log({"a/b/c": 5.0}), {"event": "started", "key": "x/y/z", "at": START}]
    assert pc.run_walls(log) == {"a/b/c": (5.0, "r0")}


def test_live_worker_time_ignores_cache_hits() -> None:
    ev = {
        "workers": {
            "metric": {"wall_ms": 14_000, "cache_hit": False},
            "log": {"wall_ms": 9_000, "cache_hit": True},
        }
    }
    assert pc.live_worker_s(ev) == pytest.approx(14)
    assert pc.live_worker_s(None) == 0


def test_cold_case_cost() -> None:
    walls = pc.run_walls(_log(RUNS))
    full_rerun = walls["rerun/c1/HELIOS-Full"][1]
    evidence = {full_rerun: {"workers": {"m": {"wall_ms": 14_000, "cache_hit": False}}}}
    costs = pc.cold_case_costs(walls, evidence.get)
    # noRouter 20 + Full (18 - 14) + D 4; baselines 6 + 5
    assert costs == {"c1": {"helios_s": pytest.approx(28), "baselines_s": 11}}


def test_report_projects_to_the_pool() -> None:
    report = pc.compute_report({"c1": {"helios_s": 36, "baselines_s": 18}})
    assert report["cases"] == 1
    assert report["helios_s_per_case"]["median"] == 36
    assert report["pool_projection_h"]["helios_e1_e3"]["median"] == 2.4  # 240 x 36 s
    assert report["pool_projection_h"]["baselines_e2"]["median"] == 1.2
    assert report["pool_projection_h"]["helios_e1_e3"]["mean"] == 2.4
    empty = pc.compute_report({})
    assert empty["pool_projection_h"]["helios_e1_e3"]["median"] is None
