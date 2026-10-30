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
import pyarrow.parquet as pq

from helios.graph.anomaly_intensity import (
    COUNT_METRICS,
    COUNTER_SUFFIXES,
    bucket_count,
    service_of,
)
from helios.graph.span_features import ERROR_CODES
from helios.pipelines.l_pipe.lpipe_config import (
    DIGEST_TOKEN_CAP,
    LOG_LINES_PER_SERVICE,
    LOG_MIN_LINES,
    LOG_RISE_FACTOR,
    METRIC_LINES_PER_SERVICE,
    ONSET_UNITS,
    TEMPLATE_CHARS,
    TRACE_LINES_PER_SERVICE,
    TRACE_MIN_SPANS,
    TRACE_RISE_FACTOR,
    TRACE_VALIDATED_ROOTS,
)
from helios.telemetry.log_templates import BUCKET_SECONDS, features_for_window
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
    "log_digest",
    "metric_digest",
    "trace_digest",
    "trace_format_validated",
]

HELIOS_ENABLE_LPIPE_DIGESTS: bool = True

Modality = Literal["metric", "log", "trace"]
_PREFIX: dict[str, str] = {"metric": "M", "log": "L", "trace": "T"}
_SERVICE_LABELS = frozenset({"service_name", "service", "job", "instance", "__name__"})
_HISTOGRAM_TOTAL = "+Inf"
_DIGITS = 6
_ERROR_LEVELS = ("ERROR", "FATAL", "CRITICAL")


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


def _rise(before: int, after: int, before_s: float, after_s: float) -> float:
    """Rate ratio after/before, one pseudo-line each side (a new template counts)."""
    return ((after + 1) / after_s) / ((before + 1) / before_s)


def _split_seconds(window: TelemetryWindow, t_start: float) -> tuple[float, float]:
    start = pd.Timestamp(window.window_start_iso).timestamp()
    end = pd.Timestamp(window.window_end_iso).timestamp()
    return max(t_start - start, 1), max(end - t_start, 1)


def _severity_lines(
    window: TelemetryWindow,
    path: Path,
    t_start: float,
    wanted: set[str],
    seconds: tuple[float, float],
) -> list[DigestLine]:
    if "severity" not in pq.read_schema(path).names:
        return []
    logs = pq.read_table(
        path, columns=["timestamp", "service_name", "severity"]
    ).to_pandas()
    levels = logs["severity"].astype("string").fillna("").str.upper()
    logs = logs[levels.isin(_ERROR_LEVELS) & logs["service_name"].isin(wanted)]
    if logs.empty:
        return []
    stamps = pd.to_datetime(
        logs["timestamp"], utc=True, format="ISO8601", errors="coerce"
    )
    after = stamps.map(lambda t: t.timestamp() >= t_start)
    out = []
    for service in sorted(set(logs["service_name"])):
        mine = logs["service_name"] == service
        a = int((mine & after).sum())
        b = int((mine & ~after).sum())
        weight = _rise(b, a, *seconds)
        if weight >= LOG_RISE_FACTOR:
            out.append(
                DigestLine(
                    "",
                    service,
                    f"{service} {a} error-level lines after trigger, {b} before",
                    weight,
                )
            )
    return out


def log_digest(
    window: TelemetryWindow,
    trigger: TriggerRecord,
    candidates: Sequence[str],
    *,
    root: Path,
    token_cap: int = DIGEST_TOKEN_CAP,
) -> Digest | None:
    """Templates new or rising after the trigger, and error-level line counts; None without P3."""
    if window.p3_logs_path is None:
        return None
    features = features_for_window(window, root, BUCKET_SECONDS)
    if features is None:
        return None
    start = pd.Timestamp(window.window_start_iso).timestamp()
    t_start = (
        start
        + math.floor((trigger.trigger_time_s - start) / BUCKET_SECONDS) * BUCKET_SECONDS
    )
    seconds = _split_seconds(window, t_start)
    wanted = set(candidates)
    counts = features.counts[features.counts["service"].isin(wanted)].copy()
    stamps = pd.to_datetime(counts["bucket_start"], utc=True)
    counts["after"] = stamps.map(lambda t: t.timestamp() >= t_start)
    text_of = dict(
        zip(
            features.templates["template_id"],
            features.templates["template"],
            strict=True,
        )
    )
    per_service: dict[str, list[DigestLine]] = {}
    grouped = counts.groupby(["service", "template_id", "after"])["count"].sum()
    for service, template in sorted({(s, t) for s, t, _ in grouped.index}):
        a = int(grouped.get((service, template, True), 0))
        b = int(grouped.get((service, template, False), 0))
        weight = _rise(b, a, *seconds)
        if a < LOG_MIN_LINES or weight < LOG_RISE_FACTOR:
            continue
        shown = text_of[template][:TEMPLATE_CHARS]
        per_service.setdefault(service, []).append(
            DigestLine(
                "",
                service,
                f'{service} log template "{shown}": {b} lines before trigger, {a} after',
                weight,
            )
        )
    lines = [
        line
        for service in sorted(per_service)
        for line in sorted(per_service[service], key=lambda d: (-d.weight, d.text))[
            :LOG_LINES_PER_SERVICE
        ]
    ]
    lines += _severity_lines(
        window, _resolve(window.p3_logs_path, root), t_start, wanted, seconds
    )
    return cap_lines("log", lines, token_cap)


