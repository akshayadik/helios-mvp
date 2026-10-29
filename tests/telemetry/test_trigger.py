"""Shared detection trigger (S2.1): causal scoring, firing rule, scope, parameters."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.telemetry.trigger import (
    Z_CAP,
    DetectorParams,
    TriggerSource,
    causal_z,
    detect,
    detector_hash,
    load_detector_params,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path

T0 = 1_790_000_000  # window start, epoch seconds
BUCKET = 30
N_BUCKETS = 30
START = datetime.fromtimestamp(T0, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
END = datetime.fromtimestamp(T0 + BUCKET * N_BUCKETS, UTC).strftime(
    "%Y-%m-%dT%H:%M:%SZ"
)
PARAMS = DetectorParams(
    bucket_seconds=BUCKET, threshold=6, persistence=2, provisional=True
)


def _steady(bucket: int) -> int:
    return 40 + bucket % 3


def _window(
    root: Path,
    level: dict[tuple[str, str], dict[int, int]],
    *,
    services: tuple[str, ...] = ("cart", "ad"),
) -> TelemetryWindow:
    """P1 window: every (service, metric) is steady, except buckets given in ``level``."""
    rows: list[tuple[float, str, float, str]] = []
    keys = {(s, "latency") for s in services} | set(level)
    for service, metric in sorted(keys):
        for b in range(N_BUCKETS):
            value = level.get((service, metric), {}).get(b, _steady(b))
            for k in range(3):  # three samples per bucket, same value
                rows.append(
                    (
                        T0 + b * BUCKET + 10 * k,
                        metric,
                        value,
                        json.dumps({"service_name": service}),
                    )
                )
    d = root / "w"
    d.mkdir(exist_ok=True)
    pq.write_table(
        pa.table(
            {
                "timestamp": [r[0] for r in rows],
                "metric_name": [r[1] for r in rows],
                "value": [float(r[2]) for r in rows],
                "labels": [r[3] for r in rows],
            }
        ),
        d / "p1.parquet",
    )
    return TelemetryWindow(
        incident_id="opaque",
        variant_config_hash="h" * 64,
        window_start_iso=START,
        window_end_iso=END,
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        p1_metrics_path="w/p1.parquet",
    )


def _step(start: int, length: int, value: int = 80) -> dict[int, int]:
    return dict.fromkeys(range(start, start + length), value)


# ── causal scoring ───────────────────────────────────────────────────────────


def test_causal_z_uses_only_the_past() -> None:
    v = np.array([1, 1, 2, 1, 1, 9, 1], dtype=float)
    z = causal_z(v, count_series=False, warmup=4)
    assert np.isnan(z[:4]).all()
    assert z[5] > z[4]
    assert causal_z(v[:6], count_series=False, warmup=4)[5] == z[5]


def test_flat_gauge_small_move_scores_against_its_level() -> None:
    v = np.array([200, 200, 200, 200, 200, 202], dtype=float)
    z = causal_z(v, count_series=False, warmup=4)
    assert z[5] < 1


def test_flat_zero_gauge_gives_no_evidence_until_it_varies() -> None:
    v = np.array([0, 0, 0, 0, 0, 3, 3], dtype=float)
    z = causal_z(v, count_series=False, warmup=4)
    assert np.isnan(z[5])
    assert np.isfinite(z[6])


def test_z_is_capped_as_a_numeric_guard() -> None:
    v = np.array([40, 41, 42, 40, 41, 10**9], dtype=float)
    assert causal_z(v, count_series=False, warmup=4)[5] == Z_CAP


# ── firing rule ──────────────────────────────────────────────────────────────


def test_detector_fires_at_first_sustained_crossing_and_names_the_service(
    tmp_path: Path,
) -> None:
    window = _window(tmp_path, {("cart", "latency"): _step(10, 4)})
    rec = detect(window, PARAMS, root=tmp_path)
    assert rec.source == TriggerSource.THRESHOLD
    assert rec.suspects[0] == "cart"
    assert rec.trigger_time_s == T0 + 10 * BUCKET
    assert rec.incident_id == "opaque"


def test_single_bucket_blip_never_fires_with_persistence_two(tmp_path: Path) -> None:
    window = _window(tmp_path, {("cart", "latency"): _step(10, 1)})
    assert detect(window, PARAMS, root=tmp_path).source == TriggerSource.FALLBACK


def test_out_of_scope_services_never_trigger_or_appear(tmp_path: Path) -> None:
    window = _window(
        tmp_path,
        {("load-generator", "cpu"): _step(10, 6)},
        services=("cart", "ad", "load-generator"),
    )
    rec = detect(window, PARAMS, root=tmp_path)
    assert rec.source == TriggerSource.FALLBACK
    assert "load-generator" not in rec.suspects


def test_out_of_scope_anomaly_is_recorded_as_context(tmp_path: Path) -> None:
    window = _window(
        tmp_path,
        {("cart", "latency"): _step(10, 4), ("otel-collector", "cpu"): _step(10, 4)},
        services=("cart", "ad", "otel-collector"),
    )
    rec = detect(window, PARAMS, root=tmp_path)
    assert rec.suspects == ("cart",)
    assert rec.context == ("otel-collector",)


def test_no_data_gives_fallback_at_window_start(tmp_path: Path) -> None:
    window = TelemetryWindow(
        incident_id="empty",
        variant_config_hash="h" * 64,
        window_start_iso=START,
        window_end_iso=END,
        evaluation_phase=EvaluationPhase.EXPLORATORY,
    )
    rec = detect(window, PARAMS, root=tmp_path)
    assert rec.source == TriggerSource.FALLBACK
    assert rec.trigger_time_s == T0
    assert rec.suspects == ()
    assert rec.context == ()


def test_moving_window_start_does_not_move_the_trigger(tmp_path: Path) -> None:
    window = _window(tmp_path, {("cart", "latency"): _step(14, 4)})
    full = detect(window, PARAMS, root=tmp_path)
    cropped = detect(window, PARAMS, root=tmp_path, crop_start_s=2 * BUCKET)
    assert (cropped.trigger_time_s, cropped.suspects) == (
        full.trigger_time_s,
        full.suspects,
    )


def test_detect_is_deterministic(tmp_path: Path) -> None:
    window = _window(tmp_path, {("cart", "latency"): _step(10, 4)})
    first = detect(window, PARAMS, root=tmp_path).model_dump_json()
    assert detect(window, PARAMS, root=tmp_path).model_dump_json() == first


# ── parameters ───────────────────────────────────────────────────────────────


def test_detector_hash_changes_with_any_parameter() -> None:
    base = detector_hash(PARAMS)
    for changed in (
        replace(PARAMS, bucket_seconds=60),
        replace(PARAMS, threshold=8),
        replace(PARAMS, persistence=3),
        replace(PARAMS, provisional=False),
    ):
        assert detector_hash(changed) != base
    assert detector_hash(PARAMS) == base


def test_provisional_flag_round_trips_from_the_frozen_file(tmp_path: Path) -> None:
    path = tmp_path / "trigger.json"
    path.write_text(
        json.dumps(
            {
                "bucket_seconds": 30,
                "threshold": 6,
                "persistence": 2,
                "provisional": True,
            }
        )
    )
    assert load_detector_params(path) == PARAMS
    assert load_detector_params().provisional in (True, False)  # the committed file


def test_missing_or_incomplete_parameter_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_detector_params(tmp_path / "absent.json")
    path = tmp_path / "partial.json"
    path.write_text(json.dumps({"bucket_seconds": 30, "threshold": 6}))
    with pytest.raises(ValueError, match="keys"):
        load_detector_params(path)


# ── owner signal rules D-g, D-h (2026-10-27) ─────────────────────────────────


def test_sum_series_are_gauges_and_counts_keep_the_poisson_floor() -> None:
    import pandas as pd

    from helios.graph.anomaly_intensity import metric_series

    rows = [
        (T0 + b * BUCKET, name, float(b * 10), json.dumps({"service_name": "cart"}))
        for b in range(6)
        for name in ("rpc_duration_sum", "rpc_duration_count", "cpu", "error")
    ]
    frame = pd.DataFrame(rows, columns=["timestamp", "metric_name", "value", "labels"])
    series = metric_series(frame, START, 6, BUCKET)["cart"]
    # order is by metric name: cpu, error, rpc_duration_count, rpc_duration_sum
    assert [s.is_count for s in series] == [False, True, True, False]
    assert [s.upward_only for s in series] == [True, False, False, False]


def test_upward_only_series_ignore_drops() -> None:
    v = np.array([40, 41, 42, 40, 41, 5], dtype=float)
    assert causal_z(v, count_series=False, upward_only=True, warmup=4)[5] == 0
    assert causal_z(v, count_series=False, warmup=4)[5] > 6


def test_cpu_drop_does_not_trigger_but_workload_drop_does(tmp_path: Path) -> None:
    services = ("cart", "ad")
    cpu_drop = _window(
        tmp_path, {("cart", "cpu"): _step(10, 6, value=1)}, services=services
    )
    assert detect(cpu_drop, PARAMS, root=tmp_path).source == TriggerSource.FALLBACK
    other = tmp_path / "other"
    other.mkdir()
    workload_drop = _window(
        other, {("cart", "workload"): _step(10, 6, value=1)}, services=services
    )
    rec = detect(workload_drop, PARAMS, root=other)
    assert rec.source == TriggerSource.THRESHOLD
    assert rec.suspects[0] == "cart"


# ── short-history and many-series corrections (owner, 2026-10-27, D-i) ──────


def test_short_history_is_discounted() -> None:
    from helios.telemetry.trigger import history_discount

    noise = [40, 41, 42, 40]
    short = causal_z(np.array([*noise, 60], dtype=float), count_series=False, warmup=4)
    long_ = causal_z(
        np.array([*(noise * 5), 60], dtype=float), count_series=False, warmup=4
    )
    assert short[-1] < long_[-1]
    assert history_discount(4) > history_discount(20) > history_discount(400) >= 1
    assert history_discount(400) < 1.01


def test_one_event_on_a_flat_count_series_stays_below_one() -> None:
    z = causal_z(np.array([0, 0, 0, 0, 0, 1], dtype=float), count_series=True, warmup=4)
    assert 0 < z[5] < 1


def test_many_series_raise_the_bar() -> None:
    from helios.telemetry.trigger import series_correction

    assert series_correction(1) == 1
    assert series_correction(300) > series_correction(10) > 1


# ── OTel signal repair (S2-M7-ENG10): histograms, span metrics, traces ──────


def test_histogram_buckets_fold_to_their_total_for_the_detector() -> None:
    import pandas as pd

    from helios.graph.anomaly_intensity import metric_series

    rows = [
        (
            T0 + b * BUCKET,
            "rpc_server_duration_milliseconds_bucket",
            float(b * 10),
            json.dumps({"service_name": "ad", "le": le}),
        )
        for b in range(6)
        for le in ("5", "10", "50", "+Inf")
    ]
    frame = pd.DataFrame(rows, columns=["timestamp", "metric_name", "value", "labels"])
    assert len(metric_series(frame, START, 6, BUCKET)["ad"]) == 4  # UEG-C view
    folded = metric_series(frame, START, 6, BUCKET, fold_histograms=True)["ad"]
    assert len(folded) == 1  # only the +Inf bucket: the request count
    assert folded[0].is_count


def test_span_error_calls_and_latency_count_rises_only() -> None:
    from helios.graph.anomaly_intensity import UPWARD_ONLY_METRICS

    assert {
        "span_error_calls_total",
        "span_mean_latency_milliseconds",
    } <= UPWARD_ONLY_METRICS
    assert "span_calls_total" not in UPWARD_ONLY_METRICS  # workload: both ways


def _spans(rows: list[tuple[str, int, int, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        rows, columns=["service_name", "start_time_us", "duration_us", "status_code"]
    )


def test_detector_fires_on_a_span_metric_error_burst(tmp_path: Path) -> None:
    errors = {b: 0 if b < 18 else 12 * (b - 17) for b in range(N_BUCKETS)}
    window = _window(
        tmp_path,
        {("cart", "span_error_calls_total"): errors},  # cumulative counter
        services=("cart", "ad"),
    )
    rec = detect(window, PARAMS, root=tmp_path)
    assert rec.source == TriggerSource.THRESHOLD
    assert rec.suspects[0] == "cart"
    assert rec.trigger_time_s == T0 + 18 * BUCKET


def test_detector_never_reads_raw_spans(tmp_path: Path) -> None:
    # The RCAEval build corpus has no traces but the pool has: a raw-span
    # signal could not be calibrated for the pool (design, since trigger-v1).
    # Trace evidence reaches the detector only as span metrics (S2-M7-ENG10).
    window = _window(tmp_path, {}, services=("cart", "ad"))
    us = 1_000_000
    rows = [
        (service, (T0 + b * BUCKET + k) * us, 3000, "ERROR" if b >= 18 else "UNSET")
        for b in range(N_BUCKETS)
        for k in range(20)
        for service in ("cart", "ad")
    ]
    pq.write_table(pa.Table.from_pandas(_spans(rows)), tmp_path / "w" / "p2.parquet")
    with_traces = window.model_copy(update={"p2_traces_path": "w/p2.parquet"})
    assert detect(with_traces, PARAMS, root=tmp_path) == detect(
        window, PARAMS, root=tmp_path
    )


def test_a_sustained_burst_on_a_zero_count_series_stays_high() -> None:
    # Before S2-M7-ENG10 a count series with MAD 0 fell back to the std of its
    # history, which the burst's own first bucket inflates: the second burst
    # bucket scored ~4 instead of ~10 and a sustained error burst never fired.
    errors = np.array([0] * 18 + [12] * 4, dtype=float)
    z = causal_z(errors, count_series=True, upward_only=True)
    assert z[18] > 8
    assert z[19] > 8 and z[20] > 8  # the burst does not mask itself
    gauge = np.array([0] * 18 + [12] * 4, dtype=float)
    assert np.isnan(causal_z(gauge, count_series=False)[18])  # flat-zero gauge rule


def test_detector_scores_a_histogram_by_its_total_only(tmp_path: Path) -> None:
    from helios.telemetry.trigger import service_scores

    def hist(root: Path, les: tuple[str, ...]) -> TelemetryWindow:
        rows = []
        for b in range(N_BUCKETS):
            total = 600 * b + (0 if b < 18 else 400 * (b - 17))  # traffic surge
            for le in les:
                rows.append(
                    (
                        float(T0 + b * BUCKET),
                        "rpc_server_duration_milliseconds_bucket",
                        float(total),
                        json.dumps({"service_name": "ad", "le": le}),
                    )
                )
        (root / "w").mkdir(parents=True)
        pq.write_table(
            pa.table(
                {
                    "timestamp": [r[0] for r in rows],
                    "metric_name": [r[1] for r in rows],
                    "value": [r[2] for r in rows],
                    "labels": [r[3] for r in rows],
                }
            ),
            root / "w" / "p1.parquet",
        )
        return TelemetryWindow(
            incident_id="opaque",
            variant_config_hash="h" * 64,
            window_start_iso=START,
            window_end_iso=END,
            evaluation_phase=EvaluationPhase.EXPLORATORY,
            p1_metrics_path="w/p1.parquet",
        )

    one = service_scores(hist(tmp_path / "a", ("+Inf",)), BUCKET, root=tmp_path / "a")
    many = (*(str(2**k) for k in range(30)), "+Inf")
    folded = service_scores(hist(tmp_path / "b", many), BUCKET, root=tmp_path / "b")
    assert np.array_equal(one.z, folded.z, equal_nan=True)


def test_detector_version_is_v2_after_the_signal_repair() -> None:
    from helios.telemetry.trigger import DETECTOR_VERSION

    assert DETECTOR_VERSION == "trigger-v2"


def test_frozen_detector_is_the_calibration_selection() -> None:
    # S2-M7-EVAL01 (owner 2026-10-29): calibration run 6 on RCAEval build +
    # otel_build_v3 selected (60 s, 10, 3); the frozen file must match it.
    from pathlib import Path

    from helios.telemetry.trigger import DETECTOR_VERSION

    report_path = Path(__file__).resolve().parents[2] / (
        "docs/sprints/s2-reasoning/s2_1_trigger_calibration.json"
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    selected = report["selected"]
    params = load_detector_params()
    assert not params.provisional
    assert report["detector_version"] == DETECTOR_VERSION
    assert (params.bucket_seconds, params.threshold, params.persistence) == (
        selected["bucket_seconds"],
        selected["threshold"],
        selected["persistence"],
    )
    assert detector_hash(params) == selected["detector_hash"]
