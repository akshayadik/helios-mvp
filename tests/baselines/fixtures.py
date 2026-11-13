"""A small sealed capture with real HELIOS stream schemas (S4.8 tests)."""

from __future__ import annotations

import datetime as dt
import json
from typing import TYPE_CHECKING, Any

import pyarrow as pa
import pyarrow.parquet as pq

from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.telemetry.seal import write_seal
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path

KEY = b"test-secret-at-least-32-chars-long!!"
START = 1_700_000_000  # Unix seconds, a multiple of 15 plus 5 (checks bucketing)
STEP = 15
N = 8  # metric points: START .. START + 105


def capture(
    root: Path,
    incident_id: str,
    *,
    phase: EvaluationPhase = EvaluationPhase.EXPLORATORY,
    seal: bool = True,
) -> Path:
    inc = root / incident_id
    inc.mkdir(parents=True)
    metrics: dict[str, list[Any]] = {
        "timestamp": [],
        "metric_name": [],
        "value": [],
        "labels": [],
    }
    for i in range(N):
        for svc, base in (("cart", 1), ("ad", 10)):
            for host in ("h1", "h2"):  # two series per name: exported as the mean
                metrics["timestamp"].append(float(START + i * STEP))
                metrics["metric_name"].append("cpu")
                metrics["value"].append(base + i + (2 if host == "h2" else 0))
                metrics["labels"].append(
                    json.dumps({"service_name": svc, "host_name": host})
                )
    pq.write_table(pa.table(metrics), inc / "p1_metrics.parquet")
    pq.write_table(
        pa.table(
            {
                "trace_id": ["t1", "t1", "t2"],
                "span_id": ["s1", "s2", "s3"],
                "parent_span_id": ["", "s1", ""],
                "operation_name": ["GetCart", "GetAd", "GetCart"],
                "service_name": ["cart", "ad", "cart"],
                "start_time_us": [
                    (START + 1) * 1_000_000,
                    (START + 2) * 1_000_000,
                    (START + 20) * 1_000_000,
                ],
                "duration_us": [2000, 4000, 6000],
                "status_code": ["UNSET", "ERROR", "503"],
            }
        ),
        inc / "p2_traces.parquet",
    )

    def iso(s: int) -> str:
        return dt.datetime.fromtimestamp(s, tz=dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    pq.write_table(
        pa.table(
            {
                "timestamp": [iso(START + 3), iso(START + 4), iso(START + 31)],
                "service_name": ["cart", "cart", "ad"],
                "severity": ["INFO", "", "ERROR"],
                "body": ["ok", "Connection FAILED", "boom"],
                "trace_id": ["", "", ""],
                "span_id": ["", "", ""],
            }
        ),
        inc / "p3_logs.parquet",
    )
    window = TelemetryWindow(
        incident_id=incident_id,
        variant_config_hash="a" * 64,
        window_start_iso=dt.datetime.fromtimestamp(START, tz=dt.UTC).isoformat(),
        window_end_iso=dt.datetime.fromtimestamp(
            START + (N - 1) * STEP, tz=dt.UTC
        ).isoformat(),
        evaluation_phase=phase,
        p1_metrics_path=str(inc / "p1_metrics.parquet"),
        p2_traces_path=str(inc / "p2_traces.parquet"),
        p3_logs_path=str(inc / "p3_logs.parquet"),
    )
    manifest = {**window.model_dump(), "window_hash": window.compute_window_hash()}
    (inc / "manifest.json").write_text(json.dumps(manifest, default=str))
    if seal:
        write_seal(inc, window, KEY)
    return inc


def window_of(inc: Path) -> TelemetryWindow:
    raw = json.loads((inc / "manifest.json").read_text())
    raw.pop("window_hash")
    return TelemetryWindow(**raw)