def trace_format_validated(window: TelemetryWindow, *, root: Path) -> bool:
    """True only for P2 written by the OTel capture, the one trace format build data validated (L-f).

    RCAEval-format traces (the confirmatory pool) were never seen on build data,
    so the trace worker skips them, as the detector does; anything not under a
    validated capture root fails closed.
    """
    if window.p2_traces_path is None:
        return False
    path = _resolve(window.p2_traces_path, root).resolve()
    return any(path.is_relative_to((root / r).resolve()) for r in TRACE_VALIDATED_ROOTS)


def _ms(us: float) -> str:
    return f"{us / 1_000:.3g} ms"


def trace_digest(
    window: TelemetryWindow,
    trigger: TriggerRecord,
    candidates: Sequence[str],
    *,
    root: Path,
    token_cap: int = DIGEST_TOKEN_CAP,
) -> Digest | None:
    """Operations whose median latency rose, and error-span counts; None without validated P2."""
    if window.p2_traces_path is None or not trace_format_validated(window, root=root):
        return None
    spans = pd.read_parquet(
        _resolve(window.p2_traces_path, root),
        columns=[
            "service_name",
            "operation_name",
            "start_time_us",
            "duration_us",
            "status_code",
        ],
    )
    spans = spans[spans["service_name"].isin(set(candidates))]
    after = (
        spans["start_time_us"].astype("float64") >= trigger.trigger_time_s * 1_000_000
    )
    error = (
        spans["status_code"]
        .astype("string")
        .fillna("")
        .str.strip()
        .str.upper()
        .isin(ERROR_CODES)
    )
    start = pd.Timestamp(window.window_start_iso).timestamp()
    seconds = _split_seconds(window, max(trigger.trigger_time_s, start))
    per_service: dict[str, list[DigestLine]] = {}
    for (service, op), group in spans.groupby(
        ["service_name", "operation_name"], sort=True
    ):
        mask = after.loc[group.index]
        b, a = group.loc[~mask, "duration_us"], group.loc[mask, "duration_us"]
        if len(b) < TRACE_MIN_SPANS or len(a) < TRACE_MIN_SPANS:
            continue
        mb, ma = float(b.median()), float(a.median())
        if mb <= 0 or ma / mb < TRACE_RISE_FACTOR:
            continue
        per_service.setdefault(str(service), []).append(
            DigestLine(
                "",
                str(service),
                f'{service} operation "{op}" median latency {_ms(mb)} before trigger, '
                f"{_ms(ma)} after",
                ma / mb,
            )
        )
    for service in sorted(set(spans["service_name"])):
        mine = spans["service_name"] == service
        a_err = int((mine & error & after).sum())
        b_err = int((mine & error & ~after).sum())
        weight = _rise(b_err, a_err, *seconds)
        if a_err and weight >= TRACE_RISE_FACTOR:
            per_service.setdefault(str(service), []).append(
                DigestLine(
                    "",
                    str(service),
                    f"{service} {a_err} error spans after trigger, {b_err} before",
                    weight,
                )
            )
    lines = [
        line
        for service in sorted(per_service)
        for line in sorted(per_service[service], key=lambda d: (-d.weight, d.text))[
            :TRACE_LINES_PER_SERVICE
        ]
    ]
    return cap_lines("trace", lines, token_cap)
