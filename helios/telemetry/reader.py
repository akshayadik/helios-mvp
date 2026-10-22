"""Parquet capture reader — Spine Hardening utility (§3.7).

Loads the manifest.json and P1/P2/P3 Parquet files written by TelemetryCapture,
reconstructs the TelemetryWindow schema, and verifies the snapshot hash so that
captures recorded today remain verifiable years from now.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pyarrow.parquet as pq

from helios.schemas.telemetry import TelemetryWindow
from helios.telemetry.seal import check_seal
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance

__all__ = ["CaptureReader", "CaptureVerification"]


@dataclass(frozen=True)
class CaptureVerification:
    """Result of reading and verifying a single telemetry capture.

    hash_matches is True when the TelemetryWindow fields in manifest.json were
    not altered after recording. It does NOT cover Parquet bytes; that is the
    content seal (seal_checked / seal_error, see helios.telemetry.seal).
    `intact` requires both.
    """

    incident_id: str
    window: TelemetryWindow
    stored_hash: str
    computed_hash: str
    stream_row_counts: dict[str, int] = field(default_factory=dict)
    seal_checked: bool = False
    seal_error: str | None = None

    @property
    def hash_matches(self) -> bool:
        return self.stored_hash == self.computed_hash

    @property
    def content_intact(self) -> bool:
        return self.seal_checked and self.seal_error is None

    @property
    def intact(self) -> bool:
        return self.hash_matches and self.content_intact


class CaptureReader:
    """Reads a telemetry capture from disk and verifies its snapshot hash.

    Accepts the same output_dir used by CaptureConfig / TelemetryCapture so
    that both writer and reader use a consistent path convention:
        {output_dir}/{incident_id}/manifest.json
        {output_dir}/{incident_id}/p1_metrics.parquet
        {output_dir}/{incident_id}/p2_traces.parquet
        {output_dir}/{incident_id}/p3_logs.parquet
    """

    def __init__(self, output_dir: Path, seal_key: bytes | None = None) -> None:
        """seal_key enables the content-seal check; without it seal_checked is False."""
        self._output_dir = output_dir
        self._seal_key = seal_key

    def read(self, incident_id: str) -> CaptureVerification:
        """Load and verify a recorded capture; raise FileNotFoundError if absent."""
        incident_dir = self._output_dir / incident_id
        manifest_path = incident_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(
                f"No capture found for incident_id={incident_id!r} "
                f"(expected {manifest_path})"
            )

        raw: dict[str, object] = json.loads(manifest_path.read_text())
        stored_hash = str(raw.pop("window_hash"))
        raw.pop(
            "snapshot_hash", None
        )  # post-capture annotation; not a TelemetryWindow field

        window = TelemetryWindow(**raw)
        computed_hash = window.compute_window_hash()

        row_counts: dict[str, int] = {}
        for stream, attr in (
            ("p1_metrics", "p1_metrics_path"),
            ("p2_traces", "p2_traces_path"),
            ("p3_logs", "p3_logs_path"),
        ):
            path_val = getattr(window, attr)
            if path_val is not None:
                parquet_path = Path(str(path_val))
                if parquet_path.exists():
                    row_counts[stream] = pq.read_table(parquet_path).num_rows
                else:
                    row_counts[stream] = 0

        seal_error = None
        if self._seal_key is not None:
            seal_error = check_seal(incident_dir, window, self._seal_key)

        return CaptureVerification(
            incident_id=incident_id,
            window=window,
            stored_hash=stored_hash,
            computed_hash=computed_hash,
            stream_row_counts=row_counts,
            seal_checked=self._seal_key is not None,
            seal_error=seal_error,
        )
