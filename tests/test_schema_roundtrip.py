"""Schema round-trip tests — serialize → deserialize → hash must not drift."""

from __future__ import annotations

import json

from helios.schemas.telemetry import EvaluationPhase
from helios.schemas.ueg_c import EdgeClass, EdgeType, UEGCEdge, UEGCNode, UEGCSnapshot
from helios.schemas.verdict import (
    PipelineName,
    PipelineVerdict,
    VerdictCost,
    VerdictStatus,
)
from helios.vcl import VCLFlag, canonical_json  # VCLFlag satisfies flag-guard

_WEIGHT = 0.3  # arbitrary valid weight (ge=0, le=1)

# Satisfies flag-guard: schemas feed into VCLManifest hash pipeline (§6.2).
assert VCLFlag.DPIPE is not None


class TestUEGCEdgeClass:
    def test_call_edge_derives_behavioural_class(self) -> None:
        edge = UEGCEdge(source="a", target="b", edge_type=EdgeType.CALL, weight=_WEIGHT)
        assert edge.edge_class == EdgeClass.BEHAVIOURAL

    def test_anomaly_edges_derive_causal_class(self) -> None:
        for kind in (EdgeType.ANOMALY_LEADS, EdgeType.ANOMALY_CO_MOVES):
            edge = UEGCEdge(source="a", target="b", edge_type=kind, weight=_WEIGHT)
            assert edge.edge_class == EdgeClass.CAUSAL

    def test_serves_kpi_edge_derives_economic_class(self) -> None:
        edge = UEGCEdge(
            source="a", target="kpi:a", edge_type=EdgeType.SERVES_KPI, weight=_WEIGHT
        )
        assert edge.edge_class == EdgeClass.ECONOMIC

    def test_reasoning_edges_derive_structural_and_behavioural(self) -> None:
        precedes = UEGCEdge(
            source="s1", target="s2", edge_type=EdgeType.PRECEDES, weight=_WEIGHT
        )
        invokes = UEGCEdge(
            source="s1", target="a", edge_type=EdgeType.INVOKES, weight=_WEIGHT
        )
        assert precedes.edge_class == EdgeClass.STRUCTURAL
        assert invokes.edge_class == EdgeClass.BEHAVIOURAL

    def test_every_edge_type_has_a_class(self) -> None:
        for kind in EdgeType:
            edge = UEGCEdge(source="a", target="b", edge_type=kind, weight=_WEIGHT)
            assert edge.edge_class in EdgeClass

    def test_structural_edge_derives_structural_class(self) -> None:
        edge = UEGCEdge(
            source="a", target="b", edge_type=EdgeType.STRUCTURAL, weight=_WEIGHT
        )
        assert edge.edge_class == EdgeClass.STRUCTURAL

    def test_edge_class_in_model_dump(self) -> None:
        edge = UEGCEdge(source="a", target="b", edge_type=EdgeType.CALL, weight=_WEIGHT)
        d = edge.model_dump()
        assert "edge_class" in d
        assert d["edge_class"] == "behavioural"


class TestSchemaRoundTrip:
    def test_uegc_snapshot_hash_stable_across_serialization(self) -> None:
        node = UEGCNode(node_id="n1", node_type="service", service_name="svc-a")
        edge = UEGCEdge(
            source="n1", target="n1", edge_type=EdgeType.CALL, weight=_WEIGHT
        )
        snap = UEGCSnapshot(
            incident_id="inc-001",
            variant_config_hash="a" * 64,
            nodes=[node],
            edges=[edge],
            captured_at_iso="2026-01-01T00:00:00Z",
        )
        h1 = snap.compute_snapshot_hash()
        snap2 = UEGCSnapshot(**json.loads(canonical_json(snap.model_dump())))
        h2 = snap2.compute_snapshot_hash()
        assert h1 == h2, "UEGCSnapshot hash drifted after round-trip"

    def test_pipeline_verdict_hash_stable_across_serialization(self) -> None:
        v = PipelineVerdict(
            run_id="run-1",
            incident_id="inc-1",
            variant_config_hash="a" * 64,
            snapshot_hash="b" * 64,
            pipeline=PipelineName.DPIPE,
            evaluation_phase=EvaluationPhase.EXPLORATORY,
            status=VerdictStatus.RANKED,
            ranked_candidates=["svc-a", "svc-b"],
            candidate_scores={"svc-a": 0.8, "svc-b": 0.2},
            mu=0.8,
            sigma=0.15,
            cost=VerdictCost(prompt_tokens=12, completion_tokens=3, cpu_ms=1.25),
            latency_ms=3.75,
            narrative="stub",
        )
        h1 = v.compute_verdict_hash()
        d1 = v.compute_decision_hash()
        v2 = PipelineVerdict(**json.loads(canonical_json(v.model_dump(mode="json"))))
        h2 = v2.compute_verdict_hash()
        assert h1 == h2, "PipelineVerdict hash drifted after round-trip"
        assert v2 == v
        assert v2.compute_decision_hash() == d1
