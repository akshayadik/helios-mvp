"""Tests for RunOrchestrator — full C1 pipeline dispatch for a corpus."""

from __future__ import annotations

import datetime as dt
import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from pathlib import Path

from helios.integrity_gate import AppendOnlyLedger
from helios.orchestrator.ledger import ReconciliationLedger
from helios.orchestrator.runner import RunOrchestrator
from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.vcl import get_variant, set_current_manifest

if TYPE_CHECKING:
    from helios.vcl.config import VCLManifest  # noqa: F401 — flag-guard compliance

_KEY = b"test-secret-at-least-32-chars-long!!"
_VARIANT = "HELIOS-Full"


def _make_capture(captures: Path, incident_id: str) -> None:
    """Write a minimal valid capture under captures/{incident_id}/."""
    inc_dir = captures / incident_id
    inc_dir.mkdir(parents=True, exist_ok=True)
    window = TelemetryWindow(
        incident_id=incident_id,
        variant_config_hash="a" * 64,
        window_start_iso=dt.datetime(2026, 1, 1, tzinfo=dt.UTC).isoformat(),
        window_end_iso=dt.datetime(2026, 1, 1, 0, 5, tzinfo=dt.UTC).isoformat(),
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        p1_metrics_path=None,
        p2_traces_path=None,
        p3_logs_path=None,
    )
    manifest = window.model_dump()
    manifest["window_hash"] = window.compute_window_hash()
    (inc_dir / "manifest.json").write_text(
        json.dumps(manifest, default=str), encoding="utf-8"
    )


def _make_orchestrator(tmp_path: Path, captures: Path) -> RunOrchestrator:
    manifest = get_variant(_VARIANT)
    set_current_manifest(manifest)
    return RunOrchestrator(
        manifest=manifest,
        captures_dir=captures,
        db_path=tmp_path / "results.duckdb",
        registry_path=tmp_path / "registry.jsonl",
        reconciliation_path=tmp_path / "reconciliation.jsonl",
        exclusion_ledger=MagicMock(spec=AppendOnlyLedger),
        hmac_key=_KEY,
    )


class TestRunOrchestrator:
    def test_single_incident_produces_passed_reconciliation_entry(
        self, tmp_path: Path
    ) -> None:
        captures = tmp_path / "captures"
        _make_capture(captures, "inc-001")
        orch = _make_orchestrator(tmp_path, captures)
        orch.run(captures)

        rec_path = tmp_path / "reconciliation.jsonl"
        lines = rec_path.read_text().splitlines()
        assert len(lines) == 1
        row = json.loads(lines[0])
        assert row["incident_id"] == "inc-001"
        assert row["outcome"] == "passed"

    def test_reconciliation_chain_is_valid(self, tmp_path: Path) -> None:
        captures = tmp_path / "captures"
        _make_capture(captures, "inc-001")
        _make_capture(captures, "inc-002")
        orch = _make_orchestrator(tmp_path, captures)
        orch.run(captures)

        rec = ReconciliationLedger(key=_KEY, log_path=tmp_path / "reconciliation.jsonl")
        ok, msg = rec.verify()
        assert ok, msg

    def test_tampered_capture_is_skipped(self, tmp_path: Path) -> None:
        captures = tmp_path / "captures"
        _make_capture(captures, "inc-001")
        mpath = captures / "inc-001" / "manifest.json"
        data = json.loads(mpath.read_text())
        data["window_hash"] = "f" * 64
        mpath.write_text(json.dumps(data))

        orch = _make_orchestrator(tmp_path, captures)
        orch.run(captures)

        row = json.loads(
            (tmp_path / "reconciliation.jsonl").read_text().splitlines()[0]
        )
        assert row["outcome"] == "skipped"

    def test_three_pipeline_verdicts_inserted_per_incident(
        self, tmp_path: Path
    ) -> None:
        captures = tmp_path / "captures"
        _make_capture(captures, "inc-001")
        orch = _make_orchestrator(tmp_path, captures)
        orch.run(captures)

        from helios.store.result_store import ResultStore

        store = ResultStore(tmp_path / "results.duckdb")
        rows = store._con.execute(
            "SELECT pipeline FROM result_row WHERE incident_id='inc-001'"
        ).fetchall()
        assert {r[0] for r in rows} == {"dpipe", "gpipe", "lpipe"}
