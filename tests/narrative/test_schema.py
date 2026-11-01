"""Per-slot output schema for the LLM narrator (S2.8 round 2).

The schema offers only field combinations the entry supports; the model still
chooses the claims and writes every sentence, and the verifier still checks
each claim on its own.
"""

from __future__ import annotations

from typing import Any

from helios.narrative.params import load_narrator_params
from helios.narrative.schema import slot_schema
from helios.narrative.template import template_slots
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from tests.narrative.test_verifier import ENTRY

P = load_narrator_params()


def _field_fits(value: Any, spec: dict[str, Any]) -> bool:
    if "const" in spec:
        return bool(value == spec["const"])
    if "enum" in spec:
        return value in spec["enum"]
    if spec.get("type") == "array":
        n = len(value) if isinstance(value, list) else -1
        if not spec.get("minItems", 0) <= n <= spec.get("maxItems", n):
            return False
        return all(_field_fits(v, spec["items"]) for v in value)
    if spec.get("type") == "string":
        return isinstance(value, str) and len(value) <= spec.get(
            "maxLength", len(value)
        )
    return False


def _fits(claim: dict[str, Any], schema: dict[str, Any]) -> bool:
    """Whether one claim matches one of the slot schema's claim options."""
    for option in schema["properties"]["claims"]["items"]["anyOf"]:
        props = option["properties"]
        if (
            set(claim) <= set(props)
            and set(option["required"]) <= set(claim)
            and all(_field_fits(claim[k], props[k]) for k in claim)
        ):
            return True
    return False


def _options(slot: str, kind: str) -> list[dict[str, Any]]:
    schema = slot_schema(slot, ENTRY, P)
    assert schema is not None
    return [
        o["properties"]
        for o in schema["properties"]["claims"]["items"]["anyOf"]
        if o["properties"]["kind"]["const"] == kind
    ]


def test_every_template_claim_fits_its_slot_schema() -> None:
    for slot, claims in template_slots(ENTRY, P).items():
        schema = slot_schema(slot, ENTRY, P)
        assert schema is not None
        for claim in claims:
            raw = claim.model_dump(mode="json", exclude_none=True)
            raw["cites"] = list(raw["cites"])
            assert _fits(raw, schema), (slot, raw)


def test_ranking_options_are_the_fused_order() -> None:
    got = {
        (o["service"]["const"], o["rank"]["const"])
        for o in _options("story", "ranking")
    }
    assert got == {("cart", 1), ("ad", 2), ("payment", 3)}


def test_shift_options_carry_the_evidence_direction() -> None:
    got = {
        (o["service"]["const"], o["channel"]["const"], o["direction"]["const"])
        for o in _options("story", "shift")
    }
    assert ("payment", "resource", "down") in got  # levels 10 -> 4
    assert ("cart", "error", "up") in got  # no levels: the sign of the shift
    assert not any(s == "cart" and ch == "score" for s, ch, _ in got)


def test_schema_rejects_what_the_verifier_rejects() -> None:
    schema = slot_schema("story", ENTRY, P)
    assert schema is not None
    base = {"kind": "ranking", "service": "cart", "rank": 1, "cites": ["F"]}
    assert _fits({**base, "sentence": "cart is the top suspect."}, schema)
    assert not _fits({**base, "rank": 2, "sentence": "x"}, schema)
    shift = {
        "kind": "shift",
        "service": "payment",
        "channel": "resource",
        "direction": "up",
        "cites": ["D:payment:resource"],
        "sentence": "x",
    }
    assert not _fits(shift, schema)  # levels fell
    edge = {
        "kind": "call_structure",
        "caller": "frontend",
        "callee": "cart",
        "feature": "wait",
        "cites": ["G:cart:wait_from"],
        "sentence": "x",
    }
    assert _fits(edge, schema)
    assert not _fits({**edge, "caller": "cart", "callee": "frontend"}, schema)
    assert not _fits({**base, "cites": ["L:log:claim1"], "sentence": "x"}, schema)


def test_contradiction_and_steps_offer_only_supported_fields() -> None:
    (contra,) = _options("contradictions", "contradiction")
    assert contra["pipeline"]["const"] == "gpipe"
    assert contra["service"]["const"] == "ad"
    assert set(contra["cites"]["items"]["enum"]) == {"G:ad:self_shift"}
    steps = _options("verification", "verification_step")
    assert {o["modality"]["const"] for o in steps} == {"metric", "log", "edge"}
    for o in steps:
        assert set(o["target_service"]["enum"]) == {"cart", "ad", "payment"}
        assert o["action_verb"]["enum"] == list(P.verbs)


def test_claim_count_is_capped_per_slot() -> None:
    def cap(slot: str) -> int:
        schema = slot_schema(slot, ENTRY, P)
        assert schema is not None
        return int(schema["properties"]["claims"]["maxItems"])

    assert cap("story") == 3
    assert cap("contradictions") == 3
    assert cap("verification") == P.max_steps
