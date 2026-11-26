"""One renderer for both narrators; the header comes from F only (S2.8 §5.1)."""

from __future__ import annotations

from typing import Any

import pytest

from helios.narrative.claims import Claim, ClaimKind
from helios.narrative.render import header, render, state_text
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


# ── CR-03: the state's reason in the header ─────────────────────────────────


def _f(
    state: str, contributing: list[str] | None, confidence: float | None = 0.93
) -> dict[str, Any]:
    f: dict[str, Any] = {
        "id": "F",
        "ranked": ["cart"],
        "confidence": confidence,
        "state": state,
    }
    if contributing is not None:
        f["detail"] = {"contributing": contributing}
    return f


@pytest.mark.parametrize(
    ("state", "contributing", "confidence", "said"),
    [
        (
            "confirmed",
            ["dpipe", "lpipe"],
            0.93,
            "confirmed: two or more pipelines, confidence above floor",
        ),
        (
            "confirmed",
            ["dpipe", "lpipe"],
            None,
            "confirmed: two or more pipelines voted",
        ),
        ("provisional", ["dpipe"], 0.97, "provisional: one pipeline ran"),
        ("provisional", [], None, "provisional: one pipeline ran"),
        (
            "provisional",
            ["dpipe", "gpipe", "lpipe"],
            0.88,
            "provisional: confidence below floor",
        ),
        ("non_converged", ["dpipe"], 0.9, "not converged"),
        ("provisional", None, 0.9, "provisional"),  # entry without detail
    ],
)
def test_state_text_names_the_reason(
    state: str, contributing: list[str] | None, confidence: float | None, said: str
) -> None:
    assert state_text(_f(state, contributing, confidence)) == said


def test_header_prints_reason_after_confidence() -> None:
    entry = {"steps": [_f("provisional", ["dpipe"], 0.97)]}
    assert header(entry) == (
        "Top suspects: 1. cart (confidence 0.97, provisional: one pipeline ran). [F]"
    )


def test_header_without_confidence_prints_reason_alone() -> None:
    entry = {"steps": [_f("confirmed", ["dpipe", "lpipe"], None)]}
    assert (
        header(entry)
        == "Top suspects: 1. cart (confirmed: two or more pipelines voted). [F]"
    )


def test_state_text_does_not_change_the_state() -> None:
    f = _f("provisional", ["dpipe"])
    state_text(f)
    assert f["state"] == "provisional"
