"""Planted claims (S2.9 design §5.2, owner decision R-f): one corruption per
error category, each rejected by the S2.8 verifier for the matching reason."""

from __future__ import annotations

import random
import re
from random import Random as Rng
from typing import Any

import pytest

from helios.labelling.planted import CATEGORIES, EXPECTED_REASON, corrupt, plant
from helios.narrative.params import load_narrator_params
from helios.narrative.verifier import verify
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from tests.narrative.test_verifier import ENTRY, SUPPORTED

P = load_narrator_params()

# Which categories can apply to which claim kind on ENTRY.
APPLIES = {
    "numeric_drift": {"shift", "call_structure"},
    "entity_mismatch": {
        "shift",
        "call_structure",
        "log_message",
        "ranking",
        "contradiction",
        "verification_step",
    },
    "directional_inversion": {"shift"},
    "log_quote_mismatch": {"log_message"},
    "missing_citation": {
        "shift",
        "call_structure",
        "log_message",
        "ranking",
        "contradiction",
        "verification_step",
    },
}


@pytest.mark.parametrize("category", CATEGORIES)
def test_each_category_is_rejected_by_the_verifier_with_its_reason(
    category: str,
) -> None:
    for kind, claim in SUPPORTED.items():
        planted = corrupt(claim, ENTRY, category, random.Random(7), P)
        if kind not in APPLIES[category]:
            assert planted is None, (category, kind)
            continue
        assert planted is not None, (category, kind)
        assert verify(planted, ENTRY, P) in EXPECTED_REASON[category], (
            category,
            kind,
            planted.sentence,
        )


@pytest.mark.parametrize("category", CATEGORIES)
def test_corruptions_keep_the_sentence_shape(category: str) -> None:
    for claim in SUPPORTED.values():
        planted = corrupt(claim, ENTRY, category, random.Random(3), P)
        if planted is None:
            continue
        assert planted.kind == claim.kind
        assert "\n" not in planted.sentence
        assert abs(len(planted.sentence.split()) - len(claim.sentence.split())) <= 2


def test_numbers_move_beyond_tolerance_and_keep_their_unit() -> None:
    planted = corrupt(SUPPORTED["shift"], ENTRY, "numeric_drift", random.Random(1), P)
    assert planted is not None
    nums = re.findall(r"(\d+(?:\.\d+)?) ms", planted.sentence)
    assert len(nums) == 2 and nums != ["120", "900"]
    moved = [float(a) / float(b) for a, b in zip(nums, ["120", "900"], strict=True)]
    assert any(abs(r - 1) > 10 * P.rel_tolerance for r in moved)


def _sources(n: int) -> list[tuple[str, Any, Any]]:
    claims = list(SUPPORTED.values())
    return [(f"src{i}", claims[i % len(claims)], ENTRY) for i in range(n)]


def test_plant_share_and_balance() -> None:
    # 30 real claims at a quarter: 10 planted, two per category.
    out = plant(_sources(240), 1 / 4, Rng(11), P, n_real=30)
    assert len(out) == 10  # 10 of 40 shown is a quarter
    cats = [cat for _, _, cat in out]
    assert set(cats) == set(CATEGORIES)
    assert max(map(cats.count, CATEGORIES)) - min(map(cats.count, CATEGORIES)) <= 2
    for _, claim, cat in out:
        assert verify(claim, ENTRY, P) in EXPECTED_REASON[cat]


def test_plant_never_repeats_a_source_or_a_sentence() -> None:
    # Review C1: the 240 sources are 6 claims repeated, so only the unique
    # corruptions are used and the shortfall shows in the count.
    out = plant(_sources(240), 1 / 4, Rng(11), P)
    assert len({key for key, _, _ in out}) == len(out) < 80
    assert len({(c.sentence, c.cites) for _, c, _ in out}) == len(out)


def test_plant_is_deterministic_for_a_seed() -> None:
    a = plant(_sources(60), 1 / 4, random.Random(5), P)
    b = plant(_sources(60), 1 / 4, random.Random(5), P)
    assert a == b
    assert a != plant(_sources(60), 1 / 4, random.Random(6), P)


def test_planted_and_real_items_have_the_same_shape() -> None:
    for category in CATEGORIES:
        for claim in SUPPORTED.values():
            planted = corrupt(claim, ENTRY, category, random.Random(2), P)
            if planted is not None:
                real = claim.model_dump(mode="json", exclude_none=True)
                fake = planted.model_dump(mode="json", exclude_none=True)
                assert set(real) == set(fake), (category, claim.kind)


def test_rare_categories_still_get_planted() -> None:
    # Rebuilt training-1 had no log_quote_mismatch: log claims are rare, so a
    # plain shuffled walk filled the quota before reaching one.
    shift = SUPPORTED["shift"]
    sources: list[tuple[str, Any, Any]] = []
    for i in range(400):
        claim = shift.model_copy(
            update={"sentence": f"cart latency rose from 120 ms to 900 ms. ({i})"}
        )
        sources.append((f"shift{i}", claim, ENTRY))
    sources += [(f"log{i}", SUPPORTED["log_message"], ENTRY) for i in range(3)]
    for seed in range(5):
        out = plant(sources, 1 / 4, random.Random(seed), P, n_real=60)
        assert "log_quote_mismatch" in {cat for _, _, cat in out}, seed


def test_numeric_drift_never_makes_an_impossible_percentage() -> None:
    # Review M2: "150% of its time" gives a planted claim away.
    claim = SUPPORTED["call_structure"]  # "frontend spent 94% of its time ..."
    for seed in range(20):
        planted = corrupt(claim, ENTRY, "numeric_drift", random.Random(seed), P)
        assert planted is not None
        (pct,) = re.findall(r"(\d+(?:\.\d+)?)%", planted.sentence)
        assert float(pct) <= 10**2, planted.sentence
