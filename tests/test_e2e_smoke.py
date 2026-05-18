"""E2E smoke test — full pipeline run: variant selection → stubs → DuckDB row (EG4 gate).

This is THE binding integration test for Stage 0. It verifies:
1. A VCLManifest is selected and set as the active context.
2. G-pipe and L-pipe gated stubs execute under the active manifest.
3. PipelineVerdict rows are inserted into ResultStore.
4. inclusion_rate() returns a value > 0 for the active variant.
5. evaluation_phase='exploratory' is persisted correctly.

Stage 0 has no real Parquet ingestion — pipelines receive pre-built snapshot hashes.
The test is the EG4 gate evidence artefact.

VCLManifest-aware: variant_config_hash from the active manifest.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from helios.pipelines.g_pipe.pipeline import run_gpipe
from helios.pipelines.l_pipe.stub import run_lpipe
from helios.schemas import EvaluationPhase, PipelineVerdict
from helios.schemas.ueg_c import EdgeType, NodeType, UEGCEdge, UEGCNode, UEGCSnapshot
from helios.store.result_store import ResultStore
from helios.vcl import VCLFlag, get_variant, set_current_manifest
from helios.vcl.snapshot_registry import SnapshotRegistry

if TYPE_CHECKING:
    from pathlib import Path

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

_INCIDENT = "inc-smoke-001"
_SNAP_HASH = "a" * 64

# Minimal snapshot for smoke tests — no real Parquet ingestion at Stage 0
_SMOKE_SNAPSHOT = UEGCSnapshot(
    incident_id=_INCIDENT,
    variant_config_hash="a" * 64,
    nodes=[
        UEGCNode(node_id="A", node_type=NodeType.SERVICE, service_name="A"),
        UEGCNode(node_id="B", node_type=NodeType.SERVICE, service_name="B"),
        UEGCNode(node_id="C", node_type=NodeType.SERVICE, service_name="C"),
    ],
    edges=[
        UEGCEdge(source="A", target="B", edge_type=EdgeType.CALL, weight=0.80),
        UEGCEdge(source="B", target="C", edge_type=EdgeType.CALL, weight=0.60),
    ],
    captured_at_iso="2026-01-01T00:00:00+00:00",
)

# D-pipe scores with disagreement above threshold so gpipe runs
_SMOKE_DPIPE_SCORES = {"A": 0.90, "B": 0.45, "C": 0.36}


@pytest.fixture()
def store(tmp_path: Path) -> ResultStore:
    return ResultStore(tmp_path / "smoke.db")


@pytest.fixture()
def snap_registry(tmp_path: Path) -> SnapshotRegistry:
    reg = SnapshotRegistry(tmp_path / "snapshots.jsonl")
    reg.register(_SNAP_HASH, "0" * 64)  # pre-register with a placeholder variant hash
    return reg


# ------------------------------------------------------------------
# EG4 — binding integration test
# ------------------------------------------------------------------


def test_full_pipeline_exploratory_row_inserted(
    store: ResultStore,
    snap_registry: SnapshotRegistry,
) -> None:
    """EG4 gate: Parquet-stub → g_pipe + l_pipe → DuckDB result rows (exploratory)."""
    manifest = get_variant("HELIOS-Full")
    set_current_manifest(manifest)
    vch = manifest.compute_variant_config_hash()

    # Re-register snapshot with correct variant hash
    snap_hash = _SNAP_HASH
    reg2 = SnapshotRegistry(
        snap_registry._path
    )  # access internal path for fixture reuse
    assert reg2.contains(snap_hash)

    # Run gated pipelines (simulating pipeline execution)
    g_result = run_gpipe(
        incident_id=_INCIDENT,
        snapshot=_SMOKE_SNAPSHOT,
        snapshot_hash=snap_hash,
        dpipe_scores=_SMOKE_DPIPE_SCORES,
        evaluation_phase="exploratory",
        run_id="smoke-gpipe-001",
    )
    l_result = run_lpipe(incident_id=_INCIDENT, snapshot_hash=snap_hash)

    # Build and insert PipelineVerdict rows
    for idx, result in enumerate([g_result, l_result]):
        verdict = PipelineVerdict(
            run_id=f"smoke-{result['pipeline']}-{idx}",
            incident_id=result["incident_id"],
            variant_config_hash=vch,
            snapshot_hash=result["snapshot_hash"],
            pipeline=result["pipeline"],
            evaluation_phase=EvaluationPhase.EXPLORATORY,
            ranked_candidates=result["ranked_candidates"],
            hr_at_3=result["hr_at_3"],
            cpr=result["cpr"],
            latency_ms=result["latency_ms"],
            token_count=result["token_count"],
            narrative=result["narrative"],
        )
        store.insert(verdict)

    # Assertions
    rows = store.fetch_all()
    assert len(rows) == 2
    pipelines = {r["pipeline"] for r in rows}
    assert "gpipe" in pipelines
    assert "lpipe" in pipelines

    for row in rows:
        assert row["evaluation_phase"] == "exploratory"
        assert row["variant_config_hash"] == vch
        assert row["snapshot_hash"] == snap_hash

    rate = store.inclusion_rate(vch)
    assert rate > 0


def test_full_pipeline_inactive_flag_blocks_stub(
    store: ResultStore,
    snap_registry: SnapshotRegistry,
) -> None:
    """L-pipe is inactive in HELIOS-noLLM; invoking it raises GatedComponentInactiveError."""
    from helios.vcl import GatedComponentInactiveError

    manifest = get_variant("HELIOS-noLLM")
    set_current_manifest(manifest)

    with pytest.raises(GatedComponentInactiveError):
        run_lpipe(incident_id=_INCIDENT, snapshot_hash=_SNAP_HASH)


def test_snapshot_registry_integration(
    tmp_path: Path,
    store: ResultStore,
) -> None:
    """Snapshot hash registered before pipeline run is visible after insert."""
    reg = SnapshotRegistry(tmp_path / "reg2.jsonl")
    manifest = get_variant("HELIOS-Full")
    set_current_manifest(manifest)
    vch = manifest.compute_variant_config_hash()

    snap = "e" * 64
    reg.register(snap, vch)
    assert reg.contains(snap)

    smoke_snap = UEGCSnapshot(
        incident_id="inc-reg-test",
        variant_config_hash=vch,
        nodes=[
            UEGCNode(node_id="A", node_type=NodeType.SERVICE, service_name="A"),
            UEGCNode(node_id="B", node_type=NodeType.SERVICE, service_name="B"),
            UEGCNode(node_id="C", node_type=NodeType.SERVICE, service_name="C"),
        ],
        edges=[
            UEGCEdge(source="A", target="B", edge_type=EdgeType.CALL, weight=0.80),
            UEGCEdge(source="B", target="C", edge_type=EdgeType.CALL, weight=0.60),
        ],
        captured_at_iso="2026-01-01T00:00:00+00:00",
    )
    g_result = run_gpipe(
        incident_id="inc-reg-test",
        snapshot=smoke_snap,
        snapshot_hash=snap,
        dpipe_scores=_SMOKE_DPIPE_SCORES,
        evaluation_phase="exploratory",
        run_id="smoke-reg-test-gpipe",
    )
    verdict = PipelineVerdict(
        run_id="smoke-reg-test",
        incident_id="inc-reg-test",
        variant_config_hash=vch,
        snapshot_hash=snap,
        pipeline="gpipe",
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        ranked_candidates=[],
        hr_at_3=g_result["hr_at_3"],
        cpr=g_result["cpr"],
        latency_ms=g_result["latency_ms"],
        token_count=g_result["token_count"],
        narrative=g_result["narrative"],
    )
    store.insert(verdict)
    rows = store.fetch_all()
    assert any(r["snapshot_hash"] == snap for r in rows)


# ------------------------------------------------------------------
# VCLFlag smoke (flag-guard compliance)
# ------------------------------------------------------------------


def test_vcl_flag_accessible() -> None:
    assert VCLFlag.L2B_GRAPH in VCLFlag.bool_flags()
    assert VCLFlag.L2C_LLM in VCLFlag.bool_flags()


def test_orchestrator_e2e_three_pipeline_dispatch(tmp_path: Path) -> None:
    """Full C1 path: capture → registry → 3 stubs → gate → 3 result_rows inserted."""
    import datetime as dt
    import json
    from unittest.mock import MagicMock

    from helios.integrity_gate import AppendOnlyLedger
    from helios.orchestrator.runner import RunOrchestrator
    from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
    from helios.store.result_store import ResultStore
    from helios.vcl import get_variant, set_current_manifest

    captures = tmp_path / "captures"
    inc_dir = captures / "smoke-001"
    inc_dir.mkdir(parents=True)
    window = TelemetryWindow(
        incident_id="smoke-001",
        variant_config_hash="a" * 64,
        window_start_iso=dt.datetime(2026, 1, 1, tzinfo=dt.UTC).isoformat(),
        window_end_iso=dt.datetime(2026, 1, 1, 0, 5, tzinfo=dt.UTC).isoformat(),
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        p1_metrics_path=None,
        p2_traces_path=None,
        p3_logs_path=None,
    )
    mdata = window.model_dump()
    mdata["window_hash"] = window.compute_window_hash()
    (inc_dir / "manifest.json").write_text(json.dumps(mdata, default=str))

    vcl = get_variant("HELIOS-Full")
    set_current_manifest(vcl)
    key = b"test-secret-at-least-32-chars-long!!"

    orch = RunOrchestrator(
        manifest=vcl,
        captures_dir=captures,
        db_path=tmp_path / "results.duckdb",
        registry_path=tmp_path / "registry.jsonl",
        reconciliation_path=tmp_path / "reconciliation.jsonl",
        exclusion_ledger=MagicMock(spec=AppendOnlyLedger),
        hmac_key=key,
    )
    orch.run(captures)

    store = ResultStore(tmp_path / "results.duckdb")
    rows = store._con.execute(
        "SELECT pipeline FROM result_row WHERE incident_id='smoke-001'"
    ).fetchall()
    assert {r[0] for r in rows} == {"dpipe", "gpipe", "lpipe"}
