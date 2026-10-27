"""Shared detection trigger (S2.1): one label-free start point for every system.

Design: docs/sprints/s2-reasoning/s2_1_dpipe_trigger_design.md (owner decisions
D-a … D-f). HELIOS and every baseline receive the same trigger record for an
incident; nothing else gives a system a time anchor.

How it decides (``trigger-v1``):

- Signals come from metrics and logs only (never traces: the RCAEval build
  corpus has none, so a trace signal could not be calibrated for the pool).
  Each series is bucketed (helios.graph.anomaly_intensity) and every bucket is
  scored against that series' own **past** only (``causal_z``): the detector
  never looks ahead, and no parameter refers to a position in the window.
- A service's score per bucket is its largest series score. The trigger fires
  at the first bucket where an in-scope service stays at or above the
  threshold for ``persistence`` buckets; the services above it then are the
  suspects. Out-of-scope services (helios.telemetry.scope) never decide
  anything; when they cross at the trigger they are recorded as ``context``.
- If nothing fires, the trigger falls back to the most anomalous bucket
  (``FALLBACK``); every case is still analysed.

The trigger has no VCL flag: it is shared evaluation input, like the window,
given identically to every variant and baseline (design §4).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict

from helios.graph.anomaly_intensity import (
    Series,
    bucket_count,
    log_series,
    metric_series,
)
from helios.graph.khop_pruner import SEED_COUNT
from helios.telemetry.log_templates import features_for_window
from helios.telemetry.scope import in_scope, scope_digest
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.utils import canonical_json

if TYPE_CHECKING:
    from helios.schemas.telemetry import TelemetryWindow

__all__ = [
    "DETECTOR_PARAMS_PATH",
    "DETECTOR_VERSION",
    "REL_FLOOR",
    "SUSPECT_COUNT",
    "WARMUP_BUCKETS",
    "Z_CAP",
    "DetectorParams",
    "ExternalTriggerRefusedError",
    "ProvisionalParametersError",
    "ServiceScores",
    "TriggerRecord",
    "TriggerSource",
    "causal_z",
    "detect",
    "detector_hash",
    "load_detector_params",
    "load_external_triggers",
    "robust_scale",
    "service_scores",
]

HELIOS_ENABLE_TRIGGER: bool = True

DETECTOR_VERSION = "trigger-v1"
WARMUP_BUCKETS = 4  # fixed before calibration, never tuned (design §5.3)
REL_FLOOR = 0.05  # a gauge's scale is at least 5% of its level
Z_CAP = 50  # numeric guard only; never stands in for a missing scale
SUSPECT_COUNT = SEED_COUNT
_MAD_TO_SIGMA = 1.4826
_TIME_DIGITS = 6
DETECTOR_PARAMS_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "frozen" / "trigger_detector.json"
)
_PARAM_KEYS = frozenset({"bucket_seconds", "threshold", "persistence", "provisional"})


class ExternalTriggerRefusedError(RuntimeError):
    """A confirmatory run was given externally supplied triggers (D-a)."""


class ProvisionalParametersError(RuntimeError):
    """A confirmatory run was given parameters not yet frozen by calibration."""


class TriggerSource(StrEnum):
    """How a trigger was reached."""

    THRESHOLD = "threshold"  # a signal crossed the frozen threshold
    FALLBACK = "fallback"  # nothing crossed: the most anomalous bucket
    EXTERNAL = "external"  # supplied from outside (exploratory runs only)


@dataclass(frozen=True)
class DetectorParams:
    """Frozen detector parameters (calibrated on build data, S2-M7-EVAL01)."""

    bucket_seconds: int
    threshold: float
    persistence: int
    provisional: bool


class TriggerRecord(BaseModel):
    """The one time anchor every system receives for an incident."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    incident_id: str
    trigger_time_s: float
    suspects: tuple[str, ...]
    context: tuple[str, ...]
    source: TriggerSource
    detector_hash: str


