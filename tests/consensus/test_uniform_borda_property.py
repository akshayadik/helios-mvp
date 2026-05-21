"""Hypothesis property tests for UniformBordaConsensus."""

from __future__ import annotations

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from helios.consensus.uniform_borda import UniformBordaConsensus
from helios.consensus.verdict import ConsensusVerdict
from helios.vcl import (
    VCLFlag,  # noqa: F401 — flag-guard compliance
    set_current_manifest,
)

_NAMES = st.text(alphabet="abcdefghijklmnopqrstuvwxyz-", min_size=2, max_size=8)
_CANDIDATE_LIST = st.lists(_NAMES, min_size=1, max_size=5, unique=True)


def _build_rows(ranked_lists: list[list[str]]) -> list[dict]:
    pipes = ["d_pipe", "g_pipe", "l_pipe"]
    return [
        {"pipeline": p, "ranked_candidates": r, "narrative": "normal"}
        for p, r in zip(pipes, ranked_lists, strict=False)
    ]


@pytest.fixture(autouse=True)
def _set_full_manifest() -> None:
    """Inject HELIOS-Full manifest so @gated_by(VCLFlag.MAHC) passes."""
    from helios.vcl.variants import CONFIRMATORY_VARIANTS

    set_current_manifest(CONFIRMATORY_VARIANTS["HELIOS-Full"])


@given(
    ranked_lists=st.lists(_CANDIDATE_LIST, min_size=1, max_size=3),
)
@settings(max_examples=50)
def test_fuse_result_is_consensus_verdict(ranked_lists: list[list[str]]) -> None:
    borda = UniformBordaConsensus()
    rows = _build_rows(ranked_lists)
    result = borda.fuse(
        incident_id="otel-prop",
        variant="HELIOS-Full",
        pipeline_rows=rows,
        run_id="prop-run",
    )
    assert isinstance(result, ConsensusVerdict)


@given(
    ranked_lists=st.lists(_CANDIDATE_LIST, min_size=1, max_size=3),
)
@settings(max_examples=50)
def test_fuse_top_candidate_is_in_some_pipeline(ranked_lists: list[list[str]]) -> None:
    all_candidates = {c for lst in ranked_lists for c in lst}
    borda = UniformBordaConsensus()
    rows = _build_rows(ranked_lists)
    result = borda.fuse(
        incident_id="otel-prop",
        variant="HELIOS-Full",
        pipeline_rows=rows,
        run_id="prop-run",
    )
    assert result.top_candidates[0] in all_candidates


@given(
    candidates=st.lists(_NAMES, min_size=2, max_size=4, unique=True),
)
@settings(max_examples=30)
def test_fuse_is_deterministic_across_calls(candidates: list[str]) -> None:
    borda = UniformBordaConsensus()
    rows = _build_rows([candidates, list(reversed(candidates)), candidates])
    r1 = borda.fuse(
        incident_id="otel-det",
        variant="HELIOS-Full",
        pipeline_rows=rows,
        run_id="run-1",
    )
    r2 = borda.fuse(
        incident_id="otel-det",
        variant="HELIOS-Full",
        pipeline_rows=rows,
        run_id="run-1",
    )
    assert r1.top_candidates == r2.top_candidates


@given(
    ranked_lists=st.lists(_CANDIDATE_LIST, min_size=1, max_size=3),
)
@settings(max_examples=30)
def test_fuse_pipeline_row_count_matches_input(ranked_lists: list[list[str]]) -> None:
    borda = UniformBordaConsensus()
    rows = _build_rows(ranked_lists)
    result = borda.fuse(
        incident_id="otel-prop",
        variant="HELIOS-Full",
        pipeline_rows=rows,
        run_id="prop-run",
    )
    assert result.pipeline_row_count == len(rows)
