"""OTEL Demo telemetry capture — L0 5-minute multi-modal snapshot (§3.7).

Queries Prometheus (P1), Jaeger (P2), and OpenSearch (P3) backends over a fixed
time window while a fault flag is active, serialises each stream to Parquet, and
writes a TelemetryWindow manifest for C1 snapshot-hash verification (§6.2).

Design: SOLID throughout.
  S — each fetcher owns exactly one backend protocol.
  O — new streams are added by implementing StreamFetcher; TelemetryCapture unchanged.
  L — all fetchers are substitutable (same contract, tested via _StubFetcher).
  I — StreamFetcher exposes only stream_name + fetch(); nothing more.
  D — TelemetryCapture depends on StreamFetcher abstraction, not concrete classes.

VCLManifest is accepted at construction time (CaptureConfig.manifest) so
variant_config_hash is derived from the active manifest rather than passed as a
raw string — ensuring the TelemetryWindow always reflects the true VCL state.
"""

from __future__ import annotations

import abc
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pyarrow as pa
import pyarrow.parquet as pq

from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from helios.vcl.config import VCLManifest

__all__ = [
    "CaptureConfig",
    "JaegerTracesFetcher",
    "OpenSearchLogsFetcher",
    "ParquetWriter",
    "PrometheusMetricsFetcher",
    "StreamFetcher",
    "TelemetryCapture",
    "build_default_capture",
]

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaptureConfig:
    """Immutable configuration for a single telemetry capture session.

    Defaults target the OTEL Demo running via docker compose on localhost
    with the port mappings recorded in external/README.md.
    """

    incident_id: str
    manifest: VCLManifest
    evaluation_phase: EvaluationPhase
    prometheus_url: str = "http://localhost:9090"
    jaeger_url: str = "http://localhost:32770"
    opensearch_url: str = "http://localhost:32781"
    output_dir: Path = field(default_factory=lambda: Path("data") / "captures")


# ---------------------------------------------------------------------------
# Stream fetcher abstraction (SOLID-I + SOLID-D)
# ---------------------------------------------------------------------------


class StreamFetcher(abc.ABC):
    """Contract for a single-stream telemetry fetcher (P1 / P2 / P3).

    Concrete implementations query one backend; TelemetryCapture composes them.
    """

    @property
    @abc.abstractmethod
    def stream_name(self) -> str:
        """Short key used for the Parquet filename and TelemetryWindow path field."""

    @abc.abstractmethod
    def fetch(self, start: datetime, end: datetime) -> pa.Table:
        """Return all records for the closed window [start, end] as a pyarrow Table."""


# ---------------------------------------------------------------------------
# P1: Prometheus metrics
# ---------------------------------------------------------------------------


class PrometheusMetricsFetcher(StreamFetcher):
    """P1: Prometheus /api/v1/query_range at 15-second resolution."""

    _METRICS: tuple[str, ...] = (
        "up",
        "process_cpu_seconds_total",
        "process_resident_memory_bytes",
        "http_server_duration_milliseconds_bucket",
        "rpc_server_duration_milliseconds_bucket",
    )

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    @property
    def stream_name(self) -> str:
        return "p1_metrics"

    def fetch(self, start: datetime, end: datetime) -> pa.Table:
        timestamps: list[float] = []
        names: list[str] = []
        values: list[float] = []
        label_strs: list[str] = []

        for metric in self._METRICS:
            params = urllib.parse.urlencode(
                {
                    "query": metric,
                    "start": start.timestamp(),
                    "end": end.timestamp(),
                    "step": "15s",
                }
            )
            url = f"{self._base_url}/api/v1/query_range?{params}"
            with urllib.request.urlopen(url, timeout=30) as resp:
                payload: dict[str, Any] = json.loads(resp.read())
            for result in payload.get("data", {}).get("result", []):
                labels: dict[str, str] = result.get("metric", {})
                label_str = json.dumps(labels, sort_keys=True)
                name = labels.get("__name__", metric)
                for ts, val in result.get("values", []):
                    timestamps.append(float(ts))
                    names.append(name)
                    values.append(float(val))
                    label_strs.append(label_str)

        return pa.table(
            {
                "timestamp": pa.array(timestamps, type=pa.float64()),
                "metric_name": pa.array(names, type=pa.string()),
                "value": pa.array(values, type=pa.float64()),
                "labels": pa.array(label_strs, type=pa.string()),
            }
        )


# ---------------------------------------------------------------------------
# P2: Jaeger traces
# ---------------------------------------------------------------------------


