"""The runner publishes one fused verdict per run (S2.5 MAHC, S2.6 vote-only)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

from helios.integrity_gate import AppendOnlyLedger
from helios.orchestrator import runner as runner_module
from helios.orchestrator.runner import RunOrchestrator
from helios.store.result_store import ResultStore
from helios.vcl import VCLFlag, get_variant, set_current_manifest  # noqa: F401
from tests.test_orchestrator_runner import _KEY, _make_capture

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _fake(pipeline: str, ranked: list[str], sigma: float) -> Any:
    def run(**kw: Any) -> dict[str, Any]:
        out = {
            "pipeline": pipeline,
            "incident_id": kw["incident_id"],
            "run_id": kw["run_id"],
            "variant_config_hash": get_variant(
                kw.get("_v", "HELIOS-Full")
            ).compute_variant_config_hash(),
            "snapshot_hash": kw["snapshot_hash"],
            "evaluation_phase": kw["evaluation_phase"],
            "status": "ranked",
            "ranked_candidates": ranked,
            "candidate_scores": {},
            "mu": 1,
            "sigma": sigma,
            "narrative": "",
        }
        if pipeline == "lpipe":
            out["h_struct"] = {"outputs": 1, "failed": 0}
        return out

    return run


def _run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variant: str, name: str
) -> ResultStore:
    manifest = get_variant(variant)
    hash_ = manifest.compute_variant_config_hash()

    def wrap(fn: Any) -> Any:
        def inner(**kw: Any) -> dict[str, Any]:
            return {**fn(**kw), "variant_config_hash": hash_}

        return inner

    # The disagreement counterexample: D says a then b, unsure; L says b then a, sure.
    monkeypatch.setattr(
        runner_module, "run_dpipe", wrap(_fake("dpipe", ["svc-a", "svc-b"], 0.8))
    )
    monkeypatch.setattr(
        runner_module, "run_lpipe", wrap(_fake("lpipe", ["svc-b", "svc-a"], 0.1))
    )
    captures = tmp_path / "captures"
    if not captures.exists():
        _make_capture(captures, "inc-001")
    set_current_manifest(manifest)
    RunOrchestrator(
        manifest=manifest,
        captures_dir=captures,
        db_path=tmp_path / f"{name}.duckdb",
        registry_path=tmp_path / f"{name}.registry.jsonl",
        reconciliation_path=tmp_path / f"{name}.reconciliation.jsonl",
        exclusion_ledger=MagicMock(spec=AppendOnlyLedger),
        hmac_key=_KEY,
    ).run(captures)
    return ResultStore(tmp_path / f"{name}.duckdb")


def _fusion(store: ResultStore) -> dict[str, Any]:
    rows = store.fetch_all_fusion_rows()
    assert len(rows) == 1
    return rows[0]


def test_full_stores_a_mahc_fusion_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = _fusion(_run(tmp_path, monkeypatch, "HELIOS-Full", "full"))
    assert row["method"] == "mahc"
    assert row["state"] in {"confirmed", "provisional"}
    from helios.consensus.params import load_mahc_params

    # A calibrated confidence exactly when the parameters are frozen.
    assert (row["confidence"] is None) == load_mahc_params().provisional
    assert row["evidence"]["signal"] == "unclassified"
    assert row["ranked"][0] == "svc-b"


def test_no_consensus_stores_vote_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = _fusion(_run(tmp_path, monkeypatch, "HELIOS-noConsensus", "nc"))
    assert row["method"] == "vote_only"
    assert row["state"] == "confirmed"


def test_no_consensus_differs_from_full_on_a_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    full = _fusion(_run(tmp_path, monkeypatch, "HELIOS-Full", "full"))
    plain = _fusion(_run(tmp_path, monkeypatch, "HELIOS-noConsensus", "nc"))
    assert full["ranked"][0] == "svc-b"
    assert plain["ranked"][0] == "svc-a"  # a 1.5 vs b 1.5, tie by name


def test_excluded_run_has_no_fusion_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from helios import integrity_gate

    def fail(self: Any, rows: Any, *, incident_id: str) -> Any:
        return integrity_gate.GateResult(status="FAIL", gate_check="forced")

    monkeypatch.setattr(integrity_gate.MetricIntegrityGate, "check_consistency", fail)
    store = _run(tmp_path, monkeypatch, "HELIOS-Full", "full")
    assert store.fetch_all_fusion_rows() == []


def test_rerun_equal_fusion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    a = _fusion(_run(tmp_path, monkeypatch, "HELIOS-Full", "a"))
    b = _fusion(_run(tmp_path, monkeypatch, "HELIOS-Full", "b"))
    for key in ("ranked", "scores", "confidence", "fused_sigma", "state"):
        assert a[key] == b[key], key


def test_confirmatory_run_refuses_provisional_mahc_params(tmp_path: Path) -> None:
    from helios.consensus.params import MAHCParams
    from helios.consensus.priors import fit_priors
    from helios.telemetry.trigger import ProvisionalParametersError
    from tests.test_orchestrator_runner import _make_orchestrator

    orch = _make_orchestrator(tmp_path, tmp_path / "captures")
    orch._mahc = MAHCParams(fit_priors([]), None, None, provisional=True)
    window = MagicMock(evaluation_phase="confirmatory")
    orch._detector = MagicMock(provisional=False)
    orch._dpipe = MagicMock(provisional=False)
    orch._gpipe = MagicMock(provisional=False)
    try:
        orch._trigger_for(window)
    except ProvisionalParametersError as exc:
        assert "MAHC" in str(exc)
    else:
        raise AssertionError("provisional MAHC parameters must be refused")
