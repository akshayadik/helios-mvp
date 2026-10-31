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
pytestmark = pytest.mark.filterwarnings("ignore::scipy.stats.ConstantInputWarning")


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
