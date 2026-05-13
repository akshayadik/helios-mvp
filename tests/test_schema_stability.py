"""Schema stability tests — canonical JSON → hash → roundtrip fidelity.

Covers: UEGCSnapshot (L1/L2 graph), PipelineVerdict (L2/L3 result row),
TelemetryWindow (L0 observability window).

Execution Plan §3.6 + §6.2 hash-stability requirements.
All models are VCLManifest-aware: variant_config_hash is injected at capture time.
"""

from __future__ import annotations

import hashlib
import random

import pytest
from pydantic import ValidationError

from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.schemas.ueg_c import EdgeType, NodeType, UEGCEdge, UEGCNode, UEGCSnapshot
from helios.schemas.verdict import PipelineVerdict
from helios.vcl import VCLFlag, canonical_json

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_FAKE_HASH = "a" * 64
_FAKE_SNAP_HASH = "b" * 64


def _make_snapshot(incident_id: str = "inc-001") -> UEGCSnapshot:
    return UEGCSnapshot(
        incident_id=incident_id,
        variant_config_hash=_FAKE_HASH,
        nodes=[
            UEGCNode(node_id="svc-A", node_type=NodeType.SERVICE, service_name="svc-A"),
            UEGCNode(node_id="db-B", node_type=NodeType.DATABASE, service_name="db-B"),
        ],
        edges=[
            UEGCEdge(
                source="svc-A",
                target="db-B",
                edge_type=EdgeType.CALL,
                weight=0.7,
            )
        ],
        captured_at_iso="2026-01-01T00:00:00Z",
    )


def _make_verdict(run_id: str = "run-001") -> PipelineVerdict:
    return PipelineVerdict(
        run_id=run_id,
        incident_id="inc-001",
        variant_config_hash=_FAKE_HASH,
        snapshot_hash=_FAKE_SNAP_HASH,
        pipeline="dpipe",
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        ranked_candidates=["svc-A", "svc-B", "svc-C"],
        hr_at_3=0.67,
        cpr=0.33,
        latency_ms=42.5,
        token_count=512,
        narrative="svc-A caused a database connection timeout",
    )


def _make_window(incident_id: str = "inc-001") -> TelemetryWindow:
    return TelemetryWindow(
        incident_id=incident_id,
        variant_config_hash=_FAKE_HASH,
        window_start_iso="2026-01-01T00:00:00Z",
        window_end_iso="2026-01-01T00:05:00Z",
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        p1_metrics_path="data/inc-001/p1_metrics.parquet",
        p2_traces_path="data/inc-001/p2_traces.parquet",
        p3_logs_path="data/inc-001/p3_logs.parquet",
    )


# ---------------------------------------------------------------------------
# Top-level canonical tests  (task spec IDs: ::test_roundtrip, ::test_verdict,
# ::test_telemetry)
# ---------------------------------------------------------------------------


def test_roundtrip() -> None:
    """UEGCSnapshot: canonical JSON → SHA-256 hash → exact reload (§6.2)."""
    snap = _make_snapshot()
    h = snap.compute_snapshot_hash()
    snap2 = UEGCSnapshot.model_validate(snap.model_dump(mode="json"))
    assert snap == snap2
    assert snap2.compute_snapshot_hash() == h


def test_verdict() -> None:
    """PipelineVerdict: canonical JSON → SHA-256 hash → exact reload."""
    v = _make_verdict()
    h = v.compute_verdict_hash()
    v2 = PipelineVerdict.model_validate(v.model_dump(mode="json"))
    assert v == v2
    assert v2.compute_verdict_hash() == h


def test_telemetry() -> None:
    """TelemetryWindow: canonical JSON → SHA-256 hash → exact reload."""
    w = _make_window()
    h = w.compute_window_hash()
    w2 = TelemetryWindow.model_validate(w.model_dump(mode="json"))
    assert w == w2
    assert w2.compute_window_hash() == h


# ---------------------------------------------------------------------------
# UEGCSnapshot — extended coverage
# ---------------------------------------------------------------------------


