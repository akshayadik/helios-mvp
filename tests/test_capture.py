"""Telemetry capture tests — S0-D4-ENG04 / ENG06 / EVAL01.

test_window  → EG2 gate: 5-min window capture writes valid Parquet + manifest.
test_validate → EG2 gate: written Parquet is schema-valid after round-trip read.
"""

from __future__ import annotations

import json
import urllib.error
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from pydantic import ValidationError

from helios.schemas.telemetry import EvaluationPhase
from helios.telemetry.otel_demo_capture import (
    CaptureConfig,
    JaegerTracesFetcher,
    OpenSearchLogsFetcher,
    ParquetWriter,
    PrometheusMetricsFetcher,
    StreamFetcher,
    TelemetryCapture,
    build_default_capture,
)
from helios.telemetry.reader import CaptureReader, CaptureVerification
from helios.vcl.variants import CONFIRMATORY_VARIANTS

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def manifest():
    return CONFIRMATORY_VARIANTS["HELIOS-Full"]


@pytest.fixture()
def config(tmp_path, manifest):
    return CaptureConfig(
        incident_id="s0-cart-001",
        manifest=manifest,
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        output_dir=tmp_path / "captures",
    )


@pytest.fixture()
def window_bounds():
    start = datetime(2026, 5, 14, 10, 0, 0, tzinfo=UTC)
    end = datetime(2026, 5, 14, 10, 5, 0, tzinfo=UTC)
    return start, end


# ---------------------------------------------------------------------------
# Test doubles — satisfy StreamFetcher contract without HTTP
# ---------------------------------------------------------------------------


class _StubFetcher(StreamFetcher):
    """StreamFetcher backed by a fixed pyarrow Table; no network calls."""

    def __init__(self, stream: str, table: pa.Table) -> None:
        self._stream = stream
        self._table = table

    @property
    def stream_name(self) -> str:
        return self._stream

    def fetch(self, start: datetime, end: datetime) -> pa.Table:
        return self._table


def _metrics_table() -> pa.Table:
    return pa.table(
        {
            "timestamp": pa.array([1715000000.0], type=pa.float64()),
            "metric_name": pa.array(["process_cpu_seconds_total"], type=pa.string()),
            "value": pa.array([0.42], type=pa.float64()),
            "labels": pa.array(['{"job":"adservice"}'], type=pa.string()),
        }
    )


def _traces_table() -> pa.Table:
    return pa.table(
        {
            "trace_id": pa.array(["abc123"], type=pa.string()),
            "span_id": pa.array(["def456"], type=pa.string()),
            "operation_name": pa.array(["/GetProduct"], type=pa.string()),
            "service_name": pa.array(["productcatalogservice"], type=pa.string()),
            "start_time_us": pa.array([1715000000000000], type=pa.int64()),
            "duration_us": pa.array([1500], type=pa.int64()),
            "status_code": pa.array(["OK"], type=pa.string()),
        }
    )


def _logs_table() -> pa.Table:
    return pa.table(
        {
            "timestamp": pa.array(["2026-05-14T10:00:00Z"], type=pa.string()),
            "service_name": pa.array(["cartservice"], type=pa.string()),
            "severity": pa.array(["ERROR"], type=pa.string()),
            "body": pa.array(["connection refused"], type=pa.string()),
            "trace_id": pa.array(["abc123"], type=pa.string()),
            "span_id": pa.array(["def456"], type=pa.string()),
        }
    )


def _three_stubs() -> list[_StubFetcher]:
    return [
        _StubFetcher("p1_metrics", _metrics_table()),
        _StubFetcher("p2_traces", _traces_table()),
        _StubFetcher("p3_logs", _logs_table()),
    ]


# ---------------------------------------------------------------------------
# test_window — EG2: 5-min window captures all three streams
# ---------------------------------------------------------------------------


def test_window(config, window_bounds):
    """Orchestrator writes p1/p2/p3 Parquet files and a TelemetryWindow manifest."""
    start, end = window_bounds
    window = TelemetryCapture(
        config=config, fetchers=_three_stubs(), writer=ParquetWriter()
    ).run(start, end)

    incident_dir = config.output_dir / config.incident_id
    assert (incident_dir / "p1_metrics.parquet").exists()
    assert (incident_dir / "p2_traces.parquet").exists()
    assert (incident_dir / "p3_logs.parquet").exists()
    assert window.incident_id == config.incident_id
    assert window.evaluation_phase == EvaluationPhase.EXPLORATORY
    assert window.p1_metrics_path is not None
    assert window.p2_traces_path is not None
    assert window.p3_logs_path is not None
    assert window.p4_events_path is None
    assert window.p5_profiles_path is None


