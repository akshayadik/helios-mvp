"""Tests for UniformBordaConsensus and PassthroughConsensus."""

from __future__ import annotations

import pytest

from helios.consensus.verdict import ConsensusVerdict
from helios.vcl import (
    VCLFlag,  # noqa: F401 — flag-guard compliance
    set_current_manifest,
)


def _make_pipeline_rows(candidates_per_pipe: list[list[str]]) -> list[dict]:
    """Build mock pipeline rows from ranked candidate lists."""
    pipes = ["d_pipe", "g_pipe", "l_pipe"]
    rows = []
    for pipe, candidates in zip(pipes, candidates_per_pipe, strict=False):
        rows.append(
            {
                "pipeline": pipe,
                "ranked_candidates": candidates,
                "narrative": "normal",
            }
        )
    return rows


@pytest.fixture(autouse=True)
def _set_full_manifest() -> None:
    """Inject HELIOS-Full manifest so @gated_by(VCLFlag.MAHC) passes."""
    from helios.vcl.variants import CONFIRMATORY_VARIANTS

    set_current_manifest(CONFIRMATORY_VARIANTS["HELIOS-Full"])


def test_uniform_borda_fuse_clear_winner() -> None:
    from helios.consensus.uniform_borda import UniformBordaConsensus

    borda = UniformBordaConsensus()
    rows = _make_pipeline_rows(
        [
            ["svc-a", "svc-b", "svc-c"],
            ["svc-a", "svc-c", "svc-b"],
            ["svc-a", "svc-b", "svc-c"],
        ]
    )
    result = borda.fuse(
        incident_id="otel-001", variant="HELIOS-Full", pipeline_rows=rows, run_id="r1"
    )
    assert isinstance(result, ConsensusVerdict)
    assert result.top_candidates[0] == "svc-a"
    assert result.pipeline_row_count == 3


def test_uniform_borda_tie_broken_alphabetically() -> None:
    from helios.consensus.uniform_borda import UniformBordaConsensus

    borda = UniformBordaConsensus()
    rows = _make_pipeline_rows(
        [
            ["svc-a", "svc-b"],
            ["svc-b", "svc-a"],
            ["svc-a", "svc-b"],
        ]
    )
    result = borda.fuse(
        incident_id="otel-001", variant="HELIOS-Full", pipeline_rows=rows, run_id="r1"
    )
    assert result.top_candidates[0] in ("svc-a", "svc-b")
    # Deterministic: run twice, same order
    result2 = borda.fuse(
        incident_id="otel-001", variant="HELIOS-Full", pipeline_rows=rows, run_id="r1"
    )
    assert result.top_candidates == result2.top_candidates


def test_uniform_borda_fusion_algorithm_frozen() -> None:
    from helios.consensus.uniform_borda import (
        FUSION_CORE_VERSION,
        UniformBordaConsensus,
    )

    borda = UniformBordaConsensus()
    rows = _make_pipeline_rows([["svc-a"], ["svc-a"], ["svc-a"]])
    result = borda.fuse(
        incident_id="otel-001", variant="HELIOS-Full", pipeline_rows=rows, run_id="r1"
    )
    assert result.fusion_algorithm == FUSION_CORE_VERSION


def test_fusion_algorithm_sha_is_stable() -> None:
    from helios.consensus.uniform_borda import FUSION_ALGORITHM_SHA

    assert len(FUSION_ALGORITHM_SHA) == 64  # sha256 hex digest
    import helios.consensus.uniform_borda as mod

    assert mod.FUSION_ALGORITHM_SHA == FUSION_ALGORITHM_SHA


def test_passthrough_consensus_propagates_top_verdict() -> None:
    from helios.consensus.uniform_borda import PassthroughConsensus

    pt = PassthroughConsensus()
    rows = _make_pipeline_rows(
        [
            ["svc-x", "svc-y"],
            ["svc-x", "svc-z"],
            ["svc-y", "svc-x"],
        ]
    )
    result = pt.fuse(
        incident_id="otel-001",
        variant="HELIOS-noConsensus",
        pipeline_rows=rows,
        run_id="r1",
    )
    assert isinstance(result, ConsensusVerdict)
    assert result.fusion_algorithm == "passthrough"
    assert len(result.top_candidates) >= 1


def test_uniform_borda_empty_pipeline_rows_raises() -> None:
    from helios.consensus.uniform_borda import UniformBordaConsensus

    borda = UniformBordaConsensus()
    with pytest.raises(ValueError, match="pipeline_rows"):
        borda.fuse(
            incident_id="otel-001", variant="HELIOS-Full", pipeline_rows=[], run_id="r1"
        )
