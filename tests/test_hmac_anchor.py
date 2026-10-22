"""Tamper tests for the HMACChainedLog head anchor, schema-on-read and post-sign checks.

VCLFlag-compliant: HMACChainedLog is always-on C1 audit infrastructure,
not an ablatable component. Each test names the attack it rules out.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from bin import verify_ledgers
from bin.log_deviation import DeviationLog
from bin.log_deviation import main as deviation_cli
from helios.orchestrator.ledger import ReconciliationLedger
from helios.vcl.hmac_chain import GENESIS, HMACChainedLog, TamperDetectedError

if TYPE_CHECKING:
    from pathlib import Path

_KEY = b"test-secret-of-at-least-32-characters-x"
_OTHER_KEY = b"another-secret-of-at-least-32-characters"
_DEV = {
    "stage": "Stage 1",
    "clause": "§3.6",
    "change": "c",
    "reason": "r",
    "analytic_consequence": "a",
}


class _ConcreteLog(HMACChainedLog):
    REQUIRED_FIELDS = ("msg",)


def _filled(path: Path, n: int = 4) -> _ConcreteLog:
    log = _ConcreteLog(key=_KEY, log_path=path)
    for i in range(n):
        log.append({"msg": f"m{i}"})
    return log


def _drop_last(path: Path, k: int) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:-k]) + "\n", encoding="utf-8")


# ── Anchor lifecycle ───────────────────────────────────────────────────────────


def test_append_writes_signed_anchor(tmp_path: Path) -> None:
    log = _filled(tmp_path / "a.jsonl", 3)
    anchor = json.loads(log.anchor_path.read_text(encoding="utf-8"))
    assert log.anchor_path.name == "a.anchor.json"
    assert anchor["entries"] == 3
    assert anchor["head_signature"] == log.previous_signature()
    assert anchor["log_kind"] == "generic"
    assert log.verify() == (True, "Chain verified.")


def test_fresh_log_without_anchor_is_vacuously_valid(tmp_path: Path) -> None:
    log = _ConcreteLog(key=_KEY, log_path=tmp_path / "a.jsonl")
    ok, msg = log.verify()
    assert ok
    assert "vacuously" in msg


# ── Truncation and rollback ────────────────────────────────────────────────────


def test_truncated_tail_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "a.jsonl"
    log = _filled(path, 4)
    _drop_last(path, 2)
    ok, msg = log.verify()
    assert not ok
    assert "Anchor records 4 entries" in msg


def test_emptied_log_with_anchor_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "a.jsonl"
    log = _filled(path, 2)
    path.write_text("", encoding="utf-8")
    ok, msg = log.verify()
    assert not ok
    assert "log has 0" in msg


def test_nonempty_log_without_anchor_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "a.jsonl"
    log = _filled(path, 3)
    _drop_last(path, 1)
    log.anchor_path.unlink()
    ok, msg = log.verify()
    assert not ok
    assert "No anchor file" in msg


def test_append_onto_truncated_log_is_refused(tmp_path: Path) -> None:
    """Without this, the next append would silently re-anchor a truncated log."""
    path = tmp_path / "a.jsonl"
    log = _filled(path, 3)
    _drop_last(path, 1)
    with pytest.raises(TamperDetectedError, match="Refusing to append"):
        log.append({"msg": "late"})
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


# ── Forged or corrupted anchors ────────────────────────────────────────────────


def test_hand_edited_anchor_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "a.jsonl"
    log = _filled(path, 3)
    _drop_last(path, 1)
    anchor = json.loads(log.anchor_path.read_text(encoding="utf-8"))
    anchor["entries"] = 2
    anchor["head_signature"] = log.previous_signature()
    log.anchor_path.write_text(json.dumps(anchor), encoding="utf-8")
    ok, msg = log.verify()
    assert not ok
    assert "signature does not verify" in msg


def test_anchor_signed_with_wrong_key_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "a.jsonl"
    log = _filled(path, 2)
    forger = _ConcreteLog(key=_OTHER_KEY, log_path=path)
    log.anchor_path.unlink()
    forger._write_anchor(2, log.previous_signature())
    ok, msg = log.verify()
    assert not ok
    assert "signature does not verify" in msg


def test_corrupt_anchor_is_detected(tmp_path: Path) -> None:
    log = _filled(tmp_path / "a.jsonl", 1)
    log.anchor_path.write_text("{not json", encoding="utf-8")
    ok, msg = log.verify()
    assert not ok
    assert "unreadable" in msg


# ── Cross-log substitution (all ledgers share one key) ─────────────────────────


def test_other_kind_of_log_is_rejected(tmp_path: Path) -> None:
    rec = ReconciliationLedger(key=_KEY, log_path=tmp_path / "rec.jsonl")
    rec.record(run_id="r", incident_id="i", variant_config_hash="h", outcome="passed")
    dev = DeviationLog(key=_KEY, log_path=tmp_path / "rec.jsonl")
    ok, msg = dev.verify()
    assert not ok
    assert "missing required fields" in msg


def test_anchor_of_other_kind_is_rejected(tmp_path: Path) -> None:
    generic = _filled(tmp_path / "a.jsonl", 1)
    as_dev = DeviationLog(key=_KEY, log_path=tmp_path / "a.jsonl")
    assert generic.anchor_path == as_dev.anchor_path
    err = as_dev._check_anchor(1, generic.previous_signature())
    assert err is not None
    assert "log kind 'generic'" in err


# ── deviation_id ───────────────────────────────────────────────────────────────


def test_altered_deviation_id_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "deviation_log.jsonl"
    log = DeviationLog(key=_KEY, log_path=path)
    log.append(dict(_DEV))
    entry = json.loads(path.read_text(encoding="utf-8"))
    entry["deviation_id"] = "deadbeefdeadbeef"
    path.write_text(json.dumps(entry, sort_keys=True) + "\n", encoding="utf-8")
    ok, msg = log.verify()
    assert not ok
    assert "deviation_id" in msg


def test_legacy_entry_without_deviation_id_is_valid(tmp_path: Path) -> None:
    """Entries 1-3 of the real log predate deviation_id."""
    path = tmp_path / "deviation_log.jsonl"
    log = DeviationLog(key=_KEY, log_path=path)
    log.append(dict(_DEV))
    entry = json.loads(path.read_text(encoding="utf-8"))
    del entry["deviation_id"]
    path.write_text(json.dumps(entry, sort_keys=True) + "\n", encoding="utf-8")
    assert log.verify() == (True, "Chain verified.")


# ── Bootstrap ──────────────────────────────────────────────────────────────────


def test_init_anchor_bootstraps_legacy_log_once(tmp_path: Path) -> None:
    path = tmp_path / "a.jsonl"
    log = _filled(path, 3)
    log.anchor_path.unlink()
    assert "Anchored 3 entries" in log.init_anchor()
    assert log.verify() == (True, "Chain verified.")
    with pytest.raises(FileExistsError):
        log.init_anchor()


def test_init_anchor_refuses_invalid_log(tmp_path: Path) -> None:
    path = tmp_path / "a.jsonl"
    log = _filled(path, 3)
    log.anchor_path.unlink()
    lines = path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[1])
    tampered["msg"] = "MALICIOUS"
    lines[1] = json.dumps(tampered, sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(TamperDetectedError, match="Refusing to anchor"):
        log.init_anchor()
    assert not log.anchor_path.exists()


def test_init_anchor_on_empty_log_anchors_genesis(tmp_path: Path) -> None:
    log = _ConcreteLog(key=_KEY, log_path=tmp_path / "a.jsonl")
    log.init_anchor()
    anchor = json.loads(log.anchor_path.read_text(encoding="utf-8"))
    assert (anchor["entries"], anchor["head_signature"]) == (0, GENESIS)


# ── CLIs: a missing anchor fails even when the log is gone too ─────────────────


def test_deviation_cli_verify_requires_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEVIATION_HMAC_SECRET", _KEY.decode())
    monkeypatch.setattr("sys.argv", ["log_deviation.py", "verify"])
    assert deviation_cli() == 1
    assert "missing" in capsys.readouterr().out


def test_verify_ledgers_fails_then_bootstraps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEVIATION_HMAC_SECRET", _KEY.decode())
    log = DeviationLog(key=_KEY, log_path=tmp_path / "deviation_log.jsonl")
    log.append(dict(_DEV))
    log.anchor_path.unlink()
    assert verify_ledgers.main([]) == 1
    assert verify_ledgers.main(["--init-anchors"]) == 0
    assert verify_ledgers.main([]) == 0
    out = capsys.readouterr().out
    assert "deviation_log.anchor.json missing" in out
    assert "Anchored 1 entries" in out