class JaegerTracesFetcher(StreamFetcher):
    """P2: Jaeger /api/traces, merged across all OTEL Demo application services.

    api_prefix must match the jaeger_query.base_path in src/jaeger/config.yml.
    The OTEL Demo v2.2.0 sets base_path=/jaeger/ui, so the query API lives at
    {base_url}/jaeger/ui/api/traces rather than {base_url}/api/traces.
    """

    # Service names as reported by Jaeger — verified via /jaeger/ui/api/services.
    # Infrastructure services (flagd, frontend-proxy, load-generator) excluded.
    _SERVICES: tuple[str, ...] = (
        "accounting",
        "ad",
        "cart",
        "checkout",
        "currency",
        "email",
        "fraud-detection",
        "frontend",
        "payment",
        "product-catalog",
        "product-reviews",
        "quote",
        "recommendation",
        "shipping",
    )

    def __init__(self, base_url: str, api_prefix: str = "/jaeger/ui") -> None:
        self._base_url = base_url.rstrip("/")
        self._api_prefix = api_prefix.rstrip("/")

    @property
    def stream_name(self) -> str:
        return "p2_traces"

    def fetch(self, start: datetime, end: datetime) -> pa.Table:
        trace_ids: list[str] = []
        span_ids: list[str] = []
        parent_ids: list[str] = []
        ops: list[str] = []
        services: list[str] = []
        start_times: list[int] = []
        durations: list[int] = []
        statuses: list[str] = []

        start_us = int(start.timestamp() * 1_000_000)
        end_us = int(end.timestamp() * 1_000_000)

        for service in self._SERVICES:
            params = urllib.parse.urlencode(
                {
                    "service": service,
                    "start": start_us,
                    "end": end_us,
                    "limit": 1000,
                }
            )
            url = f"{self._base_url}{self._api_prefix}/api/traces?{params}"
            try:
                with urllib.request.urlopen(url, timeout=60) as resp:
                    payload: dict[str, Any] = json.loads(resp.read())
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    continue
                raise
            for trace in payload.get("data", []):
                tid: str = trace.get("traceID", "")
                for span in trace.get("spans", []):
                    status: str = next(
                        (
                            str(t["value"])
                            for t in span.get("tags", [])
                            if t["key"] == "otel.status_code"
                        ),
                        "UNSET",
                    )
                    parent_id = ""
                    for ref in span.get("references", []):
                        if (
                            ref.get("refType") == "CHILD_OF"
                            and ref.get("traceID") == tid
                        ):
                            parent_id = str(ref.get("spanID", ""))
                            break
                    trace_ids.append(tid)
                    span_ids.append(str(span.get("spanID", "")))
                    parent_ids.append(parent_id)
                    ops.append(str(span.get("operationName", "")))
                    services.append(service)
                    start_times.append(int(span.get("startTime", 0)))
                    durations.append(int(span.get("duration", 0)))
                    statuses.append(status)

        return pa.table(
            {
                "trace_id": pa.array(trace_ids, type=pa.string()),
                "span_id": pa.array(span_ids, type=pa.string()),
                "parent_span_id": pa.array(parent_ids, type=pa.string()),
                "operation_name": pa.array(ops, type=pa.string()),
                "service_name": pa.array(services, type=pa.string()),
                "start_time_us": pa.array(start_times, type=pa.int64()),
                "duration_us": pa.array(durations, type=pa.int64()),
                "status_code": pa.array(statuses, type=pa.string()),
            }
        )


# ---------------------------------------------------------------------------
# P3: OpenSearch logs
# ---------------------------------------------------------------------------