@dataclass(frozen=True)
class ServiceScores:
    """Max causal |z| per service (rows, sorted) and bucket (columns)."""

    services: list[str]
    z: np.ndarray
    start_s: float


def robust_scale(history: np.ndarray, *, count_series: bool) -> float:
    """Scale of a reference sample: robust spread with floors (0 = no scale).

    Spread = 1.4826 MAD, else std; floored at ``REL_FLOOR`` of the median and,
    for count series, at the Poisson noise sqrt(max(median, 1)). Shared by the
    trigger and D-pipe's trigger split, so both judge a shift the same way.
    """
    centre = float(np.median(history))
    spread = _MAD_TO_SIGMA * float(np.median(np.abs(history - centre)))
    if spread == 0:
        spread = float(np.std(history))
    floor = REL_FLOOR * abs(centre)
    if count_series:
        floor = max(floor, float(np.sqrt(max(centre, 1))))
    return max(spread, floor)


def causal_z(
    values: np.ndarray, *, count_series: bool, warmup: int = WARMUP_BUCKETS
) -> np.ndarray:
    """|z| of each bucket against the finite buckets before it (never after).

    Scale = ``robust_scale`` of the past. With no scale (a gauge flat at zero)
    a bucket gives no evidence (NaN). Buckets before ``warmup`` past values
    are NaN.
    """
    out = np.full(values.shape, np.nan, dtype="float64")
    for i in range(values.size):
        current = values[i]
        if not np.isfinite(current):
            continue
        history = values[:i][np.isfinite(values[:i])]
        if history.size < warmup:
            continue
        scale = robust_scale(history, count_series=count_series)
        if scale > 0:
            centre = float(np.median(history))
            out[i] = min(abs(float(current) - centre) / scale, Z_CAP)
    return out


def _resolve(path: str, root: Path | None) -> Path:
    p = Path(path)
    return p if p.is_absolute() or root is None else root / p


def service_scores(
    window: TelemetryWindow,
    bucket_seconds: int,
    *,
    root: Path | None = None,
    crop_start_s: float = 0,
) -> ServiceScores:
    """Causal scores of every service (in and out of scope) from metrics and logs.

    ``crop_start_s`` blanks buckets that start before window start + crop_start_s;
    it exists for the calibration's position-invariance audit only.
    """
    start_s = pd.Timestamp(window.window_start_iso).timestamp()
    n = bucket_count(window.window_start_iso, window.window_end_iso, bucket_seconds)
    parts: list[dict[str, list[Series]]] = []
    if window.p1_metrics_path is not None:
        metrics = pd.read_parquet(_resolve(window.p1_metrics_path, root))
        parts.append(metric_series(metrics, window.window_start_iso, n, bucket_seconds))
    features = features_for_window(window, root or Path(), bucket_seconds)
    if features is not None:
        parts.append(log_series(features, window.window_start_iso, n, bucket_seconds))
    first = int(np.ceil(crop_start_s / bucket_seconds)) if crop_start_s > 0 else 0
    services = sorted({s for part in parts for s in part})
    z = np.full((len(services), n), np.nan, dtype="float64")
    for row, service in enumerate(services):
        scored = []
        for part in parts:
            for series in part.get(service, []):
                values = series.values.astype("float64", copy=True)
                values[:first] = np.nan
                scored.append(causal_z(values, count_series=series.is_count))
        stacked = np.vstack(scored)
        has = np.isfinite(stacked).any(axis=0)
        z[row, has] = np.nanmax(np.where(np.isfinite(stacked), stacked, -1), axis=0)[
            has
        ]
    return ServiceScores(services=services, z=z, start_s=start_s)


