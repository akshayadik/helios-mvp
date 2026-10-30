"""G-pipe per-service features (S2.2 design §5.1).

Computed from the sealed window's spans, the frozen trigger and D-pipe's
verdict only: no label, no injection time, no window bound and no service
identity (F3). The split is at the trigger time ``t``; leads use the frozen
detector's causal scores, searched from the trigger bucket on (crossings
before it are noise). A callee with an onset leads a caller without one: in a
cascade the victim often stays under the threshold.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from helios.graph.span_features import (
    SpanAnalysis,
    analyse_spans,
    call_edges,
    ghost_edges,
    self_share,
    split_at,
    wait_share,
)
from helios.telemetry.scope import scope_key
from helios.telemetry.trigger import robust_scale, service_scores
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from helios.schemas.telemetry import TelemetryWindow
    from helios.telemetry.trigger import DetectorParams, ServiceScores, TriggerRecord

__all__ = [
    "FEATURE_COLUMNS",
    "GraphFeatures",
    "assert_no_identity",
    "compute_features",
    "lead_counts",
    "onsets",
]

FEATURE_COLUMNS: tuple[str, ...] = (
    "dpipe_score",
    "ppr_score",
    "callers_led",
    "callees_leading",
    "self_shift",
    "wait_pooled",
    "wait_pooled_rise",
    "ghost_in",
    "ghost_out",
    "error_share_shift",
)
_DIGITS = 6
Edge = tuple[str, str]


@dataclass(frozen=True)
class GraphFeatures:
    """Feature table (rows = services, columns = FEATURE_COLUMNS) and the
    graph facts the feature-weighted walk and the evidence record use."""

    services: tuple[str, ...]
    table: np.ndarray
    edge_wait_after: dict[Edge, float]
    self_share: dict[str, float]
    leaders: frozenset[str]
    ghosts: frozenset[Edge]
    onset_bucket: dict[str, int]
    callers_led: dict[str, tuple[str, ...]]
    self_shift: dict[str, float]


def onsets(
    scores: ServiceScores, trigger_time_s: float, detector: DetectorParams
) -> dict[str, int]:
    """First bucket at or after the trigger bucket whose score reaches the
    frozen threshold, per service (services that never cross are absent)."""
    first = round((trigger_time_s - scores.start_s) / detector.bucket_seconds)
    out: dict[str, int] = {}
    for row, service in enumerate(scores.services):
        z = scores.z[row, max(first, 0) :]
        hits = np.flatnonzero(np.isfinite(z) & (z >= detector.threshold))
        if hits.size:
            out[service] = max(first, 0) + int(hits[0])
    return out


def lead_counts(
    onset: Mapping[str, int], edges: frozenset[Edge]
) -> tuple[dict[str, int], dict[str, int], frozenset[str]]:
    """(callers each service leads, callees leading each service, leaders).

    Callee B leads caller A when B has an onset at least one bucket before
    A's, or A has none.
    """
    led: dict[str, int] = {}
    leading: dict[str, int] = {}
    for caller, callee in sorted(edges):
        if callee not in onset:
            continue
        if caller in onset and onset[callee] > onset[caller] - 1:
            continue
        led[callee] = led.get(callee, 0) + 1
        leading[caller] = leading.get(caller, 0) + 1
    return led, leading, frozenset(led)


def assert_no_identity(columns: Sequence[str], services: Sequence[str]) -> None:
    """Refuse any feature that is not a known column or names a service (F3)."""
    keys = {scope_key(s) for s in services} | {s.lower() for s in services}
    for column in columns:
        if any(token in keys for token in column.lower().split("_")):
            raise ValueError(f"feature column {column!r} carries a service identity")
        if column not in FEATURE_COLUMNS:
            raise ValueError(f"unknown feature column {column!r}")


def _window_share(
    scores: Mapping[str, float], names: Sequence[str]
) -> dict[str, float]:
    """Each score divided by the window's largest (0 when none is positive), so
    no feature depends on graph size or score scale (PR 1 review I4)."""
    top = max((float(scores.get(s, 0)) for s in names), default=0)
    return {s: float(scores.get(s, 0)) / top if top > 0 else 0 for s in names}


def _resolve(path: str, root: Path | None) -> Path:
    p = Path(path)
    return p if p.is_absolute() or root is None else root / p


def _pooled(shares: Mapping[Edge, float], service: str) -> float:
    return sum(v for (_, callee), v in shares.items() if callee == service)


def _self_shift(before: SpanAnalysis, after: SpanAnalysis, service: str) -> float:
    """Shift of the median self time per request after t, in robust units of
    the before part (design §5.1; gauge rule, as the detector)."""

    def self_times(a: SpanAnalysis) -> np.ndarray:
        values: np.ndarray = a.entries.loc[
            a.entries["service"] == service, "self_us"
        ].to_numpy(dtype="float64")
        return values

    old, new = self_times(before), self_times(after)
    if old.size == 0 or new.size == 0:
        return 0
    scale = robust_scale(old, count_series=False)
    return float((np.median(new) - np.median(old)) / scale) if scale > 0 else 0


def _error_share(a: SpanAnalysis, service: str) -> float:
    e = a.entries[a.entries["service"] == service]
    return float(e["error"].mean()) if len(e) else 0


def compute_features(
    window: TelemetryWindow,
    trigger: TriggerRecord,
    dpipe_scores: Mapping[str, float],
    ppr_scores: Mapping[str, float],
    services: Sequence[str],
    detector: DetectorParams,
    *,
    root: Path | None = None,
) -> GraphFeatures | None:
    """The feature table of ``services``; None without spans on both sides of t."""
    if window.p2_traces_path is None:
        return None
    spans = pd.read_parquet(_resolve(window.p2_traces_path, root))
    before, after = split_at(analyse_spans(spans), trigger.trigger_time_s)
    if before.entries.empty or after.entries.empty:
        return None
    names = tuple(sorted(services))
    keep = set(names)
    edges = frozenset(
        e
        for e in call_edges(before) | call_edges(after)
        if e[0] in keep and e[1] in keep
    )
    ghosts = frozenset(e for e in ghost_edges(before, after) if e in edges)
    wait_after = {e: v for e, v in wait_share(after).items() if e in edges}
    wait_before = {e: v for e, v in wait_share(before).items() if e in edges}
    onset = {
        s: b
        for s, b in onsets(
            service_scores(window, detector.bucket_seconds, root=root),
            trigger.trigger_time_s,
            detector,
        ).items()
        if s in keep
    }
    led, leading, leaders = lead_counts(onset, edges)
    shifts = {s: _self_shift(before, after, s) for s in names}
    dpipe_share = _window_share(dpipe_scores, names)
    ppr_share = _window_share(ppr_scores, names)
    rows = []
    for s in names:
        pooled = _pooled(wait_after, s)
        rows.append(
            [
                round(dpipe_share[s], _DIGITS),
                round(ppr_share[s], _DIGITS),
                led.get(s, 0),
                leading.get(s, 0),
                shifts[s],
                pooled,
                pooled - _pooled(wait_before, s),
                sum(callee == s for _, callee in ghosts),
                sum(caller == s for caller, _ in ghosts),
                _error_share(after, s) - _error_share(before, s),
            ]
        )
    table = np.nan_to_num(np.array(rows, dtype="float64").reshape(len(names), -1))
    return GraphFeatures(
        services=names,
        table=table,
        edge_wait_after=wait_after,
        self_share={s: v for s, v in self_share(after).items() if s in keep},
        leaders=leaders,
        ghosts=ghosts,
        onset_bucket=onset,
        callers_led={
            s: tuple(
                sorted(
                    c
                    for c, callee in edges
                    if callee == s
                    and callee in onset
                    and (c not in onset or onset[callee] <= onset[c] - 1)
                )
            )
            for s in names
        },
        self_shift=shifts,
    )
