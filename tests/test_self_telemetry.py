"""IOL lite: self-telemetry under tenant=self (S4.7, design T-g/T-h)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from helios.schemas.ueg_c import TENANT_SELF, NodeType, UEGCNode, UEGCSnapshot
from helios.telemetry.self_telemetry import (
    COMPONENTS,
    HISTORY_RUNS,
    Injection,
    SelfTelemetry,
    detect_degradation,
    parse_injection,
    with_self_partition,
)
from helios.telemetry.trigger import DetectorParams
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path

DETECTOR = DetectorParams(
    bucket_seconds=60, threshold=10, persistence=3, provisional=False
)


def _metrics(i: int) -> dict[str, dict[str, float]]:
    """A steady control plane with a little deterministic jitter."""
    jitter = (i * 7) % 5
    return {
        "helios.dpipe": {"wall_ms": 200 + jitter},
        "helios.lpipe": {"wall_ms": 9000 + 10 * jitter},
        "helios.model": {"compute_ms": 4000 + 10 * jitter, "errors": 0},
        "helios.consensus": {"first_ms": 300 + jitter, "non_converged": 0},
    }


def _filled(n: int, injection: Injection | None = None) -> SelfTelemetry:
    st = SelfTelemetry(injection=injection)
    for i in range(n):
        st.record(f"run-{i}", _metrics(i))
    return st


def _read(st: SelfTelemetry) -> dict[str, object]:
    graph = with_self_partition(
        None, st.series(), incident_id="i", config_hash="h", captured_at_iso="t"
    )
    first = max(0, len(st.records) - HISTORY_RUNS)
    return detect_degradation(graph, DETECTOR, first_run=first)


def test_injection_specs() -> None:
    inj = parse_injection("component=helios.model,metric=compute_ms,from=12,factor=3")
    assert inj == Injection("helios.model", "compute_ms", 12, 3)
    for bad in (
        "component=helios.model,metric=compute_ms,from=x,factor=3",
        "component=nowhere,metric=compute_ms,from=1,factor=3",
        "component=helios.model,metric=compute_ms,from=1",
        "component=helios.model,metric=compute_ms,from=1,factor=-2",
    ):
        with pytest.raises(ValueError, match="bad injection"):
            parse_injection(bad)


def test_injection_changes_only_the_recorded_measure() -> None:
    st = _filled(4, Injection("helios.model", "compute_ms", 2, 3))
    assert [r["helios.model"]["compute_ms"] for r in st.records] == [
        4000,
        4020,
        3 * 4040,
        3 * 4010,
    ]
    assert [r["helios.lpipe"]["wall_ms"] for r in st.records] == [
        9000,
        9020,
        9040,
        9010,
    ]


def test_history_persists_across_resumes(tmp_path: Path) -> None:
    path = tmp_path / "self" / "results.HELIOS-Full.jsonl"
    first = SelfTelemetry(path=path)
    first.record("a", _metrics(0))
    first.record("b", _metrics(1))
    again = SelfTelemetry(path=path)
    assert again.records == first.records
    line = json.loads(path.read_text().splitlines()[1])
    assert (line["run_id"], line["index"]) == ("b", 1)


def test_series_mark_missing_runs() -> None:
    st = _filled(2)
    st.record("c", {"helios.dpipe": {"wall_ms": 210}})  # no L-pipe this run
    series = st.series()
    assert series["helios.dpipe"]["wall_ms"] == [200, 202, 210]
    assert series["helios.lpipe"]["wall_ms"][:2] == [9000, 9020]
    assert series["helios.lpipe"]["wall_ms"][2] != series["helios.lpipe"]["wall_ms"][2]


def test_partition_is_self_tenant_and_never_a_candidate() -> None:
    prod = UEGCSnapshot(
        incident_id="i",
        variant_config_hash="h",
        nodes=[
            UEGCNode(node_id="cart", node_type=NodeType.SERVICE, service_name="cart")
        ],
        edges=[],
        captured_at_iso="t",
    )
    composed = with_self_partition(
        prod, _filled(3).series(), incident_id="i", config_hash="h", captured_at_iso="t"
    )
    selves = [n for n in composed.nodes if n.tenant == TENANT_SELF]
    assert sorted(n.node_id for n in selves) == sorted(COMPONENTS)
    assert composed.candidate_ids() == ["cart"]
    assert prod.candidate_ids() == ["cart"]
    assert len(composed.edges) == 5
    alone = with_self_partition(
        None, {}, incident_id="i", config_hash="h", captured_at_iso="t"
    )
    assert alone.candidate_ids() == []


def test_a_steady_control_plane_is_not_flagged() -> None:
    assert _read(_filled(60))["degraded"] is None
    assert _read(SelfTelemetry()) == {"degraded": None, "runs_read": 0}


def test_injected_degradation_is_found_by_the_frozen_rule() -> None:
    st = _filled(60, Injection("helios.model", "compute_ms", 40, 3))
    found = _read(st)
    assert found["degraded"] == "helios.model"
    assert found["from_run"] == 40
    assert found["known_at_run"] == 40 + DETECTOR.persistence


def test_too_few_degraded_runs_are_not_enough() -> None:
    st = _filled(42, Injection("helios.model", "compute_ms", 40, 3))
    assert _read(st)["degraded"] is None  # persistence not reached yet


def test_only_the_frozen_ladder_is_accepted() -> None:
    from helios.telemetry.self_telemetry import check_protocol

    for factor in (2, 3, 5, 8):
        check_protocol(Injection("helios.model", "compute_ms", 30, factor))
    for bad in (
        Injection("helios.model", "compute_ms", 30, 4),
        Injection("helios.model", "compute_ms", 10, 5),
        Injection("helios.lpipe", "wall_ms", 30, 5),
    ):
        with pytest.raises(ValueError, match="frozen E-H6"):
            check_protocol(bad)
