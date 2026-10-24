"""Tests for the binding seed register (Ch3 p.108; S0.8).

Seeds must be inside 10,000,000-10,009,999, never shared between two
confirmatory runs, and identical on every machine: the layout digest and a
few exact values are pinned here.
"""

from __future__ import annotations

import pytest

from helios.research.analysis_plan import (
    FAMILY_A_HYPOTHESES,
    FAMILY_B_HYPOTHESES,
    FAMILY_E_HYPOTHESES,
)
from helios.research.seeds import (
    BCA_HYPOTHESIS_SLOTS,
    OPAQUE_ID_CORPUS_SLOTS,
    PREWARM_LENGTH,
    RUN_SYSTEM_SLOTS,
    TRAINING_SLOTS,
    bca_seed,
    opaque_id_seed,
    prewarm_seed,
    register_layout,
    run_seed,
    seed_for,
    training_seed,
)
from helios.vcl import (
    CONFIRMATORY_VARIANTS,
    EXPLORATORY_VARIANTS,
    VCLFlag,  # noqa: F401 — flag-guard compliance
)

FIRST, LAST = 10_000_000, 10_009_999
CASES = [f"case-{i:03d}" for i in range(240)]

# Pinned after the first generation; a change here means seeds moved.
LAYOUT_SHA256 = "ce0cab374e9a7d66a7c996266afbca3175665f8d148bf7b034ff7b7a000f871f"


def _block_seeds(purpose: str) -> list[int]:
    seeds: list[int] = []
    i = 0
    while True:
        try:
            seeds.append(seed_for(purpose, i))
        except ValueError:
            return seeds
        i += 1


def test_every_block_lies_inside_the_register_and_blocks_are_disjoint() -> None:
    seen: set[int] = set()
    for block in register_layout()["blocks"]:  # type: ignore[attr-defined]
        seeds = _block_seeds(block["purpose"])
        assert seeds[0] == block["first_seed"]
        assert seeds[-1] == block["last_seed"]
        assert all(FIRST <= s <= LAST for s in seeds)
        assert not seen & set(seeds), block["purpose"]
        seen |= set(seeds)


def test_confirmatory_and_baseline_runs_never_share_a_seed() -> None:
    seeds = [run_seed(c, s, case_order=CASES) for c in CASES for s in RUN_SYSTEM_SLOTS]
    assert len(seeds) == len(set(seeds)) == 240 * 20


def test_exact_values_are_stable() -> None:
    assert run_seed("case-000", "HELIOS-Full", case_order=CASES) == FIRST
    assert run_seed("case-001", "HELIOS-noLLM", case_order=CASES) == FIRST + 25
    assert training_seed("gpipe_ranker") == FIRST + 7_200
    assert training_seed("acp_predictor", replicate=5) == FIRST + 7_213
    assert bca_seed("A-H3") == FIRST + 7_328
    assert opaque_id_seed("rcaeval_confirmatory") == FIRST + 7_392
    assert prewarm_seed(PREWARM_LENGTH - 1) == FIRST + 8_607


def test_layout_digest_is_pinned() -> None:
    assert register_layout()["layout_sha256"] == LAYOUT_SHA256


def test_run_seed_depends_on_position_not_name() -> None:
    renamed = [f"opaque-{i}" for i in range(240)]
    assert run_seed("opaque-7", "HELIOS-D", case_order=renamed) == run_seed(
        "case-007", "HELIOS-D", case_order=CASES
    )


def test_run_slots_cover_every_variant_and_baseline() -> None:
    expected = {*CONFIRMATORY_VARIANTS, *EXPLORATORY_VARIANTS} | {
        f"BASELINE-{k}" for k in range(1, 6)
    }
    assert set(RUN_SYSTEM_SLOTS) == expected
    assert RUN_SYSTEM_SLOTS[:8] == tuple(CONFIRMATORY_VARIANTS)


def test_bca_slots_follow_the_analysis_plan() -> None:
    plan_ids = [
        h["id"]
        for h in (*FAMILY_A_HYPOTHESES, *FAMILY_B_HYPOTHESES, *FAMILY_E_HYPOTHESES)
    ]
    assert list(BCA_HYPOTHESIS_SLOTS) == plan_ids


def test_layout_lists_every_slot() -> None:
    layout = register_layout()
    assert layout["first_seed"] == FIRST and layout["last_seed"] == LAST
    assert layout["training_slots"] == list(TRAINING_SLOTS)
    assert layout["opaque_id_corpus_slots"] == list(OPAQUE_ID_CORPUS_SLOTS)


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: seed_for("nope", 0), "unknown seed purpose"),
        (lambda: seed_for("bca", -1), "outside"),
        (lambda: prewarm_seed(PREWARM_LENGTH), "outside"),
        (lambda: run_seed("x", "HELIOS-Full", case_order=CASES), "not in case_order"),
        (lambda: run_seed("a", "HELIOS-Full", case_order=["a", "a"]), "duplicate"),
        (lambda: run_seed("case-000", "HELIOS-X", case_order=CASES), "unregistered"),
        (lambda: training_seed("gpipe_ranker", replicate=8), "replicate"),
        (lambda: bca_seed("A-H9"), "unregistered"),
        (lambda: opaque_id_seed("other"), "unregistered"),
    ],
)
def test_invalid_requests_are_refused(call: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        call()  # type: ignore[operator]
