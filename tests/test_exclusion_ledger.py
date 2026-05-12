"""Tests for bin/log_exclusion.py — ExclusionLedger (§3.6.8).

VCLFlag-compliant: ExclusionLedger is always-on C1 audit infrastructure.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_HERE = Path(__file__).resolve().parent.parent


def _load_log_exclusion_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "log_exclusion", _HERE / "bin" / "log_exclusion.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["log_exclusion"] = mod
    spec.loader.exec_module(mod)
    return mod


log_exclusion = _load_log_exclusion_module()

_KEY = b"test-secret-of-at-least-32-characters-x"
_FIELDS: dict[str, str] = {
    "variant_config_hash": "a" * 64,
    "snapshot_hash": "b" * 64,
    "run_id": "run-001",
    "incident_id": "incident-042",
    "gate_check": "snapshot_hash_match",
    "reason": "hash mismatch between pipeline outputs",
    "analytic_consequence": "run-001 excluded from variant analysis",
}


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "exclusion_ledger.jsonl"


@pytest.fixture
def ledger(log_path: Path) -> Any:
    return log_exclusion.ExclusionLedger(key=_KEY, log_path=log_path)


# ── Tracking ref: tests/test_exclusion_ledger.py::test_append ─────────────────


def test_append(ledger: Any, log_path: Path) -> None:
    entry = ledger.append(_FIELDS.copy())
    assert entry["prev_signature"] == log_exclusion.GENESIS
    assert len(entry["signature"]) == 64
    int(entry["signature"], 16)
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    json.loads(lines[0])


# ── Schema ─────────────────────────────────────────────────────────────────────


def test_schema(ledger: Any) -> None:
    entry = ledger.append(_FIELDS.copy())
    required = {
        "timestamp_utc",
        "commit_sha",
        "prev_signature",
        "variant_config_hash",
        "snapshot_hash",
        "run_id",
        "incident_id",
        "gate_check",
        "reason",
        "analytic_consequence",
        "signature",
    }
    assert required <= set(entry.keys())
    assert entry["timestamp_utc"].endswith("Z")
    assert len(entry["signature"]) == 64
    assert entry["incident_id"] == "incident-042"


# ── Chain integrity ────────────────────────────────────────────────────────────


def test_chain_links_across_two_entries(ledger: Any) -> None:
    e1 = ledger.append({**_FIELDS, "run_id": "run-001"})
    e2 = ledger.append({**_FIELDS, "run_id": "run-002"})
    assert e2["prev_signature"] == e1["signature"]


# ── Verify ─────────────────────────────────────────────────────────────────────


def test_verify_passes_on_clean_log(ledger: Any) -> None:
    ledger.append({**_FIELDS, "run_id": "run-001"})
    ledger.append({**_FIELDS, "run_id": "run-002"})
    ok, msg = ledger.verify()
    assert ok, msg


def test_verify_fails_on_tampered_log(ledger: Any, log_path: Path) -> None:
    ledger.append({**_FIELDS, "run_id": "run-001"})
    ledger.append({**_FIELDS, "run_id": "run-002"})
    lines = log_path.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    entry["reason"] = "TAMPERED"
    lines[0] = json.dumps(entry, sort_keys=True)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, _ = ledger.verify()
    assert not ok


# ── Validation ─────────────────────────────────────────────────────────────────


def test_missing_required_field_raises(ledger: Any) -> None:
    with pytest.raises(ValueError, match="Missing required fields"):
        ledger.append({"variant_config_hash": "a" * 64})


def test_short_key_raises(log_path: Path) -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        log_exclusion.ExclusionLedger(key=b"short", log_path=log_path)


# ── load_key() ─────────────────────────────────────────────────────────────────


def test_missing_secret_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(log_exclusion.ENV_KEY, raising=False)
    with pytest.raises(SystemExit):
        log_exclusion.load_key()
