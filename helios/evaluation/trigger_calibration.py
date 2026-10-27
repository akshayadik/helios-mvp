"""Calibration of the shared detection trigger on build data (S2.1, design §5.3).

Build labels only; the confirmatory pool is refused. Everything here is fixed
before the calibration run:

- ``GRID``: candidate bucket sizes, thresholds and persistences. Warm-up is
  not tuned (``WARMUP_BUCKETS``), and no parameter refers to a position.
- Selection rule (owner limit D-e): among settings whose false-trigger rate is
  at most 5% on **each** build corpus, the smallest mean of the corpora's
  median delays; ties go to fewer no-triggers, then the higher threshold, then
  the higher persistence. ``None`` when nothing qualifies: the result then
  goes to the owner and the limit is never relaxed here.
- Crop-invariance audit: the selected setting is rerun on windows whose start
  is cropped by ``CROP_FRACTIONS`` of each window's slack (pre-injection span
  minus warm-up, longest persistence and one bucket). Every crop must keep the
  false rate at or below 5% and the median delay within one bucket.

A case whose injection lies outside its window is excluded and counted.
Reports hold aggregates only, never an incident ID.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pandas as pd

from helios.adapters.rcaeval import verify_ground_truth
from helios.evaluation.trigger_eval import (
    TriggerLabel,
    classify_trigger,
    injection_inside_window,
    trigger_delay_s,
)
from helios.schemas.telemetry import TelemetryWindow
from helios.telemetry.scope import scope_key
from helios.telemetry.trigger import WARMUP_BUCKETS
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from helios.telemetry.trigger import DetectorParams, TriggerRecord

__all__ = [
    "CORPORA",
    "CROP_FRACTIONS",
    "FALSE_RATE_LIMIT",
    "GRID",
    "ONSET_TOLERANCE_S",
    "CalibrationCase",
    "CorpusResult",
    "audit_passes",
    "crop_starts",
    "evaluate",
    "load_cases",
    "select",
]

HELIOS_ENABLE_TRIGGER_CALIBRATION: bool = True

FALSE_RATE_LIMIT = 0.05  # owner decision D-e: at most 5% on each build corpus
GRID: dict[str, tuple[float, ...]] = {
    "bucket_seconds": (15, 30, 60),
    "threshold": (3, 4, 5, 6, 8, 10, 12),
    "persistence": (1, 2, 3),
}
CROP_FRACTIONS: tuple[float, ...] = (0.25, 0.4, 0.6)
# A trigger whose bucket ends up to 60 s before the recorded injection counts
# as true (owner decision 2026-10-27, deviation entry 49): RCAEval's recorded
# injection times lag the visible onset by up to about a minute.
ONSET_TOLERANCE_S = 60
CORPORA: dict[str, tuple[str, str, str]] = {
    # corpus: (captures dir, label-free manifest, signed ground truth)
    "rcaeval_build": (
        "data/rcaeval/build",
        "data/rcaeval/build_manifest.json",
        "data/rcaeval/ground_truth_build.json",
    ),
    "otel_build": (
        "data/otel/build",
        "data/otel/build_manifest.json",
        "data/otel/ground_truth_build.json",
    ),
}
_DIGITS = 6


@dataclass(frozen=True)
class CalibrationCase:
    """One build window with its label (calibration only)."""

    incident_id: str
    window: TelemetryWindow
    inject_time_s: float
    root_cause: str
    fault: str | None = None


@dataclass(frozen=True)
class CorpusResult:
    """Aggregate trigger outcome of one setting on one corpus."""

    n: int
    true: int
    false: int
    no_trigger: int
    excluded: int
    median_delay_s: float | None
    root_among_suspects: int
    false_by_fault: dict[str, int] = field(default_factory=dict)

    @property
    def false_rate(self) -> float:
        return self.false / self.n if self.n else 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "true": self.true,
            "false": self.false,
            "no_trigger": self.no_trigger,
            "excluded": self.excluded,
            "false_rate": round(self.false_rate, _DIGITS),
            "median_delay_s": self.median_delay_s,
            "root_among_suspects": self.root_among_suspects,
            "false_by_fault": dict(sorted(self.false_by_fault.items())),
        }


def _seconds(value: Any) -> float:
    if isinstance(value, int | float):
        return float(value)
    return float(pd.Timestamp(str(value)).timestamp())


def load_cases(corpus: str, *, root: Path, key: bytes) -> list[CalibrationCase]:
    """Build cases of a corpus with their signed labels; the pool is refused."""
    if corpus not in CORPORA:
        raise ValueError(f"calibration uses build corpora only, not {corpus!r}")
    captures, manifest, truth = (root / p for p in CORPORA[corpus])
    order = json.loads(manifest.read_text(encoding="utf-8"))["case_order"]
    labels = verify_ground_truth(truth, key)
    cases = []
    for incident_id in order:
        raw = json.loads(
            (captures / incident_id / "manifest.json").read_text(encoding="utf-8")
        )
        raw.pop("window_hash", None)
        raw.pop("snapshot_hash", None)
        label = labels[incident_id]
        cases.append(
            CalibrationCase(
                incident_id=incident_id,
                window=TelemetryWindow(**raw),
                inject_time_s=_seconds(label["inject_time"]),
                root_cause=str(label["root_cause_service"]),
                fault=str(label["fault"]) if corpus == "otel_build" else None,
            )
        )
    return cases


def evaluate(
    records: Sequence[TriggerRecord],
    cases: Sequence[CalibrationCase],
    *,
    bucket_seconds: float | None = None,
) -> CorpusResult:
    """Counts of true, false and missed triggers over the usable cases."""
    labels: dict[TriggerLabel, int] = dict.fromkeys(TriggerLabel, 0)
    delays: list[float] = []
    hits = excluded = 0
    false_by_fault: dict[str, int] = {}
    for record, case in zip(records, cases, strict=True):
        if not injection_inside_window(case.window, case.inject_time_s):
            excluded += 1
            continue
        label = classify_trigger(
            record,
            case.inject_time_s,
            bucket_seconds=bucket_seconds,
            tolerance_s=ONSET_TOLERANCE_S,
        )
        labels[label] += 1
        delay = trigger_delay_s(
            record,
            case.inject_time_s,
            bucket_seconds=bucket_seconds,
            tolerance_s=ONSET_TOLERANCE_S,
        )
        if delay is not None:
            delays.append(delay)
        root = scope_key(case.root_cause)
        hits += any(scope_key(s) == root for s in record.suspects)
        if case.fault is not None:
            false_by_fault[case.fault] = false_by_fault.get(case.fault, 0) + (
                label == TriggerLabel.FALSE
            )
    return CorpusResult(
        n=sum(labels.values()),
        true=labels[TriggerLabel.TRUE],
        false=labels[TriggerLabel.FALSE],
        no_trigger=labels[TriggerLabel.NO_TRIGGER],
        excluded=excluded,
        median_delay_s=(
            round(float(statistics.median(delays)), _DIGITS) if delays else None
        ),
        root_among_suspects=hits,
        false_by_fault=false_by_fault,
    )


def select(
    results: Mapping[DetectorParams, Mapping[str, CorpusResult]],
) -> DetectorParams | None:
    """The design §5.3 rule; None when no setting meets the limit on every corpus."""
    qualified = []
    for params, by_corpus in results.items():
        corpora = list(by_corpus.values())
        if any(r.false_rate > FALSE_RATE_LIMIT for r in corpora):
            continue
        if any(r.median_delay_s is None for r in corpora):
            continue
        delay = statistics.mean(float(r.median_delay_s or 0) for r in corpora)
        misses = sum(r.no_trigger for r in corpora)
        qualified.append(
            ((delay, misses, -params.threshold, -params.persistence), params)
        )
    if not qualified:
        return None
    return min(qualified, key=lambda item: item[0])[1]


def crop_starts(case: CalibrationCase, bucket_seconds: int) -> list[float]:
    """Crop offsets for the audit, taken from the window's slack only."""
    start = pd.Timestamp(case.window.window_start_iso).timestamp()
    reserve = (WARMUP_BUCKETS + int(max(GRID["persistence"])) + 1) * bucket_seconds
    slack = case.inject_time_s - start - reserve
    if slack <= 0:
        return []
    return [round(f * slack, _DIGITS) for f in CROP_FRACTIONS]


def audit_passes(
    uncropped: CorpusResult,
    cropped: Mapping[float, CorpusResult],
    *,
    bucket_seconds: int,
) -> bool:
    """Every crop keeps the limit and moves the median delay by at most a bucket."""
    for result in cropped.values():
        if result.false_rate > FALSE_RATE_LIMIT:
            return False
        if result.median_delay_s is None or uncropped.median_delay_s is None:
            return False
        if abs(result.median_delay_s - uncropped.median_delay_s) > bucket_seconds:
            return False
    return True
