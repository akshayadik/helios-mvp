"""Deterministic telemetry digests for the L-pipe workers (S2.3 design §5.2)."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

import pandas as pd

from helios.pipelines.l_pipe.digests import (
    Digest,
    DigestLine,
    cap_lines,
    estimate_tokens,
    log_digest,
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
Row = tuple[float, str, str, str]


def _iso(t: float) -> str:
    return str(pd.Timestamp(t, unit="s", tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"))


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


def _p3(tmp_path: Path, rows: list[Row]) -> str:
    frame = pd.DataFrame(
        {
            "timestamp": [_iso(START + t) for t, _, _, _ in rows],
            "service_name": [s for _, s, _, _ in rows],
            "severity": [sev for _, _, _, sev in rows],
            "body": [b for _, _, b, _ in rows],
        }
    )
    path = tmp_path / "p3.parquet"
    frame.to_parquet(path)
    return str(path)


def _steady(service: str, sev: str = "INFO") -> list[Row]:
    return [(t, service, "request served ok", sev) for t in range(10, N * BUCKET, 60)]


def _log_digest(tmp_path: Path, rows: list[Row], cands: list[str]) -> Digest | None:
    return log_digest(
        _window(tmp_path, p3_logs_path=_p3(tmp_path, rows)),
        _trigger(),
        cands,
        root=tmp_path,
    )


def test_new_template_after_trigger_listed(tmp_path: Path) -> None:
    fail: list[Row] = [
        (
            T_BUCKET * BUCKET + 20 + i,
            "cart",
            f"connection to 10.0.0.{i} failed",
            "ERROR",
        )
        for i in range(5)
    ]
    digest = _log_digest(tmp_path, _steady("cart") + fail, ["cart"])
    assert digest is not None
    texts = [line.text for line in digest.lines]
    new = [t for t in texts if "connection to" in t]
    assert len(new) == 1
    assert new[0].endswith("0 lines before trigger, 5 after")
    assert not any("request served ok" in t for t in texts)
    assert "cart 5 error-level lines after trigger, 0 before" in texts


def test_rising_template_listed_with_counts(tmp_path: Path) -> None:
    slow: list[Row] = [(t, "cart", "slow query took 120ms", "WARN") for t in (50, 250)]
    slow += [
        (T_BUCKET * BUCKET + 5 * i, "cart", "slow query took 300ms", "WARN")
        for i in range(12)
    ]
    digest = _log_digest(tmp_path, _steady("cart") + slow, ["cart"])
    assert digest is not None
    rising = [line.text for line in digest.lines if "slow query" in line.text]
    assert rising == [
        'cart log template "slow query took <DUR>": 2 lines before trigger, 12 after'
    ]


def test_empty_severity_and_silent_service(tmp_path: Path) -> None:
    fail: list[Row] = [
        (T_BUCKET * BUCKET + 20 + i, "cart", "cache unavailable", "") for i in range(4)
    ]
    digest = _log_digest(tmp_path, _steady("cart", "") + fail, ["cart", "payment"])
    assert digest is not None
    assert {line.service for line in digest.lines} == {"cart"}
    assert not any("error-level" in line.text for line in digest.lines)


def test_log_digest_deterministic(tmp_path: Path) -> None:
    fail: list[Row] = [
        (T_BUCKET * BUCKET + 20 + i, "cart", "boom", "ERROR") for i in range(3)
    ]
    rows = _steady("cart") + fail
    assert _log_digest(tmp_path, rows, ["cart"]) == _log_digest(
        tmp_path, rows, ["cart"]
    )
