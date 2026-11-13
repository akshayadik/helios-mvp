"""Export a sealed HELIOS window into RCAEval's file layout (S4.8 B-a).

Baselines read the same sealed bytes HELIOS reads, never RCAEval's raw case
folders (their names carry the root-cause service and the fault). The caller
checks the window's hash and content seal first (``CaptureReader``).

Files written (RCAEval's names and columns, ``main.py`` at 2fca61b):

- ``data.csv``: wide metrics, ``time`` (Unix seconds) and one
  ``<service>_<metric>`` column per series, the mean where several series
  share a name (OTel series that differ only in host or container labels);
- ``logs.csv``: ``time`` (HH:MM), ``timestamp`` (ns), ``container_name``,
  ``message``, ``level``;
- ``traces.csv``: ``time``, ``traceID``, ``spanID``, ``parentSpanID``,
  ``serviceName``, ``methodName``, ``operationName``, ``startTime`` and
  ``duration`` (microseconds), ``statusCode``;
- ``logts.csv``, ``tracets_err.csv``, ``tracets_lat.csv``: the 15-second
  series the multi-source methods read. RCAEval ships them with RE2/RE3 and
  holds no code that derives them, and the Hugging Face copy the pool comes
  from does not carry them, so they are rebuilt here (a recorded departure):
  per service, log lines and error lines per bucket (``<service>_log``,
  ``<service>_logerror``); per span operation, error spans per bucket
  (``<service>_<operation>``) and mean span duration in ms per bucket (empty
  where a bucket has no span; the methods forward-fill).

A span is an error when its status is ``ERROR`` / ``STATUS_CODE_ERROR`` or an
HTTP code of at least 400. A log line is an error when its severity is ERROR,
FATAL or CRITICAL or its body matches ``error|fail`` (any case).
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pandas as pd
import pyarrow.parquet as pq

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path

    from helios.schemas.telemetry import TelemetryWindow

__all__ = [
    "BUCKET_S",
    "EXPORT_VERSION",
    "export_window",
    "is_error_log",
    "is_error_span",
]

EXPORT_VERSION = "rcaeval-export-v1"
BUCKET_S = 15
_NS_PER_S = 1_000_000_000
_US_PER_MS = 1000
_HTTP_ERROR = 400
_ERROR_STATUS = frozenset({"ERROR", "STATUS_CODE_ERROR"})
_ERROR_SEVERITY = frozenset({"ERROR", "FATAL", "CRITICAL"})
_ERROR_WORDS = r"(?i)error|fail"


def is_error_span(status: Any) -> bool:
    """A span error: textual ERROR status or an HTTP code of at least 400."""
    text = str(status).strip().upper()
    if text in _ERROR_STATUS:
        return True
    return text.isdigit() and int(text) >= _HTTP_ERROR


def is_error_log(severity: Any, body: Any) -> bool:
    """A log error: ERROR/FATAL/CRITICAL severity or "error"/"fail" in the body."""
    if str(severity).strip().upper() in _ERROR_SEVERITY:
        return True
    return bool(pd.Series([str(body)]).str.contains(_ERROR_WORDS).iloc[0])


def _epoch(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def _grid(start_s: float, end_s: float) -> list[int]:
    first = int(start_s // BUCKET_S) * BUCKET_S
    return list(range(first, int(end_s) + 1, BUCKET_S))


def _read(root: Path, rel: str | None) -> pd.DataFrame | None:
    if rel is None or not (root / rel).is_file():
        return None
    return pq.read_table(root / rel).to_pandas()


def _metrics(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame({"time": []})
    services = df["labels"].map(lambda s: json.loads(s)["service_name"])
    wide = (
        pd.DataFrame(
            {
                "time": df["timestamp"].astype("float64").floordiv(1).astype("int64"),
                "column": services + "_" + df["metric_name"].astype(str),
                "value": df["value"].astype("float64"),
            }
        )
        .pivot_table(index="time", columns="column", values="value", aggfunc="mean")
        .sort_index()
    )
    wide = wide.reindex(sorted(wide.columns), axis=1)
    wide.columns.name = None
    return wide.reset_index()


def _logs(df: pd.DataFrame | None) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    if df is None or df.empty:
        return pd.DataFrame(), None
    stamps = df["timestamp"].map(_epoch)
    logs = pd.DataFrame(
        {
            "time": pd.to_datetime(stamps, unit="s", utc=True).dt.strftime("%H:%M"),
            "timestamp": (stamps * _NS_PER_S).round().astype("int64"),
            "container_name": df["service_name"].astype(str),
            "message": df["body"].astype(str),
            "level": df["severity"].astype(str).str.lower(),
        }
    )
    error = [
        is_error_log(s, b) for s, b in zip(df["severity"], df["body"], strict=True)
    ]
    counts = pd.DataFrame(
        {
            "bucket": stamps.floordiv(BUCKET_S).astype("int64") * BUCKET_S,
            "service": df["service_name"].astype(str),
            "error": error,
        }
    )
    return logs, counts


def _traces(df: pd.DataFrame | None) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    if df is None or df.empty:
        return pd.DataFrame(), None
    start_s = df["start_time_us"].astype("int64") / 1_000_000
    traces = pd.DataFrame(
        {
            "time": pd.to_datetime(start_s, unit="s", utc=True).dt.strftime("%H:%M"),
            "traceID": df["trace_id"].astype(str),
            "spanID": df["span_id"].astype(str),
            "parentSpanID": df["parent_span_id"].astype(str),
            "serviceName": df["service_name"].astype(str),
            "methodName": df["operation_name"].astype(str),
            "operationName": df["operation_name"].astype(str),
            "startTime": df["start_time_us"].astype("int64"),
            "duration": df["duration_us"].astype("int64"),
            "statusCode": df["status_code"].astype(str),
        }
    )
    spans = pd.DataFrame(
        {
            "bucket": start_s.floordiv(BUCKET_S).astype("int64") * BUCKET_S,
            "column": traces["serviceName"] + "_" + traces["operationName"],
            "error": traces["statusCode"].map(is_error_span),
            "ms": traces["duration"] / _US_PER_MS,
        }
    )
    return traces, spans


def _series(
    grid: list[int], rows: pd.DataFrame, column: str, value: str, agg: str
) -> pd.DataFrame:
    table = rows.pivot_table(index="bucket", columns=column, values=value, aggfunc=agg)
    table = table.reindex(index=grid).reindex(sorted(table.columns), axis=1)
    if agg != "mean":
        table = table.fillna(0).astype("int64")
    table.index.name = "time"
    table.columns.name = None
    return table.reset_index()


def export_window(window: TelemetryWindow, root: Path, out_dir: Path) -> dict[str, int]:
    """Write the RCAEval layout of one window; return row counts per file."""
    grid = _grid(_epoch(window.window_start_iso), _epoch(window.window_end_iso))
    data = _metrics(_read(root, window.p1_metrics_path))
    logs, log_rows = _logs(_read(root, window.p3_logs_path))
    traces, span_rows = _traces(_read(root, window.p2_traces_path))
    files: dict[str, pd.DataFrame] = {
        "data.csv": data,
        "logs.csv": logs,
        "traces.csv": traces,
    }
    if log_rows is not None:
        log_rows = log_rows.assign(n=1, column_log=log_rows["service"] + "_log").astype(
            {"error": "int64"}
        )
        total = _series(grid, log_rows, "column_log", "n", "sum")
        errs = _series(
            grid,
            log_rows.assign(column_err=log_rows["service"] + "_logerror"),
            "column_err",
            "error",
            "sum",
        )
        files["logts.csv"] = total.merge(errs, on="time")
    else:
        files["logts.csv"] = pd.DataFrame({"time": grid})
    if span_rows is not None:
        files["tracets_err.csv"] = _series(
            grid, span_rows.astype({"error": "int64"}), "column", "error", "sum"
        )
        files["tracets_lat.csv"] = _series(grid, span_rows, "column", "ms", "mean")
    out_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for name, frame in files.items():
        frame.to_csv(out_dir / name, index=False, quoting=csv.QUOTE_MINIMAL)
        counts[name] = len(frame)
    return counts


def utc_now_iso() -> str:  # pragma: no cover - convenience for callers
    return datetime.now(tz=UTC).isoformat()
