"""Tests for RunOrchestrator — full C1 pipeline dispatch for a corpus."""

from __future__ import annotations

import datetime as dt
import json
import time
import types
from dataclasses import replace
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

if TYPE_CHECKING:
    from pathlib import Path

from helios.integrity_gate import AppendOnlyLedger
from helios.orchestrator import runner as runner_module
from helios.orchestrator.ledger import ReconciliationLedger
from helios.orchestrator.runner import RunOrchestrator
from helios.pipelines.d_pipe.params import load_dpipe_params
from helios.pipelines.d_pipe.pipeline import run_dpipe as run_dpipe_unpatched
from helios.pipelines.g_pipe.params import load_gpipe_params
from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.schemas.ueg_c import NodeType, UEGCNode, UEGCSnapshot
from helios.schemas.verdict import PipelineName
from helios.store.result_store import ResultStore
from helios.telemetry.seal import write_seal
from helios.telemetry.trigger import (
    DetectorParams,
    ExternalTriggerRefusedError,
    ProvisionalParametersError,
    TriggerRecord,
    TriggerSource,
    load_detector_params,
    load_external_triggers,
)
from helios.vcl import get_variant, set_current_manifest

if TYPE_CHECKING:
    from helios.vcl.config import VCLManifest  # noqa: F401 — flag-guard compliance

_KEY = b"test-secret-at-least-32-chars-long!!"
_VARIANT = "HELIOS-Full"
_FINAL_PARAMS = DetectorParams(
    bucket_seconds=30, threshold=6, persistence=2, provisional=False
)


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


def _make_orchestrator(
    tmp_path: Path, captures: Path, **trigger_options: Any
) -> RunOrchestrator:
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
        **trigger_options,
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
        "gpu_ms": 640,  # model compute time from the LLM gateway (S1.10)
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
        assert lpipe["gpu_ms"] == 640
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


# ---------------------------------------------------------------------------
# Shared detection trigger through the orchestrator (S2.1)
# ---------------------------------------------------------------------------


def _capture_with_traces(
    captures: Path,
    incident_id: str,
    phase: EvaluationPhase = EvaluationPhase.EXPLORATORY,
) -> None:
    """A sealed capture that declares a traces file, so the graph path runs."""
    inc_dir = captures / incident_id
    inc_dir.mkdir(parents=True, exist_ok=True)
    traces = inc_dir / "p2_traces.parquet"
    # One span; build_ueg_c is replaced in these tests.
    pq.write_table(pa.table({"span_id": ["s1"]}), traces)
    window = TelemetryWindow(
        incident_id=incident_id,
        variant_config_hash="a" * 64,
        window_start_iso=dt.datetime(2026, 1, 1, tzinfo=dt.UTC).isoformat(),
        window_end_iso=dt.datetime(2026, 1, 1, 0, 5, tzinfo=dt.UTC).isoformat(),
        evaluation_phase=phase,
        p2_traces_path=str(traces),
    )
    manifest = window.model_dump()
    manifest["window_hash"] = window.compute_window_hash()
    (inc_dir / "manifest.json").write_text(
        json.dumps(manifest, default=str), encoding="utf-8"
    )
    write_seal(inc_dir, window, _KEY)


def _graph() -> UEGCSnapshot:
    return UEGCSnapshot(
        incident_id="inc-001",
        variant_config_hash="a" * 64,
        nodes=[
            UEGCNode(node_id=s, node_type=NodeType.SERVICE, service_name=s)
            for s in ("ad", "cart", "prometheus")
        ],
        edges=[],
        captured_at_iso="",
    )


def _record(
    *suspects: str, source: TriggerSource = TriggerSource.THRESHOLD
) -> TriggerRecord:
    return TriggerRecord(
        incident_id="inc-001",
        trigger_time_s=1_767_225_660,
        suspects=suspects,
        context=(),
        source=source,
        detector_hash="d" * 64,
    )


