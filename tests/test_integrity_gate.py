"""Tests for helios.integrity_gate — VCLFlag-compliant."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from helios.integrity_gate import AppendOnlyLedger, GateResult, MetricIntegrityGate
from helios.vcl.config import VCLManifest

# ---------------------------------------------------------------------------
# Test double
# ---------------------------------------------------------------------------

_CONSEQUENCE = "affects ablation run; check exclusion_ledger.jsonl"
_INCIDENT = "INC-001"
_SNAP_HASH = "a" * 64
_CFG_HASH_WRONG = "b" * 64


class _MockLedger:
    def __init__(self) -> None:
        self.entries: list[dict[str, str]] = []

    def append(self, fields: dict[str, str]) -> None:
        self.entries.append(fields)


def _make_manifest(**overrides: bool | str) -> VCLManifest:
    return VCLManifest(**overrides)


def _make_gate(
    manifest: VCLManifest | None = None,
    ledger: _MockLedger | None = None,
    run_id: str = "run-001",
    analytic_consequence: str = _CONSEQUENCE,
) -> tuple[MetricIntegrityGate, _MockLedger]:
    if ledger is None:
        ledger = _MockLedger()
    if manifest is None:
        manifest = _make_manifest()
    gate = MetricIntegrityGate.from_manifest(
        manifest,
        ledger=ledger,
        run_id=run_id,
        analytic_consequence=analytic_consequence,
    )
    return gate, ledger


def _valid_row(manifest: VCLManifest | None = None) -> dict[str, Any]:
    if manifest is None:
        manifest = _make_manifest()
    return {
        "variant_config_hash": manifest.compute_variant_config_hash(),
        "snapshot_hash": _SNAP_HASH,
        "run_id": "run-001",
        "pipeline": "dpipe",
    }


# ---------------------------------------------------------------------------
# GateResult
# ---------------------------------------------------------------------------


def test_gate_result_pass_has_no_reason() -> None:
    r = GateResult(status="PASS")
    assert r.reason is None
    assert r.gate_check is None


def test_gate_result_frozen() -> None:
    r = GateResult(status="PASS")
    with pytest.raises(FrozenInstanceError):
        r.status = "FAIL"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


def test_appendonly_ledger_protocol_satisfied() -> None:
    ledger = _MockLedger()
    assert isinstance(ledger, AppendOnlyLedger)


# ---------------------------------------------------------------------------
# from_manifest factory
# ---------------------------------------------------------------------------


def test_from_manifest_factory_derives_correct_hash() -> None:
    manifest = _make_manifest(dpipe=True)
    gate, _ = _make_gate(manifest=manifest)
    expected = manifest.compute_variant_config_hash()
    row = {
        "variant_config_hash": expected,
        "snapshot_hash": _SNAP_HASH,
        "run_id": "run-001",
    }
    result = gate.check(row, incident_id=_INCIDENT)
    assert result.status == "PASS"


# ---------------------------------------------------------------------------
# check() — happy path
# ---------------------------------------------------------------------------


def test_pass_on_valid_row() -> None:
    gate, ledger = _make_gate()
    result = gate.check(_valid_row(), incident_id=_INCIDENT)
    assert result.status == "PASS"
    assert ledger.entries == []


def test_pass_does_not_write_to_ledger() -> None:
    gate, ledger = _make_gate()
    gate.check(_valid_row(), incident_id=_INCIDENT)
    assert len(ledger.entries) == 0


# ---------------------------------------------------------------------------
# check() — failures
# ---------------------------------------------------------------------------


def test_fail_missing_required_field_run_id() -> None:
    gate, _ = _make_gate()
    row = _valid_row()
    del row["run_id"]
    result = gate.check(row, incident_id=_INCIDENT)
    assert result.status == "FAIL"
    assert result.gate_check == "required_field_present"
    assert "run_id" in (result.reason or "")


def test_fail_missing_snapshot_hash() -> None:
    gate, _ = _make_gate()
    row = _valid_row()
    del row["snapshot_hash"]
    result = gate.check(row, incident_id=_INCIDENT)
    assert result.status == "FAIL"
    assert result.gate_check == "required_field_present"


def test_fail_missing_variant_config_hash() -> None:
    gate, _ = _make_gate()
    row = _valid_row()
    del row["variant_config_hash"]
    result = gate.check(row, incident_id=_INCIDENT)
    assert result.status == "FAIL"
    assert result.gate_check == "required_field_present"


def test_fail_config_hash_mismatch() -> None:
    gate, _ = _make_gate()
    row = _valid_row()
    row["variant_config_hash"] = _CFG_HASH_WRONG
    result = gate.check(row, incident_id=_INCIDENT)
    assert result.status == "FAIL"
    assert result.gate_check == "variant_config_hash_match"


def test_fail_writes_all_seven_ledger_fields() -> None:
    gate, ledger = _make_gate()
    row = _valid_row()
    row["variant_config_hash"] = _CFG_HASH_WRONG
    gate.check(row, incident_id=_INCIDENT)
    assert len(ledger.entries) == 1
    entry = ledger.entries[0]
    for field in (
        "variant_config_hash",
        "snapshot_hash",
        "run_id",
        "incident_id",
        "gate_check",
        "reason",
        "analytic_consequence",
    ):
        assert field in entry, f"Missing field '{field}' in ledger entry"


def test_fail_ledger_entry_has_correct_incident_id() -> None:
    gate, ledger = _make_gate()
    row = _valid_row()
    row["variant_config_hash"] = _CFG_HASH_WRONG
    gate.check(row, incident_id="INC-999")
    assert ledger.entries[0]["incident_id"] == "INC-999"


def test_fail_ledger_entry_has_analytic_consequence() -> None:
    gate, ledger = _make_gate(analytic_consequence="custom-consequence")
    row = _valid_row()
    row["variant_config_hash"] = _CFG_HASH_WRONG
    gate.check(row, incident_id=_INCIDENT)
    assert ledger.entries[0]["analytic_consequence"] == "custom-consequence"


# ---------------------------------------------------------------------------
# check_consistency()
# ---------------------------------------------------------------------------


def test_check_consistency_pass_on_identical_rows() -> None:
    manifest = _make_manifest()
    gate, _ = _make_gate(manifest=manifest)
    row = _valid_row(manifest)
    result = gate.check_consistency([row, dict(row)], incident_id=_INCIDENT)
    assert result.status == "PASS"


def test_check_consistency_fails_on_config_hash_mismatch() -> None:
    manifest = _make_manifest()
    gate, _ = _make_gate(manifest=manifest)
    row_a = _valid_row(manifest)
    row_b = dict(row_a)
    row_b["variant_config_hash"] = "c" * 64
    # Per-row check() catches the mismatch before the cross-pipeline check.
    result = gate.check_consistency([row_a, row_b], incident_id=_INCIDENT)
    assert result.status == "FAIL"
    assert result.gate_check == "variant_config_hash_match"


def test_check_consistency_fails_on_snapshot_hash_mismatch() -> None:
    manifest = _make_manifest()
    gate, _ = _make_gate(manifest=manifest)
    row_a = _valid_row(manifest)
    row_b = dict(row_a)
    row_b["snapshot_hash"] = "d" * 64
    result = gate.check_consistency([row_a, row_b], incident_id=_INCIDENT)
    assert result.status == "FAIL"
    assert result.gate_check == "cross_pipeline_snapshot_hash_match"


def test_check_consistency_per_row_failure_propagated() -> None:
    manifest = _make_manifest()
    gate, _ = _make_gate(manifest=manifest)
    row_a = _valid_row(manifest)
    row_b = dict(row_a)
    del row_b["run_id"]
    result = gate.check_consistency([row_a, row_b], incident_id=_INCIDENT)
    assert result.status == "FAIL"
    assert result.gate_check == "required_field_present"


def test_check_consistency_passes_gpipe_sentinel_row() -> None:
    """Sentinel verdict (narrative='gpipe-gated-or-skipped') must pass the gate."""
    manifest = _make_manifest()
    gate, _ = _make_gate(manifest=manifest)
    cfg_hash = manifest.compute_variant_config_hash()
    snap_hash = _SNAP_HASH
    rows: list[dict[str, Any]] = [
        {
            "pipeline": "dpipe",
            "variant_config_hash": cfg_hash,
            "snapshot_hash": snap_hash,
            "run_id": "run-001",
        },
        {
            "pipeline": "gpipe",
            "variant_config_hash": cfg_hash,
            "snapshot_hash": snap_hash,
            "run_id": "run-001",
            "narrative": "gpipe-gated-or-skipped",
            "ranked_candidates": [],
        },
        {
            "pipeline": "lpipe",
            "variant_config_hash": cfg_hash,
            "snapshot_hash": snap_hash,
            "run_id": "run-001",
        },
    ]
    result = gate.check_consistency(rows, incident_id=_INCIDENT)
    assert result.status == "PASS"
