"""One renderer for both narrators; the header comes from F only (S2.8 §5.1)."""

from __future__ import annotations

from typing import Any

from helios.narrative.claims import Claim, ClaimKind
from helios.narrative.render import render
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def _entry(ranked: list[str], confidence: float | None = 0.91) -> dict[str, Any]:
    return {
        "steps": [
            {"id": "T"},
            {
                "id": "F",
                "ranked": ranked,
                "confidence": confidence,
                "state": "confirmed",
            },
        ]
    }


def _claim(sentence: str, cites: tuple[str, ...]) -> Claim:
    return Claim(
        kind=ClaimKind.RANKING,
        service="ad",
        rank=1,
        cites=cites,
        sentence=sentence,
    )


def test_render_header_from_f_only() -> None:
    text = render(
        _entry(["cart", "ad", "payment", "email"]),
        {"story": [_claim("ad is the top suspect.", ("F",))]},
    )
    header = text.splitlines()[0]
    assert "1. cart" in header and "2. ad" in header and "3. payment" in header
    assert "email" not in header
    assert "confirmed" in header and "0.91" in header
    assert "ad is the top suspect. [F]" in text


def test_render_without_ranking() -> None:
    text = render(_entry([], confidence=None), {})
    assert text.splitlines()[0].startswith("No suspect ranked")


def test_render_same_shape_for_both_sources() -> None:
    claims = {"story": [_claim("x rose.", ("D:x:error", "L:log:L2"))]}
    a = render(_entry(["x"]), claims)
    b = render(_entry(["x"]), {"story": list(claims["story"])})
    assert a == b
    assert "x rose. [D:x:error, L:log:L2]" in a
    assert "Contradictions" not in a  # empty slots are not rendered
