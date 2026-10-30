"""MAHC weighted fusion and vote-only (S2.5 design §5.3, §5.6; M-d)."""

from __future__ import annotations

import pytest

from helios.consensus.mahc import MAHC_EPSILON, Vote, fuse, votes_from
from helios.consensus.vote_only import vote_only
from helios.schemas.verdict import PipelineName, PipelineVerdict, VerdictStatus
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

EQUAL = {"dpipe": 1, "gpipe": 1, "lpipe": 1}


def _v(pipeline: str, ranked: list[str], sigma: float | None) -> Vote:
    return Vote(pipeline, tuple(ranked), 1 if sigma is None else sigma)


def test_ch3_counterexample_same_ranking_different_sigma() -> None:
    sure = fuse([_v(p, ["a", "b"], 0.1) for p in EQUAL], EQUAL)
    unsure = fuse([_v(p, ["a", "b"], 0.8) for p in EQUAL], EQUAL)
    assert sure.ranked == unsure.ranked == ("a", "b")
    assert sure.scores == pytest.approx(unsure.scores)
    assert sure.fused_sigma == pytest.approx(0.1)
    assert unsure.fused_sigma == pytest.approx(0.8)


def test_disagreement_counterexample() -> None:
    votes = [
        _v("dpipe", ["a", "b"], 0.8),
        _v("lpipe", ["a", "b"], 0.8),
        _v("gpipe", ["b", "a"], 0.1),
    ]
    assert fuse(votes, EQUAL).ranked[0] == "b"
    plain = vote_only(votes)
    assert plain.ranked[0] == "a"
    assert plain.scores == pytest.approx({"a": 2.5, "b": 2})
    assert plain.fused_sigma is None


def test_weights_follow_prior_over_variance() -> None:
    f = fuse(
        [_v("dpipe", ["a"], 0.5 + 0.1), _v("gpipe", ["b"], 0.6)],
        {"dpipe": 0.9, "gpipe": 0.3},
    )
    assert f.weights["dpipe"] / f.weights["gpipe"] == pytest.approx(3)
    assert sum(f.weights.values()) == pytest.approx(1)


def test_zero_sigma_uses_epsilon() -> None:
    f = fuse([_v("dpipe", ["a"], 0), _v("gpipe", ["b"], 1)], EQUAL)
    # weights are stored rounded to 6 digits
    assert f.weights["dpipe"] / f.weights["gpipe"] == pytest.approx(
        (1 + MAHC_EPSILON) / MAHC_EPSILON, rel=1e-3
    )


def test_single_vote() -> None:
    f = fuse([_v("dpipe", ["a", "b", "c"], 0.4)], EQUAL)
    assert f.ranked == ("a", "b", "c")
    assert f.fused_sigma == pytest.approx(0.4)
    assert f.contributing == ("dpipe",)
    assert f.top1s_agree


def test_no_votes() -> None:
    f = fuse([], EQUAL)
    assert f.ranked == () and f.fused_sigma is None and f.contributing == ()


def test_ties_by_name() -> None:
    f = fuse([_v("dpipe", ["b"], 0.3), _v("gpipe", ["a"], 0.3)], EQUAL)
    assert f.ranked == ("a", "b")
    assert not f.top1s_agree


def _verdict(
    pipeline: PipelineName,
    status: VerdictStatus,
    ranked: list[str],
    sigma: float | None,
) -> PipelineVerdict:
    return PipelineVerdict(
        run_id="r",
        incident_id="i",
        variant_config_hash="h",
        snapshot_hash="s",
        pipeline=pipeline,
        evaluation_phase="exploratory",
        status=status,
        ranked_candidates=ranked,
        sigma=sigma,
        mu=None if not ranked else 1,
        latency_ms=1,
    )


def test_votes_from_keeps_ranked_lists_only() -> None:
    votes = votes_from(
        [
            _verdict(
                PipelineName.DPIPE, VerdictStatus.RANKED, ["cart", "jaeger"], None
            ),
            _verdict(PipelineName.GPIPE, VerdictStatus.SKIPPED, [], None),
            _verdict(PipelineName.LPIPE, VerdictStatus.ABSTAINED, [], None),
        ]
    )
    assert votes == [Vote("dpipe", ("cart",), 1)]
