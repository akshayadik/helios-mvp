"""Signal type of the trigger (S2.5 design §5.1, owner decision M-a).

MAHC's priors are keyed on what kind of signal fired, never on the fault
label. The frozen detector pools a service's series into one score and does
not say which crossed; this read-only step names it: for the trigger's top
suspect, the metric series with the largest causal z at the trigger bucket
(the detector's own ``causal_z``), sorted by keyword into resource, latency or
error. A fallback trigger, a window without metrics or a series name no word
matches is UNCLASSIFIED. The detector and its parameters are unchanged.
"""

from __future__ import annotations

import math
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from helios.graph.anomaly_intensity import bucket_count, named_metric_series
from helios.telemetry.trigger import TriggerSource, causal_z
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from helios.schemas.telemetry import TelemetryWindow
    from helios.telemetry.trigger import TriggerRecord

__all__ = [
    "ERROR_WORDS",
    "LATENCY_WORDS",
    "RESOURCE_WORDS",
    "SignalType",
    "classify",
    "signal_type",
]

HELIOS_ENABLE_SIGNAL_TYPE: bool = True

# Fixed with the S2.5 pre-run deviation entry; checked in this order.
ERROR_WORDS: tuple[str, ...] = ("error", "fail", "5xx")
LATENCY_WORDS: tuple[str, ...] = ("latency", "duration", "response_time")
RESOURCE_WORDS: tuple[str, ...] = (
    "cpu",
    "mem",
    "memory",
    "gc",
    "thread",
    "fd",
    "disk",
    "socket",
)


class SignalType(StrEnum):
    """What kind of signal set off the trigger."""

    RESOURCE = "resource"
    LATENCY = "latency"
    ERROR = "error"
    UNCLASSIFIED = "unclassified"


def classify(series_name: str) -> SignalType:
    """Keyword type of a metric name: error, then latency, then resource."""
    name = series_name.lower()
    for words, kind in (
        (ERROR_WORDS, SignalType.ERROR),
        (LATENCY_WORDS, SignalType.LATENCY),
        (RESOURCE_WORDS, SignalType.RESOURCE),
    ):
        if any(w in name for w in words):
            return kind
    return SignalType.UNCLASSIFIED


def signal_type(
    window: TelemetryWindow,
    trigger: TriggerRecord,
    *,
    root: Path,
    bucket_seconds: int,
) -> SignalType:
    """The type of the top suspect's strongest series at the trigger bucket."""
    if (
        trigger.source == TriggerSource.FALLBACK
        or not trigger.suspects
        or window.p1_metrics_path is None
    ):
        return SignalType.UNCLASSIFIED
    path = Path(window.p1_metrics_path)
    metrics = pd.read_parquet(path if path.is_absolute() else root / path)
    n = bucket_count(window.window_start_iso, window.window_end_iso, bucket_seconds)
    start = pd.Timestamp(window.window_start_iso).timestamp()
    bucket = int(math.floor((trigger.trigger_time_s - start) / bucket_seconds))
    if not 0 <= bucket < n:
        return SignalType.UNCLASSIFIED
    series = named_metric_series(
        metrics, window.window_start_iso, n, bucket_seconds, fold_histograms=True
    ).get(trigger.suspects[0], [])
    best: tuple[float, str] | None = None
    for name, s in series:
        z = float(
            causal_z(s.values, count_series=s.is_count, upward_only=s.upward_only)[
                bucket
            ]
        )
        if np.isfinite(z) and (best is None or (z, name) > best):
            best = (z, name)
    return SignalType.UNCLASSIFIED if best is None else classify(best[1])