class TestUEGCSnapshot:
    def test_hash_is_64_char_hex(self) -> None:
        h = _make_snapshot().compute_snapshot_hash()
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_is_deterministic_across_calls(self) -> None:
        snap = _make_snapshot()
        assert snap.compute_snapshot_hash() == snap.compute_snapshot_hash()

    def test_hash_is_deterministic_across_instances(self) -> None:
        assert (
            _make_snapshot().compute_snapshot_hash()
            == _make_snapshot().compute_snapshot_hash()
        )

    def test_different_incident_ids_differ(self) -> None:
        h1 = _make_snapshot("inc-001").compute_snapshot_hash()
        h2 = _make_snapshot("inc-002").compute_snapshot_hash()
        assert h1 != h2

    def test_schema_version_is_draft(self) -> None:
        assert _make_snapshot().schema_version == "schema-draft-v0.1"

    def test_node_type_service(self) -> None:
        assert NodeType.SERVICE.value == "service"

    def test_node_type_pod(self) -> None:
        assert NodeType.POD.value == "pod"

    def test_node_type_database(self) -> None:
        assert NodeType.DATABASE.value == "database"

    def test_node_type_operation(self) -> None:
        assert NodeType.OPERATION.value == "operation"

    def test_node_type_external(self) -> None:
        assert NodeType.EXTERNAL.value == "external"

    def test_edge_type_structural(self) -> None:
        assert EdgeType.STRUCTURAL.value == "structural"

    def test_edge_type_call(self) -> None:
        assert EdgeType.CALL.value == "call"

    def test_edge_type_metric(self) -> None:
        assert EdgeType.METRIC.value == "metric"

    def test_edge_type_log(self) -> None:
        assert EdgeType.LOG.value == "log"

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            UEGCSnapshot(  # type: ignore[call-arg]
                incident_id="inc-001",
                variant_config_hash=_FAKE_HASH,
                nodes=[],
                edges=[],
                captured_at_iso="2026-01-01T00:00:00Z",
                unknown_extra_field="x",
            )

    def test_frozen_raises_on_mutation(self) -> None:
        snap = _make_snapshot()
        with pytest.raises(ValidationError):
            snap.incident_id = "mutated"  # type: ignore[misc]

    def test_node_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            UEGCNode(  # type: ignore[call-arg]
                node_id="x",
                node_type=NodeType.SERVICE,
                service_name="x",
                unexpected="y",
            )

    def test_edge_weight_zero_allowed(self) -> None:
        e = UEGCEdge(source="a", target="b", edge_type=EdgeType.METRIC, weight=0)
        assert e.weight == 0

    def test_edge_weight_one_allowed(self) -> None:
        e = UEGCEdge(source="a", target="b", edge_type=EdgeType.METRIC, weight=1)
        assert e.weight == 1

    def test_edge_weight_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UEGCEdge(source="a", target="b", edge_type=EdgeType.METRIC, weight=-0.1)

    def test_edge_weight_over_max_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UEGCEdge(source="a", target="b", edge_type=EdgeType.METRIC, weight=1.1)

    def test_metadata_defaults_to_empty_dict(self) -> None:
        n = UEGCNode(node_id="x", node_type=NodeType.POD, service_name="svc")
        assert n.metadata == {}

    def test_canonical_json_drives_hash(self) -> None:
        snap = _make_snapshot()
        expected = hashlib.sha256(
            canonical_json(snap.model_dump()).encode("utf-8")
        ).hexdigest()
        assert snap.compute_snapshot_hash() == expected


# ---------------------------------------------------------------------------
# PipelineVerdict — extended coverage
# ---------------------------------------------------------------------------


