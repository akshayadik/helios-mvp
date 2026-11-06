"""One renderer for both narrators (S2.8 design §5.1, §5.8 style blinding)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from helios.narrative.claims import SLOTS
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from helios.narrative.claims import Claim

__all__ = ["header", "render"]

_TITLES = {
    "story": "What happened",
    "contradictions": "Where the pipelines disagree",
    "verification": "What to check",
}


def _fusion(entry: Mapping[str, Any]) -> Mapping[str, Any]:
    return next(s for s in entry["steps"] if s["id"] == "F")


def header(entry: Mapping[str, Any]) -> str:
    """The code-filled first line: fused top 3, confidence and state."""
    f = _fusion(entry)
    ranked = list(f.get("ranked") or [])[:3]
    if not ranked:
        return "No suspect ranked. [F]"
    top = ", ".join(f"{n}. {s}" for n, s in enumerate(ranked, start=1))
    conf = f.get("confidence")
    detail = f"{f['state']}" if conf is None else f"confidence {conf:.2f}, {f['state']}"
    return f"Top suspects: {top} ({detail}). [F]"


def render(entry: Mapping[str, Any], slots: Mapping[str, Sequence[Claim]]) -> str:
    """Header, then each non-empty slot's sentences with their citations."""
    lines = [header(entry)]
    for slot in SLOTS:
        claims = list(slots.get(slot, ()))
        if not claims:
            continue
        lines += ["", f"{_TITLES[slot]}:"]
        lines += [f"- {c.sentence} [{', '.join(c.cites)}]" for c in claims]
    return "\n".join(lines)
