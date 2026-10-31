"""Machine verification report for narratives (S2.8 owner decision N-h).

Computed from stored narrative rows only, per narrator: how often the model's
first draft passes the verifier, why claims are rejected, how often a retry
rescues a slot, how often a slot falls back to the template, and the sentence
and slot shapes that would reveal a style gap before the S2.9 raters see them.
It needs no labels and no human labour.
"""

from __future__ import annotations

from collections import Counter
from statistics import mean, median
from typing import TYPE_CHECKING, Any

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = ["narrative_report"]


def _ratio(num: int, den: int) -> float | None:
    return num / den if den else None


def _shape(values: list[int]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "mean": None, "median": None, "max": None}
    return {
        "n": len(values),
        "mean": mean(values),
        "median": median(values),
        "max": max(values),
    }


def _one(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    slots = [s for r in rows for s in r["slots"].values()]
    called = [s for s in slots if s["attempts"] > 0]
    retried = [s for s in called if s["attempts"] > 1]
    displayed = [c for s in slots for c in s["claims"]]
    reasons: Counter[str] = Counter(str(r[1]) for s in slots for r in s["rejections"])
    drafted = sum(int(s.get("drafted_first", 0)) for s in called)
    accepted = sum(int(s.get("accepted_first", 0)) for s in called)
    return {
        "narratives": len(rows),
        "claims_displayed": len(displayed),
        "slots_called": len(called),
        "first_pass_claim_acceptance": _ratio(accepted, drafted),
        "first_pass_slot_acceptance": _ratio(
            sum(1 for s in called if s["attempts"] == 1 and not s["fallback"]),
            len(called),
        ),
        "retry_success": _ratio(
            sum(1 for s in retried if not s["fallback"]), len(retried)
        ),
        "slot_fallback_rate": _ratio(
            sum(1 for s in called if s["fallback"]), len(called)
        ),
        "rejections": dict(sorted(reasons.items())),
        "sentence_words": _shape([len(c["sentence"].split()) for c in displayed]),
        "claims_per_slot": _shape([len(s["claims"]) for s in slots if s["claims"]]),
    }


def narrative_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The report per narrator (``llm``, ``template``) over stored rows."""
    return {
        narrator: _one([r for r in rows if r["narrator"] == narrator])
        for narrator in sorted({str(r["narrator"]) for r in rows})
    }
