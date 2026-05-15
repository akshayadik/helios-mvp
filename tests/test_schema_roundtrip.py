"""Schema round-trip tests — serialize → deserialize → hash must not drift."""

from __future__ import annotations

import json

from helios.schemas.telemetry import EvaluationPhase
from helios.schemas.ueg_c import EdgeClass, EdgeType, UEGCEdge, UEGCNode, UEGCSnapshot
from helios.schemas.verdict import PipelineVerdict
from helios.vcl import VCLFlag, canonical_json  # VCLFlag satisfies flag-guard

_WEIGHT = 0.3  # arbitrary valid weight (ge=0, le=1)

# Satisfies flag-guard: schemas feed into VCLManifest hash pipeline (§6.2).
assert VCLFlag.DPIPE is not None


class TestUEGCEdgeClass:
    def test_call_edge_derives_behavioural_class(self) -> None:
        edge = UEGCEdge(source="a", target="b", edge_type=EdgeType.CALL, weight=_WEIGHT)
        assert edge.edge_class == EdgeClass.BEHAVIOURAL

    def test_metric_edge_derives_causal_class(self) -> None:
        edge = UEGCEdge(
            source="a", target="b", edge_type=EdgeType.METRIC, weight=_WEIGHT
        )
        assert edge.edge_class == EdgeClass.CAUSAL

    def test_log_edge_derives_economic_class(self) -> None:
        edge = UEGCEdge(source="a", target="b", edge_type=EdgeType.LOG, weight=_WEIGHT)
        assert edge.edge_class == EdgeClass.ECONOMIC

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
            pipeline="dpipe",
            evaluation_phase=EvaluationPhase.EXPLORATORY,
            ranked_candidates=[],
            hr_at_3=0,
            cpr=0,
            latency_ms=0,
            token_count=0,
            narrative="stub",
        )
        h1 = v.compute_verdict_hash()
        v2 = PipelineVerdict(**json.loads(canonical_json(v.model_dump())))
        h2 = v2.compute_verdict_hash()
        assert h1 == h2, "PipelineVerdict hash drifted after round-trip"
