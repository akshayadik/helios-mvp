"""G-pipe — conditional PPR-traversal peer pipeline (§3.6.7, §3.4).

Gated by VCLFlag.GPIPE. Entry gate: PPR disagreement >= DISAGREEMENT_THRESHOLD.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import networkx as nx

from helios.pipelines.g_pipe.gpipe_config import DISAGREEMENT_THRESHOLD, GPIPE_PPR_ALPHA
from helios.schemas.ueg_c import UEGCSnapshot  # noqa: TCH001
from helios.schemas.verdict import VERDICT_SCHEMA_VERSION
from helios.vcl import VCLFlag, gated_by
from helios.vcl.decorators import get_current_manifest

if TYPE_CHECKING:
    from helios.vcl.config import VCLManifest

__all__ = ["compute_ppr_disagreement", "run_gpipe", "should_run_gpipe"]

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
    dpipe_scores = dpipe_verdict.get("ppr_scores", {})
    return compute_ppr_disagreement(dpipe_scores) >= DISAGREEMENT_THRESHOLD


def _build_nx_graph(snapshot: UEGCSnapshot) -> nx.DiGraph:
    graph: nx.DiGraph = nx.DiGraph()
    for node in snapshot.nodes:
        graph.add_node(node.service_name)
    for edge in snapshot.edges:
        graph.add_edge(edge.source, edge.target, weight=edge.weight)
    return graph


def _ppr_traverse(
    snapshot: UEGCSnapshot,
    seed_weights: dict[str, float],
) -> tuple[list[str], dict[str, float]]:
    graph = _build_nx_graph(snapshot)
    personalization: dict[str, float] | None = {
        k: v for k, v in seed_weights.items() if k in graph.nodes
    }
    if not personalization or sum(personalization.values()) <= 0.00:
        personalization = None
    raw_scores: dict[str, float] = nx.pagerank(
        graph, alpha=GPIPE_PPR_ALPHA, personalization=personalization
    )
    ranked = sorted(raw_scores, key=raw_scores.__getitem__, reverse=True)
    return ranked, raw_scores


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
        "ranked_candidates": [],
        "ppr_scores": {},
        "hr_at_3": 0.00,
        "cpr": 0.00,
        "latency_ms": 0.00,
        "token_count": 0,
        "narrative": "gpipe-gated-or-skipped",
        "evaluation_phase": evaluation_phase,
        "schema_version": VERDICT_SCHEMA_VERSION,
    }


def _build_gpipe_verdict(
    incident_id: str,
    snapshot_hash: str,
    manifest: VCLManifest,
    ranked: list[str],
    ppr_scores: dict[str, float],
    evaluation_phase: str,
    run_id: str,
) -> dict[str, Any]:
    import time

    start = time.monotonic()
    latency_ms = (time.monotonic() - start) * 1000
    return {
        "pipeline": "gpipe",
        "incident_id": incident_id,
        "run_id": run_id,
        "variant_config_hash": manifest.compute_variant_config_hash(),
        "snapshot_hash": snapshot_hash,
        "ranked_candidates": ranked,
        "ppr_scores": ppr_scores,
        "hr_at_3": 0.00,
        "cpr": 0.00,
        "latency_ms": latency_ms,
        "token_count": 0,
        "narrative": "gpipe-traversal-complete",
        "evaluation_phase": evaluation_phase,
        "schema_version": VERDICT_SCHEMA_VERSION,
    }


@gated_by(VCLFlag.GPIPE)
def run_gpipe(
    incident_id: str,
    snapshot: UEGCSnapshot,
    snapshot_hash: str,
    dpipe_scores: dict[str, float],
    evaluation_phase: str,
    run_id: str,
) -> dict[str, Any]:
    manifest = get_current_manifest()
    assert manifest is not None
    disagreement = compute_ppr_disagreement(dpipe_scores)
    if disagreement < DISAGREEMENT_THRESHOLD:
        return _sentinel_verdict(
            incident_id, snapshot_hash, manifest, evaluation_phase, run_id
        )
    ranked, ppr_out = _ppr_traverse(snapshot, seed_weights=dpipe_scores)
    return _build_gpipe_verdict(
        incident_id, snapshot_hash, manifest, ranked, ppr_out, evaluation_phase, run_id
    )
