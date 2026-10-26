"""Tests for RunOrchestrator — full C1 pipeline dispatch for a corpus."""

from __future__ import annotations

import datetime as dt
import json
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from helios.integrity_gate import AppendOnlyLedger
from helios.orchestrator.ledger import ReconciliationLedger
from helios.orchestrator.runner import RunOrchestrator
from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.schemas.verdict import PipelineName
from helios.telemetry.seal import write_seal
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
    write_seal(inc_dir, window, _KEY)  # a real capture is sealed once final


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

    def test_all_three_pipeline_verdicts_share_run_id(self, tmp_path: Path) -> None:
        """D-pipe, G-pipe, and L-pipe verdicts for one incident share the same run_id."""
        captures = tmp_path / "captures"
        _make_capture(captures, "inc-runid-001")
        orch = _make_orchestrator(tmp_path, captures)
        orch.run(captures)

        from helios.store.result_store import ResultStore

        store = ResultStore(tmp_path / "results.duckdb")
        rows = store.fetch_all_for_incident("inc-runid-001")
        run_ids = {r["run_id"] for r in rows}
        assert len(run_ids) == 1, f"Expected 1 run_id, got: {run_ids}"


# ---------------------------------------------------------------------------
# Verdict contract through the orchestrator (S1.8)
# ---------------------------------------------------------------------------


def _fake_lpipe(**kwargs: Any) -> dict[str, Any]:
    return {
        "pipeline": "lpipe",
        "incident_id": kwargs["incident_id"],
        "run_id": kwargs["run_id"],
        "variant_config_hash": get_variant(_VARIANT).compute_variant_config_hash(),
        "snapshot_hash": kwargs["snapshot_hash"],
        "evaluation_phase": kwargs["evaluation_phase"],
        "status": "ranked",
        "ranked_candidates": ["svc-b", "svc-a"],
        "candidate_scores": {},
        "mu": None,
        "sigma": None,
        "prompt_tokens": 410,
        "completion_tokens": 90,
        "latency_ms": 987_654,  # the pipeline's own clock; the runner's wins
        "narrative": "svc-b",
        "prompt_version": "rca_v1",
    }


def _rows(tmp_path: Path) -> dict[str, dict[str, object]]:
    from helios.store.result_store import ResultStore

    store = ResultStore(tmp_path / "results.duckdb")
    rows = {str(r["pipeline"]): r for r in store.fetch_all()}
    store.close()
    return rows


class TestVerdictContract:
    def test_every_pipeline_gives_a_contract_row(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("helios.orchestrator.runner.run_lpipe", _fake_lpipe)
        captures = tmp_path / "captures"
        _make_capture(captures, "inc-001")
        _make_orchestrator(tmp_path, captures).run(captures)

        rows = _rows(tmp_path)
        # No metrics in the capture: the D-pipe has nothing to rank; no graph,
        # so the G-pipe is not dispatched.
        assert rows["dpipe"]["status"] == "abstained"
        assert rows["gpipe"]["status"] == "skipped"
        assert rows["gpipe"]["narrative"] == "gpipe-gated-or-skipped"
        lpipe = rows["lpipe"]
        assert lpipe["status"] == "ranked"
        assert json.loads(str(lpipe["ranked_candidates"])) == ["svc-b", "svc-a"]
        assert (lpipe["prompt_tokens"], lpipe["completion_tokens"]) == (410, 90)
        assert lpipe["prompt_version"] == "rca_v1"
        # Latency and CPU time are measured by the runner, the same way for all.
        assert 0 <= float(str(lpipe["latency_ms"])) < 987_654
        assert float(str(lpipe["cpu_ms"])) >= 0
        assert {str(r["schema_version"]) for r in rows.values()} == {
            "schema-draft-v0.5"
        }

    def test_variant_without_dpipe_gives_a_skipped_dpipe_verdict(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # HELIOS-LLM-only turns the D-pipe off; the runner used to let
        # GatedComponentInactiveError escape and abort the run.
        manifest = get_variant("HELIOS-LLM-only")
        assert not manifest.dpipe
        set_current_manifest(manifest)
        captures = tmp_path / "captures"
        _make_capture(captures, "inc-001")
        orch = RunOrchestrator(
            manifest=manifest,
            captures_dir=captures,
            db_path=tmp_path / "results.duckdb",
            registry_path=tmp_path / "registry.jsonl",
            reconciliation_path=tmp_path / "reconciliation.jsonl",
            exclusion_ledger=MagicMock(spec=AppendOnlyLedger),
            hmac_key=_KEY,
        )
        monkeypatch.setattr(
            "helios.orchestrator.runner.run_lpipe",
            lambda **kw: {
                **_fake_lpipe(**kw),
                "variant_config_hash": manifest.compute_variant_config_hash(),
            },
        )
        orch.run(captures)

        rows = _rows(tmp_path)
        assert rows["dpipe"]["status"] == "skipped"
        assert rows["dpipe"]["narrative"] == "dpipe-gated-or-skipped"
        assert (rows["dpipe"]["latency_ms"], rows["dpipe"]["cpu_ms"]) == (0, 0)
        assert rows["lpipe"]["status"] == "ranked"

    def test_output_for_another_pipeline_is_refused(self, tmp_path: Path) -> None:
        captures = tmp_path / "captures"
        orch = _make_orchestrator(tmp_path, captures)
        base = {
            "run_id": "r",
            "incident_id": "i",
            "variant_config_hash": "a" * 64,
            "snapshot_hash": "b" * 64,
            "evaluation_phase": EvaluationPhase.EXPLORATORY,
        }
        with pytest.raises(ValueError, match="returned a verdict for 'gpipe'"):
            orch._dispatch(
                PipelineName.DPIPE, base, lambda: {**base, "pipeline": "gpipe"}
            )
