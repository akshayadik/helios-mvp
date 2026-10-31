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
from helios.vcl.hmac_chain import verify_public
from tests.pipelines.l_pipe.test_pipeline import OTEL, FakeClient
from tests.test_runner_lpipe import KEY, stage_capture

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.filterwarnings("ignore::scipy.stats.ConstantInputWarning")

SIGNER = generate_private_key()


def _run(
    tmp_path: Path, variant: str = "HELIOS-Full", *, signer: Any = SIGNER
) -> tuple[ResultStore, Path]:
    captures = tmp_path / "captures"
    if not captures.exists():
        stage_capture(captures)
    manifest = get_variant(variant)
    set_current_manifest(manifest)
    db = tmp_path / "r.duckdb"
    RunOrchestrator(
        manifest=manifest,
        captures_dir=captures,
        db_path=db,
        registry_path=tmp_path / "r.registry.jsonl",
        reconciliation_path=tmp_path / "r.reconciliation.jsonl",
        exclusion_ledger=MagicMock(spec=AppendOnlyLedger),
        hmac_key=KEY,
        lpipe_client=FakeClient(),  # type: ignore[arg-type]
        coe_signer=signer,
    ).run(captures)
    return ResultStore(db), tmp_path / "r.coe.jsonl"


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
    assert _step(entry, "G")["outcome"] == "PASS"
    # fusion_record mirrors the stored row exactly (the ref is recomputable)
    assert set(fusion) == set(fusion_record("r", "i", "h", _fused_like()))


def _fused_like() -> Any:
    from tests.test_coe_entry import _fused

    return _fused()


def test_coe_items_cover_all_three_pipelines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The staged case is below the routing gate; force G-pipe so its items show.
    from helios.orchestrator import runner as runner_module
    from helios.pipelines.g_pipe import pipeline as gpipe_module

    monkeypatch.setattr(runner_module, "should_run_gpipe", lambda *_a: True)
    monkeypatch.setattr(gpipe_module, "DISAGREEMENT_THRESHOLD", 0)
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


def test_routing_record_below_the_gate(tmp_path: Path) -> None:
    _, path = _run(tmp_path)
    (entry,) = _entries(path)
    routing = _step(entry, "R")
    assert routing["ran"] is False
    assert routing["gate_value"] < routing["threshold"]
    assert _step(entry, "P:gpipe")["status"] == "skipped"
    assert _step(entry, "P:gpipe")["items"] == []


def test_excluded_run_has_no_coe_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from helios import integrity_gate

    def fail(self: Any, rows: Any, *, incident_id: str) -> Any:
        return integrity_gate.GateResult(status="FAIL", gate_check="forced")

    monkeypatch.setattr(integrity_gate.MetricIntegrityGate, "check_consistency", fail)
    _, path = _run(tmp_path)
    assert not path.exists() or _entries(path) == []


def test_no_llm_variant_entry_has_no_l_items(tmp_path: Path) -> None:
    _, path = _run(tmp_path, "HELIOS-noLLM")
    (entry,) = _entries(path)
    lpipe = _step(entry, "P:lpipe")
    assert lpipe["status"] == "skipped" and lpipe["items"] == []
    assert lpipe["h_struct"]["structural_zero"] is True
    assert not any(
        i["id"].startswith("L:") for s in entry["steps"] for i in s.get("items", [])
    )


def test_confirmatory_without_key_is_refused(tmp_path: Path) -> None:
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
    )
    orch._reader._pool_lock = lambda _incident: None
    with pytest.raises(MissingSigningKeyError, match="Ed25519"):
        orch.run(captures)
    assert not (tmp_path / "r.coe.jsonl").exists()
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
    assert set(stored["services"][0]) == {"service", "shift", "score", "final"}
