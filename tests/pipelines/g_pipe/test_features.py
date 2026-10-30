"""G-pipe per-service features (S2.2 design §5.1)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from helios.pipelines.g_pipe.features import (
    FEATURE_COLUMNS,
    assert_no_identity,
    compute_features,
    lead_counts,
    onsets,
)
from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.telemetry.trigger import (
    DetectorParams,
    ServiceScores,
    TriggerRecord,
    TriggerSource,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

REPO = Path(__file__).resolve().parents[3]
DETECTOR = DetectorParams(
    bucket_seconds=60, threshold=10, persistence=3, provisional=False
)
T0 = 1_790_000_000  # window start, s
T_TRIGGER = T0 + 600


def _scores(rows: dict[str, list[float]]) -> ServiceScores:
    services = sorted(rows)
    return ServiceScores(
        services=services,
        z=np.array([rows[s] for s in services], dtype="float64"),
        start_s=T0,
    )


def test_onset_ignores_crossings_before_the_trigger() -> None:
    nan = float("nan")
    scores = _scores({"a": [nan, 12, 1, 1, 1, 1, 1, 1, 1, 1, 11, 1]})
    assert onsets(scores, T_TRIGGER, DETECTOR) == {"a": 10}


def test_callee_with_onset_leads_caller_without_one() -> None:
    led, leading, leaders = lead_counts({"b": 10}, frozenset({("a", "b")}))
    assert led == {"b": 1}
    assert leading == {"a": 1}
    assert leaders == frozenset({"b"})


def test_leads_need_a_full_bucket() -> None:
    led, leading, leaders = lead_counts({"a": 10, "b": 10}, frozenset({("a", "b")}))
    assert led == {} and leading == {} and leaders == frozenset()
    led, _, _ = lead_counts({"a": 11, "b": 10}, frozenset({("a", "b")}))
    assert led == {"b": 1}


def _window(
    tmp_path: Path,
    rows: list[tuple[str, str, str | None, str, float, float]],
    end_s: int = T0 + 900,
) -> TelemetryWindow:
    """Trace-only window; rows = (trace, span, parent, service, start s, end s)."""
    path = tmp_path / "p2_traces.parquet"
    pd.DataFrame(
        {
            "trace_id": [r[0] for r in rows],
            "span_id": [r[1] for r in rows],
            "parent_span_id": [r[2] for r in rows],
            "operation_name": ["op"] * len(rows),
            "service_name": [r[3] for r in rows],
            "start_time_us": [int(r[4] * 1_000_000) for r in rows],
            "duration_us": [int((r[5] - r[4]) * 1_000_000) for r in rows],
            "status_code": ["UNSET"] * len(rows),
        }
    ).to_parquet(path)
    return TelemetryWindow(
        incident_id="opaque",
        variant_config_hash="h" * 64,
        window_start_iso=datetime.fromtimestamp(T0, UTC).isoformat(),
        window_end_iso=datetime.fromtimestamp(end_s, UTC).isoformat(),
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        p2_traces_path=str(path),
    )


def _trigger() -> TriggerRecord:
    return TriggerRecord(
        incident_id="opaque",
        trigger_time_s=T_TRIGGER,
        suspects=(),
        context=(),
        source=TriggerSource.THRESHOLD,
        detector_hash="d" * 64,
    )


def _calls(
    trace: str, start: float, caller_end: float, callee: str = "b"
) -> list[tuple[str, str, str | None, str, float, float]]:
    return [
        (trace, f"{trace}a", None, "a", start, caller_end),
        (trace, f"{trace}b", f"{trace}a", callee, start + 0.1, caller_end - 0.1),
    ]


def test_no_split_gives_none(tmp_path: Path) -> None:
    rows = _calls("t1", T_TRIGGER + 10, T_TRIGGER + 11)
    assert (
        compute_features(
            _window(tmp_path, rows), _trigger(), {}, {}, ["a", "b"], DETECTOR
        )
        is None
    )


def test_service_without_spans_after_t_has_finite_features(tmp_path: Path) -> None:
    rows = [
        *_calls("t1", T0 + 10, T0 + 11),
        ("t2", "x", None, "a", T_TRIGGER + 5, T_TRIGGER + 6),
    ]
    f = compute_features(
        _window(tmp_path, rows), _trigger(), {"a": 1}, {}, ["a", "b"], DETECTOR
    )
    assert f is not None
    assert f.table.shape == (2, len(FEATURE_COLUMNS))
    assert np.isfinite(f.table).all()


def test_features_ignore_window_bounds(tmp_path: Path) -> None:
    rows = (
        _calls("t1", T0 + 10, T0 + 12)
        + _calls("t2", T_TRIGGER + 5, T_TRIGGER + 9)
        + _calls("t3", T_TRIGGER + 20, T_TRIGGER + 30, callee="c")
    )
    first = compute_features(
        _window(tmp_path, rows),
        _trigger(),
        {"a": 1},
        {"b": 2},
        ["a", "b", "c"],
        DETECTOR,
    )
    later = tmp_path / "later"
    later.mkdir()
    second = compute_features(
        _window(later, rows, end_s=T0 + 1_800),
        _trigger(),
        {"a": 1},
        {"b": 2},
        ["a", "b", "c"],
        DETECTOR,
    )
    assert first is not None and second is not None
    assert np.array_equal(first.table, second.table)
    assert first.ghosts == frozenset({("a", "c")})


def test_feature_audit_rejects_a_service_named_column() -> None:
    with pytest.raises(ValueError, match="identity"):
        assert_no_identity([*FEATURE_COLUMNS, "is_payment"], ["payment", "cart"])
    with pytest.raises(ValueError, match="unknown"):
        assert_no_identity(["latency_rank"], ["payment"])


def test_feature_columns_carry_no_service_names() -> None:
    case = sorted((REPO / "data/otel/build_v3").iterdir())[0]
    services = sorted(
        pd.read_parquet(case / "p2_traces.parquet")["service_name"].unique()
    )
    assert len(services) > 10
    assert_no_identity(FEATURE_COLUMNS, services)


def test_self_shift_measures_self_time_so_a_slow_leaf_stands_out(
    tmp_path: Path,
) -> None:
    # Design §5.1: shift of the median self TIME; a leaf's self share is
    # always one, so only its self time can show a CPU fault.
    rows: list[tuple[str, str, str | None, str, float, float]] = [
        *[(f"b{i}", f"b{i}", None, "leaf", T0 + i, T0 + i + 0.010) for i in range(5)],
        *[
            (f"b{i}", f"q{i}", None, "leaf", T0 + i + 0.5, T0 + i + 0.512)
            for i in range(5)
        ],
        *[
            (f"a{i}", f"a{i}", None, "leaf", T_TRIGGER + i, T_TRIGGER + i + 0.040)
            for i in range(5)
        ],
    ]
    f = compute_features(
        _window(tmp_path, rows), _trigger(), {}, {}, ["leaf"], DETECTOR
    )
    assert f is not None
    assert f.table[0, FEATURE_COLUMNS.index("self_shift")] > 0


def test_no_degree_features_and_window_normalised_scores(tmp_path: Path) -> None:
    # PR 1 review C2/I4 (owner 2026-10-30): degree is a per-service constant in
    # a fixed topology and raw scores scale with the window; neither may enter.
    assert "in_degree" not in FEATURE_COLUMNS
    assert "out_degree" not in FEATURE_COLUMNS
    rows = [
        *_calls("t1", T0 + 10, T0 + 12),
        *_calls("t2", T_TRIGGER + 5, T_TRIGGER + 9),
    ]
    w = _window(tmp_path, rows)
    small = compute_features(
        w, _trigger(), {"a": 1, "b": 2}, {"a": 0.1, "b": 0.3}, ["a", "b"], DETECTOR
    )
    large = compute_features(
        w, _trigger(), {"a": 10, "b": 20}, {"a": 1, "b": 3}, ["a", "b"], DETECTOR
    )
    assert small is not None and large is not None
    assert np.array_equal(small.table, large.table)
    assert small.table[1, FEATURE_COLUMNS.index("dpipe_score")] == 1