def detector_hash(params: DetectorParams) -> str:
    """SHA-256 over the parameters, the fixed constants and the scope list."""
    payload = {
        "version": DETECTOR_VERSION,
        "params": asdict(params),
        "warmup_buckets": WARMUP_BUCKETS,
        "rel_floor": REL_FLOOR,
        "z_cap": Z_CAP,
        "suspect_count": SUSPECT_COUNT,
        "scope": scope_digest(),
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _above(
    scores: ServiceScores, rows: list[int], b: int, threshold: float
) -> list[str]:
    col = scores.z[rows, b] if rows else np.array([])
    hits = [
        (float(v), scores.services[r])
        for r, v in zip(rows, col, strict=True)
        if np.isfinite(v) and v >= threshold
    ]
    return [name for _, name in sorted(hits, key=lambda t: (-t[0], t[1]))]


def detect(
    window: TelemetryWindow,
    params: DetectorParams,
    *,
    root: Path | None = None,
    crop_start_s: float = 0,
) -> TriggerRecord:
    """The shared trigger of one window (design §5.2)."""
    scores = service_scores(
        window, params.bucket_seconds, root=root, crop_start_s=crop_start_s
    )
    inside = [i for i, s in enumerate(scores.services) if in_scope(s)]
    outside = [i for i, s in enumerate(scores.services) if not in_scope(s)]
    n = scores.z.shape[1]
    sub = scores.z[inside] if inside else np.full((1, n), np.nan)
    finite = np.isfinite(sub).any(axis=0)
    peak = np.where(
        finite, np.nanmax(np.where(np.isfinite(sub), sub, -1), axis=0), np.nan
    )
    crossing = np.isfinite(peak) & (peak >= params.threshold)

    bucket, source = None, TriggerSource.FALLBACK
    for b in range(n - params.persistence + 1):
        if crossing[b : b + params.persistence].all():
            bucket, source = b, TriggerSource.THRESHOLD
            break
    if bucket is None:
        if not finite.any():
            suspects: list[str] = []
            bucket = 0
        else:
            bucket = int(np.nanargmax(np.where(finite, peak, -1)))
            suspects = _above(scores, inside, bucket, np.nextafter(0, 1))
    else:
        suspects = _above(scores, inside, bucket, params.threshold)
    context = sorted(_above(scores, outside, bucket, params.threshold))
    if source == TriggerSource.FALLBACK and not finite.any():
        context = []
    return TriggerRecord(
        incident_id=window.incident_id,
        trigger_time_s=round(
            scores.start_s + bucket * params.bucket_seconds, _TIME_DIGITS
        ),
        suspects=tuple(suspects[:SUSPECT_COUNT]),
        context=tuple(context),
        source=source,
        detector_hash=detector_hash(params),
    )


def load_detector_params(path: Path = DETECTOR_PARAMS_PATH) -> DetectorParams:
    """The frozen parameters; a missing file or key is an error, never a default."""
    if not path.is_file():
        raise FileNotFoundError(f"detector parameters not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if set(raw) != _PARAM_KEYS:
        raise ValueError(f"detector parameter keys must be {sorted(_PARAM_KEYS)}")
    params = DetectorParams(
        bucket_seconds=int(raw["bucket_seconds"]),
        threshold=float(raw["threshold"]),
        persistence=int(raw["persistence"]),
        provisional=bool(raw["provisional"]),
    )
    if params.bucket_seconds < 1 or params.persistence < 1 or params.threshold <= 0:
        raise ValueError("bucket_seconds and persistence must be >= 1; threshold > 0")
    return params


def load_external_triggers(path: Path) -> dict[str, TriggerRecord]:
    """Externally supplied triggers (JSON lines), by incident ID.

    The plug-in for the exploratory run that gives every system another anchor
    (decision D-a); the runner refuses it in confirmatory runs. Every record
    must be marked ``external``.
    """
    records: dict[str, TriggerRecord] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = TriggerRecord.model_validate_json(line)
        if record.source != TriggerSource.EXTERNAL:
            raise ValueError("every supplied trigger must have source 'external'")
        if record.incident_id in records:
            raise ValueError("an incident appears twice in the trigger file")
        records[record.incident_id] = record
    return records
