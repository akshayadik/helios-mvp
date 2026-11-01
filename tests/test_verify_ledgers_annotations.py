"""bin/verify_ledgers.py --annotations <dir> (S2.9): HMAC chain and own Ed25519 anchor."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from bin import verify_ledgers as cli
from helios.labelling.annotations import AnnotationLedger
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.ed25519 import generate_private_key, public_key_pem

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

SECRET = "annotations-test-secret-at-least-32-chars"


def _label(i: int) -> dict[str, Any]:
    return {
        "set_hash": "s" * 64,
        "item": f"i{i}",
        "person": "R1",
        "kind": "label",
        "verdict": "supported",
        "category": "",
        "note": "",
        "dwell_ms": 900,
    }


def test_verify_ledgers_annotations_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DEVIATION_HMAC_SECRET", SECRET)
    private = generate_private_key()
    pub = tmp_path / "pub.pem"
    pub.write_bytes(public_key_pem(private))
    d = tmp_path / "sets"
    d.mkdir()
    path = d / "t1.annotations.jsonl"
    log = AnnotationLedger(SECRET.encode(), path, ed25519_private=private)
    for i in range(3):
        log.append(_label(i))
    args = ["--annotations", str(d), "--public-key", str(pub)]
    assert cli.main(args) == 0
    assert cli.main([*args, "--public-only"]) == 0
    monkeypatch.delenv("DEVIATION_HMAC_SECRET")
    assert cli.main([*args, "--public-only"]) == 0  # no secret needed
    lines = path.read_text().splitlines()
    entry = json.loads(lines[0])
    entry["verdict"] = "unsupported"
    lines[0] = json.dumps(entry)
    path.write_text("\n".join(lines) + "\n")
    assert cli.main([*args, "--public-only"]) == 1
    monkeypatch.setenv("DEVIATION_HMAC_SECRET", SECRET)
    assert cli.main(args) == 1
    assert "t1.annotations.jsonl" in capsys.readouterr().out
