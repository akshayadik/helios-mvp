"""Annotations ledger (S2.9 design §5.5): HMAC per entry, own Ed25519 anchor key."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from helios.labelling.annotations import AnnotationLedger, latest
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.ed25519 import generate_private_key
from helios.vcl.hmac_chain import TamperDetectedError, verify_public

if TYPE_CHECKING:
    from pathlib import Path

KEY = b"k" * 32


def _label(
    item: str, person: str, verdict: str = "supported", **kw: Any
) -> dict[str, Any]:
    return {
        "set_hash": "s" * 64,
        "item": item,
        "person": person,
        "kind": "label",
        "verdict": verdict,
        "category": kw.get("category", ""),
        "note": kw.get("note", ""),
        "dwell_ms": kw.get("dwell_ms", 1200),
    }


def _signed(tmp_path: Path, n: int = 3) -> tuple[AnnotationLedger, Path]:
    path = tmp_path / "set.annotations.jsonl"
    log = AnnotationLedger(KEY, path, ed25519_private=generate_private_key())
    for i in range(n):
        log.append(_label(f"i{i}", "R1"))
    return log, path


def _public(log: AnnotationLedger, path: Path) -> tuple[bool, str]:
    assert log._ed_public is not None
    return verify_public(
        path, log.anchor_path, log._ed_public, from_entry=None, log_kind="annotations"
    )


def test_append_and_latest_wins(tmp_path: Path) -> None:
    log, _ = _signed(tmp_path, n=0)
    log.append(_label("x", "R1", "supported"))
    log.append(_label("x", "R1", "unsupported", category="numeric_drift"))
    log.append(_label("x", "R2", "supported", dwell_ms=0))
    got = latest(log, "label")
    assert got["x", "R1"]["verdict"] == "unsupported"
    assert got["x", "R1"]["category"] == "numeric_drift"
    assert got["x", "R2"]["dwell_ms"] == 0
    assert latest(log, "adjudication") == {}
    assert log.verify()[0] and _public(log, log._path)[0]


@pytest.mark.parametrize("attack", ["edit", "remove", "truncate"])
def test_tamper_edit_remove_truncate_fail_verify(tmp_path: Path, attack: str) -> None:
    log, path = _signed(tmp_path)
    lines = path.read_text().splitlines()
    if attack == "edit":
        entry = json.loads(lines[1])
        entry["verdict"] = "unsupported"
        lines[1] = json.dumps(entry)
    elif attack == "remove":
        del lines[1]
    else:
        lines = lines[:-1]
    path.write_text("\n".join(lines) + "\n")
    assert not log.verify()[0]
    assert not _public(log, path)[0]


def test_unsigned_anchor_refused_when_key_given(tmp_path: Path) -> None:
    _, path = _signed(tmp_path, n=1)
    with pytest.raises(TamperDetectedError, match="signed"):
        AnnotationLedger(KEY, path).append(_label("y", "R1"))


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "opinion"},
        {"verdict": "maybe"},
        {"verdict": "unsupported", "category": ""},
        {"verdict": "unsupported", "category": "vibes"},
        {"verdict": "supported", "category": "numeric_drift"},
        {"kind": "blind_guess", "verdict": "supported"},
        {"dwell_ms": -1},
    ],
)
def test_bad_kind_or_category_refused(tmp_path: Path, bad: dict[str, Any]) -> None:
    log, path = _signed(tmp_path, n=0)
    with pytest.raises(ValueError):
        log.append({**_label("z", "R1"), **bad})
    assert not path.exists() or path.read_text() == ""


def test_blind_guess_and_adjudication_accepted(tmp_path: Path) -> None:
    log, _ = _signed(tmp_path, n=0)
    log.append({**_label("z", "R1"), "kind": "blind_guess", "verdict": "unsure"})
    log.append(
        {
            **_label("z", "ADJ", "unsupported", category="entity_mismatch"),
            "kind": "adjudication",
        }
    )
    assert latest(log, "blind_guess")["z", "R1"]["verdict"] == "unsure"
    assert latest(log, "adjudication")["z", "ADJ"]["category"] == "entity_mismatch"
