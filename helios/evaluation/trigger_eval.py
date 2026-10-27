"""Post-run trigger classification (S2.1, design §5.4; owner decision D-c).

Every trigger is treated as genuine while systems run. Afterwards, outside the
pipelines, each one is labelled against the true injection time from the
signed ground truth:

- TRUE: a threshold trigger whose bucket ends after the injection (it fired in
  the bucket holding the injection, or later);
- FALSE: a threshold trigger whose whole bucket ends at or before the injection;
- NO_TRIGGER: the detector fell back (nothing crossed the threshold).

A trigger is stamped with the start of its bucket, and the detector cannot
resolve time finer than a bucket; without ``bucket_seconds`` the stamp itself
is compared (an instantaneous trigger). Delay runs to the end of the trigger
bucket, when the detector can first know.

Nothing here is on the run path: the pipelines never see these labels.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

import pandas as pd

from helios.telemetry.trigger import TriggerSource
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from helios.schemas.telemetry import TelemetryWindow
    from helios.telemetry.trigger import TriggerRecord

__all__ = [
    "TriggerLabel",
    "classify_trigger",
    "injection_inside_window",
    "trigger_delay_s",
]

HELIOS_ENABLE_TRIGGER_EVAL: bool = True


class TriggerLabel(StrEnum):
    """Outcome of one shared trigger, known only after scoring."""

    TRUE = "true"
    FALSE = "false"
    NO_TRIGGER = "no_trigger"


def classify_trigger(
    record: TriggerRecord, inject_time_s: float, *, bucket_seconds: float | None = None
) -> TriggerLabel:
    """Label one trigger against the true injection time."""
    if record.source == TriggerSource.FALLBACK:
        return TriggerLabel.NO_TRIGGER
    if bucket_seconds is None:
        early = record.trigger_time_s < inject_time_s
    else:
        early = record.trigger_time_s + bucket_seconds <= inject_time_s
    return TriggerLabel.FALSE if early else TriggerLabel.TRUE


def trigger_delay_s(
    record: TriggerRecord, inject_time_s: float, *, bucket_seconds: float | None = None
) -> float | None:
    """Seconds from the injection to when a true trigger is known; None otherwise."""
    label = classify_trigger(record, inject_time_s, bucket_seconds=bucket_seconds)
    if label != TriggerLabel.TRUE:
        return None
    return record.trigger_time_s + (bucket_seconds or 0) - inject_time_s


def injection_inside_window(window: TelemetryWindow, inject_time_s: float) -> bool:
    """Whether the injection lies inside the recorded window (S1.1 data check)."""
    start = pd.Timestamp(window.window_start_iso).timestamp()
    end = pd.Timestamp(window.window_end_iso).timestamp()
    return bool(start <= inject_time_s <= end)
