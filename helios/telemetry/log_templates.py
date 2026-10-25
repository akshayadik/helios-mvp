"""Log templates and template features per window (S1.4).

Drain3 turns P3 log bodies into templates (``connection to <IP> failed`` for
every connection failure). The features are label-free and use only the
window's own logs: template counts per service per time bucket, and novelty,
the templates a service emits for the first time in the window in that bucket.
No injection time, case name or cross-case vocabulary is used, so a
confirmatory window is processed exactly like a build window.

Determinism ("templates stable across reruns"):

- Drain's clusters depend on message order, so messages are mined in one
  canonical order (time, service, body), not in file order.
- A cluster's template can widen as later messages arrive; each message is
  assigned its cluster's *final* template.
- Template IDs are SHA-256 prefixes of the template text, not Drain's
  counters, so the same template has the same ID in every window and run.

The Drain parameters below are Drain3's defaults (sim_th 0.4, depth 4) plus
masking for addresses, UUIDs, hex strings and numbers. drain3 is pinned
exactly in pyproject.toml; a change of version or parameter changes the
features and is a deviation entry.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
import pyarrow.parquet as pq
from drain3 import TemplateMiner
from drain3.masking import MaskingInstruction
from drain3.template_miner_config import TemplateMinerConfig

from helios.schemas.telemetry import EvaluationPhase
from helios.telemetry.pool_lock import require_unlocked
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Callable

    from helios.schemas.telemetry import TelemetryWindow

__all__ = [
    "BUCKET_SECONDS",
    "DRAIN_DEPTH",
    "DRAIN_SIM_TH",
    "MASKS",
    "LogTemplateFeatures",
    "extract_templates",
    "features_for_window",
    "template_id",
]

HELIOS_ENABLE_LOG_TEMPLATES: bool = True

DRAIN_SIM_TH = 0.4
DRAIN_DEPTH = 4
BUCKET_SECONDS = 30

# (regex, mask name), applied in this order before Drain sees a message.
MASKS: tuple[tuple[str, str], ...] = (
    (
        r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?",
        "TIME",
    ),
    (r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b", "UUID"),
    (r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "EMAIL"),
    (r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b", "IP"),
    (r"\b0x[0-9a-fA-F]+\b", "HEX"),
    (r"\b[0-9a-fA-F]{16,}\b", "HEX"),
    (r"(?<![\w.])\d+(?:\.\d+)?(?:ns|us|\u00b5s|\u03bcs|ms|s|m|h)\b", "DUR"),
    (r"(?<![\w.])[-+]?\d+(?:\.\d+)?(?![\w.])", "NUM"),
)

_TEMPLATE_COLUMNS = ["template_id", "template", "count"]
_COUNT_COLUMNS = ["bucket_start", "service", "template_id", "count"]
_NOVELTY_COLUMNS = ["bucket_start", "service", "novel_templates", "novel_lines"]


def template_id(template: str) -> str:
    """Stable ID of a template: the first 12 hex digits of its SHA-256."""
    return hashlib.sha256(template.encode("utf-8")).hexdigest()[:12]


def _miner() -> TemplateMiner:
    config = TemplateMinerConfig()
    config.drain_sim_th = DRAIN_SIM_TH
    config.drain_depth = DRAIN_DEPTH
    config.masking_instructions = [MaskingInstruction(rx, name) for rx, name in MASKS]
    return TemplateMiner(persistence_handler=None, config=config)


@dataclass(frozen=True)
class LogTemplateFeatures:
    """Template features of one window.

    templates: template_id, template, count (all services), sorted by ID.
    counts: lines per (bucket_start, service, template_id).
    novelty: per (bucket_start, service), how many templates the service
        emits for the first time in the window, and how many lines they have.
        A service's first active bucket is novel by construction; consumers
        treat it as warm-up.
    skipped_lines: lines with an empty body or no parsable timestamp.
    """

    templates: pd.DataFrame
    counts: pd.DataFrame
    novelty: pd.DataFrame
    skipped_lines: int

    def digest(self) -> str:
        """SHA-256 over every feature value; equal digests = identical features."""
        payload = {
            "templates": self.templates.to_dict(orient="split"),
            "counts": self.counts.to_dict(orient="split"),
            "novelty": self.novelty.to_dict(orient="split"),
            "skipped_lines": self.skipped_lines,
        }
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _empty(skipped: int) -> LogTemplateFeatures:
    return LogTemplateFeatures(
        templates=pd.DataFrame(columns=_TEMPLATE_COLUMNS),
        counts=pd.DataFrame(columns=_COUNT_COLUMNS),
        novelty=pd.DataFrame(columns=_NOVELTY_COLUMNS),
        skipped_lines=skipped,
    )


def extract_templates(
    logs: pd.DataFrame,
    window_start_iso: str,
    bucket_seconds: int = BUCKET_SECONDS,
) -> LogTemplateFeatures:
    """Mine templates from P3 log rows (timestamp, service_name, body).

    Buckets are aligned to the window start. The input row order does not
    affect the result.
    """
    if bucket_seconds <= 0:
        raise ValueError("bucket_seconds must be positive")
    stamps = pd.to_datetime(
        logs["timestamp"], utc=True, format="ISO8601", errors="coerce"
    )
    frame = pd.DataFrame(
        {
            "ts": stamps,
            "service": logs["service_name"].astype("string").fillna("").to_numpy(),
            "body": logs["body"].astype("string").fillna("").str.strip().to_numpy(),
        }
    )
    usable = frame["ts"].notna() & (frame["body"] != "")
    skipped = int((~usable).sum())
    frame = frame[usable].sort_values(["ts", "service", "body"], kind="stable")
    if frame.empty:
        return _empty(skipped)

    miner = _miner()
    clusters = [miner.add_log_message(b)["cluster_id"] for b in frame["body"]]
    final = {c.cluster_id: c.get_template() for c in miner.drain.clusters}
    frame["template"] = [final[c] for c in clusters]
    frame["template_id"] = frame["template"].map(template_id)

    start = pd.Timestamp(window_start_iso)
    start = (
        start.tz_localize("UTC") if start.tzinfo is None else start.tz_convert("UTC")
    )
    width = pd.Timedelta(seconds=bucket_seconds)
    frame["bucket_start"] = (start + ((frame["ts"] - start) // width) * width).map(
        lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    templates = (
        frame.groupby(["template_id", "template"], sort=True)
        .size()
        .reset_index(name="count")
    )
    counts = (
        frame.groupby(["bucket_start", "service", "template_id"], sort=True)
        .size()
        .reset_index(name="count")
    )
    first = counts.groupby(["service", "template_id"])["bucket_start"].transform("min")
    novel = counts[counts["bucket_start"] == first]
    novelty = (
        counts[["bucket_start", "service"]]
        .drop_duplicates()
        .merge(
            novel.groupby(["bucket_start", "service"])
            .agg(novel_templates=("template_id", "size"), novel_lines=("count", "sum"))
            .reset_index(),
            on=["bucket_start", "service"],
            how="left",
        )
        .fillna({"novel_templates": 0, "novel_lines": 0})
        .astype({"novel_templates": "int64", "novel_lines": "int64"})
        .sort_values(["bucket_start", "service"])
        .reset_index(drop=True)
    )
    return LogTemplateFeatures(
        templates=templates.reset_index(drop=True),
        counts=counts.reset_index(drop=True),
        novelty=novelty,
        skipped_lines=skipped,
    )


def features_for_window(
    window: TelemetryWindow,
    root: Path,
    bucket_seconds: int = BUCKET_SECONDS,
    pool_lock: Callable[[str], None] = require_unlocked,
) -> LogTemplateFeatures | None:
    """Template features of a sealed window; None when it has no logs.

    ``root`` resolves repo-relative window paths. Confirmatory windows go
    through the pool lock first, as in CaptureReader.
    """
    if window.evaluation_phase == EvaluationPhase.CONFIRMATORY:
        pool_lock(window.incident_id)
    if window.p3_logs_path is None:
        return None
    path = Path(window.p3_logs_path)
    path = path if path.is_absolute() else root / path
    logs = pq.read_table(path, columns=["timestamp", "service_name", "body"])
    return extract_templates(logs.to_pandas(), window.window_start_iso, bucket_seconds)
