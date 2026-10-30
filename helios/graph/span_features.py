"""Span-level features for G-pipe (S2.2 design §5.1; owner decisions G-d, G-e).

A service's work on one request starts at an **entry span**: a span whose
parent is missing or belongs to another service. Its own spans below the entry
(server → client → … in the same service) are part of that work; the first
spans of *other* services reached through them are its **frontier**: the calls
it waits on. Per entry span:

- wait on callee B = length of the union of B's frontier intervals, clipped to
  the entry span (concurrent calls overlap; the union, never the sum, G-d);
- self = entry duration - length of the union of all frontier intervals;
- a call edge (service, B) for every frontier span of B.

Missing or empty parents make a span an entry with no caller. Splitting at the
trigger is by entry start, so a request that straddles the trigger stays whole
(design G-e: the ghost-edge baseline is everything before the trigger).
Input columns are the P2 contract (OTel capture and the RCAEval adapter).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pandas as pd

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "SpanAnalysis",
    "analyse_spans",
    "call_edges",
    "ghost_edges",
    "self_share",
    "span_totals",
    "split_at",
    "wait_by_callee",
    "wait_share",
]

_ENTRY_COLUMNS = [
    "trace_id",
    "span_id",
    "service",
    "start_us",
    "duration_us",
    "self_us",
    "error",
]
_WAIT_COLUMNS = ["trace_id", "span_id", "caller", "callee", "start_us", "wait_us"]
_US_PER_S = 1_000_000
ERROR_CODES = frozenset({"2", "ERROR", "STATUS_CODE_ERROR"})  # OTel text or enum


@dataclass(frozen=True)
class SpanAnalysis:
    """Entry spans and their per-callee waits (one row per entry and callee)."""

    entries: pd.DataFrame
    waits: pd.DataFrame


def _union_length(intervals: Iterable[tuple[int, int]]) -> float:
    """Total length covered by the intervals (empty ones ignored)."""
    total = 0
    start: int | None = None
    end: int | None = None
    for lo, hi in sorted(intervals):
        if hi <= lo:
            continue
        if end is None or start is None or lo > end:
            if end is not None and start is not None:
                total += end - start
            start, end = lo, hi
        elif hi > end:
            end = hi
    if end is not None and start is not None:
        total += end - start
    return float(total)


def _no_parent(value: object) -> bool:
    return value is None or value == "" or (isinstance(value, float) and value != value)


def _interval(row: dict[str, Any]) -> tuple[int, int]:
    lo = int(row["start_time_us"])
    return lo, lo + int(row["duration_us"])


def analyse_spans(spans: pd.DataFrame) -> SpanAnalysis:
    """Entry spans, their self time and their waits on each callee."""
    owners = spans.groupby(["trace_id", "span_id"])["service_name"].nunique()
    if (owners > 1).any():
        raise ValueError(
            "a span is listed under more than one service: the capture's span "
            "attribution is broken (PR 1 review C1)"
        )
    entries: list[tuple[object, ...]] = []
    waits: list[tuple[object, ...]] = []
    for trace_id, trace in spans.groupby("trace_id", sort=True):
        rows: list[dict[str, Any]] = trace.sort_values(
            ["start_time_us", "span_id"]
        ).to_dict("records")
        by_id = {str(r["span_id"]): r for r in rows}
        children: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            parent = r["parent_span_id"]
            if not _no_parent(parent) and str(parent) in by_id:
                children[str(parent)].append(r)
        for r in rows:
            parent = r["parent_span_id"]
            service = str(r["service_name"])
            known = not _no_parent(parent) and str(parent) in by_id
            if known and str(by_id[str(parent)]["service_name"]) == service:
                continue  # inside another entry of the same service
            lo, hi = _interval(r)
            frontier: dict[str, list[tuple[int, int]]] = defaultdict(list)
            stack = list(children[str(r["span_id"])])
            while stack:
                child = stack.pop()
                child_service = str(child["service_name"])
                if child_service == service:
                    stack.extend(children[str(child["span_id"])])
                    continue
                c_lo, c_hi = _interval(child)
                frontier[child_service].append((max(c_lo, lo), min(c_hi, hi)))
            all_wait = _union_length(i for ivs in frontier.values() for i in ivs)
            error = str(r.get("status_code", "")).strip().upper() in ERROR_CODES
            span_id = str(r["span_id"])
            entries.append(
                (trace_id, span_id, service, lo, hi - lo, (hi - lo) - all_wait, error)
            )
            for callee in sorted(frontier):
                wait = _union_length(frontier[callee])
                waits.append((trace_id, span_id, service, callee, lo, wait))
    return SpanAnalysis(
        entries=pd.DataFrame(entries, columns=_ENTRY_COLUMNS),
        waits=pd.DataFrame(waits, columns=_WAIT_COLUMNS),
    )


def split_at(analysis: SpanAnalysis, t_s: float) -> tuple[SpanAnalysis, SpanAnalysis]:
    """Entries (and their waits) starting before ``t_s`` and at or after it."""
    cut = t_s * _US_PER_S
    e, w = analysis.entries, analysis.waits
    return (
        SpanAnalysis(e[e["start_us"] < cut], w[w["start_us"] < cut]),
        SpanAnalysis(e[e["start_us"] >= cut], w[w["start_us"] >= cut]),
    )


def call_edges(analysis: SpanAnalysis) -> frozenset[tuple[str, str]]:
    """(caller service, callee service) pairs seen as calls."""
    w = analysis.waits
    return frozenset(
        (str(a), str(b)) for a, b in zip(w["caller"], w["callee"], strict=True)
    )


def wait_by_callee(analysis: SpanAnalysis) -> dict[tuple[str, str], float]:
    """Total wait (us) of each caller on each callee."""
    sums = analysis.waits.groupby(["caller", "callee"], sort=True)["wait_us"].sum()
    return {(str(a), str(b)): float(v) for (a, b), v in sums.items()}


def span_totals(analysis: SpanAnalysis) -> dict[str, tuple[float, float]]:
    """Per service: (total entry duration us, total self us)."""
    sums = analysis.entries.groupby("service", sort=True)[
        ["duration_us", "self_us"]
    ].sum()
    return {
        str(s): (float(r["duration_us"]), float(r["self_us"]))
        for s, r in sums.iterrows()
    }


def self_share(analysis: SpanAnalysis) -> dict[str, float]:
    """Per service: median over its requests of self time / duration.

    Each request counts once, so one long-lived span (an event stream) cannot
    dominate as it would in a ratio of summed durations.
    """
    e = analysis.entries[analysis.entries["duration_us"] > 0]
    shares = (e["self_us"] / e["duration_us"]).groupby(e["service"], sort=True)
    return {str(s): float(v) for s, v in shares.median().items()}


def wait_share(analysis: SpanAnalysis) -> dict[tuple[str, str], float]:
    """Per (caller, callee): mean over the caller's requests of wait / duration.

    A request of the caller that did not call the callee counts as zero.
    """
    e = analysis.entries[analysis.entries["duration_us"] > 0]
    requests = e.groupby("service", sort=True).size()
    w = analysis.waits.merge(
        e[["trace_id", "span_id", "duration_us"]], on=["trace_id", "span_id"]
    )
    w = w.assign(share=w["wait_us"] / w["duration_us"])
    sums = w.groupby(["caller", "callee"], sort=True)["share"].sum()
    return {(str(a), str(b)): float(v) / int(requests[a]) for (a, b), v in sums.items()}


def ghost_edges(
    before: SpanAnalysis, after: SpanAnalysis
) -> frozenset[tuple[str, str]]:
    """Call edges seen after the trigger and never before it (G-e)."""
    return call_edges(after) - call_edges(before)