def test_window_variant_hash_comes_from_manifest(config, window_bounds):
    """TelemetryWindow.variant_config_hash matches the VCLManifest — not a raw string arg."""
    start, end = window_bounds
    window = TelemetryCapture(
        config=config, fetchers=_three_stubs(), writer=ParquetWriter()
    ).run(start, end)
    assert window.variant_config_hash == config.manifest.compute_variant_config_hash()


def test_window_hash_is_deterministic(config, window_bounds):
    """Same config + same window bounds → identical compute_window_hash (C1 snapshot identity)."""
    start, end = window_bounds
    run_a = TelemetryCapture(
        config=config, fetchers=_three_stubs(), writer=ParquetWriter()
    ).run(start, end)
    run_b = TelemetryCapture(
        config=config, fetchers=_three_stubs(), writer=ParquetWriter()
    ).run(start, end)
    assert run_a.compute_window_hash() == run_b.compute_window_hash()


def test_window_manifest_json_written_with_hash(config, window_bounds):
    """manifest.json is written alongside Parquets and contains the window_hash field."""
    start, end = window_bounds
    window = TelemetryCapture(
        config=config, fetchers=_three_stubs(), writer=ParquetWriter()
    ).run(start, end)

    manifest_path = config.output_dir / config.incident_id / "manifest.json"
    assert manifest_path.exists()
    data = json.loads(manifest_path.read_text())
    assert data["incident_id"] == config.incident_id
    assert data["window_hash"] == window.compute_window_hash()


def test_window_fetchers_called_with_correct_bounds(config, window_bounds):
    """Each fetcher receives exactly the start/end datetimes passed to run()."""
    start, end = window_bounds
    calls: list[tuple[datetime, datetime]] = []

    class _RecordingFetcher(_StubFetcher):
        def fetch(self, s: datetime, e: datetime) -> pa.Table:
            calls.append((s, e))
            return super().fetch(s, e)

    fetchers = [
        _RecordingFetcher("p1_metrics", _metrics_table()),
        _RecordingFetcher("p2_traces", _traces_table()),
        _RecordingFetcher("p3_logs", _logs_table()),
    ]
    TelemetryCapture(config=config, fetchers=fetchers, writer=ParquetWriter()).run(
        start, end
    )
    assert len(calls) == 3
    assert all(s == start and e == end for s, e in calls)


# ---------------------------------------------------------------------------
# test_validate — EG2: Parquet files are readable and schema-valid
# ---------------------------------------------------------------------------


def test_validate(tmp_path):
    """Metrics Parquet round-trips: identical columns and row count after write-read."""
    table = _metrics_table()
    path = tmp_path / "p1_metrics.parquet"
    ParquetWriter().write(table, path)

    read_back = pq.read_table(path)
    assert read_back.num_rows == table.num_rows
    assert set(read_back.column_names) == set(table.column_names)


def test_validate_traces_round_trip(tmp_path):
    """Traces Parquet preserves all seven expected columns."""
    table = _traces_table()
    ParquetWriter().write(table, tmp_path / "p2_traces.parquet")

    read_back = pq.read_table(tmp_path / "p2_traces.parquet")
    expected = {
        "trace_id",
        "span_id",
        "operation_name",
        "service_name",
        "start_time_us",
        "duration_us",
        "status_code",
    }
    assert expected.issubset(set(read_back.column_names))


def test_validate_logs_round_trip(tmp_path):
    """Logs Parquet preserves all six expected columns."""
    table = _logs_table()
    ParquetWriter().write(table, tmp_path / "p3_logs.parquet")

    read_back = pq.read_table(tmp_path / "p3_logs.parquet")
    expected = {"timestamp", "service_name", "severity", "body", "trace_id", "span_id"}
    assert expected.issubset(set(read_back.column_names))


