"""Integration test for run_dpipe - full Stages A-D with stub inputs."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from helios.pipelines.d_pipe.pipeline import run_dpipe
from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.vcl import (
    VCLFlag,  # noqa: F401 — flag-guard compliance
    get_variant,
    set_current_manifest,
)


@pytest.fixture()
def manifest():
    m = get_variant("HELIOS-Full")
    set_current_manifest(m)
    return m


def test_run_dpipe_with_no_p1_metrics_returns_verdict(manifest, tmp_path: Path) -> None:
    window = TelemetryWindow(
        incident_id="inc-test",
        variant_config_hash="a" * 64,
        window_start_iso=dt.datetime(2026, 1, 1, tzinfo=dt.UTC).isoformat(),
        window_end_iso=dt.datetime(2026, 1, 1, 0, 5, tzinfo=dt.UTC).isoformat(),
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        p1_metrics_path=None,
        p2_traces_path=None,
        p3_logs_path=None,
    )
    result = run_dpipe(
        window=window,
        ueg_c=None,
        incident_id="inc-test",
        snapshot_hash="b" * 64,
        variant_config_hash="a" * 64,
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        run_id="run-001",
    )
    assert "hr_at_3" in result
    assert "cpr" in result
    assert "ranked_candidates" in result
    assert isinstance(result["hr_at_3"], int | float)
