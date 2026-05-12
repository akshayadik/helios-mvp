"""HMAC chain integrity tests for bin/log_deviation.py (§B.12).

VCLFlag-compliant: DeviationLog is always-on C1 audit infrastructure.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from helios.vcl.hmac_chain import TamperDetectedError

_HERE = Path(__file__).resolve().parent.parent


def _load_log_deviation_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "log_deviation", _HERE / "bin" / "log_deviation.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["log_deviation"] = mod
    spec.loader.exec_module(mod)
    return mod


log_deviation = _load_log_deviation_module()

_KEY = b"test-secret-of-at-least-32-characters-x"
_FIELDS: dict[str, str] = {
    "stage": "Stage 0",
    "clause": "§test",
    "change": "test change",
    "reason": "test reason",
    "analytic_consequence": "test consequence",
}


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "deviation_log.jsonl"


@pytest.fixture
def log(log_path: Path) -> Any:
    return log_deviation.DeviationLog(key=_KEY, log_path=log_path)


# ── Schema (tracking ref: tests/test_deviation_log.py::test_schema) ───────────


def test_schema(log: Any) -> None:
    entry = log.append(_FIELDS.copy())
    required = {
        "timestamp_utc",
        "commit_sha",
        "prev_signature",
        "stage",
        "clause",
        "change",
        "reason",
        "analytic_consequence",
        "signature",
        "deviation_id",
    }
    assert required <= set(entry.keys())
    assert entry["timestamp_utc"].endswith("Z")
    assert len(entry["signature"]) == 64
    int(entry["signature"], 16)  # must parse as hex
    assert entry["prev_signature"] == log_deviation.GENESIS
    assert entry["deviation_id"] == entry["signature"][:16]


# ── Required field validation ──────────────────────────────────────────────────


def test_missing_required_field_raises(log: Any) -> None:
    with pytest.raises(ValueError, match="Missing required fields"):
        log.append({"stage": "Stage 0"})


# ── Chain integrity ────────────────────────────────────────────────────────────


def test_first_entry_has_genesis_prev_signature(log: Any) -> None:
    entry = log.append(_FIELDS.copy())
    assert entry["prev_signature"] == log_deviation.GENESIS
    assert len(entry["signature"]) == 64


def test_signature_is_64_hex_chars(log: Any) -> None:
    entry = log.append(_FIELDS.copy())
    assert len(entry["signature"]) == 64
    int(entry["signature"], 16)


def test_chain_links_correctly_across_three_entries(log: Any) -> None:
    e1 = log.append({**_FIELDS, "change": "first"})
    e2 = log.append({**_FIELDS, "change": "second"})
    e3 = log.append({**_FIELDS, "change": "third"})
    assert e2["prev_signature"] == e1["signature"]
    assert e3["prev_signature"] == e2["signature"]


def test_signature_recomputes_to_same_value(log: Any) -> None:
    entry = log.append(_FIELDS.copy())
    assert log.compute_signature(entry) == entry["signature"]


def test_tampered_change_field_breaks_signature(log: Any) -> None:
    entry = log.append(_FIELDS.copy())
    tampered = dict(entry)
    tampered["change"] = "MALICIOUS"
    assert log.compute_signature(tampered) != entry["signature"]


def test_tampered_prev_signature_breaks_chain(log: Any) -> None:
    e1 = log.append({**_FIELDS, "change": "first"})
    e2 = log.append({**_FIELDS, "change": "second"})
    assert e2["prev_signature"] == e1["signature"]
    tampered = dict(e2)
    tampered["prev_signature"] = "0" * 64
    assert log.compute_signature(tampered) != e2["signature"]


# ── Verify ─────────────────────────────────────────────────────────────────────


def test_verify_chain_passes_on_clean_log(log: Any, log_path: Path) -> None:
    log.append({**_FIELDS, "change": "first"})
    log.append({**_FIELDS, "change": "second"})
    ok, msg = log.verify()
    assert ok, msg


def test_verify_chain_fails_on_tampered_log(log: Any, log_path: Path) -> None:
    log.append({**_FIELDS, "change": "first"})
    log.append({**_FIELDS, "change": "second"})
    lines = log_path.read_text(encoding="utf-8").splitlines()
    second = json.loads(lines[1])
    second["change"] = "MALICIOUS"
    lines[1] = json.dumps(second, sort_keys=True)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, _ = log.verify()
    assert not ok


# ── Format ─────────────────────────────────────────────────────────────────────


def test_log_file_is_one_json_per_line(log: Any, log_path: Path) -> None:
    log.append({**_FIELDS, "change": "a"})
    log.append({**_FIELDS, "change": "b"})
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        json.loads(line)


# ── load_key() ─────────────────────────────────────────────────────────────────


def test_missing_secret_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(log_deviation.ENV_KEY, raising=False)
    with pytest.raises(SystemExit):
        log_deviation.load_key()


def test_short_secret_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(log_deviation.ENV_KEY, "too-short")
    with pytest.raises(SystemExit):
        log_deviation.load_key()


# ── Determinism ────────────────────────────────────────────────────────────────


def test_canonical_signature_is_deterministic(log: Any) -> None:
    entry = {
        "timestamp_utc": "2026-01-01T00:00:00Z",
        "commit_sha": "abc",
        "prev_signature": log_deviation.GENESIS,
        "stage": "S",
        "clause": "C",
        "change": "X",
        "reason": "R",
        "analytic_consequence": "A",
    }
    sig = log.compute_signature(entry)
    assert sig == log.compute_signature(entry)


# ── Tamper detection ──────────────────────────────────────────────────────────


def test_tamper(log: Any, log_path: Path) -> None:
    """Middle-entry tamper detected; verify_hmac_chain() raises TamperDetectedError."""
    log.append({**_FIELDS, "change": "first"})
    log.append({**_FIELDS, "change": "second"})
    log.append({**_FIELDS, "change": "third"})

    # Tamper the middle entry (line index 1 = line number 2)
    lines = log_path.read_text(encoding="utf-8").splitlines()
    middle = json.loads(lines[1])
    middle["change"] = "MALICIOUS"
    lines[1] = json.dumps(middle, sort_keys=True)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # verify_hmac_chain() raises on tamper
    with pytest.raises(TamperDetectedError, match="Line 2"):
        log.verify_hmac_chain()

    # verify() backward compat unchanged
    ok, _ = log.verify()
    assert not ok

    # Post-tamper append still works (previous_signature reads last valid line)
    e4 = log.append({**_FIELDS, "change": "fourth"})
    assert e4 is not None

    # File has 4 lines, all valid JSONL
    final_lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(final_lines) == 4
    for line in final_lines:
        json.loads(line)
