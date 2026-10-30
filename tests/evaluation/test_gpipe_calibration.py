"""G-pipe selection rule and build cases (S2.2 design §5.3, G-c, G-f)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from helios.evaluation import gpipe_calibration as gc
from helios.evaluation.gpipe_calibration import (
    CANDIDATES,
    MARGIN_HITS,
    beats,
    select_gpipe,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    import pytest

REPO = Path(__file__).resolve().parents[2]


def _hits(**per_fault: list[int]) -> dict[str, list[int]]:
    return dict(per_fault)


def test_rule_constants() -> None:
    assert MARGIN_HITS == 3
    assert CANDIDATES == ("learned", "weighted_ppr", "ppr")


def test_learned_needs_three_more_hits() -> None:
    simple = _hits(a=[0, 0], b=[0, 0], c=[0, 0])
    two_more = _hits(a=[1, 0], b=[1, 0], c=[0, 0])
    three_more = _hits(a=[1, 0], b=[1, 0], c=[1, 0])
    assert not beats(two_more, simple)
    assert beats(three_more, simple)


def test_learned_needs_more_faults_better_than_worse() -> None:
    simple = _hits(a=[0, 0, 0, 0, 0], b=[1, 0], c=[1, 0])
    lopsided = _hits(a=[1, 1, 1, 1, 1], b=[0, 0], c=[0, 0])  # +5 -1 -1 = +3
    assert not beats(lopsided, simple)


def test_tie_goes_to_the_simpler() -> None:
    same = _hits(a=[1, 1], b=[0, 1])
    hits = {"learned": same, "weighted_ppr": same, "ppr": same}
    assert select_gpipe(hits) == "ppr"


def test_survivor_then_faces_plain_ppr() -> None:
    ppr = _hits(a=[0, 0], b=[0, 0], c=[0, 0], d=[0, 0])
    weighted = _hits(a=[1, 0], b=[1, 0], c=[1, 0], d=[0, 0])
    learned = _hits(a=[1, 0], b=[1, 0], c=[1, 0], d=[1, 0])  # +1 over weighted
    assert (
        select_gpipe({"learned": learned, "weighted_ppr": weighted, "ppr": ppr})
        == "weighted_ppr"
    )
    best = _hits(a=[1, 1], b=[1, 1], c=[1, 1], d=[1, 1])
    assert select_gpipe({"learned": best, "weighted_ppr": ppr, "ppr": ppr}) == "learned"


def test_cases_exclude_image_slow_load_and_count_79(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from helios.evaluation import trigger_calibration as tc

    order = json.loads((REPO / "data/otel/build_v3_manifest.json").read_text())[
        "case_order"
    ]
    labels: dict[str, dict[str, Any]] = {
        i: {
            "inject_time": 1_790_000_000,
            "root_cause_service": "cart",
            "fault": "cartFailure",
        }
        for i in order
    }
    monkeypatch.setattr(tc, "verify_ground_truth", lambda _p, _k: labels)
    cases = gc.load_gpipe_cases(root=REPO, key=b"k")
    assert len(cases) == 79
    assert not any(c.fault == "imageSlowLoad" for c in cases)
    earlier = [c for c in cases if c.stem]
    assert len(earlier) == 16
    assert {c.fault for c in earlier} <= {
        "adHighCpu",
        "cartFailure",
        "productCatalogFailure",
        "recommendationCacheFailure",
    }
