"""Unit tests for HMACChainedLog base class.

VCLFlag-compliant: HMACChainedLog is always-on C1 audit infrastructure,
not an ablatable component.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from helios.vcl.hmac_chain import GENESIS, HMACChainedLog

_KEY = b"test-secret-of-at-least-32-characters-x"


class _ConcreteLog(HMACChainedLog):
    REQUIRED_FIELDS = ("msg",)


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "test.jsonl"


@pytest.fixture
def log(log_path: Path) -> _ConcreteLog:
    return _ConcreteLog(key=_KEY, log_path=log_path)


def test_genesis_on_missing_file(log: _ConcreteLog) -> None:
    assert log.previous_signature() == GENESIS


def test_genesis_on_empty_file(log: _ConcreteLog, log_path: Path) -> None:
    log_path.write_text("", encoding="utf-8")
    assert log.previous_signature() == GENESIS


def test_genesis_on_whitespace_only_file(log: _ConcreteLog, log_path: Path) -> None:
    log_path.write_text("   \n\n   \n", encoding="utf-8")
    assert log.previous_signature() == GENESIS


def test_signature_excludes_signature_field(log: _ConcreteLog) -> None:
    entry_with_sig = {"msg": "hello", "signature": "abc", "prev_signature": GENESIS}
    entry_without_sig = {"msg": "hello", "prev_signature": GENESIS}
    assert log.compute_signature(entry_with_sig) == log.compute_signature(
        entry_without_sig
    )


def test_signature_excludes_deviation_id_field(log: _ConcreteLog) -> None:
    base = {"msg": "hello", "prev_signature": GENESIS}
    with_id = {**base, "deviation_id": "abc123"}
    assert log.compute_signature(base) == log.compute_signature(with_id)


def test_short_key_raises_at_construction(log_path: Path) -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        _ConcreteLog(key=b"tooshort", log_path=log_path)


def test_append_missing_required_field_raises(log: _ConcreteLog) -> None:
    with pytest.raises(ValueError, match="Missing required fields"):
        log.append({})


def test_append_writes_valid_jsonl(log: _ConcreteLog, log_path: Path) -> None:
    log.append({"msg": "hello"})
    log.append({"msg": "world"})
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        json.loads(line)


def test_verify_passes_on_clean_log(log: _ConcreteLog) -> None:
    log.append({"msg": "a"})
    log.append({"msg": "b"})
    ok, msg = log.verify()
    assert ok, msg


def test_verify_fails_on_tampered_entry(log: _ConcreteLog, log_path: Path) -> None:
    log.append({"msg": "a"})
    log.append({"msg": "b"})
    lines = log_path.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    entry["msg"] = "TAMPERED"
    lines[0] = json.dumps(entry, sort_keys=True)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, _ = log.verify()
    assert not ok


def test_verify_empty_log_is_valid(log: _ConcreteLog) -> None:
    ok, msg = log.verify()
    assert ok
    assert "vacuously" in msg