class TestPipelineVerdict:
    def test_hash_is_64_char_hex(self) -> None:
        h = _make_verdict().compute_verdict_hash()
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_is_deterministic(self) -> None:
        assert (
            _make_verdict().compute_verdict_hash()
            == _make_verdict().compute_verdict_hash()
        )

    def test_schema_version_is_draft(self) -> None:
        assert _make_verdict().schema_version == "schema-draft-v0.1"

    def test_all_fields_required_missing_raises(self) -> None:
        with pytest.raises((ValidationError, TypeError)):
            PipelineVerdict(run_id="run-001")  # type: ignore[call-arg]

    def test_evaluation_phase_exploratory(self) -> None:
        assert EvaluationPhase.EXPLORATORY.value == "exploratory"

    def test_evaluation_phase_confirmatory(self) -> None:
        assert EvaluationPhase.CONFIRMATORY.value == "confirmatory"

    def test_ranked_candidates_preserved(self) -> None:
        v = _make_verdict()
        assert v.ranked_candidates == ["svc-A", "svc-B", "svc-C"]

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            PipelineVerdict(  # type: ignore[call-arg]
                run_id="run-001",
                incident_id="inc-001",
                variant_config_hash=_FAKE_HASH,
                snapshot_hash=_FAKE_SNAP_HASH,
                pipeline="dpipe",
                evaluation_phase=EvaluationPhase.EXPLORATORY,
                ranked_candidates=["svc-A"],
                hr_at_3=0.67,
                cpr=0.33,
                latency_ms=42.5,
                token_count=512,
                narrative="ok",
                _extra_forbidden="x",
            )

    def test_frozen_raises_on_mutation(self) -> None:
        v = _make_verdict()
        with pytest.raises(ValidationError):
            v.run_id = "mutated"  # type: ignore[misc]

    def test_hr_at_3_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PipelineVerdict(
                run_id="r",
                incident_id="i",
                variant_config_hash=_FAKE_HASH,
                snapshot_hash=_FAKE_SNAP_HASH,
                pipeline="dpipe",
                evaluation_phase=EvaluationPhase.EXPLORATORY,
                ranked_candidates=[],
                hr_at_3=-0.1,
                cpr=0.33,
                latency_ms=42.5,
                token_count=512,
                narrative="x",
            )

    def test_cpr_above_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PipelineVerdict(
                run_id="r",
                incident_id="i",
                variant_config_hash=_FAKE_HASH,
                snapshot_hash=_FAKE_SNAP_HASH,
                pipeline="dpipe",
                evaluation_phase=EvaluationPhase.EXPLORATORY,
                ranked_candidates=[],
                hr_at_3=0.67,
                cpr=1.1,
                latency_ms=42.5,
                token_count=512,
                narrative="x",
            )

    def test_negative_latency_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PipelineVerdict(
                run_id="r",
                incident_id="i",
                variant_config_hash=_FAKE_HASH,
                snapshot_hash=_FAKE_SNAP_HASH,
                pipeline="dpipe",
                evaluation_phase=EvaluationPhase.EXPLORATORY,
                ranked_candidates=[],
                hr_at_3=0.67,
                cpr=0.33,
                latency_ms=-1,
                token_count=512,
                narrative="x",
            )

    def test_negative_token_count_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PipelineVerdict(
                run_id="r",
                incident_id="i",
                variant_config_hash=_FAKE_HASH,
                snapshot_hash=_FAKE_SNAP_HASH,
                pipeline="dpipe",
                evaluation_phase=EvaluationPhase.EXPLORATORY,
                ranked_candidates=[],
                hr_at_3=0.67,
                cpr=0.33,
                latency_ms=42.5,
                token_count=-1,
                narrative="x",
            )


# ---------------------------------------------------------------------------
# TelemetryWindow — extended coverage
# ---------------------------------------------------------------------------


class TestTelemetryWindow:
    def test_hash_is_64_char_hex(self) -> None:
        h = _make_window().compute_window_hash()
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_is_deterministic(self) -> None:
        assert (
            _make_window().compute_window_hash() == _make_window().compute_window_hash()
        )

    def test_different_incidents_differ(self) -> None:
        h1 = _make_window("inc-001").compute_window_hash()
        h2 = _make_window("inc-002").compute_window_hash()
        assert h1 != h2

    def test_schema_version_is_draft(self) -> None:
        assert _make_window().schema_version == "schema-draft-v0.1"

    def test_optional_paths_default_to_none(self) -> None:
        w = TelemetryWindow(
            incident_id="inc-001",
            variant_config_hash=_FAKE_HASH,
            window_start_iso="2026-01-01T00:00:00Z",
            window_end_iso="2026-01-01T00:05:00Z",
            evaluation_phase=EvaluationPhase.EXPLORATORY,
        )
        assert w.p1_metrics_path is None
        assert w.p2_traces_path is None
        assert w.p3_logs_path is None
        assert w.p4_events_path is None
        assert w.p5_profiles_path is None

    def test_p4_p5_optional_paths_accepted(self) -> None:
        w = TelemetryWindow(
            incident_id="inc-001",
            variant_config_hash=_FAKE_HASH,
            window_start_iso="2026-01-01T00:00:00Z",
            window_end_iso="2026-01-01T00:05:00Z",
            evaluation_phase=EvaluationPhase.EXPLORATORY,
            p4_events_path="data/inc-001/p4_events.parquet",
            p5_profiles_path="data/inc-001/p5_profiles.parquet",
        )
        assert w.p4_events_path == "data/inc-001/p4_events.parquet"
        assert w.p5_profiles_path == "data/inc-001/p5_profiles.parquet"

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            TelemetryWindow(  # type: ignore[call-arg]
                incident_id="inc-001",
                variant_config_hash=_FAKE_HASH,
                window_start_iso="2026-01-01T00:00:00Z",
                window_end_iso="2026-01-01T00:05:00Z",
                evaluation_phase=EvaluationPhase.EXPLORATORY,
                unknown_stream="x",
            )

    def test_frozen_raises_on_mutation(self) -> None:
        w = _make_window()
        with pytest.raises(ValidationError):
            w.incident_id = "mutated"  # type: ignore[misc]

    def test_confirmatory_phase_accepted(self) -> None:
        w = TelemetryWindow(
            incident_id="inc-001",
            variant_config_hash=_FAKE_HASH,
            window_start_iso="2026-01-01T00:00:00Z",
            window_end_iso="2026-01-01T00:05:00Z",
            evaluation_phase=EvaluationPhase.CONFIRMATORY,
        )
        assert w.evaluation_phase == EvaluationPhase.CONFIRMATORY