def test_validate_parquet_writer_creates_parent_dirs(tmp_path):
    """ParquetWriter creates nested directories that don't exist yet."""
    path = tmp_path / "deep" / "nested" / "p1_metrics.parquet"
    ParquetWriter().write(_metrics_table(), path)
    assert path.exists()


# ---------------------------------------------------------------------------
# Concrete fetcher tests — mock HTTP, verify pa.Table schema + content
# ---------------------------------------------------------------------------


def _http_mock(payload: dict) -> MagicMock:
    """Context-manager mock for urllib.request.urlopen returning JSON payload."""
    cm = MagicMock()
    cm.__enter__.return_value = cm
    cm.read.return_value = json.dumps(payload).encode()
    return cm


class TestPrometheusMetricsFetcher:
    def test_fetch_returns_expected_columns(self, window_bounds):
        """Parses Prometheus query_range response into a four-column table."""
        start, end = window_bounds
        payload = {
            "data": {
                "result": [
                    {
                        "metric": {"__name__": "up", "job": "adservice"},
                        "values": [[1715000000.0, "0.42"]],
                    }
                ]
            }
        }
        with patch("urllib.request.urlopen", return_value=_http_mock(payload)):
            table = PrometheusMetricsFetcher("http://prometheus:9090").fetch(start, end)

        assert set(table.column_names) == {
            "timestamp",
            "metric_name",
            "value",
            "labels",
        }
        assert table.num_rows > 0

    def test_fetch_empty_result_produces_empty_table(self, window_bounds):
        """Prometheus returning no series yields a valid zero-row table."""
        start, end = window_bounds
        payload: dict[str, object] = {"data": {"result": []}}
        with patch("urllib.request.urlopen", return_value=_http_mock(payload)):
            table = PrometheusMetricsFetcher("http://prometheus:9090").fetch(start, end)

        assert table.num_rows == 0
        assert set(table.column_names) == {
            "timestamp",
            "metric_name",
            "value",
            "labels",
        }


class TestJaegerTracesFetcher:
    def test_fetch_returns_expected_columns(self, window_bounds):
        """Parses Jaeger traces response into a seven-column table."""
        start, end = window_bounds
        payload = {
            "data": [
                {
                    "traceID": "abc123",
                    "spans": [
                        {
                            "spanID": "def456",
                            "operationName": "/GetProduct",
                            "startTime": 1715000000000000,
                            "duration": 1500,
                            "tags": [{"key": "otel.status_code", "value": "OK"}],
                        }
                    ],
                }
            ]
        }
        with patch("urllib.request.urlopen", return_value=_http_mock(payload)):
            table = JaegerTracesFetcher("http://jaeger:16686").fetch(start, end)

        expected = {
            "trace_id",
            "span_id",
            "operation_name",
            "service_name",
            "start_time_us",
            "duration_us",
            "status_code",
        }
        assert expected == set(table.column_names)
        assert table.num_rows > 0

    def test_fetch_404_responses_skipped_silently(self, window_bounds):
        """Services returning HTTP 404 are skipped; result is an empty table."""
        start, end = window_bounds
        error = urllib.error.HTTPError("http://x", 404, "Not Found", {}, None)  # type: ignore[arg-type]
        with patch("urllib.request.urlopen", side_effect=error):
            table = JaegerTracesFetcher("http://jaeger:16686").fetch(start, end)

        assert table.num_rows == 0

    def test_fetch_non_404_http_error_propagates(self, window_bounds):
        """HTTP errors other than 404 (e.g. 503) are re-raised."""
        start, end = window_bounds
        error = urllib.error.HTTPError("http://x", 503, "Unavailable", {}, None)  # type: ignore[arg-type]
        with (
            patch("urllib.request.urlopen", side_effect=error),
            pytest.raises(urllib.error.HTTPError),
        ):
            JaegerTracesFetcher("http://jaeger:16686").fetch(start, end)


