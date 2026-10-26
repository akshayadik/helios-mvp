"""Scoring path (S1.9): fixture scores against hand-computed values."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import TYPE_CHECKING

import pytest

from helios.consensus.verdict import ConsensusVerdict
from helios.evaluation.scoring import (
    SCORING_VERSION,
    Corpus,
    GroundTruth,
    avg_at_k,
    hr_at,
    load_ground_truth,
    mean_scores,
    rank_of,
    reciprocal_rank,
    score_ranking,
    score_store,
    service_key,
)
from helios.schemas.telemetry import EvaluationPhase
from helios.schemas.verdict import PipelineName, PipelineVerdict, VerdictStatus
from helios.store.result_store import ResultStore
from helios.telemetry.pool_lock import PoolLockedError
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path

KEY = b"k" * 32
TWELVE = [f"s{i:02d}" for i in range(1, 13)]


# ── metrics, by hand ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("ranked", "truth", "rank", "hr1", "hr3", "hr10", "avg5", "mrr"),
    [
        # first place: every score is full
        (["a", "b", "c"], "a", 1, 1, 1, 1, 1, 1),
        # second place: Avg@5 = (0 + 1 + 1 + 1 + 1) / 5
        (["b", "a", "c"], "a", 2, 0, 1, 1, 4 / 5, 1 / 2),
        # fourth place: HR@3 misses; Avg@5 = (0 + 0 + 0 + 1 + 1) / 5
        (["b", "c", "d", "a"], "a", 4, 0, 0, 1, 2 / 5, 1 / 4),
        # seventh of twelve: only HR@10 hits; Avg@5 = 0
        (TWELVE, "s07", 7, 0, 0, 1, 0, 1 / 7),
        # eleventh of twelve: beyond HR@10
        (TWELVE, "s11", 11, 0, 0, 0, 0, 1 / 11),
        # absent: every score is zero (MRR 0, metric contract §2)
        (["b", "c"], "a", None, 0, 0, 0, 0, 0),
        # empty list (abstained or failed pipeline)
        ([], "a", None, 0, 0, 0, 0, 0),
    ],
)
def test_scores_match_hand_computation(
    ranked: list[str],
    truth: str,
    rank: int | None,
    hr1: int,
    hr3: int,
    hr10: int,
    avg5: float,
    mrr: float,
) -> None:
    case = score_ranking(ranked, truth)
    assert case.rank == rank
    assert (case.hr_at_1, case.hr_at_3, case.hr_at_10) == (hr1, hr3, hr10)
    assert case.avg_at_5 == pytest.approx(avg5)
    assert case.mrr == pytest.approx(mrr)


def test_metric_helpers() -> None:
    assert rank_of(["x", "y"], "y") == 2
    assert hr_at(3, 3) == 1
    assert hr_at(4, 3) == 0
    assert hr_at(None, 10) == 0
    assert avg_at_k(1) == 1
    assert avg_at_k(3, k=3) == pytest.approx(1 / 3)
    assert reciprocal_rank(None) == 0
    with pytest.raises(ValueError, match="k must be"):
        hr_at(1, 0)


def test_stem_matching_is_for_otel_labels_only() -> None:
    assert service_key("adService") == service_key("ad") == "ad"
    assert service_key("product-catalog") == service_key("productCatalogService")
    assert service_key("service") == "service"
    assert rank_of(["cart", "ad"], "adService", stem=True) == 2
    assert rank_of(["cart", "ad"], "adService") is None  # exact by default


# ── ground truth ─────────────────────────────────────────────────────────────


def _signed_truth(root: Path, corpus: str, labels: dict[str, str]) -> Path:
    body = {
        "kind": "rcaeval-ground-truth",
        "corpus": corpus,
        "cases": {k: {"root_cause_service": v} for k, v in labels.items()},
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    signature = hmac.new(KEY, canonical, hashlib.sha256).hexdigest()
    path = root / "data" / "rcaeval" / f"ground_truth_{corpus}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**body, "signature": signature}), encoding="utf-8")
    return path


def test_build_ground_truth_verifies_and_matches_exactly(tmp_path: Path) -> None:
    path = _signed_truth(tmp_path, "build", {"rc-1": "cart"})
    gt = load_ground_truth("build", root=tmp_path, key=KEY)
    assert gt.corpus == Corpus.BUILD
    assert gt.labels == {"rc-1": "cart"}
    assert not gt.stem
    assert gt.digest == hashlib.sha256(path.read_bytes()).hexdigest()


def test_altered_or_unkeyed_ground_truth_is_refused(tmp_path: Path) -> None:
    path = _signed_truth(tmp_path, "build", {"rc-1": "cart"})
    with pytest.raises(ValueError, match="a key is needed"):
        load_ground_truth("build", root=tmp_path)
    path.write_text(path.read_text().replace("cart", "frontend"), encoding="utf-8")
    with pytest.raises(ValueError, match="does not verify"):
        load_ground_truth("build", root=tmp_path, key=KEY)


def test_pool_ground_truth_is_locked_until_build_freeze(tmp_path: Path) -> None:
    _signed_truth(tmp_path, "pool", {"rc-9": "cart"})
    with pytest.raises(PoolLockedError, match="build-freeze"):
        load_ground_truth("pool", root=tmp_path, key=KEY, frozen=lambda: False)
    gt = load_ground_truth("pool", root=tmp_path, key=KEY, frozen=lambda: True)
    assert gt.labels == {"rc-9": "cart"}


def test_capture_ground_truth_matches_by_stem(tmp_path: Path) -> None:
    path = tmp_path / "data" / "ground_truth.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"s0-ad-001": {"root_cause_service": "adService"}}))
    gt = load_ground_truth(Corpus.CAPTURES, root=tmp_path)
    assert gt.stem
    case = gt.score("s0-ad-001", ["cart", "ad"])
    assert case is not None
    assert case.rank == 2
    assert gt.score("unknown-case", ["ad"]) is None


# ── scoring stored runs ──────────────────────────────────────────────────────


def _verdict(
    run_id: str,
    incident_id: str,
    pipeline: PipelineName,
    ranked: list[str],
    status: VerdictStatus = VerdictStatus.RANKED,
    phase: EvaluationPhase = EvaluationPhase.EXPLORATORY,
) -> PipelineVerdict:
    return PipelineVerdict(
        run_id=run_id,
        incident_id=incident_id,
        variant_config_hash="a" * 64,
        snapshot_hash="b" * 64,
        pipeline=pipeline,
        evaluation_phase=phase,
        status=status,
        ranked_candidates=ranked,
        latency_ms=1,
    )


def _consensus(run_id: str, incident_id: str, ranked: list[str]) -> ConsensusVerdict:
    return ConsensusVerdict(
        incident_id=incident_id,
        variant="HELIOS-Full",
        top_candidates=ranked,
        borda_scores={c: float(len(ranked) - i) for i, c in enumerate(ranked)},
        candidate_universe_size=len(ranked),
        consensus_rank=len(ranked),
        fusion_algorithm="borda-v1",
        fusion_algorithm_sha="abc",
        pipeline_row_count=3,
        run_id=run_id,
        timestamp_utc="2026-10-26T10:00:00Z",
    )


GT = GroundTruth(
    corpus=Corpus.BUILD,
    labels={"inc-1": "cart", "inc-2": "payment"},
    digest="d" * 64,
    stem=False,
)


def _store(tmp_path: Path) -> ResultStore:
    store = ResultStore(tmp_path / "results.duckdb")
    store.insert(_verdict("r1", "inc-1", PipelineName.DPIPE, ["ad", "cart", "email"]))
    store.insert(
        _verdict("r1", "inc-1", PipelineName.GPIPE, [], status=VerdictStatus.SKIPPED)
    )
    store.insert(
        _verdict("r1", "inc-1", PipelineName.LPIPE, [], status=VerdictStatus.FAILED)
    )
    store.insert(_verdict("r2", "inc-2", PipelineName.DPIPE, ["cart", "ad"]))
    store.insert(_verdict("r3", "inc-3", PipelineName.DPIPE, ["cart"]))  # no label
    store.insert_consensus(_consensus("r1", "inc-1", ["cart", "ad", "email"]))
    return store


def test_score_store_matches_hand_computation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    report = score_store(store, GT, frozen=lambda: False)
    assert (report.scored, report.skipped_pipelines, report.unlabelled) == (4, 1, 1)

    rows = {(r["run_id"], r["list_kind"], r["source"]): r for r in store.fetch_scores()}
    fused = rows["r1", "fused", "HELIOS-Full"]
    assert (fused["ground_truth_rank"], fused["hr_at_1"], fused["mrr"]) == (1, 1, 1)
    d1 = rows["r1", "pipeline", "dpipe"]
    assert (d1["ground_truth_rank"], d1["hr_at_1"], d1["hr_at_3"]) == (2, 0, 1)
    assert d1["avg_at_5"] == pytest.approx(4 / 5)
    assert d1["mrr"] == pytest.approx(1 / 2)
    failed = rows["r1", "pipeline", "lpipe"]
    assert failed["source_status"] == "failed"
    assert (failed["ground_truth_rank"], failed["hr_at_10"], failed["mrr"]) == (
        None,
        0,
        0,
    )
    absent = rows["r2", "pipeline", "dpipe"]
    assert (absent["ground_truth_rank"], absent["hr_at_3"]) == (None, 0)
    assert ("r1", "pipeline", "gpipe") not in rows  # skipped: not dispatched
    assert all(r["scoring_version"] == SCORING_VERSION for r in rows.values())
    assert all(r["ground_truth_sha256"] == "d" * 64 for r in rows.values())
    # The label is never stored, only its rank.
    assert not any("root_cause" in column for column in fused)
    assert mean_scores(store.fetch_scores())["hr_at_3"] == pytest.approx(2 / 4)


def test_rescoring_replaces_rows(tmp_path: Path) -> None:
    store = _store(tmp_path)
    score_store(store, GT, frozen=lambda: False)
    score_store(store, GT, frozen=lambda: False)
    assert len(store.fetch_scores()) == 4
    assert mean_scores([]) == {}


def test_confirmatory_runs_are_scored_only_after_build_freeze(tmp_path: Path) -> None:
    store = ResultStore(tmp_path / "results.duckdb")
    store.insert(
        _verdict(
            "r1",
            "inc-1",
            PipelineName.DPIPE,
            ["cart"],
            phase=EvaluationPhase.CONFIRMATORY,
        )
    )
    with pytest.raises(PoolLockedError, match="build-freeze"):
        score_store(store, GT, frozen=lambda: False)
    assert score_store(store, GT, frozen=lambda: True).scored == 1
