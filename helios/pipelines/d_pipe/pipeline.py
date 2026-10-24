"""D-pipe entry point - orchestrates Stages A-D behind VCLFlag.DPIPE."""

from __future__ import annotations

import math
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
from helios.vcl import VCLFlag, gated_by, get_current_manifest

__all__ = ["run_dpipe"]

if TYPE_CHECKING:
    from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
    from helios.schemas.ueg_c import UEGCSnapshot


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
    w_error: float = W_ERROR_DEFAULT,
    rho_threshold: float = RHO_THRESHOLD_DEFAULT,
    topology_boost_factor: float = TOPOLOGY_BOOST_DEFAULT,
    ground_truth_service: str | None = None,
) -> dict[str, Any]:
    """Run D-pipe Stages A-D and return a verdict dict."""
    # Stage A: parse metrics
    if window.p1_metrics_path is not None:
        df = pd.read_parquet(window.p1_metrics_path)
        parsed = MetricsParser().parse(df)
    else:
        parsed = ParsedMetrics(
            error_deltas={}, latency_means={}, steps=[], p1_services=[]
        )

    # Stage B: anomaly scoring
    scorer = AnomalyScorer(w_error=w_error)
    scores = scorer.score(parsed.error_deltas, parsed.latency_means, parsed.p1_services)

    # Stage C: directional propagation (gated by DPIPE_PROPAGATION flag)
    manifest = get_current_manifest()
    assert manifest is not None  # guaranteed by @gated_by decorator
    if manifest.dpipe_propagation and ueg_c is not None:
        from helios.schemas.ueg_c import EdgeType

        engine = PropagationEngine(
            rho_threshold=rho_threshold,
            topology_boost_factor=topology_boost_factor,
        )
        call_edges = [e for e in ueg_c.edges if e.edge_type == EdgeType.CALL]
        score_final = engine.propagate(
            scores, parsed.error_deltas, call_edges, p1_services=parsed.p1_services
        )
    else:
        score_final = dict(scores)

    # Stage D: verdict
    verdict = DVerdict.compute(score_final, ground_truth_service=ground_truth_service)

    # Normalise for PipelineVerdict schema: mrr must be in [0, 1]; narrative must be str.
    mrr_raw = verdict.get("mrr", float("nan"))
    mrr_norm: float = (
        0.00 if (mrr_raw is None or math.isnan(mrr_raw)) else float(mrr_raw)
    )
    narrative_raw = verdict.get("narrative")
    narrative_norm: str = "" if narrative_raw is None else str(narrative_raw)

    return {
        **verdict,
        "mrr": mrr_norm,
        "narrative": narrative_norm,
        "incident_id": incident_id,
        "snapshot_hash": snapshot_hash,
        "variant_config_hash": variant_config_hash,
        "evaluation_phase": str(evaluation_phase),
        "run_id": run_id,
        "pipeline": "dpipe",
        "latency_ms": 0.00,
        "token_count": 0,
        "ppr_scores": score_final,
    }