class TestOpenSearchLogsFetcher:
    def test_fetch_returns_expected_columns(self, window_bounds):
        """Parses OpenSearch hits into a six-column table."""
        start, end = window_bounds
        payload = {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "@timestamp": "2026-05-14T10:00:00Z",
                            "serviceName": "cartservice",
                            "severityText": "ERROR",
                            "body": "connection refused",
                            "traceId": "abc123",
                            "spanId": "def456",
                        }
                    }
                ]
            }
        }
        with patch("urllib.request.urlopen", return_value=_http_mock(payload)):
            table = OpenSearchLogsFetcher("http://opensearch:9200").fetch(start, end)

        assert set(table.column_names) == {
            "timestamp",
            "service_name",
            "severity",
            "body",
            "trace_id",
            "span_id",
        }
        assert table.num_rows == 1

    def test_fetch_empty_hits_produces_empty_table(self, window_bounds):
        """OpenSearch returning no hits yields a valid zero-row table."""
        start, end = window_bounds
        payload: dict[str, object] = {"hits": {"hits": []}}
        with patch("urllib.request.urlopen", return_value=_http_mock(payload)):
            table = OpenSearchLogsFetcher("http://opensearch:9200").fetch(start, end)

        assert table.num_rows == 0


class TestBuildDefaultCapture:
    def test_returns_telemetry_capture_with_correct_incident_id(self, manifest):
        """Factory wires a TelemetryCapture with three fetchers and the given incident_id."""
        capture = build_default_capture("s0-adhc-001", manifest)
        assert isinstance(capture, TelemetryCapture)
        assert capture._config.incident_id == "s0-adhc-001"
        assert capture._config.manifest is manifest


# ---------------------------------------------------------------------------
# CaptureReader — Spine Hardening: record → read → verify hash
# ---------------------------------------------------------------------------


@pytest.fixture()
def recorded_window(config, window_bounds):
    """Run a full capture with stubs and return (output_dir, TelemetryWindow)."""
    start, end = window_bounds
    window = TelemetryCapture(
        config=config, fetchers=_three_stubs(), writer=ParquetWriter()
    ).run(start, end)
    return config.output_dir, window


class TestCaptureReader:
    def test_hash_matches_original_recording(self, recorded_window):
        """CaptureVerification.hash_matches is True when manifest is untampered."""
        output_dir, window = recorded_window
        result = CaptureReader(output_dir).read(window.incident_id)
        assert isinstance(result, CaptureVerification)
        assert result.hash_matches

    def test_computed_hash_equals_stored_hash(self, recorded_window):
        """computed_hash and stored_hash are identical on a clean capture."""
        output_dir, window = recorded_window
        result = CaptureReader(output_dir).read(window.incident_id)
        assert result.computed_hash == result.stored_hash

    def test_stored_hash_equals_original_window_hash(self, recorded_window):
        """stored_hash loaded from manifest.json matches the original window hash."""
        output_dir, window = recorded_window
        result = CaptureReader(output_dir).read(window.incident_id)
        assert result.stored_hash == window.compute_window_hash()

    def test_window_schema_valid_no_validation_error(self, recorded_window):
        """TelemetryWindow reconstructed from manifest.json raises no ValidationError."""
        output_dir, window = recorded_window
        result = CaptureReader(output_dir).read(window.incident_id)
        try:
            _ = result.window
        except ValidationError as exc:
            pytest.fail(f"TelemetryWindow reconstruction raised ValidationError: {exc}")

    def test_window_incident_id_preserved(self, recorded_window):
        """Reconstructed TelemetryWindow carries the original incident_id."""
        output_dir, window = recorded_window
        result = CaptureReader(output_dir).read(window.incident_id)
        assert result.window.incident_id == window.incident_id

    def test_stream_row_counts_positive(self, recorded_window):
        """stream_row_counts reports >0 rows for all three Parquet streams."""
        output_dir, window = recorded_window
        result = CaptureReader(output_dir).read(window.incident_id)
        assert result.stream_row_counts["p1_metrics"] > 0
        assert result.stream_row_counts["p2_traces"] > 0
        assert result.stream_row_counts["p3_logs"] > 0

    def test_tampered_manifest_detected(self, recorded_window, tmp_path):
        """Altering manifest.json causes hash_matches to be False."""
        output_dir, window = recorded_window
        manifest_path = output_dir / window.incident_id / "manifest.json"
        data = json.loads(manifest_path.read_text())
        data["incident_id"] = "tampered-id"
        manifest_path.write_text(json.dumps(data))

        result = CaptureReader(output_dir).read(window.incident_id)
        assert not result.hash_matches

    def test_missing_incident_raises_file_not_found(self, tmp_path):
        """Reading a non-existent incident_id raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            CaptureReader(tmp_path).read("s0-nonexistent-001")
