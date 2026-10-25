"""UEG-C builder — four typed edge classes from traces, metrics and logs (S1.5).

Design: docs/sprints/s1-data-graph/s1_5_ueg_c_design.md. Structural and
behavioural edges come from parent/child spans (temporal containment only as
the warned fallback for trace files without parent_span_id); causal edges
from per-service anomaly intensity (metrics + S1.4 log templates); economic
edges link services to the transaction/KPI node of each entry service;
Agent-Reasoning-Step nodes are added when reasoning steps are supplied.
Every service seen in any modality is a node. The snapshot is deterministic:
the same window and parameters give the same hash.
"""

from __future__ import annotations

import math
import warnings
from collections import defaultdict
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from helios.graph.anomaly_intensity import (
    bucket_count,
    combine,
    log_intensity,
    metric_intensity,
)
from helios.schemas.ueg_c import (
    TENANT_SELF,
    EdgeType,
    NodeType,
    UEGCEdge,
    UEGCNode,
    UEGCSnapshot,
)
from helios.telemetry.log_templates import features_for_window
from helios.vcl import VCLFlag, gated_by

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from helios.schemas.telemetry import TelemetryWindow

__all__ = [
    "BUCKET_SECONDS",
    "CAUSAL_MIN_R",
    "MAX_LAG_BUCKETS",
    "MIN_POINTS",
    "ReasoningStep",
    "SpanRecord",
    "UEGCBuilder",
    "build_ueg_c",
    "kpi_node_id",
]

# Calibration parameters (design doc § Parameters; S1.5 deviation entry).
BUCKET_SECONDS = 30
MAX_LAG_BUCKETS = 4
CAUSAL_MIN_R = 0.6
MIN_POINTS = 8


def kpi_node_id(entry_service: str) -> str:
    return f"kpi:{entry_service}"


def _psid(val: object) -> str:
    """Normalise a Parquet nullable parent_span_id cell to str or ''.

    Handles None, float('nan'), pd.NA, pd.NaT, and other pandas null variants.
    The try/except guards against pd.isna raising TypeError on array inputs.
    """
    if val is None:
        return ""
    if isinstance(val, float) and math.isnan(val):
        return ""
    try:
        if pd.isna(val):
            return ""
    except (TypeError, ValueError):
        pass
    return str(val)


@dataclass(frozen=True)
class SpanRecord:
    trace_id: str
    service_name: str
    start_us: int
    end_us: int
    span_id: str = ""
    parent_span_id: str | None = None  # None or "" for root spans


@dataclass(frozen=True)
class ReasoningStep:
    """One Agent-Reasoning-Step (P4), in the order the agent took it."""

    step_id: str
    agent: str
    text: str
    target_service: str | None = None


def _pearson(a: np.ndarray, b: np.ndarray) -> float | None:
    """Pearson r over points finite in both; None if too few or constant."""
    keep = np.isfinite(a) & np.isfinite(b)
    if int(keep.sum()) < MIN_POINTS:
        return None
    x, y = a[keep], b[keep]
    if float(np.std(x)) <= 0 or float(np.std(y)) <= 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def _lagged(a: np.ndarray, b: np.ndarray, lag: int) -> float | None:
    """r between a and b shifted so that a leads b by ``lag`` buckets (lag may be <0)."""
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    if abs(lag) >= n:
        return None
    if lag >= 0:
        return _pearson(a[: len(a) - lag], b[lag:])
    return _pearson(a[-lag:], b[: len(b) + lag])


