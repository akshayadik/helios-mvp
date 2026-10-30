"""Telemetry digests for the L-pipe workers (S2.3 design §5.2).

Deterministic code, no model: each worker reads one stream and sees a short
list of lines, each with a stable evidence ID (``M1``, ``L1``, ``T1``) it must
cite. Lines are restricted to candidate services, split at the frozen trigger,
written with times relative to the trigger, ordered by shift size and cut at
the token cap (the number cut is recorded). Lines hold real names; ``render``
masks them (L-i) and refuses a survivor.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import numpy as np
import pandas as pd

from helios.graph.anomaly_intensity import (
    COUNT_METRICS,
    COUNTER_SUFFIXES,
    bucket_count,
    service_of,
)
from helios.pipelines.l_pipe.lpipe_config import (
    DIGEST_TOKEN_CAP,
    METRIC_LINES_PER_SERVICE,
    ONSET_UNITS,
)
from helios.telemetry.trigger import load_detector_params, robust_scale
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Sequence

    from helios.pipelines.l_pipe.aliases import AliasMap
    from helios.schemas.telemetry import TelemetryWindow
    from helios.telemetry.trigger import TriggerRecord

__all__ = [
    "Digest",
    "DigestLine",
    "Modality",
    "cap_lines",
    "estimate_tokens",
    "metric_digest",
]

HELIOS_ENABLE_LPIPE_DIGESTS: bool = True

Modality = Literal["metric", "log", "trace"]
_PREFIX: dict[str, str] = {"metric": "M", "log": "L", "trace": "T"}
_SERVICE_LABELS = frozenset({"service_name", "service", "job", "instance"})
_HISTOGRAM_TOTAL = "+Inf"
_DIGITS = 6


@dataclass(frozen=True)
class DigestLine:
    """One evidence line; ``weight`` orders lines (shift size)."""

    line_id: str
    service: str
    text: str
    weight: float


@dataclass(frozen=True)
class Digest:
    """A worker's evidence: kept lines and how many the cap cut."""

    modality: Modality
    lines: tuple[DigestLine, ...]
    cut: int

    def render(self, alias: AliasMap) -> str:
        """One ``<id> <masked text>`` line per evidence line; refuses a real name."""
        text = "\n".join(
            f"{line.line_id} {alias.mask(line.text)}" for line in self.lines
        )
        alias.check(text)
        return text

    def ids(self) -> frozenset[str]:
        return frozenset(line.line_id for line in self.lines)


def estimate_tokens(text: str) -> int:
    """Token estimate used for the cap: one token per four characters, rounded up."""
    return math.ceil(len(text) / 4)


def cap_lines(
    modality: Modality, lines: Sequence[DigestLine], token_cap: int = DIGEST_TOKEN_CAP
) -> Digest:
    """Largest shifts first, IDs numbered after sorting, cut at the token cap."""
    ordered = sorted(lines, key=lambda d: (-d.weight, d.service, d.text))
    kept: list[DigestLine] = []
    used = 0
    for line in ordered:
        line_id = f"{_PREFIX[modality]}{len(kept) + 1}"
        cost = estimate_tokens(f"{line_id} {line.text}")
        if used + cost > token_cap:
            break
        kept.append(
            DigestLine(line_id, line.service, line.text, round(line.weight, _DIGITS))
        )
        used += cost
    return Digest(modality=modality, lines=tuple(kept), cut=len(ordered) - len(kept))


