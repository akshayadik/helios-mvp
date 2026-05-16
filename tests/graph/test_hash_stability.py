"""Exit gate §2.5: zero hash collisions and stable canonical round-trip.

UEGCSnapshot.compute_snapshot_hash() is gated via G-pipe (VCLFlag.L2B_GRAPH).
"""

from __future__ import annotations

from helios.schemas.ueg_c import EdgeType, NodeType, UEGCEdge, UEGCNode, UEGCSnapshot
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

_HASH = "a" * 64
_AT = "2026-01-01T00:00:00+00:00"


def _make_snapshot(incident_id: str = "inc-001") -> UEGCSnapshot:
    return UEGCSnapshot(
        incident_id=incident_id,
        variant_config_hash=_HASH,
        nodes=[UEGCNode(node_id="a", node_type=NodeType.SERVICE, service_name="a")],
        edges=[UEGCEdge(source="a", target="a", edge_type=EdgeType.CALL, weight=0.80)],
        captured_at_iso=_AT,
    )


def test_snapshot_hash_stable_on_repeated_calls() -> None:
    snap = _make_snapshot()
    h1 = snap.compute_snapshot_hash()
    h2 = snap.compute_snapshot_hash()
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex digest length


def test_snapshot_hash_round_trip_via_model_dump() -> None:
    snap = _make_snapshot()
    h1 = snap.compute_snapshot_hash()
    dumped = snap.model_dump()
    reloaded = UEGCSnapshot.model_validate(dumped)
    h2 = reloaded.compute_snapshot_hash()
    assert h1 == h2


def test_different_incident_ids_produce_different_hashes() -> None:
    h1 = _make_snapshot("inc-001").compute_snapshot_hash()
    h2 = _make_snapshot("inc-002").compute_snapshot_hash()
    assert h1 != h2


def test_edge_weight_change_invalidates_hash() -> None:
    snap1 = UEGCSnapshot(
        incident_id="x",
        variant_config_hash=_HASH,
        nodes=[UEGCNode(node_id="a", node_type=NodeType.SERVICE, service_name="a")],
        edges=[UEGCEdge(source="a", target="a", edge_type=EdgeType.CALL, weight=0.3)],
        captured_at_iso=_AT,
    )
    snap2 = UEGCSnapshot(
        incident_id="x",
        variant_config_hash=_HASH,
        nodes=[UEGCNode(node_id="a", node_type=NodeType.SERVICE, service_name="a")],
        edges=[UEGCEdge(source="a", target="a", edge_type=EdgeType.CALL, weight=0.4)],
        captured_at_iso=_AT,
    )
    assert snap1.compute_snapshot_hash() != snap2.compute_snapshot_hash()
