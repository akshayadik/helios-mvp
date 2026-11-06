"""Template narrator: deterministic, and every claim passes the verifier
(S2.8 design §5.3, owner decision N-a)."""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any

import pytest

from helios.narrative.params import load_narrator_params
from helios.narrative.template import template_slots
from helios.narrative.verifier import verify
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from tests.narrative.test_verifier import ENTRY

if TYPE_CHECKING:
    from pathlib import Path

P = load_narrator_params()


def _all_verified(entry: dict[str, Any]) -> list[Any]:
    slots = template_slots(entry, P)
    claims = [c for claims in slots.values() for c in claims]
    assert [verify(c, entry, P) for c in claims] == [None] * len(claims)
    return claims


def test_template_passes_verifier_on_the_hand_built_entry() -> None:
    claims = _all_verified(ENTRY)
    kinds = {c.kind.value for c in claims}
    assert {"ranking", "shift", "call_structure", "log_message"} <= kinds
    assert "contradiction" in kinds and "verification_step" in kinds


@pytest.mark.parametrize("variant", ["HELIOS-Full", "HELIOS-noLLM", "HELIOS-D"])
def test_template_passes_verifier_on_staged_runs(tmp_path: Path, variant: str) -> None:
    from tests.test_runner_coe import _run

    _, path = _run(tmp_path, variant)
    for line in path.read_text().splitlines():
        _all_verified(json.loads(line))


def test_template_is_deterministic() -> None:
    assert template_slots(ENTRY, P) == template_slots(copy.deepcopy(ENTRY), P)


def test_empty_entry_gives_empty_slots() -> None:
    entry = {
        "steps": [
            {"id": "T", "window_start": ENTRY["steps"][0]["window_start"]},
            {"id": "F", "ranked": [], "confidence": None, "disagree": []},
        ]
    }
    assert template_slots(entry, P) == {
        "story": [],
        "contradictions": [],
        "verification": [],
    }


def test_no_levels_no_invented_unit() -> None:
    entry = copy.deepcopy(ENTRY)
    for step in entry["steps"]:
        for item in step.get("items", []):
            for key in ("before", "after", "unit"):
                item.pop(key, None)
    claims = _all_verified(entry)
    text = " ".join(c.sentence for c in claims)
    assert " ms" not in text and "from " not in text


def test_one_contradiction_per_disagreeing_pipeline() -> None:
    slots = template_slots(ENTRY, P)
    assert [c.pipeline for c in slots["contradictions"]] == ["gpipe"]
    assert len(slots["verification"]) <= P.max_steps
    assert all(c.kind.value == "verification_step" for c in slots["verification"])


def test_candidates_pass_the_verifier_and_cover_the_template() -> None:
    # Owner decision (b), 2026-11-01: the LLM picks from these; code wrote them.
    from helios.narrative.template import candidate_claims

    cands = candidate_claims(ENTRY, P)
    for slot, claims in template_slots(ENTRY, P).items():
        assert [verify(c, ENTRY, P) for c in cands[slot]] == [None] * len(cands[slot])
        assert set(claims) <= set(cands[slot]), slot
        assert len(set(cands[slot])) == len(cands[slot])


def test_candidates_offer_every_edge_line_and_step() -> None:
    from helios.narrative.template import candidate_claims

    cands = candidate_claims(ENTRY, P)
    edges = {
        (c.caller, c.callee, c.feature)
        for c in cands["story"]
        if c.kind.value == "call_structure"
    }
    assert edges == {
        ("frontend", "cart", "wait"),
        ("checkout", "cart", "lead"),
        ("cart", "redis", "ghost"),
    }
    shifts = {(c.service, c.channel) for c in cands["story"] if c.kind.value == "shift"}
    assert {("cart", "latency"), ("cart", "error"), ("ad", "resource")} <= shifts
    targets = {c.target_service for c in cands["verification"]}
    assert targets == {"cart", "ad", "payment"}


@pytest.mark.parametrize("variant", ["HELIOS-Full", "HELIOS-noLLM"])
def test_candidates_pass_the_verifier_on_staged_runs(
    tmp_path: Path, variant: str
) -> None:
    from helios.narrative.template import candidate_claims
    from tests.test_runner_coe import _run

    _, path = _run(tmp_path, variant)
    for line in path.read_text().splitlines():
        entry = json.loads(line)
        cands = candidate_claims(entry, P)
        for claims in cands.values():
            assert [verify(c, entry, P) for c in claims] == [None] * len(claims)
        # Review I3: the template's slots are always among the candidates.
        for slot, claims in template_slots(entry, P).items():
            assert set(claims) <= set(cands[slot]), slot


def test_metric_digest_lines_are_never_called_logs() -> None:
    from helios.narrative.template import candidate_claims
    from tests.narrative.test_verifier import _with_metric_line

    entry = _with_metric_line()
    slots = template_slots(entry, P)
    cands = candidate_claims(entry, P)
    for claims in (*slots.values(), *cands.values()):
        for claim in claims:
            assert "L:metric:M1" not in claim.cites, claim.sentence
    assert any(c.kind.value == "log_message" for c in slots["story"])


def test_log_claims_quote_only_template_text() -> None:
    from helios.narrative.template import candidate_claims
    from tests.narrative.test_verifier import _with_severity_line

    entry = _with_severity_line()
    for claims in (
        *template_slots(entry, P).values(),
        *candidate_claims(entry, P).values(),
    ):
        for claim in claims:
            if claim.kind.value == "log_message":
                assert claim.cites == ("L:log:L12",), claim.sentence
                assert claim.snippet == "connection pool exhausted after <DUR>"


def test_candidates_never_repeat_a_sentence_or_state_a_zero_share() -> None:
    # Review I2: a ghost edge between two top-3 services sits in both services'
    # items; M1: a share that rounds to 0% is not worth stating.
    from helios.narrative.template import candidate_claims

    entry = copy.deepcopy(ENTRY)
    gpipe = next(s for s in entry["steps"] if s["id"] == "P:gpipe")
    for item in gpipe["items"]:
        if item["id"] == "G:cart:ghost_edges":
            item["value"] = [["cart", "ad"]]
        if item["id"] == "G:cart:wait_from":
            item["value"] = {"frontend": 0.94, "checkout": 0.003}
    gpipe["items"].append(
        {
            "id": "G:ad:ghost_edges",
            "service": "ad",
            "text": "x",
            "value": [["cart", "ad"]],
        }
    )
    story = candidate_claims(entry, P)["story"]
    sentences = [c.sentence for c in story]
    assert len(sentences) == len(set(sentences))
    assert "cart started calling ad after the trigger." in sentences
    assert not any("0% of its time" in s for s in sentences)
