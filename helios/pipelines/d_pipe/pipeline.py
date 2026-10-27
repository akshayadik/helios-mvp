"""D-pipe entry point - orchestrates Stages A-D behind VCLFlag.DPIPE."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd

from helios.pipelines.d_pipe.dpipe_config import (
    RHO_THRESHOLD_DEFAULT,
    TOPOLOGY_BOOST_DEFAULT,
    W_ERROR_DEFAULT,
)
from helios.pipelines.d_pipe.stages.a_metrics_parser import MetricsParser, ParsedMetrics
from helios.pipelines.d_pipe.stages.b_anomaly_scorer import AnomalyScorer
from helios.pipelines.d_pipe.stages.c_propagation_engine import PropagationEngine
from helios.pipelines.d_pipe.stages.d_verdict import DVerdict
from helios.schemas.verdict import VerdictStatus, sigma_from_scores, top1_share
from helios.telemetry.scope import in_scope
from helios.vcl import VCLFlag, gated_by, get_current_manifest

__all__ = ["run_dpipe"]

if TYPE_CHECKING:
    from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
    from helios.schemas.ueg_c import UEGCSnapshot
    from helios.telemetry.trigger import TriggerRecord


@gated_by(VCLFlag.DPIPE)
def run_dpipe(
    *,
    window: TelemetryWindow,
    ueg_c: UEGCSnapshot | None,
    incident_id: str,
    snapshot_hash: str,
    variant_config_hash: str,
    evaluation_phase: EvaluationPhase,
    run_id: str,
    trigger: TriggerRecord | None = None,
    evidence_ref: float | None = None,
    w_error: float = W_ERROR_DEFAULT,
    w_resource: float = 0,
    rho_threshold: float = RHO_THRESHOLD_DEFAULT,
    topology_boost_factor: float = TOPOLOGY_BOOST_DEFAULT,
) -> dict[str, Any]:
    """Run D-pipe Stages A-D and return a verdict dict.

    ``trigger`` is the shared detection trigger (S2.1): with it, Stage B scores
    the shift after the trigger against the part before it and sigma is
    reported (``evidence_ref`` = the frozen trigger threshold). Out-of-scope
    services (D-f) are never ranked; their telemetry still informs the scores.
    """
    # Stage A: parse metrics
    if window.p1_metrics_path is not None:
        df = pd.read_parquet(window.p1_metrics_path)
        parsed = MetricsParser().parse(df)
    else:
        parsed = ParsedMetrics(
            error_deltas={}, latency_means={}, steps=[], p1_services=[]
        )

    # Stage B: anomaly scoring
    scorer = AnomalyScorer(w_error=w_error, w_resource=w_resource)
    evidence: dict[str, float] = {}
    if trigger is not None:
        scored = scorer.score_split(parsed, split_s=trigger.trigger_time_s)
        scores, evidence = scored.scores, scored.evidence
    else:
        scores = scorer.score(
            parsed.error_deltas, parsed.latency_means, parsed.p1_services
        )

    # Stage C: directional propagation (gated by DPIPE_PROPAGATION flag)
    manifest = get_current_manifest()
    assert manifest is not None  # guaranteed by @gated_by decorator
    if manifest.dpipe_propagation and ueg_c is not None:
        from helios.schemas.ueg_c import EdgeType

        engine = PropagationEngine(
            rho_threshold=rho_threshold,
            topology_boost_factor=topology_boost_factor,
        )
        # Propagate along calls between candidate services only (never onto KPI
        # or reasoning-step nodes). Under ueg_structural OFF the graph is
        # untyped, so every edge between two candidates counts.
        candidates = set(ueg_c.candidate_ids())
        call_edges = [
            e
            for e in ueg_c.edges
            if e.edge_type in (EdgeType.CALL, EdgeType.UNTYPED)
            and e.source in candidates
            and e.target in candidates
        ]
        score_final = engine.propagate(
            scores, parsed.error_deltas, call_edges, p1_services=parsed.p1_services
        )
    else:
        score_final = dict(scores)

    # Stage D: verdict over in-scope services only (D-f)
    score_final = {s: v for s, v in score_final.items() if in_scope(s)}
    verdict = DVerdict.compute(score_final)
    narrative_raw = verdict.get("narrative")
    narrative_norm: str = "" if narrative_raw is None else str(narrative_raw)

    return {
        **verdict,
        "narrative": narrative_norm,
        "incident_id": incident_id,
        "snapshot_hash": snapshot_hash,
        "variant_config_hash": variant_config_hash,
        "evaluation_phase": str(evaluation_phase),
        "run_id": run_id,
        "pipeline": "dpipe",
        "status": (
            VerdictStatus.RANKED
            if verdict["ranked_candidates"]
            else VerdictStatus.ABSTAINED
        ),
        "candidate_scores": score_final,
        # Label-free mu (top-1 share) and sigma (spread and evidence, S2.1).
        "mu": top1_share(score_final) if verdict["ranked_candidates"] else None,
        "sigma": (
            sigma_from_scores(score_final, evidence, evidence_ref=evidence_ref)
            if verdict["ranked_candidates"] and evidence and evidence_ref
            else None
        ),
    }
