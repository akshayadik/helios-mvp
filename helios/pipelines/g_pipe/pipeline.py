"""G-pipe — conditional graph peer pipeline (§3.6.7, §3.4; S2.2 culprit vs victim).

Gated by VCLFlag.GPIPE. Entry gate: PPR disagreement >= DISAGREEMENT_THRESHOLD
(unchanged until the S3.1 router). The frozen parameters choose the ranker
(plain PPR, feature-weighted PPR or the learned ranker, S2.2 design §5.2);
plain PPR is used whenever the trace features cannot be computed (no traces,
no spans on both sides of the trigger) and under ``ueg_structural`` OFF
(HELIOS-noStructural, owner decision G-h). sigma and the per-suspect evidence come
from the features (design §5.4); without them sigma is None.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from helios.pipelines.g_pipe.features import FEATURE_COLUMNS, compute_features
from helios.pipelines.g_pipe.gpipe_config import DISAGREEMENT_THRESHOLD
from helios.pipelines.g_pipe.rankers import plain_ppr, weighted_ppr
from helios.schemas.ueg_c import UEGCSnapshot  # noqa: TCH001
from helios.schemas.verdict import VERDICT_SCHEMA_VERSION, VerdictStatus, top1_share
from helios.vcl import VCLFlag, gated_by
from helios.vcl.decorators import get_current_manifest

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from helios.pipelines.g_pipe.features import GraphFeatures
    from helios.pipelines.g_pipe.params import GPipeParams
    from helios.schemas.telemetry import TelemetryWindow
    from helios.telemetry.trigger import DetectorParams, TriggerRecord
    from helios.vcl.config import VCLManifest

__all__ = [
    "GPipeRanking",
    "compute_ppr_disagreement",
    "evidence_for",
    "gpipe_rank",
    "gpipe_sigma",
    "run_gpipe",
    "should_run_gpipe",
]
_DIGITS = 6
_EVIDENCE_KINDS = 3

HELIOS_ENABLE_GPIPE: bool = True


def compute_ppr_disagreement(ppr_scores: dict[str, float]) -> float:
    """Ratio of 3rd-ranked to top-ranked PPR score.

    Returns 0.00 when fewer than 3 candidates or top score is non-positive.
    Raises ValueError on any negative score — D-pipe PPR scores must be non-negative.
    """
    if any(v < 0.00 for v in ppr_scores.values()):
        raise ValueError(f"ppr_scores contains negative values: {ppr_scores}")
    if len(ppr_scores) < 3:
        return 0.00
    sorted_scores = sorted(ppr_scores.values(), reverse=True)
    top = sorted_scores[0]
    if top <= 0.00:
        return 0.00
    return sorted_scores[2] / top


def should_run_gpipe(dpipe_verdict: dict[str, Any], manifest: Any) -> bool:
    if not manifest.gpipe:
        return False
    if not manifest.l2b_graph:
        return False
    dpipe_scores = dpipe_verdict.get("candidate_scores", {})
    return compute_ppr_disagreement(dpipe_scores) >= DISAGREEMENT_THRESHOLD


def _ppr_traverse(
    snapshot: UEGCSnapshot,
    seed_weights: dict[str, float],
) -> tuple[list[str], dict[str, float]]:
    """Plain PPR (``rankers.plain_ppr``), ranked best first."""
    scores = plain_ppr(snapshot, seed_weights)
    ranked = sorted(scores, key=scores.__getitem__, reverse=True)
    return ranked, scores


@dataclass(frozen=True)
class GPipeRanking:
    """One window's G-pipe result before it becomes a verdict."""

    ranker: str
    scores: dict[str, float]
    ranked: list[str]
    sigma: float | None
    evidence: dict[str, Any]


def _softmax(scores: Mapping[str, float]) -> dict[str, float]:
    """Order-preserving map of learned scores onto non-negative shares (μ)."""
    top = max(scores.values())
    exp = {s: math.exp(v - top) for s, v in scores.items()}
    total = sum(exp.values())
    return {s: v / total for s, v in exp.items()}


def gpipe_sigma(
    scores: Mapping[str, float], features: GraphFeatures | None, top: str
) -> float | None:
    """sigma = 1 - gap * strength (design §5.4); None without features."""
    if features is None or top not in features.services or not scores:
        return None
    ordered = sorted(scores.values(), reverse=True)
    first = ordered[0]
    second = ordered[1] if len(ordered) > 1 else 0
    gap = (first - second) / first if first > 0 else 0
    row = features.table[features.services.index(top)]
    kinds = (
        row[FEATURE_COLUMNS.index("wait_pooled_rise")] > 0,
        top in features.leaders,
        row[FEATURE_COLUMNS.index("ghost_in")] > 0,
    )
    strength = sum(kinds) / _EVIDENCE_KINDS
    return float(round(min(max(1 - gap * strength, 0), 1), _DIGITS))


