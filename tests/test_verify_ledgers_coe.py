"""bin/verify_ledgers.py --coe <dir> (S2.7): HMAC chain and Ed25519 anchor."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from bin import verify_ledgers as cli
from helios.orchestrator.coe import CoELedger
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.ed25519 import generate_private_key, public_key_pem

if TYPE_CHECKING:
    from pathlib import Path

SECRET = "coe-test-secret-at-least-32-characters"


def _entry(n: int) -> dict[str, Any]:
    return {
        "run_id": f"run-{n}",
        "incident_id": f"inc-{n}",
        "variant_config_hash": "h" * 64,
        "snapshot_hash": "s" * 64,
        "evaluation_phase": "exploratory",
        "steps": [{"id": "G", "outcome": "PASS"}],
    }


@pytest.fixture()
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Any]:
    monkeypatch.setenv("DEVIATION_HMAC_SECRET", SECRET)
    private = generate_private_key()
    pub = tmp_path / "pub.pem"
    pub.write_bytes(public_key_pem(private))
    (tmp_path / "runs").mkdir()
    return pub, private


def _write(path: Path, private: Any, n: int = 2) -> CoELedger:
    log = CoELedger(SECRET.encode(), path, ed25519_private=private)
    for i in range(n):
        log.append(_entry(i))
    return log


def _main(tmp_path: Path, pub: Path) -> int:
    return cli.main(["--coe", str(tmp_path / "runs"), "--public-key", str(pub)])


def test_verify_ledgers_coe_ok_and_tampered(
    tmp_path: Path, setup: tuple[Path, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    pub, private = setup
    path = tmp_path / "runs" / "a.coe.jsonl"
    _write(path, private)
    _write(tmp_path / "runs" / "b.coe.jsonl", private, n=1)
    assert _main(tmp_path, pub) == 0
    out = capsys.readouterr().out
    assert "a.coe.jsonl" in out and "b.coe.jsonl" in out
    path.write_text(path.read_text().replace("inc-1", "inc-9"))
    assert _main(tmp_path, pub) == 1


def test_unsigned_coe_reported_unsigned(
    tmp_path: Path, setup: tuple[Path, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    pub, _ = setup
    _write(tmp_path / "runs" / "a.coe.jsonl", None)
    assert _main(tmp_path, pub) == 1
    assert "unsigned" in capsys.readouterr().out


def test_wrong_public_key_fails(tmp_path: Path, setup: tuple[Path, Any]) -> None:
    pub, _ = setup
    _write(tmp_path / "runs" / "a.coe.jsonl", generate_private_key())
    assert _main(tmp_path, pub) == 1


def test_empty_directory_fails(tmp_path: Path, setup: tuple[Path, Any]) -> None:
    pub, _ = setup
    assert _main(tmp_path, pub) == 1
