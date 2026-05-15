"""Tests for ReconciliationLedger — per-incident outcome HMAC-chained log."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from helios.orchestrator.ledger import ReconciliationLedger

if TYPE_CHECKING:
    from pathlib import Path

_KEY = b"test-secret-at-least-32-chars-long!!"
_VCH = "a" * 64


class TestReconciliationLedgerRecord:
    def test_record_passed(self, tmp_path: Path) -> None:
        ledger = ReconciliationLedger(key=_KEY, log_path=tmp_path / "rec.jsonl")
        entry = ledger.record(
            run_id="run-1",
            incident_id="inc-001",
            variant_config_hash=_VCH,
            outcome="passed",
        )
        assert entry["outcome"] == "passed"
        assert entry["incident_id"] == "inc-001"
        assert entry["gate_check"] == ""

    def test_record_excluded_with_gate_check(self, tmp_path: Path) -> None:
        ledger = ReconciliationLedger(key=_KEY, log_path=tmp_path / "rec.jsonl")
        entry = ledger.record(
            run_id="run-1",
            incident_id="inc-001",
            variant_config_hash=_VCH,
            outcome="excluded",
            gate_check="variant_config_hash_match",
        )
        assert entry["outcome"] == "excluded"
        assert entry["gate_check"] == "variant_config_hash_match"

    def test_record_invalid_outcome_raises(self, tmp_path: Path) -> None:
        ledger = ReconciliationLedger(key=_KEY, log_path=tmp_path / "rec.jsonl")
        with pytest.raises(ValueError, match="outcome must be one of"):
            ledger.record(
                run_id="run-1",
                incident_id="inc-001",
                variant_config_hash=_VCH,
                outcome="unknown",
            )

    def test_chain_verified_after_multiple_records(self, tmp_path: Path) -> None:
        path = tmp_path / "rec.jsonl"
        ledger = ReconciliationLedger(key=_KEY, log_path=path)
        for i in range(3):
            ledger.record(
                run_id=f"run-{i}",
                incident_id=f"inc-{i:03d}",
                variant_config_hash=_VCH,
                outcome="passed",
            )
        ok, msg = ledger.verify()
        assert ok, msg

    def test_all_outcomes_accepted(self, tmp_path: Path) -> None:
        ledger = ReconciliationLedger(key=_KEY, log_path=tmp_path / "rec.jsonl")
        for outcome in ("attempted", "passed", "excluded", "skipped"):
            ledger.record(
                run_id="run-1",
                incident_id="inc-001",
                variant_config_hash=_VCH,
                outcome=outcome,
            )
