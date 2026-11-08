"""ACP features and blast-radius tier (S3.2 design P-b, P-c; entry 82).

Label-free and known at dispatch: the frozen S2.5 signal type, which pillars
the window holds, the size of the incident's graph snapshot, the D-pipe's
top-1 score share and the metric family of the trigger's strongest series.
Nothing here reads a label, a fault name or a capture directory name (the
leakage test checks the imports). Values are rounded to six digits, the
``canonical_json`` convention, so reruns are bitwise equal.
"""

from __future__ import annotations

import math
from collections import defaultdict
from enum import StrEnum
from typing import TYPE_CHECKING

from helios.schemas.ueg_c import EdgeType, NodeType, UEGCSnapshot
from helios.telemetry.signal_type import SignalType
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "ACP_FEATURE_NAMES",
    "BlastTier",
    "MetricFamily",
    "acp_features",
    "blast_radius_tier",
    "metric_family",
]

HELIOS_ENABLE_ACP_FEATURES: bool = True

_DIGITS = 6


class MetricFamily(StrEnum):
    """Family of a metric series name (keyword match, checked in order)."""

    ERROR = "error"
    LATENCY = "latency"
    NETWORK = "network"
    MEMORY = "memory"
    DISK = "disk"
    CPU = "cpu"
    UNKNOWN = "unknown"


# Fixed with the S3.2 pre-run entry; checked in this order (error and latency
# as in the S2.5 signal type, so the two never disagree on those names).
_FAMILY_WORDS: tuple[tuple[MetricFamily, tuple[str, ...]], ...] = (
    (MetricFamily.ERROR, ("error", "fail", "5xx")),
    (MetricFamily.LATENCY, ("latency", "duration", "response_time")),
    (
        MetricFamily.NETWORK,
        ("socket", "network", "net_", "tcp", "packet", "receive", "transmit"),
    ),
    (MetricFamily.MEMORY, ("mem", "gc", "heap", "rss")),
    (MetricFamily.DISK, ("disk", "fs_", "io_", "fd")),
    (MetricFamily.CPU, ("cpu", "thread", "load")),
)

ACP_FEATURE_NAMES: tuple[str, ...] = (
    "bias",
    "signal_resource",
    "signal_latency",
    "signal_error",
    "has_logs",
    "has_traces",
    "log_services",
    "log_call_edges",
    "log_anomaly_edges",
    "d_top1_share",
    "family_error",
    "family_latency",
    "family_network",
    "family_memory",
    "family_disk",
    "family_cpu",
)
_FAMILIES = (
    MetricFamily.ERROR,
    MetricFamily.LATENCY,
    MetricFamily.NETWORK,
    MetricFamily.MEMORY,
    MetricFamily.DISK,
    MetricFamily.CPU,
)


class BlastTier(StrEnum):
    """Transitive callers of the D-pipe top-1: 1 (0-1), 2 (2-4), 3 (5+)."""

    ONE = "1"
    TWO = "2"
    THREE = "3"
    UNKNOWN = "unknown"


def metric_family(series_name: str | None) -> MetricFamily:
    """Keyword family of a metric name; UNKNOWN for None or no match."""
    if not series_name:
        return MetricFamily.UNKNOWN
    name = series_name.lower()
    for family, words in _FAMILY_WORDS:
        if any(w in name for w in words):
            return family
    return MetricFamily.UNKNOWN


def _snapshot(graph: object) -> UEGCSnapshot | None:
    return graph if isinstance(graph, UEGCSnapshot) else None


def _graph_counts(graph: UEGCSnapshot | None) -> tuple[int, int, int]:
    """(service nodes, call edges, anomaly edges) of the snapshot."""
    if graph is None:
        return 0, 0, 0
    services = sum(1 for n in graph.nodes if n.node_type == NodeType.SERVICE)
    calls = sum(1 for e in graph.edges if e.edge_type == EdgeType.CALL)
    anomaly = sum(
        1
        for e in graph.edges
        if e.edge_type in {EdgeType.ANOMALY_LEADS, EdgeType.ANOMALY_CO_MOVES}
    )
    return services, calls, anomaly


def _top1_share(ranked: Sequence[str], scores: Mapping[str, float]) -> float:
    values = [max(float(scores.get(s, 0)), 0) for s in ranked]
    total = sum(values)
    return values[0] / total if values and total > 0 else 0


def acp_features(
    *,
    signal: SignalType,
    family: MetricFamily,
    has_logs: bool,
    has_traces: bool,
    graph: object,
    d_ranked: Sequence[str],
    d_scores: Mapping[str, float],
) -> tuple[float, ...]:
    """The ACP feature vector, in ``ACP_FEATURE_NAMES`` order."""
    services, calls, anomaly = _graph_counts(_snapshot(graph))
    x: list[float] = [
        1,
        1 if signal == SignalType.RESOURCE else 0,
        1 if signal == SignalType.LATENCY else 0,
        1 if signal == SignalType.ERROR else 0,
        1 if has_logs else 0,
        1 if has_traces else 0,
        math.log1p(services),
        math.log1p(calls),
        math.log1p(anomaly),
        _top1_share(d_ranked, d_scores),
        *(1 if family == f else 0 for f in _FAMILIES),
    ]
    return tuple(round(float(v), _DIGITS) for v in x)


def blast_radius_tier(graph: object, top: str | None) -> BlastTier:
    """Tier of the services that transitively call ``top`` over call edges;
    UNKNOWN without a snapshot, without call edges or without a top-1."""
    snap = _snapshot(graph)
    if snap is None or top is None:
        return BlastTier.UNKNOWN
    callers: dict[str, set[str]] = defaultdict(set)
    for e in snap.edges:
        if e.edge_type == EdgeType.CALL and e.source != e.target:
            callers[e.target].add(e.source)
    if not callers:
        return BlastTier.UNKNOWN
    seen: set[str] = set()
    todo = [top]
    while todo:
        for c in callers.get(todo.pop(), set()):
            if c not in seen and c != top:
                seen.add(c)
                todo.append(c)
    n = len(seen)
    if n <= 1:
        return BlastTier.ONE
    return BlastTier.TWO if n <= 4 else BlastTier.THREE
