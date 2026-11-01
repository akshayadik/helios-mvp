"""bin/labelling_set.py (S2.9 §5.3): verified ledgers only, pool locked, no ground truth."""

from __future__ import annotations

import builtins
import json
from typing import TYPE_CHECKING, Any

from bin import labelling_set as tool
from helios.orchestrator.coe import CoELedger
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.ed25519 import generate_private_key, public_key_pem
from tests.labelling.test_sets import entries

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

SECRET = "k" * 40  # test-only HMAC secret


def _ledgers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str = "exploratory"
) -> tuple[Path, Path, Path]:
    monkeypatch.setenv("DEVIATION_HMAC_SECRET", SECRET)
    private = generate_private_key()
    pub = tmp_path / "pub.pem"
    pub.write_bytes(public_key_pem(private))
    d = tmp_path / "runs"
    d.mkdir()
    log = CoELedger(SECRET.encode(), d / "a.coe.jsonl", ed25519_private=private)
    for e in entries(4):
        e["evaluation_phase"] = phase
        log.append(e)
    rubric = tmp_path / "rubric.md"
    rubric.write_text("# rubric\n", "utf-8")
    return d, pub, rubric


def _args(d: Path, pub: Path, rubric: Path, out: Path) -> list[str]:
    return [
        "--coe",
        str(d),
        "--out",
        str(out),
        "--share",
        "training",
        "--rubric",
        str(rubric),
        "--public-key",
        str(pub),
    ]


def test_cli_builds_a_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d, pub, rubric = _ledgers(tmp_path, monkeypatch)
    assert tool.main(_args(d, pub, rubric, tmp_path / "set")) == 0
    manifest = json.loads((tmp_path / "set" / "manifest.json").read_text("utf-8"))
    assert manifest["rubric_sha"] == tool.rubric_sha(rubric)
    assert manifest["ledgers"][0]["file"] == "a.coe.jsonl"


def test_cli_refuses_unverified_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d, pub, rubric = _ledgers(tmp_path, monkeypatch)
    path = d / "a.coe.jsonl"
    lines = path.read_text().splitlines()
    first = json.loads(lines[0])
    first["run_id"] = "edited"
    path.write_text("\n".join([json.dumps(first), *lines[1:]]) + "\n")
    assert tool.main(_args(d, pub, rubric, tmp_path / "set")) == 2
    assert not (tmp_path / "set").exists()


def test_cli_refuses_confirmatory_entries_before_build_freeze(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d, pub, rubric = _ledgers(tmp_path, monkeypatch, phase="confirmatory")
    monkeypatch.setattr(tool, "build_frozen", lambda: False)
    assert tool.main(_args(d, pub, rubric, tmp_path / "set")) == 2
    assert not (tmp_path / "set").exists()


def test_cli_never_opens_ground_truth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d, pub, rubric = _ledgers(tmp_path, monkeypatch)
    opened: list[str] = []
    real_open = builtins.open

    def _open(file: Any, *args: Any, **kwargs: Any) -> Any:
        if "ground_truth" in str(file):
            opened.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _open)
    assert tool.main(_args(d, pub, rubric, tmp_path / "set")) == 0
    assert opened == []