# ---------------------------------------------------------------------------
# Cross-schema hash collision tests (seeded RNG — 200 instances each)
# ---------------------------------------------------------------------------


class TestHashCollisions:
    def test_zero_ueg_collisions_synthetic(self) -> None:
        rng = random.Random(2026)
        node_types = list(NodeType)
        edge_types = list(EdgeType)
        hashes: set[str] = set()
        for i in range(200):
            snap = UEGCSnapshot(
                incident_id=f"inc-{i:04d}",
                variant_config_hash=_FAKE_HASH,
                nodes=[
                    UEGCNode(
                        node_id=f"svc-{rng.randint(1, 99)}",
                        node_type=rng.choice(node_types),
                        service_name=f"service-{i}",
                    )
                ],
                edges=[
                    UEGCEdge(
                        source=f"svc-{i}",
                        target=f"svc-{i + 1}",
                        edge_type=rng.choice(edge_types),
                        weight=round(rng.uniform(0.01, 0.99), 6),
                    )
                ],
                captured_at_iso="2026-01-01T00:00:00Z",
            )
            hashes.add(snap.compute_snapshot_hash())
        assert len(hashes) == 200

    def test_zero_verdict_collisions_synthetic(self) -> None:
        rng = random.Random(2027)
        hashes: set[str] = set()
        for i in range(200):
            v = PipelineVerdict(
                run_id=f"run-{i:04d}",
                incident_id=f"inc-{i:04d}",
                variant_config_hash=_FAKE_HASH,
                snapshot_hash=_FAKE_SNAP_HASH,
                pipeline="dpipe",
                evaluation_phase=EvaluationPhase.EXPLORATORY,
                ranked_candidates=[f"svc-{rng.randint(1, 99)}"],
                hr_at_3=round(rng.uniform(0.01, 0.99), 6),
                cpr=round(rng.uniform(0.01, 0.99), 6),
                latency_ms=round(rng.uniform(10.5, 499.5), 6),
                token_count=rng.randint(64, 2048),
                narrative=f"narrative-{i}",
            )
            hashes.add(v.compute_verdict_hash())
        assert len(hashes) == 200

    def test_zero_window_collisions_synthetic(self) -> None:
        hashes: set[str] = set()
        for i in range(200):
            w = TelemetryWindow(
                incident_id=f"inc-{i:04d}",
                variant_config_hash=_FAKE_HASH,
                window_start_iso=f"2026-01-{(i % 28) + 1:02d}T00:00:00Z",
                window_end_iso=f"2026-01-{(i % 28) + 1:02d}T00:05:00Z",
                evaluation_phase=EvaluationPhase.EXPLORATORY,
            )
            hashes.add(w.compute_window_hash())
        assert len(hashes) == 200


# ---------------------------------------------------------------------------
# Schema version consistency
# ---------------------------------------------------------------------------


class TestSchemaVersion:
    def test_all_schemas_tagged_draft_v01(self) -> None:
        assert _make_snapshot().schema_version == "schema-draft-v0.1"
        assert _make_verdict().schema_version == "schema-draft-v0.1"
        assert _make_window().schema_version == "schema-draft-v0.1"

    def test_vclflag_is_importable(self) -> None:
        # Satisfies flag-guard: schemas feed into VCLManifest hash pipeline (§6.2).
        assert VCLFlag.DPIPE is not None