class UEGCBuilder:
    def __init__(self, *, enable_structural: bool = True) -> None:
        self._enable_structural = enable_structural

    def build(
        self,
        spans: list[SpanRecord],
        *,
        incident_id: str,
        variant_config_hash: str,
        captured_at_iso: str,
        parent_span_id_col_present: bool = False,
        service_modalities: Mapping[str, Iterable[str]] | None = None,
        intensity: Mapping[str, np.ndarray] | None = None,
        reasoning_steps: Sequence[ReasoningStep] = (),
    ) -> UEGCSnapshot:
        modalities: dict[str, set[str]] = defaultdict(set)
        for s in spans:
            modalities[s.service_name].add("traces")
        for service, kinds in (service_modalities or {}).items():
            modalities[service].update(kinds)
        for service in intensity or {}:
            modalities.setdefault(service, set())
        nodes = [
            UEGCNode(
                node_id=svc,
                node_type=NodeType.SERVICE,
                service_name=svc,
                metadata={"modalities": ",".join(sorted(kinds))} if kinds else {},
            )
            for svc, kinds in modalities.items()
        ]

        pairs, roots = self._call_pairs(spans, parent_span_id_col_present)
        edges: list[UEGCEdge] = []
        if self._enable_structural:
            edges.extend(
                UEGCEdge(source=a, target=b, edge_type=EdgeType.STRUCTURAL, weight=1)
                for a, b in sorted(pairs)
            )
        edges.extend(self._call_edges(spans, pairs))
        kpi_nodes, economic = self._economic(spans, roots)
        nodes.extend(kpi_nodes)
        edges.extend(economic)
        edges.extend(self._causal_edges(intensity or {}))
        ars_nodes, ars_edges = self._reasoning(reasoning_steps)
        nodes.extend(ars_nodes)
        edges.extend(ars_edges)

        return UEGCSnapshot(
            incident_id=incident_id,
            variant_config_hash=variant_config_hash,
            nodes=sorted(nodes, key=lambda n: (n.node_type.value, n.node_id)),
            edges=sorted(edges, key=lambda e: (e.edge_type.value, e.source, e.target)),
            captured_at_iso=captured_at_iso,
        )

    # -- calls ------------------------------------------------------------

    def _call_pairs(
        self, spans: list[SpanRecord], parent_span_id_col_present: bool
    ) -> tuple[dict[tuple[str, str], set[str]], dict[str, str]]:
        """Caller -> callee pairs with the traces they occur in, and each trace's root service.

        Parent/child linkage when the column exists; a root-only trace then has
        no pairs (valid topology). Temporal containment only when the column is
        absent from the Parquet file (schema v1), with a warning.
        """
        if not parent_span_id_col_present:
            warnings.warn(
                "parent_span_id absent — falling back to temporal containment",
                stacklevel=3,
            )
            return self._pairs_temporal(spans)
        span_svc = {(s.trace_id, s.span_id): s.service_name for s in spans}
        pairs: dict[tuple[str, str], set[str]] = defaultdict(set)
        roots: dict[str, str] = {}
        for child in spans:
            if not child.parent_span_id:
                roots.setdefault(child.trace_id, child.service_name)
                continue
            parent = span_svc.get((child.trace_id, child.parent_span_id))
            if parent and parent != child.service_name:
                pairs[parent, child.service_name].add(child.trace_id)
        return pairs, roots

    @staticmethod
    def _pairs_temporal(
        spans: list[SpanRecord],
    ) -> tuple[dict[tuple[str, str], set[str]], dict[str, str]]:
        by_trace: dict[str, list[SpanRecord]] = defaultdict(list)
        for s in spans:
            by_trace[s.trace_id].append(s)
        pairs: dict[tuple[str, str], set[str]] = defaultdict(set)
        roots: dict[str, str] = {}
        for tid, trace_spans in by_trace.items():
            ordered = sorted(trace_spans, key=lambda s: (s.start_us, -s.end_us))
            roots[tid] = ordered[0].service_name
            for i, span_s in enumerate(ordered):
                for j in range(i - 1, -1, -1):
                    span_p = ordered[j]
                    if span_p.service_name == span_s.service_name:
                        continue  # same-service: keep scanning
                    if (
                        span_p.start_us <= span_s.start_us
                        and span_p.end_us >= span_s.end_us
                    ):
                        pairs[span_p.service_name, span_s.service_name].add(tid)
                        break
        return pairs, roots

    @staticmethod
    def _latency_series(spans: list[SpanRecord]) -> dict[str, np.ndarray]:
        """Mean span duration per service per bucket, from the earliest span."""
        if not spans:
            return {}
        origin = min(s.start_us for s in spans)
        width = BUCKET_SECONDS * 1_000_000
        n = (max(s.start_us for s in spans) - origin) // width + 1
        sums: dict[str, np.ndarray] = {}
        counts: dict[str, np.ndarray] = {}
        for s in spans:
            i = (s.start_us - origin) // width
            sums.setdefault(s.service_name, np.zeros(n))[i] += s.end_us - s.start_us
            counts.setdefault(s.service_name, np.zeros(n))[i] += 1
        with np.errstate(invalid="ignore", divide="ignore"):
            return {
                k: np.where(counts[k] > 0, sums[k] / counts[k], np.nan) for k in sums
            }

    def _call_edges(
        self, spans: list[SpanRecord], pairs: dict[tuple[str, str], set[str]]
    ) -> list[UEGCEdge]:
        total = len({s.trace_id for s in spans})
        if total == 0:
            return []
        latency = self._latency_series(spans)
        return [
            UEGCEdge(
                source=a,
                target=b,
                edge_type=EdgeType.CALL,
                weight=len(tids) / total,
                correlation=_pearson(latency[a], latency[b]),
            )
            for (a, b), tids in sorted(pairs.items())
        ]

    # -- economic -----------------------------------------------------------

    @staticmethod
    def _economic(
        spans: list[SpanRecord], roots: dict[str, str]
    ) -> tuple[list[UEGCNode], list[UEGCEdge]]:
        services_in: dict[str, set[str]] = defaultdict(set)
        for s in spans:
            services_in[s.trace_id].add(s.service_name)
        traces_of: dict[str, list[str]] = defaultdict(list)
        for tid, entry in roots.items():
            traces_of[entry].append(tid)
        nodes: list[UEGCNode] = []
        edges: list[UEGCEdge] = []
        for entry, tids in sorted(traces_of.items()):
            kpi = kpi_node_id(entry)
            nodes.append(
                UEGCNode(
                    node_id=kpi,
                    node_type=NodeType.TRANSACTION_KPI,
                    service_name=entry,
                    metadata={"kpi": "user_transactions", "traces": str(len(tids))},
                )
            )
            seen: dict[str, int] = defaultdict(int)
            for tid in tids:
                for svc in services_in[tid]:
                    seen[svc] += 1
            edges.extend(
                UEGCEdge(
                    source=svc,
                    target=kpi,
                    edge_type=EdgeType.SERVES_KPI,
                    weight=count / len(tids),
                )
                for svc, count in sorted(seen.items())
            )
        return nodes, edges

    # -- causal -------------------------------------------------------------

    @staticmethod
    def _causal_edges(intensity: Mapping[str, np.ndarray]) -> list[UEGCEdge]:
        services = sorted(intensity)
        edges: list[UEGCEdge] = []
        for i, a in enumerate(services):
            for b in services[i + 1 :]:
                best: tuple[float, int] | None = None
                for lag in range(-MAX_LAG_BUCKETS, MAX_LAG_BUCKETS + 1):
                    r = _lagged(intensity[a], intensity[b], lag)
                    if r is not None and (
                        best is None
                        or r > best[0]
                        or (r == best[0] and abs(lag) < abs(best[1]))
                    ):
                        best = (r, lag)
                if best is None or best[0] < CAUSAL_MIN_R:
                    continue
                r, lag = best
                seconds = abs(lag) * BUCKET_SECONDS
                if lag == 0:
                    edges.extend(
                        UEGCEdge(
                            source=s,
                            target=t,
                            edge_type=EdgeType.ANOMALY_CO_MOVES,
                            weight=r,
                            correlation=r,
                            lag_seconds=0,
                        )
                        for s, t in ((a, b), (b, a))
                    )
                else:
                    src, tgt = (a, b) if lag > 0 else (b, a)
                    edges.append(
                        UEGCEdge(
                            source=src,
                            target=tgt,
                            edge_type=EdgeType.ANOMALY_LEADS,
                            weight=r,
                            correlation=r,
                            lag_seconds=seconds,
                        )
                    )
        return edges

    # -- agent reasoning steps -----------------------------------------------

    @staticmethod
    def _reasoning(
        steps: Sequence[ReasoningStep],
    ) -> tuple[list[UEGCNode], list[UEGCEdge]]:
        nodes = [
            UEGCNode(
                node_id=f"ars:{step.step_id}",
                node_type=NodeType.AGENT_REASONING_STEP,
                service_name=step.agent,
                tenant=TENANT_SELF,
                metadata={"order": str(i), "text": step.text},
            )
            for i, step in enumerate(steps)
        ]
        edges = [
            UEGCEdge(
                source=f"ars:{a.step_id}",
                target=f"ars:{b.step_id}",
                edge_type=EdgeType.PRECEDES,
                weight=1,
            )
            for a, b in pairwise(steps)
        ]
        edges.extend(
            UEGCEdge(
                source=f"ars:{step.step_id}",
                target=step.target_service,
                edge_type=EdgeType.INVOKES,
                weight=1,
            )
            for step in steps
            if step.target_service
        )
        return nodes, edges


