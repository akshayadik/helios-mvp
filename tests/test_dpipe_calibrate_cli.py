"""bin/dpipe_calibrate.py, OTel fix refit options (entry 77)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from helios.evaluation.dpipe_calibration import dpipe_grid, select_dpipe
from helios.evaluation.trigger_calibration import CalibrationCase
from helios.pipelines.d_pipe.params import DPipeParams
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_memory_grid_keeps_the_s21_grid_first_and_adds_2300() -> None:
    s21, full = dpipe_grid(), dpipe_grid(memory=True)
    assert full[: len(s21)] == s21
    assert (len(s21), len(full)) == (800, 3100)
    extra = full[len(s21) :]
    assert all(p.w_memory is not None for p in extra)
    assert all(
        round(p.w_error + p.w_resource + (p.w_memory or 0), 6) < 1 for p in extra
    )


def test_ties_prefer_the_setting_without_w_memory() -> None:
    old = DPipeParams(0.3, 0.2, 0.2, 1, provisional=False)
    new = DPipeParams(0.3, 0.2, 0.2, 1, provisional=False, w_memory=0)
    scores = {"rcaeval_build": 0.6, "otel_build_v3": 0.6}
    assert select_dpipe({new: scores, old: scores}) == old


def test_memory_needs_its_own_report(capsys: pytest.CaptureFixture[str]) -> None:
    from bin import dpipe_calibrate

    assert dpipe_calibrate.main(["--memory"]) == 2
    assert "own --report" in capsys.readouterr().err


def test_an_existing_report_is_never_overwritten(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from bin import dpipe_calibrate

    existing = "docs/sprints/s3-routing/calibration/memory_gate.json"
    assert dpipe_calibrate.main(["--memory", "--report", existing]) == 2
    assert "refusing to overwrite" in capsys.readouterr().err


def _case(fault: str) -> CalibrationCase:
    return CalibrationCase(
        incident_id="x",
        window=None,  # type: ignore[arg-type]
        inject_time_s=0,
        root_cause="email",
        fault=fault,
    )


def test_memory_check_needs_no_loss_outside_the_leak() -> None:
    from bin.dpipe_calibrate import memory_check

    current = DPipeParams(0.7, 0.1, 0.2, 1, provisional=False)
    new = DPipeParams(0.7, 0.1, 0.2, 1, provisional=False, w_memory=0.1)
    grid = [current, new]
    cases = {
        "otel_build_v3": [_case("emailMemoryLeak"), _case("adFailure")],
        "rcaeval_build": [],
    }
    hr3 = {
        current: {"rcaeval_build": 0.9, "otel_build_v3": 0.4},
        new: {"rcaeval_build": 0.9, "otel_build_v3": 0.6},
    }
    gains_leak = {"otel_build_v3": [[0, 1], [1, 1]], "rcaeval_build": []}
    check = memory_check(grid, hr3, gains_leak, new, current, cases)
    assert check["no_loss"] and check["adopted"]
    loses_other = {"otel_build_v3": [[0, 1], [1, 0]], "rcaeval_build": []}
    check = memory_check(grid, hr3, loses_other, new, current, cases)
    assert not check["no_loss"] and not check["adopted"]
    lower_rcaeval = {**hr3, new: {"rcaeval_build": 0.8, "otel_build_v3": 0.6}}
    check = memory_check(grid, lower_rcaeval, gains_leak, new, current, cases)
    assert not check["adopted"]
    check = memory_check(grid, hr3, gains_leak, current, current, cases)
    assert check["no_loss"] and not check["adopted"]  # fix B dropped


def test_the_grid_computes_each_memory_trend_once_per_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import numpy as np

    from bin import dpipe_calibrate
    from helios.pipelines.d_pipe.stages.b_anomaly_scorer import memory_trend

    calls: list[int] = []

    def counted(series: list[float], before: np.ndarray) -> float:
        calls.append(1)
        return memory_trend(series, before)

    monkeypatch.setattr(dpipe_calibrate, "_TREND", counted)
    trend = dpipe_calibrate._memoised_trend()
    series = [float(100 + 3 * t + (7 * t % 5)) for t in range(24)]
    before = np.arange(24) < 12
    first = trend(series, before)
    assert trend(series, before) == first == memory_trend(series, before)
    assert len(calls) == 1
    trend([*series[:-1], 999], before)
    assert len(calls) == 2
