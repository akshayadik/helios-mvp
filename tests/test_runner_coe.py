"""The runner writes one CoE entry per stored run (S2.7 design §5.3)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from helios.integrity_gate import AppendOnlyLedger
from helios.orchestrator.coe import CoELedger, fusion_record, row_ref
from helios.orchestrator.runner import MissingSigningKeyError, RunOrchestrator
from helios.store.result_store import ResultStore
from helios.vcl import VCLFlag, get_variant, set_current_manifest  # noqa: F401
from helios.vcl.ed25519 import generate_private_key
from helios.vcl.hmac_chain import TamperDetectedError, verify_public
from tests.pipelines.l_pipe.test_pipeline import OTEL, FakeClient
from tests.test_runner_lpipe import KEY, stage_capture

if TYPE_CHECKING:
    from pathlib import Path


SIGNER = generate_private_key()


def _orch(
    tmp_path: Path,
    variant: str = "HELIOS-Full",
    *,
    signer: Any = SIGNER,
    coe_path: Path | None = None,
) -> RunOrchestrator:
    captures = tmp_path / "captures"
    if not captures.exists():
        stage_capture(captures)
    manifest = get_variant(variant)
    set_current_manifest(manifest)
    return RunOrchestrator(
        manifest=manifest,
        captures_dir=captures,
        db_path=tmp_path / "r.duckdb",
        registry_path=tmp_path / "r.registry.jsonl",
        reconciliation_path=tmp_path / "r.reconciliation.jsonl",
        exclusion_ledger=MagicMock(spec=AppendOnlyLedger),
        hmac_key=KEY,
        lpipe_client=FakeClient(),  # type: ignore[arg-type]
        coe_signer=signer,
        coe_path=coe_path,
    )


def _run(
    tmp_path: Path, variant: str = "HELIOS-Full", *, signer: Any = SIGNER
) -> tuple[ResultStore, Path]:
    orch = _orch(tmp_path, variant, signer=signer)
    orch.run(tmp_path / "captures")
    return ResultStore(tmp_path / "r.duckdb"), orch.coe_path


def _entries(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def _step(entry: dict[str, Any], step_id: str) -> dict[str, Any]:
    return next(s for s in entry["steps"] if s["id"] == step_id)


def test_full_run_appends_one_coe_entry_per_stored_run(tmp_path: Path) -> None:
    store, path = _run(tmp_path)
    (entry,) = _entries(path)
    (run_id,) = {str(r["run_id"]) for r in store.fetch_all()}
    assert entry["run_id"] == run_id
    log = CoELedger(KEY, path, ed25519_private=SIGNER)
    assert log.verify()[0]
    ok, msg = verify_public(
        path, log.anchor_path, SIGNER.public_key(), from_entry=None, log_kind="coe"
    )
    assert ok, msg
    fusion = store.fetch_fusion(run_id)
    assert fusion is not None
    assert _step(entry, "F")["refs"]["fusion"] == row_ref(fusion)
    for name in ("dpipe", "gpipe", "lpipe"):
        stored = store.fetch_evidence(run_id, name)
        ref = _step(entry, f"P:{name}")["refs"]["evidence"]
        assert ref == (None if stored is None else row_ref(stored))
    assert set(entry["parameter_hashes"]) >= {"detector", "dpipe", "gpipe", "mahc"}
    # S2-BL-20: the model digest the L-pipe actually ran with, from its evidence.
    lpipe = store.fetch_evidence(run_id, "lpipe")
    assert lpipe is not None
    assert entry["parameter_hashes"]["lpipe_model"] == lpipe["model_digest"] != ""
    assert _step(entry, "G")["outcome"] == "PASS"
    # S2-BL-12: the T step records when a live detector could have known.
    t = _step(entry, "T")
    trigger = store.fetch_trigger(entry["incident_id"], entry["variant_config_hash"])
    assert trigger is not None
    delay = trigger.detection_delay_s
    assert trigger.known_at_s is not None
    assert delay is not None
    assert delay >= 0
    assert t["known_at_s"] == trigger.known_at_s
    assert t["detection_delay_s"] == delay
    # fusion_record mirrors the stored row exactly (the ref is recomputable)
    assert set(fusion) == set(fusion_record("r", "i", "h", _fused_like()))


def _fused_like() -> Any:
    from tests.test_coe_entry import _fused

    return _fused()


def test_coe_items_cover_all_three_pipelines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The staged case is below the old 0.2 gate; under the provisional router
    # Full runs G-pipe whenever a graph exists (S3.1), so its items show.
    store, path = _run(tmp_path)
    (entry,) = _entries(path)
    prefixes = {
        i["id"].split(":")[0] for s in entry["steps"] for i in s.get("items", [])
    }
    assert prefixes == {"D", "G", "L"}
    assert _step(entry, "R")["ran"] is True
    (run_id,) = {str(r["run_id"]) for r in store.fetch_all()}
    stored = store.fetch_evidence(run_id, "gpipe")
    assert stored is not None
    assert _step(entry, "P:gpipe")["refs"]["evidence"] == row_ref(stored)


def test_routing_record_of_a_routed_run(tmp_path: Path) -> None:
    # Below the old 0.2 gate, but the router decides now (S3.1): with
    # provisional parameters D alone is infeasible, so G-pipe runs and the run
    # escalates to Full.
    _, path = _run(tmp_path)
    (entry,) = _entries(path)
    routing = _step(entry, "R")
    assert routing["mode"] == "routed"
    assert routing["gate_value"] < routing["threshold"]
    assert routing["ran"] is True
    assert routing["g_decision"] == "d_infeasible"
    assert routing["stage1_arm"] == "D+G"
    assert routing["terminal_arm"] == "Full"
    assert routing["escalate"] is True
    assert len(routing["features"]) == len(routing["features"]) > 0
    assert routing["stage1_ms"] <= routing["terminal_ms"]
    assert _step(entry, "P:gpipe")["status"] != "skipped"
    assert "router" in entry["parameter_hashes"]


def test_routing_record_of_a_uniform_run(tmp_path: Path) -> None:
    # noRouter runs G-pipe on every incident with a graph, ungated (R-b).
    _, path = _run(tmp_path, "HELIOS-noRouter")
    (entry,) = _entries(path)
    routing = _step(entry, "R")
    assert routing["mode"] == "uniform"
    assert routing["gate_value"] < routing["threshold"]
    assert routing["ran"] is True
    assert routing["reason"] == "uniform"
    # Uniform runs record the router's inputs, never a decision (shadow data).
    assert len(routing["features"]) == len(routing["features_cheap"]) > 0
    assert "stage1_arm" not in routing
    assert "router" not in entry["parameter_hashes"]


def test_excluded_run_has_no_coe_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from helios import integrity_gate

    def fail(self: Any, rows: Any, *, incident_id: str) -> Any:
        return integrity_gate.GateResult(status="FAIL", gate_check="forced")

    monkeypatch.setattr(integrity_gate.MetricIntegrityGate, "check_consistency", fail)
    _, path = _run(tmp_path)
    assert not path.exists()


def test_no_llm_variant_entry_has_no_l_items(tmp_path: Path) -> None:
    _, path = _run(tmp_path, "HELIOS-noLLM")
    (entry,) = _entries(path)
    lpipe = _step(entry, "P:lpipe")
    assert lpipe["status"] == "skipped" and lpipe["items"] == []
    assert lpipe["h_struct"]["structural_zero"] is True
    assert not any(
        i["id"].startswith("L:") for s in entry["steps"] for i in s.get("items", [])
    )


def test_confirmatory_without_key_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dataclasses

    from helios.narrative import prompt as narrator_prompt
    from helios.narrative.params import load_narrator_params

    # Narrator frozen-looking, so the key refusal is the one under test.
    monkeypatch.setattr(narrator_prompt, "PROVISIONAL", False)
    frozen = dataclasses.replace(load_narrator_params(), provisional=False)
    captures = tmp_path / "captures"
    raw = json.loads(OTEL.read_text())
    raw["evaluation_phase"] = "confirmatory"
    src = tmp_path / "confirmatory_manifest.json"
    src.write_text(json.dumps(raw))
    stage_capture(captures, src)
    manifest = get_variant("HELIOS-Full")
    orch = RunOrchestrator(
        manifest=manifest,
        captures_dir=captures,
        db_path=tmp_path / "r.duckdb",
        registry_path=tmp_path / "r.registry.jsonl",
        reconciliation_path=tmp_path / "r.reconciliation.jsonl",
        exclusion_ledger=MagicMock(spec=AppendOnlyLedger),
        hmac_key=KEY,
        lpipe_client=FakeClient(),  # type: ignore[arg-type]
        narrator_params=frozen,
    )
    orch._reader._pool_lock = lambda _incident: None
    with pytest.raises(MissingSigningKeyError, match="Ed25519"):
        orch.run(captures)
    assert not orch.coe_path.exists()
    assert ResultStore(tmp_path / "r.duckdb").fetch_all() == []


def test_unsigned_exploratory_run_marks_the_anchor(tmp_path: Path) -> None:
    _, path = _run(tmp_path, signer=None)
    assert len(_entries(path)) == 1
    anchor = json.loads(CoELedger(KEY, path).anchor_path.read_text())
    assert anchor.get("anchor_unsigned") is True


def test_dpipe_evidence_row_stored(tmp_path: Path) -> None:
    store, _ = _run(tmp_path)
    (run_id,) = {str(r["run_id"]) for r in store.fetch_all()}
    stored = store.fetch_evidence(run_id, "dpipe")
    assert stored is not None and stored["services"]
    assert set(stored["services"][0]) == {
        "service",
        "error",
        "latency",
        "resource",
        "score",
        "final",
        "levels",
    }


def test_each_orchestrator_run_writes_its_own_file(tmp_path: Path) -> None:
    # Spec §4: one CoE file per orchestrator run, beside the results database.
    _, first = _run(tmp_path)
    _, second = _run(tmp_path)
    assert first != second
    assert first.parent == second.parent == tmp_path / "r.coe"
    assert len(_entries(first)) == len(_entries(second)) == 1


def test_coe_preflight_refuses_before_any_write(tmp_path: Path) -> None:
    # Review I-3: a ledger that cannot be appended to stops the run up front.
    path = tmp_path / "shared.coe.jsonl"
    CoELedger(KEY, path).append(
        {
            "run_id": "x",
            "incident_id": "x",
            "variant_config_hash": "h",
            "snapshot_hash": "s",
            "evaluation_phase": "exploratory",
            "steps": [{"id": "G"}],
        }
    )
    stage_capture(tmp_path / "captures")
    orch = _orch(tmp_path, coe_path=path)
    with pytest.raises(TamperDetectedError):
        orch.run(tmp_path / "captures")
    assert ResultStore(tmp_path / "r.duckdb").fetch_all() == []


def test_entry_is_built_before_anything_is_stored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from helios.orchestrator import runner as runner_module

    def boom(**_kw: Any) -> Any:
        raise RuntimeError("builder failed")

    monkeypatch.setattr(runner_module, "build_coe_entry", boom)
    with pytest.raises(RuntimeError, match="builder failed"):
        _run(tmp_path)
    store = ResultStore(tmp_path / "r.duckdb")
    assert store.fetch_all() == []
    assert store.fetch_all_fusion_rows() == []


def test_gate_is_not_computed_when_gpipe_is_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The routing gate raises on negative D scores; variants that never routed
    # must not start calling it (review, minor 4 re-graded).
    from helios.orchestrator import runner as runner_module

    def boom(_scores: Any) -> float:
        raise ValueError("gate called")

    monkeypatch.setattr(runner_module, "compute_ppr_disagreement", boom)
    _, path = _run(tmp_path, "HELIOS-D")
    (entry,) = _entries(path)
    routing = _step(entry, "R")
    assert routing["ran"] is False
    assert routing["gate_value"] is None
    assert routing["reason"] == "gpipe_off"
