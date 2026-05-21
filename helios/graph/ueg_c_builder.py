"""UEG-C builder — structural (containment) + call (co-occurrence) edges.

Deviation log entry for span-containment heuristic logged before merge (§2.2).
"""

from __future__ import annotations

import datetime as dt
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd

from helios.schemas.ueg_c import EdgeType, NodeType, UEGCEdge, UEGCNode, UEGCSnapshot
from helios.vcl import VCLFlag, gated_by

if TYPE_CHECKING:
    from helios.schemas.telemetry import TelemetryWindow

__all__ = ["build_ueg_c"]


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
    span_id: str = (
        ""  # required for parent_span_id lookup; "" until Task 4 wires Parquet
    )
    parent_span_id: str | None = None  # None or "" for root spans


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
    ) -> UEGCSnapshot:
        service_names = sorted({s.service_name for s in spans})
        nodes = [
            UEGCNode(node_id=svc, node_type=NodeType.SERVICE, service_name=svc)
            for svc in service_names
        ]
        edges: list[UEGCEdge] = []
        if self._enable_structural:
            edges.extend(self._structural_edges(spans, parent_span_id_col_present))
        edges.extend(self._call_edges(spans))
        return UEGCSnapshot(
            incident_id=incident_id,
            variant_config_hash=variant_config_hash,
            nodes=nodes,
            edges=edges,
            captured_at_iso=captured_at_iso,
        )

    def _structural_edges(
        self, spans: list[SpanRecord], parent_span_id_col_present: bool
    ) -> list[UEGCEdge]:
        # Fallback only when the column was structurally ABSENT from Parquet (schema v1).
        # A root-only schema v2 trace (all parent_span_id="") is a valid topology and must
        # return an empty edge list — NOT invoke temporal fallback. The caller-supplied flag
        # distinguishes absent-column v1 from root-only v2 — span data alone cannot.
        if not parent_span_id_col_present:
            import warnings

            warnings.warn(
                "parent_span_id absent — falling back to temporal containment",
                stacklevel=3,
            )
            return self._structural_edges_temporal(spans)
        if not spans:
            return []
        span_svc: dict[tuple[str, str], str] = {
            (s.trace_id, s.span_id): s.service_name for s in spans
        }
        pairs: set[tuple[str, str]] = set()
        for child in spans:
            if not child.parent_span_id:
                continue
            parent_svc = span_svc.get((child.trace_id, child.parent_span_id))
            if parent_svc and parent_svc != child.service_name:
                pairs.add((parent_svc, child.service_name))
        return [
            UEGCEdge(source=src, target=tgt, edge_type=EdgeType.STRUCTURAL, weight=1)
            for src, tgt in sorted(pairs)
        ]

    def _structural_edges_temporal(self, spans: list[SpanRecord]) -> list[UEGCEdge]:
        """Original temporal-containment derivation. Kept as named fallback for schema v1."""
        by_trace: dict[str, list[SpanRecord]] = defaultdict(list)
        for s in spans:
            by_trace[s.trace_id].append(s)

        pairs: set[tuple[str, str]] = set()
        for trace_spans in by_trace.values():
            sorted_spans = sorted(trace_spans, key=lambda s: s.start_us)
            for i, span_s in enumerate(sorted_spans):
                for j in range(i - 1, -1, -1):
                    span_p = sorted_spans[j]
                    if span_p.service_name == span_s.service_name:
                        continue  # same-service: keep scanning
                    if (
                        span_p.start_us <= span_s.start_us
                        and span_p.end_us >= span_s.end_us
                    ):
                        pairs.add((span_p.service_name, span_s.service_name))
                        break
        return [
            UEGCEdge(source=src, target=tgt, edge_type=EdgeType.STRUCTURAL, weight=1)
            for src, tgt in sorted(pairs)
        ]

    def _call_edges(self, spans: list[SpanRecord]) -> list[UEGCEdge]:
        by_trace: dict[str, list[SpanRecord]] = defaultdict(list)
        for s in spans:
            by_trace[s.trace_id].append(s)
        total = len(by_trace)
        if total == 0:
            return []
        pair_traces: dict[tuple[str, str], set[str]] = defaultdict(set)
        for tid, trace_spans in by_trace.items():
            sorted_spans = sorted(trace_spans, key=lambda s: s.start_us)
            for i, span_s in enumerate(sorted_spans):
                for j in range(i - 1, -1, -1):
                    span_p = sorted_spans[j]
                    if span_p.service_name == span_s.service_name:
                        continue
                    if (
                        span_p.start_us <= span_s.start_us
                        and span_p.end_us >= span_s.end_us
                    ):
                        pair_traces[span_p.service_name, span_s.service_name].add(tid)
                        break
        return [
            UEGCEdge(
                source=src,
                target=tgt,
                edge_type=EdgeType.CALL,
                weight=len(tids) / total,
            )
            for (src, tgt), tids in sorted(pair_traces.items())
        ]


@gated_by(VCLFlag.L2B_GRAPH)
def build_ueg_c(
    window: TelemetryWindow,
    variant_config_hash: str,
    *,
    enable_structural: bool = True,
) -> UEGCSnapshot | None:
    if window.p2_traces_path is None:
        return None
    df = pd.read_parquet(window.p2_traces_path)
    cols = df.to_dict(orient="list")
    n = len(df)
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
        for i in range(n)
    ]
    captured_at = dt.datetime.now(dt.UTC).isoformat()
    return UEGCBuilder(enable_structural=enable_structural).build(
        spans,
        incident_id=window.incident_id,
        variant_config_hash=variant_config_hash,
        captured_at_iso=captured_at,
        parent_span_id_col_present=has_psid,
    )
