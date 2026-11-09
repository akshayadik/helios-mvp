"""Signal type of the trigger, label-free (S2.5 design §5.1, M-a)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pandas as pd

from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.telemetry.signal_type import SignalType, signal_type
from helios.telemetry.trigger import TriggerRecord, TriggerSource
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

START = 1_790_000_040
BUCKET = 60
N = 20
T_BUCKET = 10


def _iso(t: float) -> str:
    return str(pd.Timestamp(t, unit="s", tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"))


def _noise(i: int) -> float:
    return [10.0, 11.0, 9.0, 10.5, 9.5][i % 5]


def _window(tmp_path: Path, series: dict[str, list[float]]) -> TelemetryWindow:
    rows: list[dict[str, Any]] = []
    for metric, values in series.items():
        for i, v in enumerate(values):
            rows.append(
                {
                    "timestamp": float(START + i * BUCKET + 5),
                    "metric_name": metric,
                    "value": v,
                    "labels": json.dumps({"service_name": "cart"}),
                }
            )
    path = tmp_path / "p1.parquet"
    pd.DataFrame(rows).to_parquet(path)
    return TelemetryWindow(
        incident_id="opaque01",
        variant_config_hash="h",
        window_start_iso=_iso(START),
        window_end_iso=_iso(START + N * BUCKET),
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        p1_metrics_path=str(path),
    )


def _trigger(source: TriggerSource = TriggerSource.THRESHOLD) -> TriggerRecord:
    return TriggerRecord(
        incident_id="opaque01",
        trigger_time_s=START + T_BUCKET * BUCKET,
        suspects=("cart",),
        context=(),
        source=source,
        detector_hash="d",
    )


def _spike(height: float) -> list[float]:
    return [_noise(i) if i < T_BUCKET else height for i in range(N)]


def _flat() -> list[float]:
    return [_noise(i) for i in range(N)]


def _type(tmp_path: Path, series: dict[str, list[float]], **kw: Any) -> SignalType:
    return signal_type(
        _window(tmp_path, series),
        kw.get("trigger", _trigger()),
        root=tmp_path,
        bucket_seconds=BUCKET,
    )


def test_cpu_spike_is_resource(tmp_path: Path) -> None:
    assert (
        _type(tmp_path, {"cpu": _spike(80), "latency-90": _spike(14)})
        == SignalType.RESOURCE
    )


def test_latency_series_is_latency(tmp_path: Path) -> None:
    assert (
        _type(tmp_path, {"cpu": _flat(), "latency-90": _spike(90)})
        == SignalType.LATENCY
    )


def test_error_counter_is_error(tmp_path: Path) -> None:
    assert _type(tmp_path, {"cpu": _flat(), "error": _spike(70)}) == SignalType.ERROR


def test_words_order_error_before_latency(tmp_path: Path) -> None:
    got = _type(tmp_path, {"http_server_duration_errors": _spike(70)})
    assert got == SignalType.ERROR


def test_fallback_trigger_is_unclassified(tmp_path: Path) -> None:
    got = _type(tmp_path, {"cpu": _spike(80)}, trigger=_trigger(TriggerSource.FALLBACK))
    assert got == SignalType.UNCLASSIFIED


def test_unknown_series_name_is_unclassified(tmp_path: Path) -> None:
    assert _type(tmp_path, {"queue_depth": _spike(80)}) == SignalType.UNCLASSIFIED


def test_never_reads_beyond_p1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    window = _window(tmp_path, {"cpu": _spike(80)})
    opened: list[str] = []
    real = pd.read_parquet

    def spy(path: Any, *a: Any, **k: Any) -> Any:
        opened.append(str(path))
        return real(path, *a, **k)

    monkeypatch.setattr(pd, "read_parquet", spy)
    window = window.model_copy(update={"p3_logs_path": str(tmp_path / "x.parquet")})
    signal_type(window, _trigger(), root=tmp_path, bucket_seconds=BUCKET)
    assert opened == [window.p1_metrics_path]


def test_strongest_series_names_the_series_signal_type_classifies(
    tmp_path: Path,
) -> None:
    """S3.2: the ACP reads the series name; signal_type is classify(name)."""
    from helios.telemetry.signal_type import classify, strongest_series

    series = {"cpu": _flat(), "latency-90": _spike(90)}
    window = _window(tmp_path, series)
    name = strongest_series(window, _trigger(), root=tmp_path, bucket_seconds=BUCKET)
    assert name == "latency-90"
    assert classify(name) == _type(tmp_path, series)
    fallback = _trigger(TriggerSource.FALLBACK)
    assert (
        strongest_series(window, fallback, root=tmp_path, bucket_seconds=BUCKET) is None
    )
