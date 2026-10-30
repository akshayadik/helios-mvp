"""Deterministic telemetry digests for the L-pipe workers (S2.3 design §5.2)."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

import pandas as pd

from helios.pipelines.l_pipe.digests import (
    DigestLine,
    cap_lines,
    estimate_tokens,
    metric_digest,
)
from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.telemetry.trigger import TriggerRecord, TriggerSource
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

START = 1_790_000_040  # a whole minute
BUCKET = 60
N = 20
T_BUCKET = 10


def _iso(t: float) -> str:
    return pd.Timestamp(t, unit="s", tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def _window(tmp_path: Path, **paths: str | None) -> TelemetryWindow:
    return TelemetryWindow(
        incident_id="opaque01",
        variant_config_hash="h",
        window_start_iso=_iso(START),
        window_end_iso=_iso(START + N * BUCKET),
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        **paths,
    )


def _trigger() -> TriggerRecord:
    return TriggerRecord(
        incident_id="opaque01",
        trigger_time_s=START + T_BUCKET * BUCKET,
        suspects=(),
        context=(),
        source=TriggerSource.THRESHOLD,
        detector_hash="d",
    )


def _p1(tmp_path: Path, series: dict[tuple[str, str], list[float]]) -> str:
    rows: list[dict[str, Any]] = []
    for (service, metric), values in series.items():
        for i, v in enumerate(values):
            rows.append(
                {
                    "timestamp": float(START + i * BUCKET + 5),
                    "metric_name": metric,
                    "value": v,
                    "labels": json.dumps({"service_name": service}),
                }
            )
    path = tmp_path / "p1.parquet"
    pd.DataFrame(rows).to_parquet(path)
    return str(path)


def _series(after: float) -> list[float]:
    return [10.0 if i % 2 == 0 else 12.0 for i in range(T_BUCKET)] + [after] * (
        N - T_BUCKET
    )


def test_cap_keeps_largest_shifts_and_counts_cut() -> None:
    lines = [
        DigestLine("", "a", "a shift three " + "x" * 30, 3),
        DigestLine("", "b", "b shift one " + "x" * 30, 1),
        DigestLine("", "c", "c shift two " + "x" * 30, 2),
    ]
    one = estimate_tokens("M1 " + lines[0].text)
    digest = cap_lines("metric", lines, token_cap=2 * one + 1)
    assert [line.service for line in digest.lines] == ["a", "c"]
    assert digest.cut == 1


def test_ids_follow_sorted_order() -> None:
    lines = [DigestLine("", s, f"{s} t", w) for s, w in (("b", 1), ("a", 2), ("c", 2))]
    digest = cap_lines("log", lines, token_cap=1_000)
    assert [(line.line_id, line.service) for line in digest.lines] == [
        ("L1", "a"),
        ("L2", "c"),
        ("L3", "b"),
    ]


def test_metric_shift_exact(tmp_path: Path) -> None:
    p1 = _p1(
        tmp_path,
        {
            ("cart", "latency-90"): _series(20.0),
            ("payment", "latency-90"): _series(14.0),
        },
    )
    digest = metric_digest(
        _window(tmp_path, p1_metrics_path=p1),
        _trigger(),
        ["cart", "payment"],
        root=tmp_path,
        bucket_seconds=BUCKET,
    )
    assert digest is not None
    assert [line.text for line in digest.lines] == [
        "cart latency-90 up 6.1 robust units, beyond 3 from +0 s",
        "payment latency-90 up 2.0 robust units",
    ]
    assert round(digest.lines[0].weight, 3) == round(9 / 1.4826, 3)


def test_metric_digest_reads_only_p1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p1 = _p1(tmp_path, {("cart", "latency-90"): _series(20.0)})
    opened: list[str] = []
    real = pd.read_parquet

    def spy(path: Any, *args: Any, **kwargs: Any) -> pd.DataFrame:
        opened.append(str(path))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", spy)
    window = _window(
        tmp_path,
        p1_metrics_path=p1,
        p2_traces_path=str(tmp_path / "p2.parquet"),
        p3_logs_path=str(tmp_path / "p3.parquet"),
    )
    metric_digest(window, _trigger(), ["cart"], root=tmp_path, bucket_seconds=BUCKET)
    assert opened == [p1]


def test_relative_times_only(tmp_path: Path) -> None:
    p1 = _p1(tmp_path, {("cart", "latency-90"): _series(20.0)})
    digest = metric_digest(
        _window(tmp_path, p1_metrics_path=p1),
        _trigger(),
        ["cart"],
        root=tmp_path,
        bucket_seconds=BUCKET,
    )
    assert digest is not None
    for line in digest.lines:
        assert not re.search(r"\d{4}-\d{2}-\d{2}|\d{9,}", line.text)


def test_no_p1_no_digest(tmp_path: Path) -> None:
    assert (
        metric_digest(
            _window(tmp_path),
            _trigger(),
            ["cart"],
            root=tmp_path,
            bucket_seconds=BUCKET,
        )
        is None
    )