def _resolve(path: str, root: Path | None) -> Path:
    p = Path(path)
    return p if p.is_absolute() or root is None else root / p


def _read_spans(path: Path) -> tuple[list[SpanRecord], bool]:
    df = pd.read_parquet(path)
    cols = df.to_dict(orient="list")
    has_psid = "parent_span_id" in cols
    spans = [
        SpanRecord(
            trace_id=str(cols["trace_id"][i]),
            span_id=str(cols["span_id"][i]),
            service_name=str(cols["service_name"][i]),
            parent_span_id=_psid(cols["parent_span_id"][i]) if has_psid else None,
            start_us=int(cols["start_time_us"][i]),
            end_us=int(cols["start_time_us"][i]) + int(cols["duration_us"][i]),
        )
        for i in range(len(df))
    ]
    return spans, has_psid


@gated_by(VCLFlag.L2B_GRAPH)
def build_ueg_c(
    window: TelemetryWindow,
    variant_config_hash: str,
    *,
    enable_structural: bool = True,
    root: Path | None = None,
    reasoning_steps: Sequence[ReasoningStep] = (),
) -> UEGCSnapshot | None:
    """UEG-C snapshot of a window; None when it has no traces, metrics or logs.

    ``root`` resolves relative window paths (None: as given). Confirmatory
    windows pass the pool lock when their logs are read.
    """
    paths = (window.p1_metrics_path, window.p2_traces_path, window.p3_logs_path)
    if all(p is None for p in paths):
        return None
    spans: list[SpanRecord] = []
    has_psid = True
    if window.p2_traces_path is not None:
        spans, has_psid = _read_spans(_resolve(window.p2_traces_path, root))

    n = bucket_count(window.window_start_iso, window.window_end_iso, BUCKET_SECONDS)
    modalities: dict[str, set[str]] = defaultdict(set)
    parts = []
    if window.p1_metrics_path is not None:
        metrics = pd.read_parquet(_resolve(window.p1_metrics_path, root))
        part = metric_intensity(metrics, window.window_start_iso, n, BUCKET_SECONDS)
        for service in part:
            modalities[service].add("metrics")
        parts.append(part)
    features = features_for_window(window, root or Path(), BUCKET_SECONDS)
    if features is not None:
        part = log_intensity(features, window.window_start_iso, n, BUCKET_SECONDS)
        for service in part:
            modalities[service].add("logs")
        parts.append(part)

    return UEGCBuilder(enable_structural=enable_structural).build(
        spans,
        incident_id=window.incident_id,
        variant_config_hash=variant_config_hash,
        captured_at_iso=window.window_end_iso,
        parent_span_id_col_present=has_psid,
        service_modalities=modalities,
        intensity=combine(*parts),
        reasoning_steps=reasoning_steps,
    )
