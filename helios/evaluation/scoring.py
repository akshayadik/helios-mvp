"""Scoring path (S1.9): accuracy scores computed after dispatch, never by a pipeline.

Definitions are the metric contract's (docs/tracking/metric_contract.md §2):

- HR@k: 1 if the ground-truth root-cause service is among the top k of a
  ranked list, else 0; k ∈ {1, 3, 10}.
- Avg@5: (1/5) · Σ_{j=1..5} HR@j (RCAEval's Avg@k).
- MRR: 1 / (rank of the ground-truth service); 0 if it is absent.

Scores are computed for the fused list a variant publishes (the measurement
point) and, for diagnostics, for each pipeline's own list. They are read from
stored outputs (``result_row``, ``consensus_verdict``) joined to the ground
truth and written to their own table (``eval_score``); nothing here is called
while a pipeline runs, and no pipeline accepts ground truth
(tests/evaluation/test_no_ground_truth_leak.py).

Ground truth: the RCAEval files are HMAC-signed by the importer and verified
here; their labels are already canonical service names (helios.adapters.names),
so they match exactly. The OTel Demo captures (exploratory) label services
``adService`` where the graph says ``ad``; they match by service stem. The
confirmatory pool's ground truth is refused until tag build-freeze (D11).
Scores never store the label itself, only the rank it was found at and the
digest of the ground-truth file.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from helios.adapters.rcaeval import verify_ground_truth
from helios.telemetry.pool_lock import BUILD_FREEZE_TAG, PoolLockedError, build_frozen
from helios.telemetry.scope import filter_in_scope, in_scope
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence
    from pathlib import Path

    from helios.store.result_store import ResultStore

__all__ = [
    "AVG_K",
    "HR_KS",
    "SCORING_VERSION",
    "CaseScore",
    "Corpus",
    "GroundTruth",
    "ListKind",
    "OutOfScopeLabelError",
    "ScoringReport",
    "avg_at_k",
    "hr_at",
    "load_ground_truth",
    "mean_scores",
    "rank_of",
    "reciprocal_rank",
    "score_ranking",
    "score_store",
    "service_key",
]

HELIOS_ENABLE_SCORING: bool = True

SCORING_VERSION = "scoring-v2"  # v2: out-of-scope services dropped (S2.1, D-f)
HR_KS: tuple[int, ...] = (1, 3, 10)
AVG_K = 5

GROUND_TRUTH_FILES: dict[str, str] = {
    "build": "data/rcaeval/ground_truth_build.json",
    "pool": "data/rcaeval/ground_truth_pool.json",
    "captures": "data/ground_truth.json",
    "otel_build": "data/otel/ground_truth_build.json",
    "otel_build_v2": "data/otel/ground_truth_build_v2.json",
    "otel_build_v3": "data/otel/ground_truth_build_v3.json",
}


class Corpus(StrEnum):
    """Which ground truth a run is scored against."""

    BUILD = "build"  # RCAEval build/calibration corpus (signed)
    POOL = "pool"  # RCAEval confirmatory pool (signed; locked until build-freeze)
    CAPTURES = "captures"  # OTel Demo captures (exploratory)
    OTEL_BUILD = "otel_build"  # OTel Demo build captures (S1.2; signed)
    OTEL_BUILD_V2 = "otel_build_v2"  # recapture, varied normal period (S2.1; signed)
    OTEL_BUILD_V3 = "otel_build_v3"  # attributed logs, span metrics, 25 users (signed)


class ListKind(StrEnum):
    """Whose ranked list a score belongs to."""

    FUSED = "fused"  # the list a variant publishes (the measurement point)
    PIPELINE = "pipeline"  # one pipeline's own list (diagnostics)


# ── metrics ──────────────────────────────────────────────────────────────────


def service_key(name: str) -> str:
    """Service stem for loose matching: OTel labels say ``adService``, nodes ``ad``."""
    key = "".join(ch for ch in name.lower() if ch.isalnum())
    return key.removesuffix("service") or key


def rank_of(ranked: Sequence[str], truth: str, *, stem: bool = False) -> int | None:
    """1-based rank of ``truth`` in ``ranked``, or None when it is absent."""
    if stem:
        target = service_key(truth)
        ranked = [service_key(c) for c in ranked]
        truth = target
    for position, candidate in enumerate(ranked, start=1):
        if candidate == truth:
            return position
    return None


def hr_at(rank: int | None, k: int) -> int:
    """HR@k of one case from the ground-truth rank."""
    if k < 1:
        raise ValueError("k must be >= 1")
    return int(rank is not None and rank <= k)


def avg_at_k(rank: int | None, k: int = AVG_K) -> float:
    """RCAEval Avg@k = (1/k) · Σ_{j=1..k} HR@j."""
    return sum(hr_at(rank, j) for j in range(1, k + 1)) / k


def reciprocal_rank(rank: int | None) -> float:
    """1 / rank, or 0 when the ground truth is absent."""
    return 0 if rank is None else 1 / rank


class OutOfScopeLabelError(ValueError):
    """A ground-truth label names an out-of-scope service (never injected; D-f)."""


@dataclass(frozen=True)
class CaseScore:
    """Scores of one ranked list for one case."""

    rank: int | None
    hr_at_1: int
    hr_at_3: int
    hr_at_10: int
    avg_at_5: float
    mrr: float


def score_ranking(
    ranked: Sequence[str], truth: str, *, stem: bool = False
) -> CaseScore:
    """Every contract accuracy score of one ranked list.

    Out-of-scope services (helios.telemetry.scope, D-f) are dropped from the
    list first, for every system alike; a label on that list is refused.
    """
    if not in_scope(truth):
        raise OutOfScopeLabelError("ground-truth label is an out-of-scope service")
    rank = rank_of(filter_in_scope(ranked), truth, stem=stem)
    hr1, hr3, hr10 = (hr_at(rank, k) for k in HR_KS)
    return CaseScore(
        rank=rank,
        hr_at_1=hr1,
        hr_at_3=hr3,
        hr_at_10=hr10,
        avg_at_5=avg_at_k(rank),
        mrr=reciprocal_rank(rank),
    )


# ── ground truth ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GroundTruth:
    """Root-cause labels of one corpus; ``digest`` identifies the file scored against."""

    corpus: Corpus
    labels: Mapping[str, str]
    digest: str
    stem: bool

    def score(self, incident_id: str, ranked: Sequence[str]) -> CaseScore | None:
        """Scores of ``ranked`` for one case, or None if the case has no label."""
        truth = self.labels.get(incident_id)
        if truth is None:
            return None
        return score_ranking(ranked, truth, stem=self.stem)


def load_ground_truth(
    corpus: Corpus | str,
    *,
    root: Path,
    key: bytes | None = None,
    frozen: Callable[[], bool] = build_frozen,
) -> GroundTruth:
    """Load a corpus' ground truth; RCAEval files must verify with ``key``.

    The pool's labels are refused until tag build-freeze exists.
    """
    corpus = Corpus(corpus)
    path = root / GROUND_TRUTH_FILES[corpus.value]
    if corpus == Corpus.POOL and not frozen():
        raise PoolLockedError(
            f"the confirmatory ground truth stays locked until tag {BUILD_FREEZE_TAG!r}"
        )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if corpus == Corpus.CAPTURES:
        raw = json.loads(path.read_text(encoding="utf-8"))
        labels = {k: str(v["root_cause_service"]) for k, v in raw.items()}
        return GroundTruth(corpus, labels, digest, stem=True)
    if key is None:
        raise ValueError(f"the {corpus.value} ground truth is signed; a key is needed")
    cases = verify_ground_truth(path, key)
    labels = {k: str(v["root_cause_service"]) for k, v in cases.items()}
    return GroundTruth(corpus, labels, digest, stem=False)


# ── scoring stored runs ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class ScoringReport:
    """What one scoring pass did (counts only, no labels)."""

    scored: int
    skipped_pipelines: int
    unlabelled: int
    rows: tuple[dict[str, Any], ...]


def _score_row(
    gt: GroundTruth,
    *,
    run_id: str,
    incident_id: str,
    list_kind: ListKind,
    source: str,
    source_status: str,
    ranked: Sequence[str],
    variant_config_hash: str | None,
) -> dict[str, Any] | None:
    case = gt.score(incident_id, ranked)
    if case is None:
        return None
    return {
        "run_id": run_id,
        "incident_id": incident_id,
        "variant_config_hash": variant_config_hash,
        "list_kind": list_kind.value,
        "source": source,
        "source_status": source_status,
        "list_length": len(ranked),
        "ground_truth_rank": case.rank,
        "hr_at_1": case.hr_at_1,
        "hr_at_3": case.hr_at_3,
        "hr_at_10": case.hr_at_10,
        "avg_at_5": case.avg_at_5,
        "mrr": case.mrr,
        "corpus": gt.corpus.value,
        "ground_truth_sha256": gt.digest,
        "scoring_version": SCORING_VERSION,
    }


def _ranked(value: object) -> list[str]:
    if isinstance(value, str):
        value = json.loads(value)
    return [str(c) for c in value] if isinstance(value, list) else []


def score_store(
    store: ResultStore,
    gt: GroundTruth,
    *,
    frozen: Callable[[], bool] = build_frozen,
) -> ScoringReport:
    """Score every stored pipeline and fused list against ``gt`` into eval_score.

    A skipped pipeline (gated off or not dispatched) produced no list and is
    not scored; abstained and failed pipelines are scored as misses, with
    their status kept so analysis can filter them. Cases without a label are
    counted, never imputed. Re-scoring replaces the earlier rows.
    """
    pipeline_rows = store.fetch_all_pipeline_rows()
    if not frozen() and any(
        r.get("evaluation_phase") == "confirmatory" for r in pipeline_rows
    ):
        raise PoolLockedError(
            f"confirmatory runs are scored only after tag {BUILD_FREEZE_TAG!r}"
        )
    rows: list[dict[str, Any]] = []
    skipped = unlabelled = 0
    for r in pipeline_rows:
        if r.get("status") == "skipped":
            skipped += 1
            continue
        row = _score_row(
            gt,
            run_id=str(r["run_id"]),
            incident_id=str(r["incident_id"]),
            list_kind=ListKind.PIPELINE,
            source=str(r["pipeline"]),
            source_status=str(r["status"]),
            ranked=_ranked(r["ranked_candidates"]),
            variant_config_hash=str(r["variant_config_hash"]),
        )
        unlabelled += row is None
        rows.extend([row] if row is not None else [])
    for c in store.fetch_all_consensus_rows():
        row = _score_row(
            gt,
            run_id=str(c["run_id"]),
            incident_id=str(c["incident_id"]),
            list_kind=ListKind.FUSED,
            source=str(c["variant"]),
            source_status="fused",
            ranked=_ranked(c["top_candidates"]),
            variant_config_hash=None,
        )
        unlabelled += row is None
        rows.extend([row] if row is not None else [])
    store.replace_scores(rows)
    return ScoringReport(
        scored=len(rows),
        skipped_pipelines=skipped,
        unlabelled=unlabelled,
        rows=tuple(rows),
    )


def mean_scores(rows: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    """Per-list means of the contract scores (for reports; counts only)."""
    rows = list(rows)
    if not rows:
        return {}
    keys = ("hr_at_1", "hr_at_3", "hr_at_10", "avg_at_5", "mrr")
    return {k: sum(float(r[k]) for r in rows) / len(rows) for k in keys}
