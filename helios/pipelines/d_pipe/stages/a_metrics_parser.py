"""Stage A: Telemetry parser -- aggregate, difference, error + latency extraction."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pandas as pd

from helios.pipelines.d_pipe.dpipe_config import INF_MIDPOINT, LE_BOUNDARIES
from helios.vcl import VCLFlag  # noqa: F401 -- flag-guard compliance

HTTP_METRIC: str = "http_server_duration_milliseconds_bucket"
GRPC_METRIC: str = "rpc_server_duration_milliseconds_bucket"
HTTP_ERROR_CODES: frozenset[str] = frozenset({"500", "503"})
GRPC_ERROR_CODES: frozenset[str] = frozenset({"12", "13", "14"})

# Label key that identifies the service -- confirmed from parquet inspection (Step 1).
_SVC_LABEL_KEY = "job"

# HTTP status code label key -- real data uses "http_status_code";
# test synthetic data uses "http_response_status_code". Check both.
_HTTP_STATUS_KEYS: tuple[str, ...] = ("http_response_status_code", "http_status_code")


@dataclass(frozen=True)
class ParsedMetrics:
    error_deltas: dict[str, list[float]]
    latency_means: dict[str, list[float]]
    steps: list[float]
    p1_services: list[str]


def _diff_series(agg: pd.Series) -> list[float]:
    """Compute delta series; set NaN where delta < 0 (counter reset)."""
    agg_sorted = agg.sort_index()
    deltas: list[float] = []
    prev = agg_sorted.iloc[0]
    for val in agg_sorted.iloc[1:]:
        diff = val - prev
        deltas.append(float("nan") if diff < 0 else float(diff))
        prev = val
    return deltas


def _histogram_mean(bucket_counts: list[float]) -> float:
    total = bucket_counts[-1]
    if total == 0:
        return float("nan")
    weighted = 0.00
    prev_count: float = 0
    prev_le: float = 0
    for i, le in enumerate(LE_BOUNDARIES):
        count_in_bin = bucket_counts[i] - prev_count
        midpoint = (prev_le + le) / 2
        weighted += count_in_bin * midpoint
        prev_count = bucket_counts[i]
        prev_le = le
    inf_count = total - bucket_counts[len(LE_BOUNDARIES) - 1]
    weighted += inf_count * INF_MIDPOINT
    return weighted / total


def _extract_http_status(labels_dict: dict[str, str]) -> str:
    """Return HTTP status code from labels, checking both known key variants."""
    for key in _HTTP_STATUS_KEYS:
        val = labels_dict.get(key, "")
        if val:
            return val
    return ""


class MetricsParser:
    def parse(self, df: pd.DataFrame) -> ParsedMetrics:
        df = df.copy()
        df["labels_dict"] = df["labels"].apply(json.loads)
        df["service"] = df["labels_dict"].apply(
            lambda d: str(d.get(_SVC_LABEL_KEY, "")).split("/")[-1]
        )
        df["le"] = df["labels_dict"].apply(lambda d: str(d.get("le", "")))
        df["http_status"] = df["labels_dict"].apply(_extract_http_status)
        df["grpc_status"] = df["labels_dict"].apply(
            lambda d: str(d.get("rpc_grpc_status_code", ""))
        )

        services = sorted(df["service"].dropna().unique())
        timestamps = sorted(df["timestamp"].unique())

        error_deltas: dict[str, list[float]] = {}
        latency_means: dict[str, list[float]] = {}

        for svc in services:
            svc_df = df[df["service"] == svc]

            # Error extraction: le=+Inf rows matching error status codes
            http_err = svc_df[
                (svc_df["metric_name"] == HTTP_METRIC)
                & (svc_df["le"] == "+Inf")
                & (svc_df["http_status"].isin(HTTP_ERROR_CODES))
            ]
            grpc_err = svc_df[
                (svc_df["metric_name"] == GRPC_METRIC)
                & (svc_df["le"] == "+Inf")
                & (svc_df["grpc_status"].isin(GRPC_ERROR_CODES))
            ]
            err_combined = pd.concat([http_err, grpc_err])
            if not err_combined.empty:
                agg_err = err_combined.groupby("timestamp")["value"].sum()
                agg_err = agg_err.reindex(timestamps, fill_value=0)
                error_deltas[svc] = _diff_series(agg_err)

            # Latency extraction: one mean per timestamp from histogram buckets
            lat_metric = (
                HTTP_METRIC
                if not svc_df[svc_df["metric_name"] == HTTP_METRIC].empty
                else GRPC_METRIC
            )
            lat_df = svc_df[svc_df["metric_name"] == lat_metric]
            means: list[float] = []
            for ts in timestamps[1:]:
                ts_df = lat_df[lat_df["timestamp"] == ts]
                if ts_df.empty:
                    means.append(float("nan"))
                    continue
                agg = ts_df.groupby("le")["value"].sum()
                bucket_counts = [float(agg.get(str(le), 0)) for le in LE_BOUNDARIES]
                bucket_counts.append(float(agg.get("+Inf", 0)))
                means.append(_histogram_mean(bucket_counts))
            if means:
                latency_means[svc] = means

        steps = list(timestamps[1:])
        p1_services = [s for s in services if s in error_deltas or s in latency_means]

        return ParsedMetrics(
            error_deltas=error_deltas,
            latency_means=latency_means,
            steps=steps,
            p1_services=p1_services,
        )