class _Spy:
    """Records the order of runner steps and the pruner's arguments."""

    def __init__(self, record: TriggerRecord) -> None:
        self.record = record
        self.events: list[str] = []
        self.prune_kwargs: dict[str, Any] = {}
        self.dpipe_trigger: TriggerRecord | None = None

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def detect(window: TelemetryWindow, params: Any, **_: Any) -> TriggerRecord:
            self.events.append("detect")
            return self.record

        def prune(snapshot: UEGCSnapshot, **kwargs: Any) -> tuple[UEGCSnapshot, None]:
            self.events.append("prune")
            self.prune_kwargs = kwargs
            return snapshot, None

        real_dpipe = run_dpipe_unpatched

        def dpipe(**kwargs: Any) -> dict[str, Any]:
            self.dpipe_trigger = kwargs["trigger"]
            return dict(real_dpipe(**kwargs))

        monkeypatch.setattr(runner_module, "detect", detect)
        monkeypatch.setattr(runner_module, "build_ueg_c", lambda *a, **k: _graph())
        monkeypatch.setattr(
            runner_module,
            "apply_structural_bundle",
            lambda s: types.SimpleNamespace(snapshot=s),
        )
        monkeypatch.setattr(runner_module, "khop_prune", prune)
        monkeypatch.setattr(runner_module, "run_dpipe", dpipe)
        monkeypatch.setattr(runner_module, "run_lpipe", _fake_lpipe)


def _store(tmp_path: Path) -> ResultStore:
    return ResultStore(tmp_path / "results.duckdb")


