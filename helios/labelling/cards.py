"""What a rater sees for one claim: the claim and the evidence it cites
(S2.9 design §5.3, owner decisions R-c and R-k).

The header shows the fused top 3 only: confidence and state come from fusion
and differ between arms. A log card shows only the logged template text, never
the digest wording around it. A cite that does not resolve gets the same
"evidence not found" card whether the claim is real or planted.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from helios.narrative.claims import SLOTS, Claim, ClaimKind
from helios.narrative.verifier import LOG_PREFIX, log_template_text
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["MISSING_CARD_TEXT", "Card", "cards_for", "displayed_claims", "header_top3"]

MISSING_CARD_TEXT = "evidence not found"
_PIPELINE_NAMES = {"dpipe": "D-pipe", "gpipe": "G-pipe", "lpipe": "L-pipe"}
_VALUE_KEYS = ("value", "before", "after", "unit")


@dataclass(frozen=True)
class Card:
    """One cited evidence item as shown to a rater."""

    id: str
    service: str | None
    text: str
    values: dict[str, Any] = field(default_factory=dict)


def _steps(entry: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(s["id"]): s for s in entry["steps"]}


def _top3(entry: Mapping[str, Any]) -> list[str]:
    return list(_steps(entry).get("F", {}).get("ranked") or [])[:3]


def header_top3(entry: Mapping[str, Any]) -> str:
    """The context line: fused top 3, no confidence or state (R-k)."""
    top = _top3(entry)
    if not top:
        return "No suspect ranked."
    return "Top suspects: " + ", ".join(f"{n}. {s}" for n, s in enumerate(top, 1))


def displayed_claims(entry: Mapping[str, Any]) -> list[tuple[str, int, Claim]]:
    """(slot, index, claim) for every displayed claim, in display order."""
    step = _steps(entry).get("N")
    if step is None:
        return []
    out = []
    for slot in SLOTS:
        raw = step.get("slots", {}).get(slot, {}).get("claims", [])
        out += [(slot, i, Claim(**c)) for i, c in enumerate(raw)]
    return out


def _card(item: Mapping[str, Any]) -> Card:
    text = str(item.get("text", ""))
    if str(item["id"]).startswith(LOG_PREFIX):
        logged = log_template_text(text)
        if logged is not None:
            return Card(str(item["id"]), item.get("service"), logged)
    values = {k: item[k] for k in _VALUE_KEYS if item.get(k) is not None}
    return Card(str(item["id"]), item.get("service"), text, values)


def cards_for(claim: Claim, entry: Mapping[str, Any]) -> list[Card]:
    """One card per cite; ``F`` is the fused top 3."""
    items = {
        str(i["id"]): i
        for s in entry["steps"]
        for i in s.get("items", [])
        if ":claim" not in str(i["id"])
    }
    cards = []
    for cite in claim.cites:
        if cite == "F" and "F" in _steps(entry):
            cards.append(Card("F", None, "fused verdict", {"top": _top3(entry)}))
        elif cite in items:
            cards.append(_card(items[cite]))
        else:
            cards.append(Card(cite, None, MISSING_CARD_TEXT))
    return cards + _context(claim, entry, {c.id for c in cards})


def _clock(iso: Any) -> str:
    return dt.datetime.fromisoformat(str(iso)).strftime("%H:%M")


def _context(claim: Claim, entry: Mapping[str, Any], shown: set[str]) -> list[Card]:
    """What the verifier checks beyond the cites: a contradiction's pipeline
    ranking and fused verdict; a verification step's incident window."""
    steps = _steps(entry)
    out = []
    if claim.kind == ClaimKind.CONTRADICTION and claim.pipeline:
        ranked = list(steps.get(f"P:{claim.pipeline}", {}).get("ranked") or [])[:3]
        name = _PIPELINE_NAMES.get(str(claim.pipeline), str(claim.pipeline))
        out.append(
            Card(f"P:{claim.pipeline}", None, f"{name} ranking", {"top": ranked})
        )
        if "F" not in shown and "F" in steps:
            out.append(Card("F", None, "fused verdict", {"top": _top3(entry)}))
    if claim.kind == ClaimKind.VERIFICATION_STEP:
        t = steps.get("T", {})
        if t.get("window_start") and t.get("window_end"):
            window = {
                "start": _clock(t["window_start"]),
                "end": _clock(t["window_end"]),
            }
            out.append(Card("T", None, "incident window (UTC)", window))
    return out