def _resolve(path: str, root: Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else root / p


def _label_suffix(labels: dict[str, str]) -> str:
    rest = {k: v for k, v in sorted(labels.items()) if k not in _SERVICE_LABELS}
    if not rest:
        return ""
    return "{" + ",".join(f"{k}={v}" for k, v in rest.items()) + "}"


def _named_series(
    metrics: pd.DataFrame, window: TelemetryWindow, n: int, bucket_seconds: int
) -> list[tuple[str, str, np.ndarray, bool]]:
    """(service, series name, bucket means, is_count), counters differenced."""
    start = pd.Timestamp(window.window_start_iso).timestamp()
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
    frame = frame[(frame["bucket"] >= 0) & (frame["bucket"] < n)]
    frame = frame[np.isfinite(frame["value"])]
    parsed = {lab: json.loads(lab) for lab in frame["labels"].unique()}
    keep = ~frame["metric"].str.endswith("_bucket") | frame["labels"].map(
        lambda lab: parsed[lab].get("le") == _HISTOGRAM_TOTAL
    )
    frame = frame[keep]
    frame["service"] = frame["labels"].map(lambda lab: service_of(parsed[lab]))
    means = frame.groupby(["service", "metric", "labels", "bucket"], sort=True)[
        "value"
    ].mean()
    out: list[tuple[str, str, np.ndarray, bool]] = []
    for (service, metric, labels), series in means.groupby(level=[0, 1, 2], sort=True):
        dense = np.full(n, np.nan)
        dense[series.index.get_level_values("bucket").astype(int)] = series.to_numpy()
        name = str(metric)
        counter = name.endswith(COUNTER_SUFFIXES)
        if counter:
            dense = np.concatenate(([np.nan], np.diff(dense)))
        label_dict = parsed[str(labels)]
        if name.endswith("_bucket"):
            label_dict = {k: v for k, v in label_dict.items() if k != "le"}
        is_count = (counter and not name.endswith("_sum")) or name in COUNT_METRICS
        out.append((str(service), name + _label_suffix(label_dict), dense, is_count))
    return out


def _metric_line(
    service: str,
    name: str,
    values: np.ndarray,
    is_count: bool,
    t_bucket: int,
    bucket_seconds: int,
) -> DigestLine | None:
    before = values[:t_bucket]
    after = values[t_bucket:]
    before = before[np.isfinite(before)]
    after_finite = after[np.isfinite(after)]
    if before.size == 0 or after_finite.size == 0:
        return None
    scale = robust_scale(before, count_series=is_count)
    if scale <= 0:
        return None
    centre = float(np.median(before))
    shift = (float(np.median(after_finite)) - centre) / scale
    if shift == 0:
        return None
    text = f"{service} {name} {'up' if shift > 0 else 'down'} {abs(shift):.1f} robust units"
    beyond = np.flatnonzero(
        np.isfinite(after) & (np.abs(after - centre) / scale >= ONSET_UNITS)
    )
    if beyond.size:
        text += f", beyond {ONSET_UNITS} from +{int(beyond[0]) * bucket_seconds} s"
    return DigestLine("", service, text, abs(shift))


def metric_digest(
    window: TelemetryWindow,
    trigger: TriggerRecord,
    candidates: Sequence[str],
    *,
    root: Path,
    bucket_seconds: int | None = None,
    token_cap: int = DIGEST_TOKEN_CAP,
) -> Digest | None:
    """Largest robust shifts after the trigger, per candidate service; None without P1."""
    if window.p1_metrics_path is None:
        return None
    if bucket_seconds is None:
        bucket_seconds = load_detector_params().bucket_seconds
    metrics = pd.read_parquet(_resolve(window.p1_metrics_path, root))
    n = bucket_count(window.window_start_iso, window.window_end_iso, bucket_seconds)
    start = pd.Timestamp(window.window_start_iso).timestamp()
    t_bucket = int(math.floor((trigger.trigger_time_s - start) / bucket_seconds))
    wanted = set(candidates)
    per_service: dict[str, list[DigestLine]] = {}
    for service, name, values, is_count in _named_series(
        metrics, window, n, bucket_seconds
    ):
        if service not in wanted:
            continue
        line = _metric_line(service, name, values, is_count, t_bucket, bucket_seconds)
        if line is not None:
            per_service.setdefault(service, []).append(line)
    lines = [
        line
        for service in sorted(per_service)
        for line in sorted(per_service[service], key=lambda d: (-d.weight, d.text))[
            :METRIC_LINES_PER_SERVICE
        ]
    ]
    return cap_lines("metric", lines, token_cap)
