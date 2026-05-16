"""UEG-C builder — structural (containment) + call (co-occurrence) edges.

Deviation log entry for span-containment heuristic logged before merge (§2.2).
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pyarrow.parquet as pq

from helios.schemas.ueg_c import EdgeType, NodeType, UEGCEdge, UEGCNode, UEGCSnapshot
from helios.vcl import VCLFlag, gated_by

if TYPE_CHECKING:
    from helios.schemas.telemetry import TelemetryWindow


@dataclass(frozen=True)
class SpanRecord:
    trace_id: str
    service_name: str
    start_us: int
    end_us: int


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
    ) -> UEGCSnapshot:
        service_names = sorted({s.service_name for s in spans})
        nodes = [
            UEGCNode(node_id=svc, node_type=NodeType.SERVICE, service_name=svc)
            for svc in service_names
        ]
        edges: list[UEGCEdge] = []
        if self._enable_structural:
            edges.extend(self._structural_edges(spans))
        edges.extend(self._call_edges(spans))
        return UEGCSnapshot(
            incident_id=incident_id,
            variant_config_hash=variant_config_hash,
            nodes=nodes,
            edges=edges,
            captured_at_iso=captured_at_iso,
        )

    def _structural_edges(self, spans: list[SpanRecord]) -> list[UEGCEdge]:
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
    tbl = pq.read_table(window.p2_traces_path)
    cols = tbl.to_pydict()
    n = len(cols["trace_id"])
    spans = [
        SpanRecord(
            trace_id=str(cols["trace_id"][i]),
            service_name=str(cols["service_name"][i]),
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
    )
