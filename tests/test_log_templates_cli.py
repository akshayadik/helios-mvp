"""In-process test of bin/log_templates.py on a synthetic two-window corpus."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.parquet as pq

from bin import log_templates as cli
from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _corpus(repo: Path) -> None:
    data = repo / "data" / "rcaeval"
    for incident_id, with_logs in (("aaa", True), ("bbb", False)):
        case = data / "build" / incident_id
        case.mkdir(parents=True)
        logs = None
        if with_logs:
            logs = f"data/rcaeval/build/{incident_id}/p3_logs.parquet"
            pq.write_table(
                pa.table(
                    {
                        "timestamp": ["2026-10-25T10:00:01Z", "2026-10-25T10:00:02Z"],
                        "service_name": ["carts", "carts"],
                        "body": ["order 1 accepted", "order 2 accepted"],
                    }
                ),
                repo / logs,
            )
        window = TelemetryWindow(
            incident_id=incident_id,
            variant_config_hash="h",
            window_start_iso="2026-10-25T10:00:00Z",
            window_end_iso="2026-10-25T10:05:00Z",
            evaluation_phase=EvaluationPhase.EXPLORATORY,
            p3_logs_path=logs,
        )
        manifest = window.model_dump(mode="json") | {"window_hash": "x"}
        (case / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (data / "build_manifest.json").write_text(
        json.dumps({"case_order": ["aaa", "bbb"]}), encoding="utf-8"
    )


def test_check_reports_stable_reruns_and_counts_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _corpus(tmp_path)
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    assert cli.main(["check", "--corpus", "build"]) == 0
    out = capsys.readouterr().out
    assert "2 windows, 1 without logs" in out
    assert "reruns identical: 1/1" in out
    assert "lines 2, skipped 0" in out
    assert "order" not in out and "carts" not in out
