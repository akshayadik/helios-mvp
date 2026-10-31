"""CoE ledger: HMAC on every entry, Ed25519 on the anchor (S2.7 design C-a)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from helios.orchestrator.coe import CoELedger
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.ed25519 import generate_private_key, load_public_key
from helios.vcl.hmac_chain import verify_public

KEY = b"k" * 32
REPO = Path(__file__).resolve().parents[1]


def _entry(n: int) -> dict[str, Any]:
    return {
        "run_id": f"run-{n}",
        "incident_id": f"inc-{n}",
        "variant_config_hash": "h" * 64,
        "snapshot_hash": "s" * 64,
        "evaluation_phase": "exploratory",
        "steps": [{"id": "T", "source": "threshold"}],
    }


def _public(log: CoELedger, path: Path) -> tuple[bool, str]:
    assert log._ed_public is not None
    return verify_public(
        path, log.anchor_path, log._ed_public, from_entry=None, log_kind="coe"
    )


def _signed(tmp_path: Path, n: int = 3) -> tuple[CoELedger, Path]:
    path = tmp_path / "run.coe.jsonl"
    log = CoELedger(KEY, path, ed25519_private=generate_private_key())
    for i in range(n):
        log.append(_entry(i))
    return log, path


def _lines(path: Path) -> list[str]:
    return [x for x in path.read_text().splitlines() if x.strip()]


def test_coe_verifies_hmac_and_public(tmp_path: Path) -> None:
    log, path = _signed(tmp_path)
    assert log.verify()[0]
    ok, msg = _public(log, path)
    assert ok, msg
    assert all("ed25519_signature" not in json.loads(x) for x in _lines(path))


def test_tamper_edit_remove_reorder_truncate_fail(tmp_path: Path) -> None:
    for name, mutate in {
        "edit": lambda ls: [ls[0], ls[1].replace("inc-1", "inc-9"), ls[2]],
        "remove": lambda ls: [ls[0], ls[2]],
        "reorder": lambda ls: [ls[1], ls[0], ls[2]],
        "truncate": lambda ls: ls[:2],
    }.items():
        log, path = _signed(tmp_path / name)
        path.write_text("".join(x + "\n" for x in mutate(_lines(path))))
        assert not log.verify()[0], name
        assert not _public(log, path)[0], name


def test_unsigned_anchor_is_reported_unsigned(tmp_path: Path) -> None:
    path = tmp_path / "run.coe.jsonl"
    log = CoELedger(KEY, path)
    log.append(_entry(0))
    assert log.verify()[0]
    ok, msg = verify_public(
        path,
        log.anchor_path,
        generate_private_key().public_key(),
        from_entry=None,
        log_kind="coe",
    )
    assert not ok and "unsigned" in msg


def test_unsigned_then_signed_append_verifies(tmp_path: Path) -> None:
    path = tmp_path / "run.coe.jsonl"
    CoELedger(KEY, path).append(_entry(0))
    log = CoELedger(KEY, path, ed25519_private=generate_private_key())
    log.append(_entry(1))
    ok, msg = _public(log, path)
    assert ok, msg


def test_two_instances_continue_the_chain(tmp_path: Path) -> None:
    private = generate_private_key()
    path = tmp_path / "run.coe.jsonl"
    CoELedger(KEY, path, ed25519_private=private).append(_entry(0))
    log = CoELedger(KEY, path, ed25519_private=private)
    log.append(_entry(1))
    assert len(_lines(path)) == 2
    assert log.verify()[0] and _public(log, path)[0]


def test_deviation_log_still_verifies_public() -> None:
    public = load_public_key(REPO / "keys/deviation_log_ed25519.pub.pem")
    ok, msg = verify_public(
        REPO / "deviation_log.jsonl",
        REPO / "deviation_log.anchor.json",
        public,
        from_entry=35,
        log_kind="deviation",
    )
    assert ok, msg
