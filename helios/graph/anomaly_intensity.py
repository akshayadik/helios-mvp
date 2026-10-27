"""Per-service anomaly intensity per time bucket (input to causal UEG-C edges).

Label-free: every value comes from the window's own metrics and logs, with no
injection time, case name or other case. Buckets are aligned to the window
start, as in S1.4 (helios.telemetry.log_templates).

- Metrics: each series (metric name + labels) is averaged per bucket;
  counters are differenced; each series becomes a robust z-score (median,
  MAD) over the window; a service's metric intensity is the max |z| over its
  series per bucket.
- Logs: per-bucket line count and lines of templates new to the service, each
  robust-z-scored the same way.
- Service intensity = max of the two; buckets with no evidence are 0.
"""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, NamedTuple

import numpy as np
import pandas as pd

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from helios.telemetry.log_templates import LogTemplateFeatures

__all__ = [
    "COUNTER_SUFFIXES",
    "COUNT_METRICS",
    "Series",
    "bucket_count",
    "combine",
    "log_intensity",
    "log_series",
    "metric_intensity",
    "metric_series",
    "robust_z",
    "service_of",
]

COUNTER_SUFFIXES: tuple[str, ...] = ("_total", "_count", "_sum", "_bucket")
# Plain per-step counts (RCAEval ``error``): event counts, like differenced counters.
COUNT_METRICS: frozenset[str] = frozenset({"error"})


class Series(NamedTuple):
    """One raw bucket series; ``is_count`` marks event counts (Poisson noise)."""

    values: np.ndarray
    is_count: bool


_MAD_TO_SIGMA = 1.4826  # MAD of a normal distribution in units of sigma


def _ts(iso: str) -> pd.Timestamp:
    t = pd.Timestamp(iso)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def bucket_count(
    window_start_iso: str, window_end_iso: str, bucket_seconds: int
) -> int:
    """Number of buckets covering the window (at least one)."""
    span = float((_ts(window_end_iso) - _ts(window_start_iso)).total_seconds())
    return max(1, math.ceil(span / bucket_seconds))


def robust_z(values: np.ndarray) -> np.ndarray:
    """|z| per point from median and MAD (std if MAD is zero); NaN stays NaN."""
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return np.full_like(values, np.nan)
    centre = float(np.median(finite))
    scale = _MAD_TO_SIGMA * float(np.median(np.abs(finite - centre)))
    if scale <= 0:
        scale = float(np.std(finite))
    if scale <= 0:
        return np.where(np.isfinite(values), 0, np.nan).astype("float64")
    return np.abs(values - centre) / scale


def service_of(labels: dict[str, str]) -> str:
    """Service of a metric series: `service_name` label, else the last part of `job`."""
    name = labels.get("service_name") or str(labels.get("job", "")).split("/")[-1]
    return str(name).strip()


def _max_over(series: list[np.ndarray], n: int) -> np.ndarray:
    stacked = np.vstack(series) if series else np.full((1, n), np.nan)
    with np.errstate(all="ignore"):
        out = np.nanmax(np.where(np.isfinite(stacked), stacked, -np.inf), axis=0)
    return np.where(np.isfinite(out), out, 0).astype("float64")


def metric_series(
    metrics: pd.DataFrame,
    window_start_iso: str,
    n_buckets: int,
    bucket_seconds: int,
) -> dict[str, list[Series]]:
    """Raw bucket means per series (metric name + labels), counters differenced.

    Services and series are in sorted order; buckets with no sample are NaN.
    """
    if metrics.empty:
        return {}
    start = _ts(window_start_iso).timestamp()
    frame = pd.DataFrame(
        {
            "bucket": np.floor(
                (metrics["timestamp"].astype("float64") - start) / bucket_seconds
            ),
            "metric": metrics["metric_name"].astype("string").fillna(""),
            "labels": metrics["labels"].astype("string").fillna("{}"),
            "value": pd.to_numeric(metrics["value"], errors="coerce"),
        }
    )
    frame = frame[(frame["bucket"] >= 0) & (frame["bucket"] < n_buckets)]
    frame = frame[np.isfinite(frame["value"])]
    if frame.empty:
        return {}
    services = {lab: service_of(json.loads(lab)) for lab in frame["labels"].unique()}
    frame["service"] = frame["labels"].map(services)
    frame = frame[frame["service"] != ""]
    means = frame.groupby(["service", "metric", "labels", "bucket"], sort=True)[
        "value"
    ].mean()
    per_service: dict[str, list[Series]] = {}
    for (service, metric, _labels), series in means.groupby(level=[0, 1, 2], sort=True):
        dense = np.full(n_buckets, np.nan)
        dense[series.index.get_level_values("bucket").astype(int)] = series.to_numpy()
        counter = str(metric).endswith(COUNTER_SUFFIXES)
        if counter:
            dense = np.concatenate(([np.nan], np.diff(dense)))
        per_service.setdefault(str(service), []).append(
            Series(dense, counter or str(metric) in COUNT_METRICS)
        )
    return dict(sorted(per_service.items()))


def metric_intensity(
    metrics: pd.DataFrame,
    window_start_iso: str,
    n_buckets: int,
    bucket_seconds: int,
) -> dict[str, np.ndarray]:
    """Metric intensity per service from P1 rows (timestamp, metric_name, value, labels)."""
    per_service = metric_series(metrics, window_start_iso, n_buckets, bucket_seconds)
    return {
        s: _max_over([robust_z(x.values) for x in v], n_buckets)
        for s, v in per_service.items()
    }


def log_series(
    features: LogTemplateFeatures,
    window_start_iso: str,
    n_buckets: int,
    bucket_seconds: int,
) -> dict[str, list[Series]]:
    """Per service: lines and novel-template lines per bucket (both counts; 0 if none)."""
    if features.novelty.empty:
        return {}
    start = _ts(window_start_iso)
    lines = features.counts.groupby(["service", "bucket_start"])["count"].sum()
    novel = features.novelty.set_index(["service", "bucket_start"])["novel_lines"]
    out: dict[str, list[Series]] = {}
    for service in sorted(features.novelty["service"].unique()):
        if not str(service).strip():
            continue  # lines without a service name are not a service (as metrics)
        rows: list[Series] = []
        for source in (lines, novel):
            part = source.loc[service]
            idx = (
                (
                    pd.to_datetime(part.index, utc=True, format="%Y-%m-%dT%H:%M:%SZ")
                    - start
                ).total_seconds()
                // bucket_seconds
            ).astype(int)
            dense = np.zeros(n_buckets)
            keep = (idx >= 0) & (idx < n_buckets)
            dense[idx[keep]] = part.to_numpy(dtype="float64")[keep]
            rows.append(Series(dense, True))
        out[str(service)] = rows
    return out


def log_intensity(
    features: LogTemplateFeatures,
    window_start_iso: str,
    n_buckets: int,
    bucket_seconds: int,
) -> dict[str, np.ndarray]:
    """Log intensity per service from S1.4 template features (same buckets)."""
    per_service = log_series(features, window_start_iso, n_buckets, bucket_seconds)
    return {
        s: _max_over([robust_z(x.values) for x in v], n_buckets)
        for s, v in per_service.items()
    }


def combine(*parts: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Bucket-wise max over the given intensity maps, per service."""
    services = sorted({s for part in parts for s in part})
    return {
        s: np.max(np.vstack([p[s] for p in parts if s in p]), axis=0) for s in services
    }
