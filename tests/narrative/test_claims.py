"""Typed claims and narrator parameters (S2.8 design §5.2, N-b, §5.8)."""

from __future__ import annotations

import json

import pytest

from helios.narrative.claims import (
    SLOTS,
    Claim,
    ClaimKind,
    ClaimSchemaError,
    parse_slot,
)
from helios.narrative.params import load_narrator_params, narrator_params_hash
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

SHIFT = {
    "kind": "shift",
    "service": "cart",
    "channel": "latency",
    "direction": "up",
    "cites": ["D:cart:latency"],
    "sentence": "cart latency rose from 120 ms to 900 ms.",
}


def test_slots_and_kinds() -> None:
    assert SLOTS == ("story", "contradictions", "verification")
    assert {k.value for k in ClaimKind} == {
        "shift",
        "call_structure",
        "log_message",
        "ranking",
        "contradiction",
        "verification_step",
    }


def test_parse_accepts_list_and_wrapped() -> None:
    (a,) = parse_slot(json.dumps([SHIFT]))
    (b,) = parse_slot(json.dumps({"claims": [SHIFT]}))
    assert a == b
    assert isinstance(a, Claim) and a.kind == ClaimKind.SHIFT
    assert a.cites == ("D:cart:latency",)


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        json.dumps({"story": "text"}),
        json.dumps([{**SHIFT, "kind": "opinion"}]),
        json.dumps([{k: v for k, v in SHIFT.items() if k != "direction"}]),
        json.dumps([{**SHIFT, "direction": "sideways"}]),
        json.dumps([{**SHIFT, "extra": 1}]),
        json.dumps(["a string"]),
    ],
)
def test_parse_rejects_unknown_kind_missing_fields_and_non_json(raw: str) -> None:
    with pytest.raises(ClaimSchemaError):
        parse_slot(raw)


def test_empty_cites_parse_and_are_left_to_the_verifier() -> None:
    (c,) = parse_slot(json.dumps([{**SHIFT, "cites": []}]))
    assert c.cites == ()


def test_params_file_contents_and_hash_stable() -> None:
    params = load_narrator_params()
    assert {"query", "inspect", "verify", "check", "filter"} == set(params.verbs)
    assert "rose" in params.direction_words["up"]
    assert "fell" in params.direction_words["down"]
    assert params.max_steps == 3
    assert narrator_params_hash(params) == narrator_params_hash(load_narrator_params())
    assert len(narrator_params_hash(params)) == 64


def test_narrator_frozen_from_round_3() -> None:
    # Entry C: round 3 (owner decision (b)) chosen; held-out run with the same
    # prompt and parameters; only the provisional flags change at the freeze.
    import dataclasses
    from pathlib import Path

    from helios.narrative import prompt

    reports = (
        Path(__file__).resolve().parents[2] / "docs/sprints/s2-reasoning/calibration"
    )
    round3 = json.loads((reports / "narrator_round3.json").read_text("utf-8"))
    final = json.loads((reports / "narrator_final.json").read_text("utf-8"))
    params = load_narrator_params()
    assert prompt.PROVISIONAL is False and params.provisional is False
    assert final["chosen_round"] == 3 and final["split"] == "heldout"
    assert round3["narrator_prompt_sha"] == prompt.NARRATOR_PROMPT_SHA
    assert final["narrator_prompt_sha"] == prompt.NARRATOR_PROMPT_SHA
    as_run = dataclasses.replace(params, provisional=True)
    assert narrator_params_hash(as_run) == round3["narrator_params_hash"]
    # Held-out re-run on the frozen file after the review fixes (entry 68).
    assert narrator_params_hash(params) == final["narrator_params_hash"]
