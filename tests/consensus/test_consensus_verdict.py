"""Tests for helios.consensus.verdict — ConsensusVerdict schema and integrity gate."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

if TYPE_CHECKING:
    from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def test_consensus_verdict_valid_construction() -> None:
    from helios.consensus.verdict import ConsensusVerdict

    cv = ConsensusVerdict(
        incident_id="otel-001",
        variant="HELIOS-Full",
        top_candidates=["svc-a", "svc-b", "svc-c"],
        borda_scores={"svc-a": 2, "svc-b": 1, "svc-c": 0},
        candidate_universe_size=3,
        consensus_rank=3,
        fusion_algorithm="borda-v1",
        fusion_algorithm_sha="abc123",
        pipeline_row_count=3,
        run_id="run-001",
        timestamp_utc="2026-05-20T10:00:00Z",
    )
    assert cv.incident_id == "otel-001"
    assert cv.pipeline_row_count == 3
    assert cv.candidate_universe_size == 3


def test_consensus_verdict_cpr_defaults_to_zero() -> None:
    from helios.consensus.verdict import CPR_PENDING, ConsensusVerdict

    cv = ConsensusVerdict(
        incident_id="otel-001",
        variant="HELIOS-Full",
        top_candidates=["svc-a"],
        borda_scores={"svc-a": 2},
        candidate_universe_size=1,
        consensus_rank=1,
        fusion_algorithm="borda-v1",
        fusion_algorithm_sha="abc123",
        pipeline_row_count=3,
        run_id="run-001",
        timestamp_utc="2026-05-20T10:00:00Z",
    )
    assert cv.cpr == CPR_PENDING


def test_consensus_verdict_empty_candidates_rejected() -> None:
    from helios.consensus.verdict import ConsensusVerdict

    with pytest.raises(ValidationError):
        ConsensusVerdict(
            incident_id="otel-001",
            variant="HELIOS-Full",
            top_candidates=[],
            borda_scores={},
            candidate_universe_size=1,
            consensus_rank=0,
            fusion_algorithm="borda-v1",
            fusion_algorithm_sha="abc123",
            pipeline_row_count=3,
            run_id="run-001",
            timestamp_utc="2026-05-20T10:00:00Z",
        )


def test_consensus_integrity_gate_passes_matching_sha() -> None:
    from helios.consensus.verdict import ConsensusIntegrityGate, ConsensusVerdict

    sha = "deadbeef"
    cv = ConsensusVerdict(
        incident_id="otel-001",
        variant="HELIOS-Full",
        top_candidates=["svc-a"],
        borda_scores={"svc-a": 2},
        candidate_universe_size=1,
        consensus_rank=1,
        fusion_algorithm="borda-v1",
        fusion_algorithm_sha=sha,
        pipeline_row_count=3,
        run_id="run-001",
        timestamp_utc="2026-05-20T10:00:00Z",
    )
    gate = ConsensusIntegrityGate(expected_sha=sha)
    gate.check(cv)  # must not raise


def test_consensus_integrity_gate_raises_on_sha_mismatch() -> None:
    from helios.consensus.verdict import ConsensusIntegrityGate, ConsensusVerdict

    cv = ConsensusVerdict(
        incident_id="otel-001",
        variant="HELIOS-Full",
        top_candidates=["svc-a"],
        borda_scores={"svc-a": 2},
        candidate_universe_size=1,
        consensus_rank=1,
        fusion_algorithm="borda-v1",
        fusion_algorithm_sha="sha-stored",
        pipeline_row_count=3,
        run_id="run-001",
        timestamp_utc="2026-05-20T10:00:00Z",
    )
    gate = ConsensusIntegrityGate(expected_sha="sha-different")
    with pytest.raises(ValueError, match="fusion_algorithm_sha mismatch"):
        gate.check(cv)