class OpenSearchLogsFetcher(StreamFetcher):
    """P3: Structured logs via OpenSearch /_search with ISO time-range filter."""

    # Index pattern verified via OTEL Collector config (src/otel-collector/otelcol-config.yml):
    # opensearch exporter sets logs_index="otel-logs" with daily time-format suffixes.
    _DEFAULT_INDEX = "otel-logs-*"

    def __init__(self, base_url: str, index: str = _DEFAULT_INDEX) -> None:
        self._base_url = base_url.rstrip("/")
        self._index = index

    @property
    def stream_name(self) -> str:
        return "p3_logs"

    def fetch(self, start: datetime, end: datetime) -> pa.Table:
        body = json.dumps(
            {
                "query": {
                    "range": {
                        "@timestamp": {
                            "gte": start.isoformat(),
                            "lte": end.isoformat(),
                            "format": "strict_date_optional_time",
                        }
                    }
                },
                "size": 10000,
                "_source": [
                    "@timestamp",
                    "serviceName",
                    "severityText",
                    "body",
                    "traceId",
                    "spanId",
                ],
            }
        ).encode()

        url = f"{self._base_url}/{self._index}/_search"
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload: dict[str, Any] = json.loads(resp.read())

        hits = payload.get("hits", {}).get("hits", [])
        timestamps: list[str] = []
        services: list[str] = []
        severities: list[str] = []
        bodies: list[str] = []
        trace_ids: list[str] = []
        span_ids: list[str] = []

        for h in hits:
            src: dict[str, Any] = h.get("_source", {})
            timestamps.append(str(src.get("@timestamp", "")))
            services.append(str(src.get("serviceName", "")))
            severities.append(str(src.get("severityText", "")))
            bodies.append(str(src.get("body", "")))
            trace_ids.append(str(src.get("traceId", "")))
            span_ids.append(str(src.get("spanId", "")))

        return pa.table(
            {
                "timestamp": pa.array(timestamps, type=pa.string()),
                "service_name": pa.array(services, type=pa.string()),
                "severity": pa.array(severities, type=pa.string()),
                "body": pa.array(bodies, type=pa.string()),
                "trace_id": pa.array(trace_ids, type=pa.string()),
                "span_id": pa.array(span_ids, type=pa.string()),
            }
        )


# ---------------------------------------------------------------------------
# Parquet writer (SOLID-S)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParquetWriter:
    """Writes a pyarrow Table to a Parquet file, creating parent directories."""

    def write(self, table: pa.Table, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, path)


# ---------------------------------------------------------------------------
# Orchestrator (SOLID-D: depends on StreamFetcher abstraction)
# ---------------------------------------------------------------------------


class TelemetryCapture:
    """Orchestrates a multi-modal 5-minute capture: fetch → write Parquet → manifest.

    P4 (K8s events) and P5 (profiling) are None in Stage 0 — Docker Compose
    provides no K8s API and the demo services are not profiled.
    """

    def __init__(
        self,
        config: CaptureConfig,
        fetchers: Sequence[StreamFetcher],
        writer: ParquetWriter,
    ) -> None:
        self._config = config
        self._fetchers = fetchers
        self._writer = writer

    def run(self, start: datetime, end: datetime) -> TelemetryWindow:
        """Execute capture for [start, end]; return the written TelemetryWindow."""
        incident_dir = self._config.output_dir / self._config.incident_id
        p1: str | None = None
        p2: str | None = None
        p3: str | None = None

        for fetcher in self._fetchers:
            table = fetcher.fetch(start, end)
            path = incident_dir / f"{fetcher.stream_name}.parquet"
            self._writer.write(table, path)
            if fetcher.stream_name == "p1_metrics":
                p1 = str(path)
            elif fetcher.stream_name == "p2_traces":
                p2 = str(path)
            elif fetcher.stream_name == "p3_logs":
                p3 = str(path)

        window = TelemetryWindow(
            incident_id=self._config.incident_id,
            variant_config_hash=self._config.manifest.compute_variant_config_hash(),
            window_start_iso=start.isoformat(),
            window_end_iso=end.isoformat(),
            evaluation_phase=self._config.evaluation_phase,
            p1_metrics_path=p1,
            p2_traces_path=p2,
            p3_logs_path=p3,
            p4_events_path=None,
            p5_profiles_path=None,
        )

        manifest_path = incident_dir / "manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(
                {**window.model_dump(), "window_hash": window.compute_window_hash()},
                indent=2,
            )
        )
        return window


# ---------------------------------------------------------------------------
# Factory: wires concrete implementations for the OTEL Demo harness
# ---------------------------------------------------------------------------


def build_default_capture(incident_id: str, manifest: VCLManifest) -> TelemetryCapture:
    """Return a TelemetryCapture targeting the localhost OTEL Demo backends."""
    config = CaptureConfig(
        incident_id=incident_id,
        manifest=manifest,
        evaluation_phase=EvaluationPhase.EXPLORATORY,
    )
    fetchers: list[StreamFetcher] = [
        PrometheusMetricsFetcher(config.prometheus_url),
        JaegerTracesFetcher(config.jaeger_url, api_prefix="/jaeger/ui"),
        OpenSearchLogsFetcher(config.opensearch_url),
    ]
    return TelemetryCapture(config=config, fetchers=fetchers, writer=ParquetWriter())
