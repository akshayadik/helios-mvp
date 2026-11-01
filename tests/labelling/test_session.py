"""Labelling session logic (S2.9 design §5.4, R-b, R-c, R-i, R-j, R-k)."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

import pytest

from helios.labelling.annotations import AnnotationLedger, latest
from helios.labelling.session import LabellingSession, SessionError
from helios.labelling.sets import ARMS, build_set, write_set
from helios.narrative.params import load_narrator_params
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.ed25519 import generate_private_key
from tests.labelling.test_sets import entries

if TYPE_CHECKING:
    from pathlib import Path

P = load_narrator_params()
KEY = b"k" * 32
SIGNER = generate_private_key()
PEOPLE_KEYS = {"R1": "key-r1", "R2": "key-r2", "ADJ": "key-adj"}


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        self.t += 2.5
        return self.t


def people() -> dict[str, dict[str, str]]:
    return {
        p: {
            "key_sha256": hashlib.sha256(k.encode()).hexdigest(),
            "role": "adjudicator" if p == "ADJ" else "rater",
        }
        for p, k in PEOPLE_KEYS.items()
    }


def make(tmp_path: Path, n: int = 4, mode: str = "label") -> LabellingSession:
    d = tmp_path / "set"
    if not d.exists():
        write_set(
            build_set(entries(n), planted_share=1 / 4, rubric_sha="r" * 64, params=P), d
        )
    ledger = AnnotationLedger(KEY, d / "set.annotations.jsonl", ed25519_private=SIGNER)
    return LabellingSession(d, ledger, people(), mode=mode, clock=Clock())


def _key(tmp_path: Path) -> dict[str, dict[str, Any]]:
    return dict(json.loads((tmp_path / "set" / "key.json").read_text("utf-8")))


def _label_all(s: LabellingSession, person: str, verdict: Any = "supported") -> None:
    while (item := s.next_item(person)) is not None:
        v = verdict(item["item"]) if callable(verdict) else verdict
        s.submit(
            person, item["item"], v, "" if v == "supported" else "numeric_drift", ""
        )
        if s.blinding_prompt(person) is not None:
            s.submit_guess(person, s.blinding_prompt(person)["item"], "unsure")  # type: ignore[index]


def test_authenticate() -> None:
    assert LabellingSession.check_key(people(), "key-r1") == "R1"
    assert LabellingSession.check_key(people(), "nope") is None


def test_rater_never_receives_secret_fields(tmp_path: Path) -> None:
    s = make(tmp_path)
    key = _key(tmp_path)
    secrets = set(ARMS) | {str(v["run_id"]) for v in key.values()}
    secrets |= {str(v["incident_id"]) for v in key.values()} | {"planted", "category"}
    item = s.next_item("R1")
    assert item is not None
    assert set(item) <= {"item", "header", "kind", "sentence", "cards", "progress"}
    text = json.dumps(item)
    assert not any(word in text for word in secrets)


def test_label_for_unserved_item_is_refused(tmp_path: Path) -> None:
    s = make(tmp_path)
    first = s.next_item("R1")
    assert first is not None
    other = next(i for i in _key(tmp_path) if i != first["item"])
    with pytest.raises(SessionError, match="not served"):
        s.submit("R1", other, "supported", "", "")
    with pytest.raises(SessionError, match="not served"):
        s.submit("R2", first["item"], "supported", "", "")


def test_two_tabs_get_the_same_next_item(tmp_path: Path) -> None:
    s = make(tmp_path)
    a, b = s.next_item("R1"), s.next_item("R1")
    assert a is not None and b is not None and a["item"] == b["item"]
    s.submit("R1", a["item"], "supported", "", "")
    with pytest.raises(SessionError):
        s.submit("R1", a["item"], "supported", "", "")  # the second tab's stale submit


def test_revise_until_both_labelled_then_locked(tmp_path: Path) -> None:
    s = make(tmp_path)
    item = s.next_item("R1")
    assert item is not None
    s.submit("R1", item["item"], "supported", "", "")
    s.revisit("R1", item["item"])
    s.submit("R1", item["item"], "unsupported", "entity_mismatch", "edge reversed")
    assert (
        latest(s.ledger, "label")[item["item"], "R1"]["category"] == "entity_mismatch"
    )
    while (nxt := s.next_item("R2")) is not None and nxt["item"] != item["item"]:
        s.submit("R2", nxt["item"], "supported", "", "")
        if (b := s.blinding_prompt("R2")) is not None:
            s.submit_guess("R2", b["item"], "unsure")
    s.submit("R2", item["item"], "supported", "", "")
    with pytest.raises(SessionError, match="locked"):
        s.revisit("R1", item["item"])


def test_adjudicator_sees_only_disagreements_unattributed(tmp_path: Path) -> None:
    s = make(tmp_path)
    key = _key(tmp_path)
    real = sorted(i for i, k in key.items() if not k["planted"])
    split, cat_only = real[0], real[1]
    _label_all(
        s, "R1", lambda i: "unsupported" if i in (split, cat_only) else "supported"
    )

    def r2(i: str) -> str:
        return "unsupported" if i == cat_only or key[i]["planted"] else "supported"

    while (item := s.next_item("R2")) is not None:
        v = r2(item["item"])
        cat = (
            "entity_mismatch"
            if item["item"] == cat_only
            else ("" if v == "supported" else "numeric_drift")
        )
        s.submit("R2", item["item"], v, cat, "")
        if (b := s.blinding_prompt("R2")) is not None:
            s.submit_guess("R2", b["item"], "unsure")
    seen = []
    while (item := s.next_item("ADJ")) is not None:
        assert len(item["labels"]) == 2
        assert all(set(lab) == {"verdict", "category"} for lab in item["labels"])
        seen.append(item["item"])
        s.submit("ADJ", item["item"], "unsupported", "numeric_drift", "")
    assert set(seen) == {split, cat_only}
    assert not any(key[i]["planted"] for i in seen)


def test_onboarding_mode_returns_answer_after_label(tmp_path: Path) -> None:
    s = make(tmp_path, mode="onboarding")
    item = s.next_item("R1")
    assert item is not None
    answer = s.submit("R1", item["item"], "supported", "", "")
    k = _key(tmp_path)[item["item"]]
    assert answer == {"planted": k["planted"], "category": k["category"]}
    labelling = make(tmp_path / "other")
    nxt = labelling.next_item("R1")
    assert nxt is not None
    assert labelling.submit("R1", nxt["item"], "supported", "", "") is None


def test_restart_resumes_from_ledger(tmp_path: Path) -> None:
    s = make(tmp_path)
    done = []
    for _ in range(3):
        item = s.next_item("R1")
        assert item is not None
        s.submit("R1", item["item"], "supported", "", "")
        done.append(item["item"])
    again = make(tmp_path)
    nxt = again.next_item("R1")
    assert nxt is not None and nxt["item"] not in done
    assert again.progress("R1")["labelled"] == 3


def test_tampered_ledger_refuses_to_start(tmp_path: Path) -> None:
    s = make(tmp_path)
    item = s.next_item("R1")
    assert item is not None
    s.submit("R1", item["item"], "supported", "", "")
    path = s.ledger._path
    entry = json.loads(path.read_text().splitlines()[0])
    entry["verdict"] = "unsupported"
    path.write_text(json.dumps(entry) + "\n")
    with pytest.raises(SessionError, match="ledger"):
        make(tmp_path)


def test_blinding_prompt_every_25_labels(tmp_path: Path) -> None:
    s = make(tmp_path, n=6)
    for n in range(1, 26):
        item = s.next_item("R1")
        assert item is not None
        assert s.blinding_prompt("R1") is None
        s.submit("R1", item["item"], "supported", "", "")
        if n < 25:
            assert s.blinding_prompt("R1") is None
    prompt = s.blinding_prompt("R1")
    assert prompt is not None and set(prompt) <= {
        "item",
        "header",
        "kind",
        "sentence",
        "cards",
    }
    assert not _key(tmp_path)[prompt["item"]]["planted"]
    s.submit_guess("R1", prompt["item"], "A")
    assert s.blinding_prompt("R1") is None
    assert latest(s.ledger, "blind_guess")[prompt["item"], "R1"]["verdict"] == "A"
