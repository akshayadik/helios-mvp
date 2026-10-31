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


def test_params_file_is_provisional_and_hash_stable() -> None:
    params = load_narrator_params()
    assert params.provisional is True
    assert {"query", "inspect", "verify", "check", "filter"} == set(params.verbs)
    assert "rose" in params.direction_words["up"]
    assert "fell" in params.direction_words["down"]
    assert params.max_steps == 3
    assert narrator_params_hash(params) == narrator_params_hash(load_narrator_params())
    assert len(narrator_params_hash(params)) == 64
