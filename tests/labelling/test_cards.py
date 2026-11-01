"""Claim and evidence cards from a CoE entry (S2.9 design §5.3, R-c, R-k)."""

from __future__ import annotations

import copy
from typing import Any

from helios.labelling.cards import (
    MISSING_CARD_TEXT,
    cards_for,
    displayed_claims,
    header_top3,
)
from helios.narrative.claims import SLOTS, Claim, ClaimKind
from helios.narrative.params import load_narrator_params
from helios.narrative.template import template_slots
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from tests.narrative.test_verifier import ENTRY

P = load_narrator_params()


def with_step_n(entry: dict[str, Any]) -> dict[str, Any]:
    """``entry`` plus a template step N, as the runner stores it."""
    out = copy.deepcopy(entry)
    slots = template_slots(entry, P)
    out["steps"].append(
        {
            "id": "N",
            "narrator": "template",
            "slots": {
                name: {
                    "source": "template",
                    "claims": [
                        c.model_dump(mode="json", exclude_none=True)
                        for c in slots[name]
                    ],
                }
                for name in SLOTS
            },
        }
    )
    return out


def test_header_has_no_confidence_or_state() -> None:
    h = header_top3(ENTRY)
    assert h == "Top suspects: 1. cart, 2. ad, 3. payment"
    assert "0.91" not in h and "confirmed" not in h


def test_displayed_claims_follow_display_order() -> None:
    entry = with_step_n(ENTRY)
    got = displayed_claims(entry)
    slots = template_slots(ENTRY, P)
    want = [(s, i, c) for s in SLOTS for i, c in enumerate(slots[s])]
    assert got == want
    assert got[0][2].kind == ClaimKind.RANKING


def test_cards_resolve_each_cite() -> None:
    claim = Claim(
        kind=ClaimKind.SHIFT,
        sentence="cart latency rose from 120 ms to 900 ms.",
        cites=("D:cart:latency",),
        service="cart",
        channel="latency",
        direction="up",
    )
    (card,) = cards_for(claim, ENTRY)
    assert card.id == "D:cart:latency" and card.service == "cart"
    assert card.values["before"] == 120 and card.values["after"] == 900
    assert card.values["unit"] == "ms"
    ranking = Claim(
        kind=ClaimKind.RANKING,
        sentence="ad is the second suspect.",
        cites=("F",),
        service="ad",
        rank=2,
    )
    (f,) = cards_for(ranking, ENTRY)
    assert f.id == "F" and f.values == {"top": ["cart", "ad", "payment"]}


def test_log_card_shows_only_template_text() -> None:
    claim = Claim(
        kind=ClaimKind.LOG_MESSAGE,
        sentence='cart logged "connection pool exhausted".',
        cites=("L:log:L12",),
        service="cart",
        snippet="connection pool exhausted",
    )
    (card,) = cards_for(claim, ENTRY)
    assert card.text == "connection pool exhausted after <DUR>"
    assert "lines before trigger" not in card.text and card.values == {}


def test_missing_evidence_card() -> None:
    claim = Claim(
        kind=ClaimKind.SHIFT,
        sentence="cart latency rose sharply after the trigger.",
        cites=("D:nope:latency",),
        service="cart",
        channel="latency",
        direction="up",
    )
    (card,) = cards_for(claim, ENTRY)
    assert card.id == "D:nope:latency"
    assert card.text == MISSING_CARD_TEXT and card.values == {}
    assert card.service is None


def test_no_step_n_gives_no_claims() -> None:
    assert displayed_claims(ENTRY) == []
