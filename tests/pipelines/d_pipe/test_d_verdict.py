"""TDD for Stage D DVerdict."""

from __future__ import annotations

import pytest

from helios.pipelines.d_pipe.stages.d_verdict import DVerdict


def test_ranking_is_score_descending() -> None:
    scores = {"svc-a": 0.9, "svc-b": 0.8, "svc-c": 0.3}
    assert DVerdict.compute(scores)["ranked_candidates"] == ["svc-a", "svc-b", "svc-c"]


def test_stage_d_takes_no_ground_truth() -> None:
    # S1.9: accuracy is scored after dispatch, never inside a pipeline.
    with pytest.raises(TypeError):
        DVerdict.compute({"a": 0.9}, ground_truth_service="a")  # type: ignore[call-arg]
    assert not {"hr_at_3", "mrr"} & set(DVerdict.compute({"a": 0.9}))


def test_alphabetic_tiebreak_is_deterministic() -> None:
    scores = {"bravo": 0.50, "alpha": 0.50}
    r1 = DVerdict.compute(scores)
    r2 = DVerdict.compute(scores)
    assert r1["ranked_candidates"] == r2["ranked_candidates"]
    assert r1["ranked_candidates"][0] == "alpha"  # alphabetically first


def test_ranked_candidates_cover_every_scored_service() -> None:
    # S1.8: the full ranking (HR@10, Avg@5 and MRR need more than the top 3).
    scores = {c: float(i) for i, c in enumerate("abcdefg")}
    result = DVerdict.compute(scores)
    assert result["ranked_candidates"] == list("gfedcba")
