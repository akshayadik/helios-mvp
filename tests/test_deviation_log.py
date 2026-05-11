"""HMAC chain integrity tests for bin/log_deviation.py.

These tests are the canary for C1 §6.5: they prove the deviation_log.jsonl
chain is genuinely tamper-evident, not just decoratively signed.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest


def _load_log_deviation_module():
    """Import bin/log_deviation.py without putting bin/ on sys.path globally."""
    here = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "log_deviation", here / "bin" / "log_deviation.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["log_deviation"] = mod
    spec.loader.exec_module(mod)
    return mod


log_deviation = _load_log_deviation_module()


@pytest.fixture
def secret_env(monkeypatch):
    monkeypatch.setenv(log_deviation.ENV_KEY, "test-secret-of-at-least-32-characters-x")
    return None


@pytest.fixture
def log_path(tmp_path):
    return tmp_path / "deviation_log.jsonl"


def make_fields(change: str = "test change") -> dict[str, Any]:
    return {
        "stage": "Stage 0",
        "clause": "§test",
        "change": change,
        "reason": "test reason",
        "analytic_consequence": "test consequence",
    }


def test_first_entry_has_genesis_prev_signature(secret_env, log_path):
    entry = log_deviation.append_entry(log_path, make_fields())
    assert entry["prev_signature"] == log_deviation.GENESIS
    assert len(entry["signature"]) == 64  # SHA-256 hex


def test_signature_is_64_hex_chars(secret_env, log_path):
    entry = log_deviation.append_entry(log_path, make_fields())
    assert len(entry["signature"]) == 64
    int(entry["signature"], 16)  # must parse as hex


def test_chain_links_correctly_across_three_entries(secret_env, log_path):
    e1 = log_deviation.append_entry(log_path, make_fields("first"))
    e2 = log_deviation.append_entry(log_path, make_fields("second"))
    e3 = log_deviation.append_entry(log_path, make_fields("third"))
    assert e2["prev_signature"] == e1["signature"]
    assert e3["prev_signature"] == e2["signature"]


def test_signature_recomputes_to_same_value(secret_env, log_path):
    entry = log_deviation.append_entry(log_path, make_fields())
    key = log_deviation.load_key()
    assert log_deviation.compute_signature(key, entry) == entry["signature"]


def test_tampered_change_field_breaks_signature(secret_env, log_path):
    entry = log_deviation.append_entry(log_path, make_fields())
    key = log_deviation.load_key()
    tampered = dict(entry)
    tampered["change"] = "MALICIOUS"
    assert log_deviation.compute_signature(key, tampered) != entry["signature"]


def test_tampered_prev_signature_breaks_chain(secret_env, log_path):
    e1 = log_deviation.append_entry(log_path, make_fields("first"))
    e2 = log_deviation.append_entry(log_path, make_fields("second"))
    assert e2["prev_signature"] == e1["signature"]
    # Now tamper with e2's prev_signature; recomputed sig must differ
    key = log_deviation.load_key()
    tampered = dict(e2)
    tampered["prev_signature"] = "0" * 64
    assert log_deviation.compute_signature(key, tampered) != e2["signature"]


def test_verify_chain_passes_on_clean_log(secret_env, log_path, monkeypatch):
    log_deviation.append_entry(log_path, make_fields("first"))
    log_deviation.append_entry(log_path, make_fields("second"))
    monkeypatch.setattr(log_deviation, "LOG_FILE", log_path)
    ok, msg = log_deviation.verify_chain(log_path)
    assert ok, msg


def test_verify_chain_fails_on_tampered_log(secret_env, log_path):
    log_deviation.append_entry(log_path, make_fields("first"))
    log_deviation.append_entry(log_path, make_fields("second"))
    # Tamper with the on-disk file
    lines = log_path.read_text().splitlines()
    second = json.loads(lines[1])
    second["change"] = "MALICIOUS"
    lines[1] = json.dumps(second, sort_keys=True)
    log_path.write_text("\n".join(lines) + "\n")
    ok, _ = log_deviation.verify_chain(log_path)
    assert not ok


def test_log_file_is_one_json_per_line(secret_env, log_path):
    log_deviation.append_entry(log_path, make_fields("a"))
    log_deviation.append_entry(log_path, make_fields("b"))
    lines = log_path.read_text().splitlines()
    assert len(lines) == 2
    for line in lines:
        json.loads(line)  # must parse


def test_missing_secret_exits(monkeypatch):
    monkeypatch.delenv(log_deviation.ENV_KEY, raising=False)
    with pytest.raises(SystemExit):
        log_deviation.load_key()


def test_short_secret_exits(monkeypatch):
    monkeypatch.setenv(log_deviation.ENV_KEY, "too-short")
    with pytest.raises(SystemExit):
        log_deviation.load_key()


def test_canonical_signature_is_deterministic(secret_env):
    key = log_deviation.load_key()
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
    sig = log_deviation.compute_signature(key, entry)
    assert sig == log_deviation.compute_signature(key, entry)
