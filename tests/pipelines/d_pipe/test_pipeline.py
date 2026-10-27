"""Integration test for run_dpipe - full Stages A-D with stub inputs."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from helios.pipelines.d_pipe.pipeline import run_dpipe
from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.telemetry.trigger import TriggerRecord, TriggerSource
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
    assert "ranked_candidates" in result
    assert not {"hr_at_3", "mrr"} & set(result)  # scored after dispatch (S1.9)


def test_run_dpipe_deterministic(manifest) -> None:
    """Calling run_dpipe twice with identical inputs must return identical outputs."""
    window = TelemetryWindow(
        incident_id="det-001",
        variant_config_hash="y" * 64,
        window_start_iso=dt.datetime(2026, 1, 1, tzinfo=dt.UTC).isoformat(),
        window_end_iso=dt.datetime(2026, 1, 1, 0, 5, tzinfo=dt.UTC).isoformat(),
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        p1_metrics_path=None,
        p2_traces_path=None,
        p3_logs_path=None,
    )

    result1 = run_dpipe(
        window=window,
        ueg_c=None,
        incident_id="det-001",
        snapshot_hash="x" * 64,
        variant_config_hash="y" * 64,
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        run_id="run-1",
    )
    result2 = run_dpipe(
        window=window,
        ueg_c=None,
        incident_id="det-001",
        snapshot_hash="x" * 64,
        variant_config_hash="y" * 64,
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        run_id="run-2",
    )

    assert result1["ranked_candidates"] == result2["ranked_candidates"]
    assert result1["candidate_scores"] == result2["candidate_scores"]


# ── trigger split, sigma and scope (S2.1, S2-M7-ENG09) ──────────────────────


def _rcaeval_window(tmp_path: Path) -> TelemetryWindow:
    import json

    import pyarrow as pa
    import pyarrow.parquet as pq

    t0 = 1_790_000_000
    rows = []
    for step in range(40):
        for svc in ("cart", "ad", "jaeger"):
            jump = step >= 20 and svc in ("cart", "jaeger")
            rows.append(
                (t0 + 15 * step, svc, "latency-90", (90 if jump else 40) + step % 3)
            )
            rows.append((t0 + 15 * step, svc, "cpu", 5 + step % 2))
    pq.write_table(
        pa.table(
            {
                "timestamp": [float(r[0]) for r in rows],
                "metric_name": [r[2] for r in rows],
                "value": [float(r[3]) for r in rows],
                "labels": [json.dumps({"service_name": r[1]}) for r in rows],
            }
        ),
        tmp_path / "p1.parquet",
    )
    return TelemetryWindow(
        incident_id="opaque",
        variant_config_hash="a" * 64,
        window_start_iso=dt.datetime.fromtimestamp(t0, dt.UTC).isoformat(),
        window_end_iso=dt.datetime.fromtimestamp(t0 + 600, dt.UTC).isoformat(),
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        p1_metrics_path=str(tmp_path / "p1.parquet"),
    )


def _trigger_at(seconds: float) -> TriggerRecord:
    return TriggerRecord(
        incident_id="opaque",
        trigger_time_s=seconds,
        suspects=("cart",),
        context=(),
        source=TriggerSource.THRESHOLD,
        detector_hash="d" * 64,
    )


def _run(window: TelemetryWindow, trigger: TriggerRecord | None) -> dict[str, Any]:
    return run_dpipe(
        window=window,
        ueg_c=None,
        incident_id="opaque",
        snapshot_hash="b" * 64,
        variant_config_hash="a" * 64,
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        run_id="r",
        trigger=trigger,
        evidence_ref=6,
    )


def test_dpipe_ranks_on_rcaeval_window(manifest, tmp_path: Path) -> None:
    out = _run(_rcaeval_window(tmp_path), _trigger_at(1_790_000_000 + 300))
    assert out["status"] == "ranked"
    assert out["ranked_candidates"][0] == "cart"
    assert out["sigma"] is not None


def test_dpipe_never_ranks_out_of_scope_services(manifest, tmp_path: Path) -> None:
    out = _run(_rcaeval_window(tmp_path), _trigger_at(1_790_000_000 + 300))
    assert "jaeger" not in out["ranked_candidates"]
    assert "jaeger" not in out["candidate_scores"]


def test_dpipe_without_trigger_has_no_sigma(manifest, tmp_path: Path) -> None:
    out = _run(_rcaeval_window(tmp_path), None)
    assert out["sigma"] is None