class TestSharedTrigger:
    def test_trigger_runs_before_pruning_and_seeds_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        spy = _Spy(_record("cart", "metric-only"))
        spy.install(monkeypatch)
        captures = tmp_path / "captures"
        _capture_with_traces(captures, "inc-001")
        _make_orchestrator(tmp_path, captures).run(captures)
        assert spy.events == ["detect", "prune"]
        assert spy.prune_kwargs["seeds"] == ["cart"]
        assert "prometheus" in spy.prune_kwargs["exclude"]
        con = duckdb.connect(str(tmp_path / "results.duckdb"))
        assert con.execute("SELECT seeds_from_trigger FROM trigger_row").fetchall() == [
            (True,)
        ]

    def test_suspects_missing_from_graph_fall_back_to_pruner_seeds(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        spy = _Spy(_record("metric-only"))
        spy.install(monkeypatch)
        captures = tmp_path / "captures"
        _capture_with_traces(captures, "inc-001")
        _make_orchestrator(tmp_path, captures).run(captures)
        assert spy.prune_kwargs["seeds"] is None
        con = duckdb.connect(str(tmp_path / "results.duckdb"))
        assert con.execute("SELECT seeds_from_trigger FROM trigger_row").fetchall() == [
            (False,)
        ]

    def test_trigger_time_identical_for_helios_and_a_baseline_reader(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        spy = _Spy(_record("cart"))
        spy.install(monkeypatch)
        captures = tmp_path / "captures"
        _capture_with_traces(captures, "inc-001")
        _make_orchestrator(tmp_path, captures).run(captures)
        variant_hash = get_variant(_VARIANT).compute_variant_config_hash()
        # The baseline harness (S4.8) reads the stored record.
        assert (
            _store(tmp_path).fetch_trigger("inc-001", variant_hash) == spy.dpipe_trigger
        )
        assert spy.dpipe_trigger == spy.record

    def test_rankings_exclude_out_of_scope_services_for_every_pipeline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def lpipe(**kw: Any) -> dict[str, Any]:
            return {**_fake_lpipe(**kw), "ranked_candidates": ["prometheus", "svc-b"]}

        def dpipe(**kw: Any) -> dict[str, Any]:
            return {
                "pipeline": "dpipe",
                "incident_id": kw["incident_id"],
                "run_id": kw["run_id"],
                "variant_config_hash": kw["variant_config_hash"],
                "snapshot_hash": kw["snapshot_hash"],
                "evaluation_phase": kw["evaluation_phase"],
                "status": "ranked",
                "ranked_candidates": ["jaeger", "cart", "ad"],
                "candidate_scores": {"jaeger": 6, "cart": 3, "ad": 1},
                "mu": 6 / 10,
                "sigma": None,
                "narrative": "",
            }

        monkeypatch.setattr(runner_module, "run_lpipe", lpipe)
        monkeypatch.setattr(runner_module, "run_dpipe", dpipe)
        captures = tmp_path / "captures"
        _make_capture(captures, "inc-001")
        _make_orchestrator(tmp_path, captures).run(captures)
        rows = _rows(tmp_path)
        assert json.loads(str(rows["lpipe"]["ranked_candidates"])) == ["svc-b"]
        assert json.loads(str(rows["dpipe"]["ranked_candidates"])) == ["cart", "ad"]
        assert json.loads(str(rows["dpipe"]["candidate_scores"])) == {
            "ad": 1,
            "cart": 3,
        }
        assert rows["dpipe"]["mu"] == 3 / 4

    def test_timing_rows_written_for_each_dispatched_pipeline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(runner_module, "run_lpipe", _fake_lpipe)
        captures = tmp_path / "captures"
        _make_capture(captures, "inc-001")
        _make_orchestrator(tmp_path, captures).run(captures)
        store = _store(tmp_path)
        run_id = str(store.fetch_all()[0]["run_id"])
        timings = store.fetch_timings(run_id)
        assert {str(t["pipeline"]) for t in timings} == {"dpipe", "lpipe"}
        trigger = store._con.execute("SELECT handover_unix FROM trigger_row").fetchone()
        assert trigger is not None
        assert all(float(str(t["started_unix"])) >= trigger[0] for t in timings)

    def test_external_trigger_is_used_in_exploratory_runs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(runner_module, "run_lpipe", _fake_lpipe)
        external = tmp_path / "triggers.jsonl"
        record = _record("cart", source=TriggerSource.EXTERNAL)
        external.write_text(record.model_dump_json() + "\n", encoding="utf-8")
        captures = tmp_path / "captures"
        _make_capture(captures, "inc-001")
        orch = _make_orchestrator(tmp_path, captures, external_triggers=external)
        orch.run(captures)
        variant_hash = get_variant(_VARIANT).compute_variant_config_hash()
        assert _store(tmp_path).fetch_trigger("inc-001", variant_hash) == record

    def test_external_file_must_hold_only_external_records(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "triggers.jsonl"
        path.write_text(_record("cart").model_dump_json() + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match="external"):
            load_external_triggers(path)

    def test_confirmatory_run_refuses_external_triggers(self, tmp_path: Path) -> None:
        external = tmp_path / "triggers.jsonl"
        record = _record("cart", source=TriggerSource.EXTERNAL)
        external.write_text(record.model_dump_json() + "\n", encoding="utf-8")
        captures = tmp_path / "captures"
        _capture_with_traces(captures, "inc-001", EvaluationPhase.CONFIRMATORY)
        orch = _make_orchestrator(
            tmp_path,
            captures,
            external_triggers=external,
            detector_params=_FINAL_PARAMS,
        )
        orch._reader._pool_lock = lambda _incident: None
        with pytest.raises(ExternalTriggerRefusedError):
            orch.run(captures)

    def test_confirmatory_run_refuses_provisional_parameters(
        self, tmp_path: Path
    ) -> None:
        captures = tmp_path / "captures"
        _capture_with_traces(captures, "inc-001", EvaluationPhase.CONFIRMATORY)
        orch = _make_orchestrator(
            tmp_path,
            captures,
            detector_params=replace(_FINAL_PARAMS, provisional=True),
        )
        orch._reader._pool_lock = lambda _incident: None
        with pytest.raises(ProvisionalParametersError):
            orch.run(captures)


class TestSharedTriggerReviewFixes:
    def test_ranking_entirely_out_of_scope_becomes_abstained(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def lpipe(**kw: Any) -> dict[str, Any]:
            return {**_fake_lpipe(**kw), "ranked_candidates": ["jaeger"]}

        monkeypatch.setattr(runner_module, "run_lpipe", lpipe)
        captures = tmp_path / "captures"
        _make_capture(captures, "inc-001")
        _make_orchestrator(tmp_path, captures).run(captures)
        lpipe_row = _rows(tmp_path)["lpipe"]
        assert lpipe_row["status"] == "abstained"
        assert json.loads(str(lpipe_row["ranked_candidates"])) == []
        assert lpipe_row["mu"] is None

    def test_handover_is_taken_before_the_graph_is_built(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        spy = _Spy(_record("cart"))
        spy.install(monkeypatch)
        built_at: list[float] = []

        def build(*_a: Any, **_k: Any) -> UEGCSnapshot:
            built_at.append(time.time())
            return _graph()

        monkeypatch.setattr(runner_module, "build_ueg_c", build)
        captures = tmp_path / "captures"
        _capture_with_traces(captures, "inc-001")
        _make_orchestrator(tmp_path, captures).run(captures)
        row = (
            _store(tmp_path)
            ._con.execute("SELECT handover_unix FROM trigger_row")
            .fetchone()
        )
        assert row is not None
        assert row[0] <= built_at[0]

    def test_gpipe_routing_sees_only_in_scope_dpipe_scores(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        spy = _Spy(_record("cart"))
        spy.install(monkeypatch)
        seen: dict[str, Any] = {}

        def dpipe(**kw: Any) -> dict[str, Any]:
            return {
                "pipeline": "dpipe",
                "incident_id": kw["incident_id"],
                "run_id": kw["run_id"],
                "variant_config_hash": kw["variant_config_hash"],
                "snapshot_hash": kw["snapshot_hash"],
                "evaluation_phase": kw["evaluation_phase"],
                "status": "ranked",
                "ranked_candidates": ["jaeger", "cart"],
                "candidate_scores": {"jaeger": 6, "cart": 3},
                "mu": 6 / 9,
                "sigma": None,
                "narrative": "",
            }

        def should_run(d_out: dict[str, Any], _manifest: Any) -> bool:
            seen["routing"] = dict(d_out["candidate_scores"])
            return False

        monkeypatch.setattr(runner_module, "run_dpipe", dpipe)
        monkeypatch.setattr(runner_module, "should_run_gpipe", should_run)
        captures = tmp_path / "captures"
        _capture_with_traces(captures, "inc-001")
        _make_orchestrator(tmp_path, captures).run(captures)
        assert seen["routing"] == {"cart": 3}


class TestDPipeParameters:
    def test_runner_uses_frozen_dpipe_params_not_defaults(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict[str, Any] = {}

        def dpipe(**kw: Any) -> dict[str, Any]:
            seen.update(kw)
            return dict(run_dpipe_unpatched(**kw))

        monkeypatch.setattr(runner_module, "run_dpipe", dpipe)
        monkeypatch.setattr(runner_module, "run_lpipe", _fake_lpipe)
        captures = tmp_path / "captures"
        _make_capture(captures, "inc-001")
        _make_orchestrator(tmp_path, captures).run(captures)
        frozen = load_dpipe_params()
        assert seen["w_error"] == frozen.w_error
        assert seen["w_resource"] == frozen.w_resource
        assert seen["rho_threshold"] == frozen.rho_threshold
        assert seen["topology_boost_factor"] == frozen.topology_boost_factor
        assert seen["evidence_ref"] == load_detector_params().threshold

    def test_confirmatory_run_refuses_provisional_dpipe_params(
        self, tmp_path: Path
    ) -> None:
        captures = tmp_path / "captures"
        _capture_with_traces(captures, "inc-001", EvaluationPhase.CONFIRMATORY)
        orch = _make_orchestrator(
            tmp_path,
            captures,
            detector_params=_FINAL_PARAMS,
            dpipe_params=replace(load_dpipe_params(), provisional=True),
        )
        orch._reader._pool_lock = lambda _incident: None
        with pytest.raises(ProvisionalParametersError):
            orch.run(captures)

    def test_missing_dpipe_parameter_file_is_an_error(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_dpipe_params(tmp_path / "absent.json")


class TestIncidentGraph:
    """The runner's graph step as a function: D-pipe calibration reuses it."""

    def test_no_traces_gives_no_graph_and_no_seeds(self) -> None:
        window = TelemetryWindow(
            incident_id="inc-001",
            variant_config_hash="a" * 64,
            window_start_iso=dt.datetime(2026, 1, 1, tzinfo=dt.UTC).isoformat(),
            window_end_iso=dt.datetime(2026, 1, 1, 0, 5, tzinfo=dt.UTC).isoformat(),
            evaluation_phase=EvaluationPhase.EXPLORATORY,
        )
        manifest = get_variant(_VARIANT)
        assert runner_module.incident_graph(
            window, manifest, "c" * 64, _record("cart")
        ) == (None, [])

    def test_graph_is_pruned_around_the_trigger_suspects(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        spy = _Spy(_record("cart", "metric-only"))
        spy.install(monkeypatch)
        captures = tmp_path / "captures"
        _capture_with_traces(captures, "inc-001")
        window = TelemetryWindow.model_validate(
            {
                k: v
                for k, v in json.loads(
                    (captures / "inc-001" / "manifest.json").read_text()
                ).items()
                if k != "window_hash"
            }
        )
        graph, seeds = runner_module.incident_graph(
            window, get_variant(_VARIANT), "c" * 64, spy.record
        )
        assert graph is not None
        assert seeds == ["cart"]
        assert spy.events == ["prune"]
        assert "prometheus" in spy.prune_kwargs["exclude"]


class TestGPipeS22:
    def test_runner_passes_window_trigger_and_frozen_params_and_stores_evidence(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        spy = _Spy(_record("cart"))
        spy.install(monkeypatch)
        seen: dict[str, Any] = {}
        evidence = {"suspects": [{"service": "cart", "wait_from": {}}]}

        def gpipe(**kw: Any) -> dict[str, Any]:
            seen.update(kw)
            return {
                "pipeline": "gpipe",
                "incident_id": kw["incident_id"],
                "run_id": kw["run_id"],
                "snapshot_hash": kw["snapshot_hash"],
                "status": "skipped",
                "ranked_candidates": [],
                "candidate_scores": {},
                "latency_ms": 1,
                "evidence": evidence,
            }

        monkeypatch.setattr(runner_module, "should_run_gpipe", lambda *_: True)
        monkeypatch.setattr(runner_module, "run_gpipe", gpipe)
        captures = tmp_path / "captures"
        _capture_with_traces(captures, "inc-001")
        _make_orchestrator(tmp_path, captures).run(captures)
        assert seen["window"].incident_id == "inc-001"
        assert seen["trigger"] == spy.record
        assert seen["params"] == load_gpipe_params()
        assert seen["detector"] == load_detector_params()
        con = duckdb.connect(str(tmp_path / "results.duckdb"))
        stored = con.execute(
            "SELECT pipeline, evidence_json FROM evidence_row"
        ).fetchall()
        assert [(p, json.loads(e)) for p, e in stored] == [("gpipe", evidence)]

    def test_confirmatory_run_refuses_provisional_gpipe_params(
        self, tmp_path: Path
    ) -> None:
        captures = tmp_path / "captures"
        _capture_with_traces(captures, "inc-001", EvaluationPhase.CONFIRMATORY)
        orch = _make_orchestrator(
            tmp_path,
            captures,
            detector_params=_FINAL_PARAMS,
            dpipe_params=replace(load_dpipe_params(), provisional=False),
            gpipe_params=replace(load_gpipe_params(), provisional=True),
        )
        orch._reader._pool_lock = lambda _incident: None
        with pytest.raises(ProvisionalParametersError, match="G-pipe"):
            orch.run(captures)