def evidence_for(
    features: GraphFeatures, ranked: Sequence[str], k: int = 3
) -> dict[str, Any]:
    """The graph facts behind each of the top ``k`` suspects (for L-pipe)."""
    suspects = []
    for service in [s for s in ranked if s in features.services][:k]:
        suspects.append(
            {
                "service": service,
                "wait_from": {
                    caller: round(share, _DIGITS)
                    for (caller, callee), share in sorted(
                        features.edge_wait_after.items()
                    )
                    if callee == service and share > 0
                },
                "leads": list(features.callers_led.get(service, ())),
                "ghost_edges": [
                    [a, b] for a, b in sorted(features.ghosts) if service in (a, b)
                ],
                "self_shift": round(features.self_shift.get(service, 0), _DIGITS),
            }
        )
    return {"suspects": suspects}


def gpipe_rank(
    snapshot: UEGCSnapshot,
    dpipe_scores: Mapping[str, float],
    *,
    manifest: VCLManifest,
    window: TelemetryWindow | None = None,
    trigger: TriggerRecord | None = None,
    params: GPipeParams | None = None,
    detector: DetectorParams | None = None,
    root: Path | None = None,
) -> GPipeRanking:
    """Rank one window with the frozen candidate (no routing gate)."""
    ppr = plain_ppr(snapshot, dpipe_scores)
    features = None
    if (
        manifest.ueg_structural
        and window is not None
        and trigger is not None
        and detector is not None
    ):
        features = compute_features(
            window,
            trigger,
            dpipe_scores,
            ppr,
            snapshot.candidate_ids(),
            detector,
            root=root,
        )
    ranker = params.ranker if params is not None else "ppr"
    if features is None or ranker == "ppr":
        ranker, scores = "ppr", ppr
    elif ranker == "weighted_ppr":
        scores = weighted_ppr(features, dpipe_scores)
    else:
        assert params is not None and params.model is not None
        scores = _softmax(params.model.score(features))
    ranked = sorted(scores, key=scores.__getitem__, reverse=True)
    return GPipeRanking(
        ranker=ranker,
        scores=scores,
        ranked=ranked,
        sigma=gpipe_sigma(scores, features, ranked[0]) if ranked else None,
        evidence=evidence_for(features, ranked) if features is not None else {},
    )


def _sentinel_verdict(
    incident_id: str,
    snapshot_hash: str,
    manifest: VCLManifest,
    evaluation_phase: str,
    run_id: str,
) -> dict[str, Any]:
    return {
        "pipeline": "gpipe",
        "incident_id": incident_id,
        "run_id": run_id,
        "variant_config_hash": manifest.compute_variant_config_hash(),
        "snapshot_hash": snapshot_hash,
        "status": VerdictStatus.SKIPPED,
        "ranked_candidates": [],
        "candidate_scores": {},
        "mu": None,
        "sigma": None,
        "latency_ms": 0.00,
        "narrative": "gpipe-gated-or-skipped",
        "evaluation_phase": evaluation_phase,
        "schema_version": VERDICT_SCHEMA_VERSION,
    }


def _build_gpipe_verdict(
    incident_id: str,
    snapshot_hash: str,
    manifest: VCLManifest,
    result: GPipeRanking,
    evaluation_phase: str,
    run_id: str,
    latency_ms: float = 0,
) -> dict[str, Any]:
    ranked = result.ranked
    return {
        "pipeline": "gpipe",
        "incident_id": incident_id,
        "run_id": run_id,
        "variant_config_hash": manifest.compute_variant_config_hash(),
        "snapshot_hash": snapshot_hash,
        "status": VerdictStatus.RANKED if ranked else VerdictStatus.ABSTAINED,
        "ranked_candidates": ranked,
        "candidate_scores": result.scores,
        # Label-free mu (top-1 share); sigma from the graph evidence (S2.2).
        "mu": top1_share(result.scores) if ranked else None,
        "sigma": result.sigma if ranked else None,
        "latency_ms": latency_ms,
        "narrative": "gpipe-traversal-complete",
        "evaluation_phase": evaluation_phase,
        "schema_version": VERDICT_SCHEMA_VERSION,
        "gpipe_ranker": result.ranker,
        "evidence": result.evidence,
    }


@gated_by(VCLFlag.GPIPE)
def run_gpipe(
    incident_id: str,
    snapshot: UEGCSnapshot,
    snapshot_hash: str,
    dpipe_scores: dict[str, float],
    evaluation_phase: str,
    run_id: str,
    *,
    window: TelemetryWindow | None = None,
    trigger: TriggerRecord | None = None,
    params: GPipeParams | None = None,
    detector: DetectorParams | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    manifest = get_current_manifest()
    assert manifest is not None
    disagreement = compute_ppr_disagreement(dpipe_scores)
    if disagreement < DISAGREEMENT_THRESHOLD:
        return _sentinel_verdict(
            incident_id, snapshot_hash, manifest, evaluation_phase, run_id
        )
    _start = time.monotonic()
    result = gpipe_rank(
        snapshot,
        dpipe_scores,
        manifest=manifest,
        window=window,
        trigger=trigger,
        params=params,
        detector=detector,
        root=root,
    )
    latency_ms = (time.monotonic() - _start) * 1000
    return _build_gpipe_verdict(
        incident_id,
        snapshot_hash,
        manifest,
        result,
        evaluation_phase,
        run_id,
        latency_ms=latency_ms,
    )
