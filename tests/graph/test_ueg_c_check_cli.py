"""In-process test of bin/ueg_c_check.py on a synthetic two-window corpus."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from bin import ueg_c_check as cli
from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from tests.graph.test_ueg_c_v02 import _write_window

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _corpus(repo: Path) -> None:
    data = repo / "data" / "rcaeval"
    case = data / "build" / "aaa"
    case.mkdir(parents=True)
    window = _write_window(case, EvaluationPhase.EXPLORATORY)
    rel = "data/rcaeval/build/aaa/w"
    window = window.model_copy(
        update={
            "incident_id": "aaa",
            "p1_metrics_path": f"{rel}/p1.parquet",
            "p2_traces_path": f"{rel}/p2.parquet",
            "p3_logs_path": f"{rel}/p3.parquet",
        }
    )
    (case / "manifest.json").write_text(
        json.dumps(window.model_dump(mode="json") | {"window_hash": "x"}),
        encoding="utf-8",
    )
    empty = data / "build" / "bbb"
    empty.mkdir()
    bare = TelemetryWindow(
        incident_id="bbb",
        variant_config_hash="h",
        window_start_iso=window.window_start_iso,
        window_end_iso=window.window_end_iso,
        evaluation_phase=EvaluationPhase.EXPLORATORY,
    )
    (empty / "manifest.json").write_text(
        json.dumps(bare.model_dump(mode="json")), encoding="utf-8"
    )
    (data / "build_manifest.json").write_text(
        json.dumps({"case_order": ["aaa", "bbb"]}), encoding="utf-8"
    )


def test_check_reports_identical_rebuilds_and_counts_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _corpus(tmp_path)
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    assert cli.main(["--corpus", "build"]) == 0
    out = capsys.readouterr().out
    assert "2 windows, 1 graphs" in out
    assert "rebuilds identical: 1/1" in out
    assert "noStructural (S1.6) changes the snapshot hash: 1/1" in out
    assert "causal edges per graph" in out
    for name in ("redis", "cart", "kafka", "logger", "frontend"):
        assert name not in out
