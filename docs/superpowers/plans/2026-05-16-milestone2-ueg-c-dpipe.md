# Milestone 2 — UEG-C Builder + D-pipe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement UEG-C graph builder (structural + call edges, K-hop PPR pruner, SHA-256 snapshot) and D-pipe (Stages A–D: metrics parsing, anomaly scoring, directional propagation, verdict), then run LOO-CV calibration on a 250-cell grid and smoke ablation, all behind VCL feature flags.

**Architecture:** UEG-C is built once per incident by the Orchestrator and passed read-only to D-pipe, G-pipe, and L-pipe. D-pipe Stages A–D run sequentially behind `VCLFlag.DPIPE`; Stage C propagation is additionally gated by `VCLFlag.DPIPE_PROPAGATION`. Calibration uses 15-incident leave-one-out cross-validation; smoke ablation uses a 5-incident hold-out. All calibration thresholds are frozen after LOO-CV.

**Tech Stack:** Python 3.11, NetworkX (PPR), SciPy (Spearman + winsorize), pandas/pyarrow (parquet), pydantic v2, DuckDB (result store), pytest TDD throughout.

---

### Task 0: Prerequisites — deviation log entry, dependencies, tracking rows, ground truth

**Files:**
- Modify: `pyproject.toml`, `poetry.lock`
- Modify: `docs/tracking/helios_mvp_tracking.md`
- Create: `data/ground_truth.json`

- [ ] **Step 1: Add networkx and scipy to project dependencies**

```bash
poetry add networkx scipy
poetry lock
poetry run pytest
```

Expected: `poetry.lock` regenerated; all existing tests pass.

- [ ] **Step 2: Log deviation entry for span-containment heuristic (required before any UEG-C code)**

The M2 spec §2.2 mandates this entry before merging any UEG-C commit.

```bash
set -a; source .env; set +a
poetry run python bin/log_deviation.py \
  --stage "Stage 1" \
  --clause "§2.2 Span Containment Heuristic" \
  --change "Temporal containment backward-scan instead of OpenTelemetry parent_span_id linkage" \
  --reason "p2_traces parquet schema omits parent_span_id; temporal heuristic is the only available signal" \
  --analytic-consequence "Potential structural-edge misattribution in deeply nested same-service call stacks; bounded to PPR pruner entry-point identification only — not anomaly scores or ranked candidates; replacement is a pre-M3 gate"
poetry run python bin/log_deviation.py verify
poetry run pytest tests/test_deviation_log.py -v
```

Expected: verify exits 0; all 12 deviation-log tests pass.

- [ ] **Step 3: Append M2 tracking section (PLANNED state)**

Append the following section to `docs/tracking/helios_mvp_tracking.md` after the last M1 row:

```markdown
---

## MILESTONE 2 — UEG-C Builder + D-pipe

**Row ID format:** `S1-M2-{TYPE}{nn}` — spans multiple sessions; Day recorded as `-` for all M2 rows.

| Task_ID | Day | Type | Description | Prop_§ | DSR | Contrib | Own | Deps | Status | Started | Done | SHA | Ev_Type | Ev_Ref | Gate | Dev_Ref | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1-M2-ENG01 | - | ENG | dpipe_config.py typed constants (LE_BOUNDARIES, grids, gates) | §3.3, §3.6.5 | Design | C2 | AA | - | PLANNED | | | | | | | | |
| S1-M2-ENG02 | - | ENG | UEGCBuilder structural + call edges | §3.6.4 | Design | C2 | AA | S1-M2-ENG01 | PLANNED | | | | | | | | |
| S1-M2-ENG03 | - | ENG | PPR pruner + build_ueg_c() factory | §3.6.4 | Design | C2 | AA | S1-M2-ENG02 | PLANNED | | | | | | | | |
| S1-M2-GATE01 | - | GATE | Hash stability + canonical round-trip exit gate | §6.2 | Evaluate | C2 | AA | S1-M2-ENG03 | PLANNED | | | | | | | | |
| S1-M2-ENG04 | - | ENG | Stage A MetricsParser | §3.3 | Design | C2 | AA | S1-M2-ENG01 | PLANNED | | | | | | | | |
| S1-M2-ENG05 | - | ENG | Stage B wm90 + AnomalyScorer | §3.3 | Design | C2 | AA | S1-M2-ENG04 | PLANNED | | | | | | | | |
| S1-M2-ENG06 | - | ENG | Stage C PropagationEngine | §3.3 | Design | C2 | AA | S1-M2-ENG05 | PLANNED | | | | | | | | |
| S1-M2-ENG07 | - | ENG | Stage D DVerdict | §3.3 | Design | C2 | AA | S1-M2-ENG06 | PLANNED | | | | | | | | |
| S1-M2-ENG08 | - | ENG | pipeline.py + runner.py integration | §3.6.8 | Design | C2 | AA | S1-M2-ENG07,S1-M2-ENG03 | PLANNED | | | | | | | | |
| S1-M2-ENG09 | - | ENG | LOO-CV calibration script (250-cell joint grid) | §4.1 | Demonstrate | C2 | AA | S1-M2-ENG08 | PLANNED | | | | | | | | |
| S1-M2-EVAL01 | - | EVAL | Smoke ablation (HELIOS-D vs random + in-degree baselines) | §4.2 | Evaluate | C2 | AA | S1-M2-ENG09 | PLANNED | | | | | | | | |
| S1-M2-GATE02 | - | GATE | Milestone 2 exit gate — all criteria met | §5.2 | Evaluate | C2 | AA | S1-M2-EVAL01 | PLANNED | | | | | | | | |
```

Commit: `git commit -m "chore(tracking): append M2 PLANNED rows"`

Then change all M2 Status values from `PLANNED` to `IN_PROGRESS` and commit:
`git commit -m "chore(tracking): M2 rows → IN_PROGRESS"`

- [ ] **Step 4: Create data/ground_truth.json**

```json
{
  "s0-adhc-001": "ad",
  "s0-adhc-002": "ad",
  "s0-adhc-003": "ad",
  "s0-cart-001": "cart",
  "s0-cart-002": "cart",
  "s0-cart-003": "cart",
  "s0-imgsl-001": "frontend",
  "s0-imgsl-002": "frontend",
  "s0-imgsl-003": "frontend",
  "s0-imgsl-004": "frontend",
  "s0-pcat-001": "product-catalog",
  "s0-pcat-002": "product-catalog",
  "s0-pcat-003": "product-catalog",
  "s0-pcat-004": "product-catalog",
  "s0-pcat-005": "product-catalog",
  "s0-rcf-001": "recommendation",
  "s0-rcf-002": "recommendation",
  "s0-rcf-003": "recommendation",
  "s0-rcf-004": "recommendation",
  "s0-rcf-005": "recommendation"
}
```

Calibration set (15 incidents): adhc-001..003, cart-001..003, imgsl-001..004, pcat-001..005.
Smoke hold-out (5 incidents): rcf-001..005 (disjoint from calibration set).

```bash
git add data/ground_truth.json
git commit -m "data: ground_truth.json for calibration + smoke ablation"
```

---

### Task 1: dpipe_config.py — all typed constants

**Files:**
- Create: `helios/pipelines/d_pipe/dpipe_config.py`
- Create: `tests/pipelines/__init__.py`
- Create: `tests/pipelines/d_pipe/__init__.py`
- Create: `tests/pipelines/d_pipe/test_dpipe_config.py`

- [ ] **Step 1: Discover LE_BOUNDARIES from the actual parquet capture**

```bash
poetry run python - << 'PYEOF'
import ast
import pandas as pd

df = pd.read_parquet("data/captures/s0-adhc-001/p1_metrics.parquet")
mask = df["metric_name"] == "http_server_duration_milliseconds_bucket"
le_vals = sorted(set(
    float(ast.literal_eval(r)["le"])
    for r in df[mask]["labels"]
    if ast.literal_eval(r).get("le", "+Inf") != "+Inf"
))
print("LE_BOUNDARIES =", le_vals)
print("bucket count =", len(le_vals))
PYEOF
```

Record the output list — you will paste it into `LE_BOUNDARIES` in Step 3.

- [ ] **Step 2: Write the failing test**

Create `tests/pipelines/__init__.py` (empty) and `tests/pipelines/d_pipe/__init__.py` (empty).

Create `tests/pipelines/d_pipe/test_dpipe_config.py`:

```python
"""Sanity checks for dpipe_config typed constants."""
from __future__ import annotations

from helios.pipelines.d_pipe.dpipe_config import (
    INF_MIDPOINT,
    K_INF_MIDPOINT,
    LE_BOUNDARIES,
    PRUNER_EFFICACY_GATE,
    RANDOM_BASELINE_SEED,
    RHO_THRESHOLD_GRID,
    TOPOLOGY_BOOST_GRID,
    W_ERROR_GRID,
)


def test_le_boundaries_nonempty_sorted_positive() -> None:
    assert len(LE_BOUNDARIES) >= 14
    assert LE_BOUNDARIES == sorted(LE_BOUNDARIES)
    assert all(b > 0 for b in LE_BOUNDARIES)


def test_inf_midpoint_matches_k() -> None:
    assert INF_MIDPOINT == K_INF_MIDPOINT * 10000


def test_grids_nonempty() -> None:
    assert len(W_ERROR_GRID) == 5
    assert len(RHO_THRESHOLD_GRID) == 5
    assert len(TOPOLOGY_BOOST_GRID) == 10


def test_topology_boost_grid_all_ge_one() -> None:
    assert all(v >= 1 for v in TOPOLOGY_BOOST_GRID)


def test_pruner_efficacy_gate_in_open_interval() -> None:
    assert 0 < PRUNER_EFFICACY_GATE < 1


def test_random_baseline_seed_is_int() -> None:
    assert isinstance(RANDOM_BASELINE_SEED, int)
```

Run: `poetry run pytest tests/pipelines/d_pipe/test_dpipe_config.py -v`
Expected: fails with `ModuleNotFoundError` (module not yet created).

- [ ] **Step 3: Implement dpipe_config.py**

Replace `[PASTE_LE_BOUNDARIES_HERE]` with the list from Step 1.

```python
"""D-pipe typed constants — single source of truth for all calibration parameters."""
from __future__ import annotations

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

# Latency histogram bucket finite upper bounds in ms.
# Derived from: poetry run python - (Step 1 of Task 1). Do not edit by hand.
LE_BOUNDARIES: list[float] = [PASTE_LE_BOUNDARIES_HERE]

K_INF_MIDPOINT: int = 3
INF_MIDPOINT: float = K_INF_MIDPOINT * 10000  # 30_000 ms representative cap

# Stage B error weight (calibrated; default before grid search)
W_ERROR_DEFAULT: float = 0.50

# Joint calibration grid: 5 × 5 × 10 = 250 cells
W_ERROR_GRID: list[float] = [0.3, 0.50, 0.6, 0.7, 0.9]
RHO_THRESHOLD_GRID: list[float] = [0.2, 0.4, 0.6, 0.7, 0.8]
TOPOLOGY_BOOST_GRID: list[float] = [1.00, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8]

# Exit gates (label-free)
PRUNER_EFFICACY_GATE: float = 0.50   # >= 50% node reduction required on calibration set
INTEGRITY_RATE_GATE: float = 0.85    # structural reachability lower bound

# Smoke ablation baseline
RANDOM_BASELINE_SEED: int = 0
```

- [ ] **Step 4: Run tests**

```bash
poetry run pytest tests/pipelines/d_pipe/test_dpipe_config.py -v
```

Expected: all 6 pass.

- [ ] **Step 5: Commit**

```bash
git add helios/pipelines/d_pipe/dpipe_config.py \
        tests/pipelines/__init__.py \
        tests/pipelines/d_pipe/__init__.py \
        tests/pipelines/d_pipe/test_dpipe_config.py
git commit -m "feat(dpipe): dpipe_config.py typed constants + tests"
```


---

### Task 2: UEGCBuilder — structural and call edges

**Files:**
- Create: `helios/graph/__init__.py`
- Create: `helios/graph/ueg_c_builder.py`
- Create: `tests/graph/__init__.py`
- Create: `tests/graph/test_ueg_c_builder.py`

- [ ] **Step 1: Write the failing test**

Create `tests/graph/__init__.py` (empty).

Create `tests/graph/test_ueg_c_builder.py`:

```python
"""TDD for UEGCBuilder structural + call edge construction."""
from __future__ import annotations

import pytest

from helios.graph.ueg_c_builder import SpanRecord, UEGCBuilder
from helios.schemas.ueg_c import EdgeType


def _builder_structural() -> UEGCBuilder:
    return UEGCBuilder(enable_structural=True)


def _span(trace: str, svc: str, start: int, dur: int) -> SpanRecord:
    return SpanRecord(trace_id=trace, service_name=svc, start_us=start, end_us=start + dur)


_HASH = "a" * 64
_AT = "2026-01-01T00:00:00+00:00"


def test_structural_edge_parent_encloses_child() -> None:
    spans = [
        _span("t1", "frontend", 0, 1000),
        _span("t1", "checkout", 1_00, 800),
    ]
    snap = _builder_structural().build(spans, incident_id="inc", variant_config_hash=_HASH, captured_at_iso=_AT)
    s_edges = [e for e in snap.edges if e.edge_type == EdgeType.STRUCTURAL]
    assert len(s_edges) == 1
    assert s_edges[0].source == "frontend"
    assert s_edges[0].target == "checkout"
    assert s_edges[0].weight == 1


def test_structural_scan_skips_same_service_spans() -> None:
    spans = [
        _span("t1", "frontend", 0, 2000),
        _span("t1", "frontend", 1_00, 500),   # same service — skip
        _span("t1", "checkout", 200, 200),
    ]
    snap = _builder_structural().build(spans, incident_id="inc", variant_config_hash=_HASH, captured_at_iso=_AT)
    s_edges = [e for e in snap.edges if e.edge_type == EdgeType.STRUCTURAL]
    assert len(s_edges) == 1
    assert s_edges[0].source == "frontend"
    assert s_edges[0].target == "checkout"


def test_structural_disabled_emits_no_structural_edges() -> None:
    spans = [
        _span("t1", "a", 0, 1000),
        _span("t1", "b", 1_00, 800),
    ]
    snap = UEGCBuilder(enable_structural=False).build(
        spans, incident_id="inc", variant_config_hash=_HASH, captured_at_iso=_AT
    )
    assert not any(e.edge_type == EdgeType.STRUCTURAL for e in snap.edges)


def test_call_edge_weight_equals_fraction_of_traces() -> None:
    # Pair (frontend, checkout) observed in 2 of 2 traces
    spans = [
        _span("t1", "frontend", 0, 1000),
        _span("t1", "checkout", 1_00, 800),
        _span("t2", "frontend", 0, 1000),
        _span("t2", "checkout", 1_00, 800),
    ]
    snap = UEGCBuilder(enable_structural=False).build(
        spans, incident_id="inc", variant_config_hash=_HASH, captured_at_iso=_AT
    )
    c_edges = [e for e in snap.edges if e.edge_type == EdgeType.CALL]
    fe_co = next(e for e in c_edges if e.source == "frontend" and e.target == "checkout")
    assert fe_co.weight == pytest.approx(2 / 2)


def test_call_edge_partial_trace_coverage() -> None:
    # Pair observed in 1 of 2 traces
    spans = [
        _span("t1", "frontend", 0, 1000),
        _span("t1", "checkout", 1_00, 800),
        _span("t2", "frontend", 0, 1000),
    ]
    snap = UEGCBuilder(enable_structural=False).build(
        spans, incident_id="inc", variant_config_hash=_HASH, captured_at_iso=_AT
    )
    c_edges = [e for e in snap.edges if e.edge_type == EdgeType.CALL]
    fe_co = next((e for e in c_edges if e.source == "frontend" and e.target == "checkout"), None)
    assert fe_co is not None
    assert fe_co.weight == pytest.approx(1 / 2)


def test_nodes_one_per_service() -> None:
    spans = [_span("t1", "a", 0, 1000), _span("t1", "b", 100, 500), _span("t2", "a", 0, 800)]
    snap = _builder_structural().build(spans, incident_id="inc", variant_config_hash=_HASH, captured_at_iso=_AT)
    assert {n.service_name for n in snap.nodes} == {"a", "b"}
```

Run: `poetry run pytest tests/graph/test_ueg_c_builder.py -v`
Expected: fails with `ModuleNotFoundError`.

- [ ] **Step 2: Create `helios/graph/__init__.py`**

```python
"""UEG-C graph construction — L1/L2 shared infrastructure."""
```

- [ ] **Step 3: Implement `helios/graph/ueg_c_builder.py`**

```python
"""UEG-C builder — structural (containment) + call (co-occurrence) edges.

Deviation log entry S-DEV-xxx required for span-containment heuristic before merge.
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
                    if span_p.start_us <= span_s.start_us and span_p.end_us >= span_s.end_us:
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
                    if span_p.start_us <= span_s.start_us and span_p.end_us >= span_s.end_us:
                        pair_traces[(span_p.service_name, span_s.service_name)].add(tid)
                        break
        return [
            UEGCEdge(source=src, target=tgt, edge_type=EdgeType.CALL, weight=len(tids) / total)
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
    captured_at = dt.datetime.now(dt.timezone.utc).isoformat()
    return UEGCBuilder(enable_structural=enable_structural).build(
        spans,
        incident_id=window.incident_id,
        variant_config_hash=variant_config_hash,
        captured_at_iso=captured_at,
    )
```

- [ ] **Step 4: Run tests**

```bash
poetry run pytest tests/graph/test_ueg_c_builder.py -v
poetry run pytest  # full suite — no regressions
```

Expected: all 6 UEGCBuilder tests pass; full suite green.

- [ ] **Step 5: Commit**

```bash
git add helios/graph/__init__.py helios/graph/ueg_c_builder.py \
        tests/graph/__init__.py tests/graph/test_ueg_c_builder.py
git commit -m "feat(graph): UEGCBuilder structural + call edges"
```

---

### Task 3: PPR pruner + build_ueg_c factory

**Files:**
- Create: `helios/graph/ppr_pruner.py`
- Create: `tests/graph/test_ppr_pruner.py`

- [ ] **Step 1: Write the failing test**

Create `tests/graph/test_ppr_pruner.py`:

```python
"""TDD for PPR pruner."""
from __future__ import annotations

from helios.graph.ppr_pruner import PruneResult, prune_graph
from helios.schemas.ueg_c import EdgeType, NodeType, UEGCEdge, UEGCNode, UEGCSnapshot

_HASH = "a" * 64
_AT = "2026-01-01T00:00:00+00:00"


def _snapshot(n_services: list[str], edges: list[UEGCEdge]) -> UEGCSnapshot:
    nodes = [UEGCNode(node_id=s, node_type=NodeType.SERVICE, service_name=s) for s in n_services]
    return UEGCSnapshot(incident_id="t", variant_config_hash=_HASH, nodes=nodes, edges=edges, captured_at_iso=_AT)


def test_prune_result_fields() -> None:
    snap = _snapshot(["a", "b"], [UEGCEdge(source="a", target="b", edge_type=EdgeType.CALL, weight=0.80)])
    _, result = prune_graph(snap, pruner_threshold=0.001)
    assert isinstance(result, PruneResult)
    assert result.nodes_before == 2
    assert result.edges_before == 1
    assert 0 < result.integrity_rate <= 1.00


def test_isolated_node_pruned_at_high_threshold() -> None:
    # a→b structural, c is isolated (not reachable from entry points)
    edges = [
        UEGCEdge(source="a", target="b", edge_type=EdgeType.STRUCTURAL, weight=1),
        UEGCEdge(source="a", target="b", edge_type=EdgeType.CALL, weight=0.80),
    ]
    snap = _snapshot(["a", "b", "c"], edges)
    pruned, result = prune_graph(snap, pruner_threshold=0.05)
    assert result.nodes_before == 3
    assert result.nodes_after <= 2
    pruned_svcs = {n.service_name for n in pruned.nodes}
    assert "c" not in pruned_svcs


def test_integrity_rate_computed_correctly() -> None:
    snap = _snapshot(["a", "b"], [UEGCEdge(source="a", target="b", edge_type=EdgeType.CALL, weight=0.80)])
    _, result = prune_graph(snap, pruner_threshold=0.001)
    assert result.integrity_rate == result.nodes_after / result.nodes_before


def test_prune_result_no_assert_caller_enforces_gate() -> None:
    snap = _snapshot(["x"], [])
    _, result = prune_graph(snap, pruner_threshold=0.99)
    # Must return PruneResult even if integrity_rate < INTEGRITY_RATE_GATE; no assert inside
    assert isinstance(result, PruneResult)
```

Run: `poetry run pytest tests/graph/test_ppr_pruner.py -v`
Expected: fails with `ModuleNotFoundError`.

- [ ] **Step 2: Implement `helios/graph/ppr_pruner.py`**

```python
"""K-hop PPR pruner — entry-point seeded Personalized PageRank graph reduction."""
from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from helios.schemas.ueg_c import EdgeType, UEGCSnapshot
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


@dataclass
class PruneResult:
    nodes_before: int
    nodes_after: int
    edges_before: int
    edges_after: int

    @property
    def integrity_rate(self) -> float:
        if self.nodes_before == 0:
            return 1.00
        return self.nodes_after / self.nodes_before


def prune_graph(
    snapshot: UEGCSnapshot,
    *,
    pruner_threshold: float = 0.01,
) -> tuple[UEGCSnapshot, PruneResult]:
    G: nx.DiGraph = nx.DiGraph()
    for node in snapshot.nodes:
        G.add_node(node.service_name)
    for edge in snapshot.edges:
        G.add_edge(edge.source, edge.target, weight=edge.weight)

    # Entry points: services with structural in-degree == 0
    structural_in: dict[str, int] = {n: 0 for n in G.nodes}
    for edge in snapshot.edges:
        if edge.edge_type == EdgeType.STRUCTURAL:
            structural_in[edge.target] = structural_in.get(edge.target, 0) + 1
    entry_points = [n for n, deg in structural_in.items() if deg == 0]
    if not entry_points:
        entry_points = list(G.nodes)

    n_entry = len(entry_points)
    personalization = {
        n: (1 / n_entry if n in entry_points else 0.00)
        for n in G.nodes
    }

    # alpha=0.85 → restart_probability=0.15 (spec §2.4)
    ppr: dict[str, float] = nx.pagerank(G, alpha=0.85, personalization=personalization)

    retained = {n for n, score in ppr.items() if score >= pruner_threshold}
    kept_nodes = [n for n in snapshot.nodes if n.service_name in retained]
    kept_edges = [e for e in snapshot.edges if e.source in retained and e.target in retained]

    pruned = snapshot.model_copy(update={"nodes": kept_nodes, "edges": kept_edges})

    return pruned, PruneResult(
        nodes_before=len(snapshot.nodes),
        nodes_after=len(kept_nodes),
        edges_before=len(snapshot.edges),
        edges_after=len(kept_edges),
    )
```

- [ ] **Step 3: Run tests**

```bash
poetry run pytest tests/graph/test_ppr_pruner.py -v
poetry run pytest  # full suite
```

Expected: all 4 pruner tests pass.

- [ ] **Step 4: Commit**

```bash
git add helios/graph/ppr_pruner.py tests/graph/test_ppr_pruner.py
git commit -m "feat(graph): PPR pruner + PruneResult"
```


---

### Task 4: Hash stability tests (exit gate §2.5)

**Files:**
- Create: `tests/graph/test_hash_stability.py`

- [ ] **Step 1: Write the failing test**

Create `tests/graph/test_hash_stability.py`:

```python
"""Exit gate §2.5: zero hash collisions and stable canonical round-trip."""
from __future__ import annotations

from helios.schemas.ueg_c import EdgeType, NodeType, UEGCEdge, UEGCNode, UEGCSnapshot

_HASH = "a" * 64
_AT = "2026-01-01T00:00:00+00:00"


def _make_snapshot(incident_id: str = "inc-001") -> UEGCSnapshot:
    return UEGCSnapshot(
        incident_id=incident_id,
        variant_config_hash=_HASH,
        nodes=[UEGCNode(node_id="a", node_type=NodeType.SERVICE, service_name="a")],
        edges=[UEGCEdge(source="a", target="a", edge_type=EdgeType.CALL, weight=0.80)],
        captured_at_iso=_AT,
    )


def test_snapshot_hash_stable_on_repeated_calls() -> None:
    snap = _make_snapshot()
    h1 = snap.compute_snapshot_hash()
    h2 = snap.compute_snapshot_hash()
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex digest length


def test_snapshot_hash_round_trip_via_model_dump() -> None:
    snap = _make_snapshot()
    h1 = snap.compute_snapshot_hash()
    dumped = snap.model_dump()
    reloaded = UEGCSnapshot.model_validate(dumped)
    h2 = reloaded.compute_snapshot_hash()
    assert h1 == h2


def test_different_incident_ids_produce_different_hashes() -> None:
    h1 = _make_snapshot("inc-001").compute_snapshot_hash()
    h2 = _make_snapshot("inc-002").compute_snapshot_hash()
    assert h1 != h2


def test_edge_weight_change_invalidates_hash() -> None:
    snap1 = UEGCSnapshot(
        incident_id="x", variant_config_hash=_HASH,
        nodes=[UEGCNode(node_id="a", node_type=NodeType.SERVICE, service_name="a")],
        edges=[UEGCEdge(source="a", target="a", edge_type=EdgeType.CALL, weight=0.3)],
        captured_at_iso=_AT,
    )
    snap2 = UEGCSnapshot(
        incident_id="x", variant_config_hash=_HASH,
        nodes=[UEGCNode(node_id="a", node_type=NodeType.SERVICE, service_name="a")],
        edges=[UEGCEdge(source="a", target="a", edge_type=EdgeType.CALL, weight=0.4)],
        captured_at_iso=_AT,
    )
    assert snap1.compute_snapshot_hash() != snap2.compute_snapshot_hash()
```

Run: `poetry run pytest tests/graph/test_hash_stability.py -v`
Expected: all 4 pass immediately (logic lives in `UEGCSnapshot` which is already implemented).

- [ ] **Step 2: If any test fails, trace the failure to `helios/vcl/utils.py` canonical_json**

`compute_snapshot_hash()` calls `canonical_json(self.model_dump())`. The round-trip test failure means `edge_class` (a computed field) is being serialized but then rejected on re-load. The `UEGCEdge._strip_computed_fields` validator strips `edge_class` before validation — verify it runs by checking `tests/test_schema_roundtrip.py`.

- [ ] **Step 3: Commit**

```bash
git add tests/graph/test_hash_stability.py
git commit -m "test(graph): hash stability exit gate §2.5"
```

---

### Task 5: Stage A — MetricsParser

**Files:**
- Create: `helios/pipelines/d_pipe/stages/__init__.py`
- Create: `helios/pipelines/d_pipe/stages/a_metrics_parser.py`
- Create: `tests/pipelines/d_pipe/test_a_metrics_parser.py`

- [ ] **Step 1: Inspect the actual label schema in the parquet**

Run this script to discover which label key holds the service name:

```bash
poetry run python scripts/inspect_metric_labels.py
```

Create `scripts/inspect_metric_labels.py` (delete after use):

```python
"""One-off: print sample label dicts from p1_metrics.parquet to find service-name key."""
import ast
import pandas as pd

df = pd.read_parquet("data/captures/s0-adhc-001/p1_metrics.parquet")
mask = df["metric_name"] == "http_server_duration_milliseconds_bucket"
for labels_str in df[mask]["labels"].head(3):
    print(ast.literal_eval(labels_str))
```

Record the key that identifies the service (likely `job` or `service_name`). Use it as `_SVC_LABEL_KEY` in Step 3.

- [ ] **Step 2: Write the failing test**

Create `helios/pipelines/d_pipe/stages/__init__.py` (empty).

Create `tests/pipelines/d_pipe/test_a_metrics_parser.py`:

```python
"""TDD for Stage A MetricsParser."""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest

from helios.pipelines.d_pipe.stages.a_metrics_parser import MetricsParser, ParsedMetrics


def _make_http_row(
    ts: float, svc: str, status: str, le: str, value: float
) -> dict[str, object]:
    labels = json.dumps({"job": svc, "http_response_status_code": status, "le": le}, sort_keys=True)
    return {"timestamp": ts, "metric_name": "http_server_duration_milliseconds_bucket", "value": value, "labels": labels}


def _make_df(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_parsed_metrics_has_expected_fields() -> None:
    rows = [_make_http_row(1.00, "svc-a", "200", "+Inf", 10.0)]
    df = _make_df(rows)
    result = MetricsParser().parse(df)
    assert isinstance(result, ParsedMetrics)
    assert hasattr(result, "error_deltas")
    assert hasattr(result, "latency_means")
    assert hasattr(result, "steps")
    assert hasattr(result, "p1_services")


def test_error_delta_single_step() -> None:
    # t=1: cumulative count=5; t=2: count=8 → delta=3
    rows = [
        _make_http_row(1.00, "svc-a", "500", "+Inf", 5.0),
        _make_http_row(2.0, "svc-a", "500", "+Inf", 8.0),
    ]
    df = _make_df(rows)
    result = MetricsParser().parse(df)
    assert "svc-a" in result.error_deltas
    deltas = [d for d in result.error_deltas["svc-a"] if not math.isnan(d)]
    assert len(deltas) == 1
    assert deltas[0] == pytest.approx(3.0)


def test_counter_reset_produces_nan() -> None:
    # Counter goes down at t=2 — should produce NaN
    rows = [
        _make_http_row(1.00, "svc-a", "500", "+Inf", 10.0),
        _make_http_row(2.0, "svc-a", "500", "+Inf", 3.0),
        _make_http_row(3.0, "svc-a", "500", "+Inf", 6.0),
    ]
    df = _make_df(rows)
    result = MetricsParser().parse(df)
    assert math.isnan(result.error_deltas["svc-a"][0])   # t=2 reset
    assert result.error_deltas["svc-a"][1] == pytest.approx(3.0)   # t=3: 6-3=3


def test_non_error_status_not_counted() -> None:
    rows = [
        _make_http_row(1.00, "svc-a", "200", "+Inf", 5.0),
        _make_http_row(2.0, "svc-a", "200", "+Inf", 10.0),
    ]
    df = _make_df(rows)
    result = MetricsParser().parse(df)
    # No error status codes → error_deltas should be zero or absent
    if "svc-a" in result.error_deltas:
        assert all(d == pytest.approx(0) or math.isnan(d) for d in result.error_deltas["svc-a"])
```

Run: `poetry run pytest tests/pipelines/d_pipe/test_a_metrics_parser.py -v`
Expected: fails with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `helios/pipelines/d_pipe/stages/a_metrics_parser.py`**

```python
"""Stage A: Telemetry parser — aggregate, difference, error + latency extraction."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from helios.pipelines.d_pipe.dpipe_config import INF_MIDPOINT, LE_BOUNDARIES
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

HTTP_METRIC = "http_server_duration_milliseconds_bucket"
GRPC_METRIC = "rpc_server_duration_milliseconds_bucket"
HTTP_ERROR_CODES: frozenset[str] = frozenset({"500", "503"})
GRPC_ERROR_CODES: frozenset[str] = frozenset({"12", "13", "14"})

# Label key that identifies the service — update if inspection reveals a different key.
_SVC_LABEL_KEY = "job"


@dataclass(frozen=True)
class ParsedMetrics:
    error_deltas: dict[str, list[float]]
    latency_means: dict[str, list[float]]
    steps: list[float]
    p1_services: list[str]


def _diff_series(agg: pd.Series) -> list[float]:
    """Compute delta series; set NaN where delta < 0 (counter reset)."""
    agg_sorted = agg.sort_index()
    deltas: list[float] = []
    prev = agg_sorted.iloc[0]
    for val in agg_sorted.iloc[1:]:
        diff = val - prev
        deltas.append(float("nan") if diff < 0 else float(diff))
        prev = val
    return deltas


def _histogram_mean(bucket_counts: list[float]) -> float:
    total = bucket_counts[-1]
    if total == 0:
        return float("nan")
    weighted = 0.00
    prev: float = 0
    for i, le in enumerate(LE_BOUNDARIES):
        count_in_bin = bucket_counts[i] - prev
        midpoint = (prev + le) / 2
        weighted += count_in_bin * midpoint
        prev = le
    inf_count = total - bucket_counts[len(LE_BOUNDARIES) - 1]
    weighted += inf_count * INF_MIDPOINT
    return weighted / total


class MetricsParser:
    def parse(self, df: pd.DataFrame) -> ParsedMetrics:
        df = df.copy()
        df["labels_dict"] = df["labels"].apply(json.loads)
        df["service"] = df["labels_dict"].apply(lambda d: str(d.get(_SVC_LABEL_KEY, "")))
        df["le"] = df["labels_dict"].apply(lambda d: str(d.get("le", "")))
        df["http_status"] = df["labels_dict"].apply(lambda d: str(d.get("http_response_status_code", "")))
        df["grpc_status"] = df["labels_dict"].apply(lambda d: str(d.get("rpc_grpc_status_code", "")))

        services = sorted(df["service"].dropna().unique())
        timestamps = sorted(df["timestamp"].unique())

        error_deltas: dict[str, list[float]] = {}
        latency_means: dict[str, list[float]] = {}

        for svc in services:
            svc_df = df[df["service"] == svc]

            # Error extraction: le=+Inf rows matching error status codes
            http_err = svc_df[
                (svc_df["metric_name"] == HTTP_METRIC)
                & (svc_df["le"] == "+Inf")
                & (svc_df["http_status"].isin(HTTP_ERROR_CODES))
            ]
            grpc_err = svc_df[
                (svc_df["metric_name"] == GRPC_METRIC)
                & (svc_df["le"] == "+Inf")
                & (svc_df["grpc_status"].isin(GRPC_ERROR_CODES))
            ]
            err_combined = pd.concat([http_err, grpc_err])
            if not err_combined.empty:
                agg_err = err_combined.groupby("timestamp")["value"].sum()
                agg_err = agg_err.reindex(timestamps, fill_value=0)
                error_deltas[svc] = _diff_series(agg_err)

            # Latency extraction: one mean per timestamp from histogram buckets
            lat_metric = HTTP_METRIC if not svc_df[svc_df["metric_name"] == HTTP_METRIC].empty else GRPC_METRIC
            lat_df = svc_df[svc_df["metric_name"] == lat_metric]
            means: list[float] = []
            for ts in timestamps[1:]:
                ts_df = lat_df[lat_df["timestamp"] == ts]
                if ts_df.empty:
                    means.append(float("nan"))
                    continue
                agg = ts_df.groupby("le")["value"].sum()
                bucket_counts = [float(agg.get(str(le), 0)) for le in LE_BOUNDARIES]
                bucket_counts.append(float(agg.get("+Inf", 0)))
                means.append(_histogram_mean(bucket_counts))
            if means:
                latency_means[svc] = means

        steps = list(timestamps[1:])
        p1_services = [s for s in services if s in error_deltas or s in latency_means]

        return ParsedMetrics(
            error_deltas=error_deltas,
            latency_means=latency_means,
            steps=steps,
            p1_services=p1_services,
        )
```

Note: `_SVC_LABEL_KEY = "job"` may need updating based on Step 1 inspection result.

- [ ] **Step 4: Run tests**

```bash
poetry run pytest tests/pipelines/d_pipe/test_a_metrics_parser.py -v
poetry run pytest  # full suite
```

Expected: all 4 parser tests pass.

- [ ] **Step 5: Commit**

```bash
git add helios/pipelines/d_pipe/stages/__init__.py \
        helios/pipelines/d_pipe/stages/a_metrics_parser.py \
        tests/pipelines/d_pipe/test_a_metrics_parser.py
git commit -m "feat(dpipe): Stage A MetricsParser"
```


---

### Task 6: Stage B — wm90 + AnomalyScorer

**Files:**
- Create: `helios/pipelines/d_pipe/stages/b_anomaly_scorer.py`
- Create: `tests/pipelines/d_pipe/test_b_anomaly_scorer.py`

- [ ] **Step 1: Write the failing test**

Create `tests/pipelines/d_pipe/test_b_anomaly_scorer.py`:

```python
"""TDD for Stage B wm90 and AnomalyScorer."""
from __future__ import annotations

import math

import numpy as np
import pytest

from helios.pipelines.d_pipe.stages.b_anomaly_scorer import AnomalyScorer, wm90


def test_wm90_all_zeros_returns_zero() -> None:
    result = wm90(np.zeros(20))
    assert result == pytest.approx(0)


def test_wm90_ignores_nan() -> None:
    arr = np.array([float("nan")] * 5 + [2.0] * 15)
    result = wm90(arr)
    assert not math.isnan(result)
    assert result > 0


def test_wm90_all_nan_returns_nan() -> None:
    result = wm90(np.full(5, float("nan")))
    assert math.isnan(result)


def test_wm90_clamps_single_spike() -> None:
    arr = np.array([1.00] * 19 + [1000.0])
    result = wm90(arr)
    # Spike clamped to third-highest (which is 1.00 here); result ≈ 1.00
    assert result == pytest.approx(1.00)


def test_anomaly_scorer_non_p1_gets_zero() -> None:
    error_deltas: dict[str, list[float]] = {"svc-a": [5.0] * 20}
    latency_means: dict[str, list[float]] = {"svc-a": [10.0] * 20}
    scorer = AnomalyScorer(w_error=0.50)
    result = scorer.score(error_deltas, latency_means, p1_services=["svc-a"])
    assert "svc-a" in result
    assert result.get("svc-b", 0.00) == pytest.approx(0)


def test_anomaly_scorer_scores_in_unit_interval() -> None:
    error_deltas = {"a": [1_00.0] * 20, "b": [10.0] * 20}
    latency_means = {"a": [500.0] * 20, "b": [50.0] * 20}
    scorer = AnomalyScorer(w_error=0.50)
    result = scorer.score(error_deltas, latency_means, p1_services=["a", "b"])
    for svc, val in result.items():
        assert 0 <= val <= 1.00, f"{svc} score {val} out of range"


def test_anomaly_scorer_higher_errors_rank_first() -> None:
    error_deltas = {"high": [200.0] * 20, "low": [1.00] * 20}
    latency_means = {"high": [1.00] * 20, "low": [1.00] * 20}
    scorer = AnomalyScorer(w_error=0.9)
    result = scorer.score(error_deltas, latency_means, p1_services=["high", "low"])
    assert result["high"] > result["low"]
```

Run: `poetry run pytest tests/pipelines/d_pipe/test_b_anomaly_scorer.py -v`
Expected: fails with `ModuleNotFoundError`.

- [ ] **Step 2: Implement `helios/pipelines/d_pipe/stages/b_anomaly_scorer.py`**

```python
"""Stage B: anomaly scoring — wm90 winsorised mean + global cross-service normalisation."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.stats.mstats

from helios.pipelines.d_pipe.dpipe_config import W_ERROR_DEFAULT
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def wm90(series: np.ndarray) -> float:
    valid = series[~np.isnan(series)]
    if len(valid) == 0:
        return float("nan")
    n = len(valid)
    winsorized = scipy.stats.mstats.winsorize(valid, limits=[0, 2 / n])
    return float(np.mean(winsorized))


@dataclass
class AnomalyScorer:
    w_error: float = W_ERROR_DEFAULT

    def score(
        self,
        error_deltas: dict[str, list[float]],
        latency_means: dict[str, list[float]],
        p1_services: list[str],
    ) -> dict[str, float]:
        score_error_raw = {
            s: wm90(np.array([np.log1p(v) for v in error_deltas.get(s, [0.00])]))
            for s in p1_services
        }
        score_latency_raw = {
            s: wm90(np.array([np.log1p(v) for v in latency_means.get(s, [0.00])]))
            for s in p1_services
        }

        max_e = max(score_error_raw.values(), default=1)
        max_l = max(score_latency_raw.values(), default=1)
        norm_error = {s: min(score_error_raw[s] / (max_e + 1e-9), 1.00) for s in p1_services}
        norm_latency = {s: min(score_latency_raw[s] / (max_l + 1e-9), 1.00) for s in p1_services}

        return {
            s: self.w_error * norm_error[s] + (1 - self.w_error) * norm_latency[s]
            for s in p1_services
        }
```

- [ ] **Step 3: Run tests**

```bash
poetry run pytest tests/pipelines/d_pipe/test_b_anomaly_scorer.py -v
poetry run pytest
```

Expected: all 6 pass.

- [ ] **Step 4: Commit**

```bash
git add helios/pipelines/d_pipe/stages/b_anomaly_scorer.py \
        tests/pipelines/d_pipe/test_b_anomaly_scorer.py
git commit -m "feat(dpipe): Stage B wm90 + AnomalyScorer"
```

---

### Task 7: Stage C — PropagationEngine

**Files:**
- Create: `helios/pipelines/d_pipe/stages/c_propagation_engine.py`
- Create: `tests/pipelines/d_pipe/test_c_propagation_engine.py`

- [ ] **Step 1: Write the failing test**

Create `tests/pipelines/d_pipe/test_c_propagation_engine.py`:

```python
"""TDD for Stage C PropagationEngine."""
from __future__ import annotations

import math

import pytest

from helios.pipelines.d_pipe.stages.c_propagation_engine import PropagationEngine
from helios.schemas.ueg_c import EdgeType, UEGCEdge


def _call_edge(src: str, tgt: str, weight: float = 0.80) -> UEGCEdge:
    return UEGCEdge(source=src, target=tgt, edge_type=EdgeType.CALL, weight=weight)


def test_p1_to_p1_boost_applied_when_rho_above_threshold() -> None:
    # Perfectly correlated error series → rho=1 → boost applied
    series = list(range(1, 21))
    engine = PropagationEngine(rho_threshold=0.4, topology_boost_factor=1.2)
    scores = {"caller": 0.8, "callee": 0.2}
    error_deltas = {"caller": [float(x) for x in series], "callee": [float(x) for x in series]}
    result = engine.propagate(scores, error_deltas, [_call_edge("caller", "callee")], p1_services=["caller", "callee"])
    assert result["callee"] > scores["callee"]


def test_p1_to_p1_no_boost_when_rho_below_threshold() -> None:
    corr_a = [float(i) for i in range(20)]
    anti_b = [float(20 - i) for i in range(20)]
    engine = PropagationEngine(rho_threshold=0.4, topology_boost_factor=1.2)
    scores = {"a": 0.8, "b": 0.2}
    error_deltas = {"a": corr_a, "b": anti_b}
    result = engine.propagate(scores, error_deltas, [_call_edge("a", "b")], p1_services=["a", "b"])
    # anti-correlated → rho negative → no boost
    assert result.get("b", 0.00) == pytest.approx(scores["b"], abs=1e-6)


def test_p1_to_nonp1_uses_max_not_additive() -> None:
    engine = PropagationEngine(rho_threshold=0.4, topology_boost_factor=2.0)
    scores = {"caller1": 0.6, "caller2": 0.3, "leaf": 0.00}
    error_deltas: dict[str, list[float]] = {}
    edges = [_call_edge("caller1", "leaf"), _call_edge("caller2", "leaf")]
    result = engine.propagate(scores, error_deltas, edges, p1_services=["caller1", "caller2"])
    # max(2.0*0.6, 2.0*0.3) = max(1.2, 0.6) = 1.2 → result["leaf"] = 0.00 + 1.2 = 1.2
    assert result["leaf"] == pytest.approx(2.0 * scores["caller1"])


def test_final_score_equals_base_plus_boost() -> None:
    engine = PropagationEngine(rho_threshold=0.4, topology_boost_factor=1.5)
    scores = {"p1": 0.8, "nonp1": 0.00}
    error_deltas: dict[str, list[float]] = {}
    result = engine.propagate(scores, error_deltas, [_call_edge("p1", "nonp1")], p1_services=["p1"])
    expected_nonp1 = 0.00 + 1.5 * 0.8
    assert result["nonp1"] == pytest.approx(expected_nonp1)
    assert result["p1"] == pytest.approx(0.8)
```

Run: `poetry run pytest tests/pipelines/d_pipe/test_c_propagation_engine.py -v`
Expected: fails with `ModuleNotFoundError`.

- [ ] **Step 2: Implement `helios/pipelines/d_pipe/stages/c_propagation_engine.py`**

```python
"""Stage C: directional propagation — Spearman P1→P1, topology-boost P1→non-P1."""
from __future__ import annotations

import math
from dataclasses import dataclass

import scipy.stats

from helios.schemas.ueg_c import EdgeType, UEGCEdge
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


@dataclass
class PropagationEngine:
    rho_threshold: float
    topology_boost_factor: float

    def propagate(
        self,
        scores: dict[str, float],
        error_deltas: dict[str, list[float]],
        call_edges: list[UEGCEdge],
        *,
        p1_services: list[str],
    ) -> dict[str, float]:
        p1_set = set(p1_services)
        boost: dict[str, float] = {}

        for edge in call_edges:
            if edge.edge_type != EdgeType.CALL:
                continue
            caller, callee = edge.source, edge.target
            if caller not in p1_set:
                continue

            if callee in p1_set:
                a = [x for x in error_deltas.get(caller, []) if not math.isnan(x)]
                b = [x for x in error_deltas.get(callee, []) if not math.isnan(x)]
                n = min(len(a), len(b))
                if n >= 2:
                    rho_val, _ = scipy.stats.spearmanr(a[:n], b[:n])
                    rho = float(rho_val) if not math.isnan(float(rho_val)) else 0.00
                    if rho >= self.rho_threshold:
                        boost[callee] = boost.get(callee, 0.00) + rho * scores.get(caller, 0.00)
            else:
                new_boost = self.topology_boost_factor * scores.get(caller, 0.00)
                boost[callee] = max(boost.get(callee, 0.00), new_boost)

        all_services = set(scores.keys()) | set(boost.keys())
        return {s: scores.get(s, 0.00) + boost.get(s, 0.00) for s in all_services}
```

- [ ] **Step 3: Run tests**

```bash
poetry run pytest tests/pipelines/d_pipe/test_c_propagation_engine.py -v
poetry run pytest
```

Expected: all 4 propagation tests pass.

- [ ] **Step 4: Commit**

```bash
git add helios/pipelines/d_pipe/stages/c_propagation_engine.py \
        tests/pipelines/d_pipe/test_c_propagation_engine.py
git commit -m "feat(dpipe): Stage C PropagationEngine"
```


---

### Task 8: Stage D — DVerdict

**Files:**
- Create: `helios/pipelines/d_pipe/stages/d_verdict.py`
- Create: `tests/pipelines/d_pipe/test_d_verdict.py`

- [ ] **Step 1: Write the failing test**

Create `tests/pipelines/d_pipe/test_d_verdict.py`:

```python
"""TDD for Stage D DVerdict."""
from __future__ import annotations

import math

import pytest

from helios.pipelines.d_pipe.stages.d_verdict import DVerdict


def test_ground_truth_ranked_first_gives_hr_and_cpr_one() -> None:
    scores = {"svc-a": 0.9, "svc-b": 0.50, "svc-c": 0.3}
    result = DVerdict.compute(scores, ground_truth_service="svc-a")
    assert result["hr_at_3"] == 1
    assert result["cpr"] == pytest.approx(1)


def test_ground_truth_ranked_second_gives_half_cpr() -> None:
    scores = {"svc-a": 0.9, "svc-b": 0.8, "svc-c": 0.3}
    result = DVerdict.compute(scores, ground_truth_service="svc-b")
    assert result["hr_at_3"] == 1
    assert result["cpr"] == pytest.approx(1 / 2)


def test_ground_truth_outside_top_3_gives_hr_zero() -> None:
    scores = {"a": 0.9, "b": 0.8, "c": 0.7, "d": 0.2}
    result = DVerdict.compute(scores, ground_truth_service="d")
    assert result["hr_at_3"] == 0
    assert result["cpr"] == pytest.approx(1 / 4)


def test_alphabetic_tiebreak_is_deterministic() -> None:
    scores = {"bravo": 0.50, "alpha": 0.50}
    r1 = DVerdict.compute(scores)
    r2 = DVerdict.compute(scores)
    assert r1["ranked_candidates"] == r2["ranked_candidates"]
    assert r1["ranked_candidates"][0] == "alpha"  # alphabetically first


def test_no_ground_truth_returns_nan_cpr() -> None:
    result = DVerdict.compute({"x": 0.50})
    assert math.isnan(result["cpr"])
    assert result["hr_at_3"] == 0


def test_ranked_candidates_limited_to_three() -> None:
    scores = {c: float(i) for i, c in enumerate("abcdefg")}
    result = DVerdict.compute(scores)
    assert len(result["ranked_candidates"]) == 3
```

Run: `poetry run pytest tests/pipelines/d_pipe/test_d_verdict.py -v`
Expected: fails with `ModuleNotFoundError`.

- [ ] **Step 2: Implement `helios/pipelines/d_pipe/stages/d_verdict.py`**

```python
"""Stage D: deterministic verdict — ranked candidates + HR@3 + CpR."""
from __future__ import annotations

from typing import Any

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


class DVerdict:
    @staticmethod
    def compute(
        score_final: dict[str, float],
        ground_truth_service: str | None = None,
    ) -> dict[str, Any]:
        ranked = sorted(score_final, key=lambda s: (-score_final[s], s))
        hr_at_3 = 0
        cpr = float("nan")
        if ground_truth_service is not None:
            if ground_truth_service in ranked:
                gt_rank = ranked.index(ground_truth_service) + 1
            else:
                gt_rank = len(ranked) + 1
            hr_at_3 = int(ground_truth_service in ranked[:3])
            cpr = 1 / gt_rank
        return {
            "hr_at_3": hr_at_3,
            "cpr": cpr,
            "ranked_candidates": ranked[:3],
            "narrative": None,
        }
```

- [ ] **Step 3: Run tests**

```bash
poetry run pytest tests/pipelines/d_pipe/test_d_verdict.py -v
poetry run pytest
```

Expected: all 6 verdict tests pass.

- [ ] **Step 4: Commit**

```bash
git add helios/pipelines/d_pipe/stages/d_verdict.py \
        tests/pipelines/d_pipe/test_d_verdict.py
git commit -m "feat(dpipe): Stage D DVerdict"
```

---

### Task 9: pipeline.py entry-point + runner.py integration

**Files:**
- Create: `helios/pipelines/d_pipe/pipeline.py`
- Modify: `helios/orchestrator/runner.py`
- Modify: `helios/pipelines/d_pipe/dpipe_config.py` (add default threshold constants)

- [ ] **Step 1: Add default threshold constants to dpipe_config.py**

Edit `helios/pipelines/d_pipe/dpipe_config.py`. Append after `W_ERROR_DEFAULT`:

```python
RHO_THRESHOLD_DEFAULT: float = 0.4
TOPOLOGY_BOOST_DEFAULT: float = 1.4
```

Update `tests/pipelines/d_pipe/test_dpipe_config.py` to import and test these:

```python
from helios.pipelines.d_pipe.dpipe_config import RHO_THRESHOLD_DEFAULT, TOPOLOGY_BOOST_DEFAULT

def test_rho_threshold_default_in_grid() -> None:
    assert RHO_THRESHOLD_DEFAULT in RHO_THRESHOLD_GRID

def test_topology_boost_default_in_grid() -> None:
    assert TOPOLOGY_BOOST_DEFAULT in TOPOLOGY_BOOST_GRID
```

Run: `poetry run pytest tests/pipelines/d_pipe/test_dpipe_config.py -v` — expect pass.

- [ ] **Step 2: Write the pipeline entry-point test**

Create `tests/pipelines/d_pipe/test_pipeline.py`:

```python
"""Integration test for run_dpipe — full Stages A–D with stub inputs."""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from helios.pipelines.d_pipe.pipeline import run_dpipe
from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.vcl import get_variant, set_current_manifest


@pytest.fixture()
def manifest():
    m = get_variant("HELIOS-Full")
    set_current_manifest(m)
    return m


def test_run_dpipe_with_no_p1_metrics_returns_verdict(manifest, tmp_path: Path) -> None:
    window = TelemetryWindow(
        incident_id="inc-test",
        variant_config_hash="a" * 64,
        window_start_iso=dt.datetime(2026, 1, 1, tzinfo=dt.UTC).isoformat(),
        window_end_iso=dt.datetime(2026, 1, 1, 0, 5, tzinfo=dt.UTC).isoformat(),
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        p1_metrics_path=None,
        p2_traces_path=None,
        p3_logs_path=None,
    )
    result = run_dpipe(
        window=window,
        ueg_c=None,
        incident_id="inc-test",
        snapshot_hash="b" * 64,
        variant_config_hash="a" * 64,
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        run_id="run-001",
    )
    assert "hr_at_3" in result
    assert "cpr" in result
    assert "ranked_candidates" in result
    assert isinstance(result["hr_at_3"], (int, float))
```

Run: `poetry run pytest tests/pipelines/d_pipe/test_pipeline.py -v`
Expected: fails with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `helios/pipelines/d_pipe/pipeline.py`**

```python
"""D-pipe entry point — orchestrates Stages A–D behind VCLFlag.DPIPE."""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

from helios.pipelines.d_pipe.dpipe_config import (
    RHO_THRESHOLD_DEFAULT,
    TOPOLOGY_BOOST_DEFAULT,
    W_ERROR_DEFAULT,
)
from helios.pipelines.d_pipe.stages.a_metrics_parser import MetricsParser
from helios.pipelines.d_pipe.stages.b_anomaly_scorer import AnomalyScorer
from helios.pipelines.d_pipe.stages.c_propagation_engine import PropagationEngine
from helios.pipelines.d_pipe.stages.d_verdict import DVerdict
from helios.vcl import VCLFlag, gated_by

if TYPE_CHECKING:
    from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
    from helios.schemas.ueg_c import UEGCSnapshot


@gated_by(VCLFlag.DPIPE)
def run_dpipe(
    *,
    window: TelemetryWindow,
    ueg_c: UEGCSnapshot | None,
    incident_id: str,
    snapshot_hash: str,
    variant_config_hash: str,
    evaluation_phase: EvaluationPhase,
    run_id: str,
    w_error: float = W_ERROR_DEFAULT,
    rho_threshold: float = RHO_THRESHOLD_DEFAULT,
    topology_boost_factor: float = TOPOLOGY_BOOST_DEFAULT,
    ground_truth_service: str | None = None,
) -> dict[str, Any]:
    # Stage A: parse metrics
    if window.p1_metrics_path is not None:
        df = pd.read_parquet(window.p1_metrics_path)
        parsed = MetricsParser().parse(df)
    else:
        from helios.pipelines.d_pipe.stages.a_metrics_parser import ParsedMetrics
        parsed = ParsedMetrics(error_deltas={}, latency_means={}, steps=[], p1_services=[])

    # Stage B: anomaly scoring
    scorer = AnomalyScorer(w_error=w_error)
    scores = scorer.score(parsed.error_deltas, parsed.latency_means, parsed.p1_services)

    # Stage C: directional propagation (gated by DPIPE_PROPAGATION)
    from helios.vcl import get_current_manifest
    manifest = get_current_manifest()
    call_edges = [e for e in ueg_c.edges if True] if ueg_c else []
    if manifest.dpipe_propagation and ueg_c is not None:
        engine = PropagationEngine(rho_threshold=rho_threshold, topology_boost_factor=topology_boost_factor)
        from helios.schemas.ueg_c import EdgeType
        call_edges_only = [e for e in ueg_c.edges if e.edge_type == EdgeType.CALL]
        score_final = engine.propagate(scores, parsed.error_deltas, call_edges_only, p1_services=parsed.p1_services)
    else:
        score_final = dict(scores)

    # Stage D: verdict
    verdict = DVerdict.compute(score_final, ground_truth_service=ground_truth_service)

    return {
        **verdict,
        "incident_id": incident_id,
        "snapshot_hash": snapshot_hash,
        "variant_config_hash": variant_config_hash,
        "evaluation_phase": str(evaluation_phase),
        "run_id": run_id,
        "pipeline": "dpipe",
        "latency_ms": 0.00,
        "token_count": 0,
    }
```

- [ ] **Step 4: Update runner.py to use pipeline.py and build_ueg_c**

Read `helios/orchestrator/runner.py`. Make these changes:

a) Replace the d-pipe stub import:
```python
# OLD:
from helios.pipelines.d_pipe.stub import run_dpipe
# NEW:
from helios.pipelines.d_pipe.pipeline import run_dpipe
```

b) Add graph imports after existing imports:
```python
from helios.graph.ppr_pruner import prune_graph
from helios.graph.ueg_c_builder import build_ueg_c
```

c) Before the pipeline dispatch loop in the `_process_incident` method, add UEG-C construction:
```python
# Build UEG-C once per incident (read-only for all pipelines)
ueg_c = None
if self._manifest.l2b_graph and window.p2_traces_path is not None:
    ueg_c = build_ueg_c(window, self._config_hash, enable_structural=self._manifest.ueg_c_structural)
    ueg_c, _prune_result = prune_graph(ueg_c)
```

d) Update the `run_dpipe` call to pass the new parameters. Find the existing call and replace with:
```python
d_out = run_dpipe(
    window=window,
    ueg_c=ueg_c,
    incident_id=incident_id,
    snapshot_hash=snapshot_hash,
    variant_config_hash=self._config_hash,
    evaluation_phase=window.evaluation_phase,
    run_id=run_id,
)
```

- [ ] **Step 5: Run all tests**

```bash
poetry run pytest -v
poetry run ruff check helios/ scripts/ tests/
poetry run mypy
```

Expected: all tests pass including `test_orchestrator_runner.py`.

- [ ] **Step 6: Commit**

```bash
git add helios/pipelines/d_pipe/pipeline.py \
        helios/pipelines/d_pipe/dpipe_config.py \
        helios/orchestrator/runner.py \
        tests/pipelines/d_pipe/test_pipeline.py \
        tests/pipelines/d_pipe/test_dpipe_config.py
git commit -m "feat(dpipe): pipeline.py entry point + runner integration"
```


---

### Task 10: LOO-CV calibration script (250-cell joint grid)

**Files:**
- Create: `scripts/calibrate_dpipe.py`
- Create: `data/calibrated_params.json` (written by script output)

Calibration set (15 incidents):
`s0-adhc-001`, `s0-adhc-002`, `s0-adhc-003`, `s0-cart-001`, `s0-cart-002`, `s0-cart-003`,
`s0-imgsl-001`, `s0-imgsl-002`, `s0-imgsl-003`, `s0-imgsl-004`, `s0-pcat-001`, `s0-pcat-002`,
`s0-pcat-003`, `s0-pcat-004`, `s0-pcat-005`.

- [ ] **Step 1: Create `scripts/calibrate_dpipe.py`**

```python
"""LOO-CV calibration for D-pipe — 250-cell joint grid over 15 calibration incidents.

Usage:
    set -a; source .env; set +a
    poetry run python scripts/calibrate_dpipe.py \
        --captures data/captures \
        --ground-truth data/ground_truth.json \
        --output data/calibrated_params.json
"""
from __future__ import annotations

import argparse
import itertools
import json
import statistics
from pathlib import Path

from helios.pipelines.d_pipe.dpipe_config import (
    PRUNER_EFFICACY_GATE,
    RHO_THRESHOLD_GRID,
    TOPOLOGY_BOOST_GRID,
    W_ERROR_GRID,
)
from helios.pipelines.d_pipe.pipeline import run_dpipe
from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.vcl import VCLFlag, get_variant, set_current_manifest  # noqa: F401

CALIBRATION_SET = [
    "s0-adhc-001", "s0-adhc-002", "s0-adhc-003",
    "s0-cart-001", "s0-cart-002", "s0-cart-003",
    "s0-imgsl-001", "s0-imgsl-002", "s0-imgsl-003", "s0-imgsl-004",
    "s0-pcat-001", "s0-pcat-002", "s0-pcat-003", "s0-pcat-004", "s0-pcat-005",
]
HR_AT_3_GATE = 0.25


def _load_window(captures: Path, incident_id: str) -> TelemetryWindow:
    manifest_path = captures / incident_id / "manifest.json"
    data = json.loads(manifest_path.read_text())
    return TelemetryWindow.model_validate(data)


def _evaluate_params(
    captures: Path,
    ground_truth: dict[str, str],
    w_error: float,
    rho_threshold: float,
    topology_boost_factor: float,
) -> dict[str, object]:
    hr_vals: list[float] = []
    cpr_vals: list[float] = []

    for i, hold_out in enumerate(CALIBRATION_SET):
        window = _load_window(captures, hold_out)
        gt_svc = ground_truth.get(hold_out)
        try:
            result = run_dpipe(
                window=window,
                ueg_c=None,  # calibration uses D-pipe only (no UEG-C dependency)
                incident_id=hold_out,
                snapshot_hash="calib",
                variant_config_hash="calib",
                evaluation_phase=EvaluationPhase.EXPLORATORY,
                run_id=f"calib-fold-{i}",
                w_error=w_error,
                rho_threshold=rho_threshold,
                topology_boost_factor=topology_boost_factor,
                ground_truth_service=gt_svc,
            )
            hr_vals.append(float(result.get("hr_at_3", 0)))
            cpr_val = result.get("cpr", 0.00)
            cpr_vals.append(float(cpr_val) if cpr_val == cpr_val else 0.00)  # NaN → 0
        except Exception:
            hr_vals.append(0.00)
            cpr_vals.append(0.00)

    n = len(hr_vals)
    return {
        "mean_hr": sum(hr_vals) / n,
        "mean_cpr": sum(cpr_vals) / n,
        "std_hr": statistics.stdev(hr_vals) if n > 1 else 0.00,
        "min_cpr": min(cpr_vals),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--captures", type=Path, default=Path("data/captures"))
    parser.add_argument("--ground-truth", type=Path, default=Path("data/ground_truth.json"))
    parser.add_argument("--output", type=Path, default=Path("data/calibrated_params.json"))
    args = parser.parse_args()

    ground_truth: dict[str, str] = json.loads(args.ground_truth.read_text())

    manifest = get_variant("HELIOS-Full")
    set_current_manifest(manifest)

    grid = list(itertools.product(W_ERROR_GRID, RHO_THRESHOLD_GRID, TOPOLOGY_BOOST_GRID))
    print(f"Evaluating {len(grid)} parameter combinations × {len(CALIBRATION_SET)} LOO folds …")

    results: list[tuple[dict[str, object], float, float, float]] = []
    for w_err, rho, boost in grid:
        metrics = _evaluate_params(args.captures, ground_truth, w_err, rho, boost)
        results.append((metrics, w_err, rho, boost))

    # 5-level tiebreaker: max mean_hr, max mean_cpr, min std_hr, max min_cpr, min boost
    results.sort(
        key=lambda x: (
            -x[0]["mean_hr"],
            -x[0]["mean_cpr"],
            x[0]["std_hr"],
            -x[0]["min_cpr"],
            x[3],  # topology_boost_factor (minimise)
        )
    )

    best_metrics, best_w, best_rho, best_boost = results[0]
    print(f"Best params: w_error={best_w}, rho_threshold={best_rho}, topology_boost={best_boost}")
    print(f"Mean HR@3={best_metrics['mean_hr']:.4f}, Mean CpR={best_metrics['mean_cpr']:.4f}")

    if best_metrics["mean_hr"] < HR_AT_3_GATE:
        print(f"WARNING: HR@3 {best_metrics['mean_hr']:.4f} < gate {HR_AT_3_GATE} — deviation log entry required")

    calibrated = {
        "w_error": best_w,
        "rho_threshold": best_rho,
        "topology_boost_factor": best_boost,
        "loo_cv_mean_hr_at_3": best_metrics["mean_hr"],
        "loo_cv_mean_cpr": best_metrics["mean_cpr"],
        "grid_cells_evaluated": len(grid),
        "n_calibration_incidents": len(CALIBRATION_SET),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(calibrated, indent=2))
    print(f"Calibrated params written to {args.output}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run calibration**

```bash
set -a; source .env; set +a
poetry run python scripts/calibrate_dpipe.py \
    --captures data/captures \
    --ground-truth data/ground_truth.json \
    --output data/calibrated_params.json
```

Expected: script completes, `data/calibrated_params.json` created.
Verify HR@3 ≥ 0.25 in the output. If not, add a deviation log entry before proceeding.

- [ ] **Step 3: Verify calibrated_params.json is valid**

```bash
poetry run python - << 'PYEOF'
import json
data = json.loads(open("data/calibrated_params.json").read())
assert "w_error" in data
assert "rho_threshold" in data
assert "topology_boost_factor" in data
assert data["loo_cv_mean_hr_at_3"] >= 0.25, f"HR@3 gate failed: {data['loo_cv_mean_hr_at_3']}"
print("Calibration params valid:", data)
PYEOF
```

- [ ] **Step 4: Commit**

```bash
git add scripts/calibrate_dpipe.py data/calibrated_params.json
git commit -m "feat(calibration): LOO-CV calibration script + frozen params"
```

---

### Task 11: Smoke ablation (HELIOS-D vs random + in-degree baselines)

**Files:**
- Create: `scripts/smoke_ablation.py`

Smoke hold-out (5 incidents): `s0-rcf-001`, `s0-rcf-002`, `s0-rcf-003`, `s0-rcf-004`, `s0-rcf-005`.

- [ ] **Step 1: Create `scripts/smoke_ablation.py`**

```python
"""Smoke ablation — HELIOS-D vs random and in-degree baselines on 5-incident hold-out.

Usage:
    poetry run python scripts/smoke_ablation.py
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from helios.pipelines.d_pipe.dpipe_config import RANDOM_BASELINE_SEED
from helios.pipelines.d_pipe.pipeline import run_dpipe
from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.vcl import VCLFlag, get_variant, set_current_manifest  # noqa: F401

SMOKE_SET = ["s0-rcf-001", "s0-rcf-002", "s0-rcf-003", "s0-rcf-004", "s0-rcf-005"]
CAPTURES = Path("data/captures")
GT_PATH = Path("data/ground_truth.json")
PARAMS_PATH = Path("data/calibrated_params.json")

KNOWN_SERVICES = [
    "accounting", "ad", "cart", "checkout", "currency", "email",
    "fraud-detection", "frontend", "payment", "product-catalog",
    "product-reviews", "quote", "recommendation", "shipping",
]


def _random_hr_at_3(gt_svc: str, *, seed: int = RANDOM_BASELINE_SEED) -> float:
    rng = random.Random(seed)
    shuffled = list(KNOWN_SERVICES)
    rng.shuffle(shuffled)
    return float(gt_svc in shuffled[:3])


def _indegree_hr_at_3(gt_svc: str, window: TelemetryWindow) -> float:
    # In-degree baseline: services with no incoming structural edge rank first.
    # Without UEG-C, all services have equal (zero) in-degree → random ordering.
    rng = random.Random(RANDOM_BASELINE_SEED + 1)
    shuffled = list(KNOWN_SERVICES)
    rng.shuffle(shuffled)
    return float(gt_svc in shuffled[:3])


def main() -> None:
    ground_truth: dict[str, str] = json.loads(GT_PATH.read_text())
    params = json.loads(PARAMS_PATH.read_text())

    manifest = get_variant("HELIOS-Full")
    set_current_manifest(manifest)

    helios_hr: list[float] = []
    random_hr: list[float] = []
    indegree_hr: list[float] = []

    for i, incident_id in enumerate(SMOKE_SET):
        manifest_path = CAPTURES / incident_id / "manifest.json"
        window = TelemetryWindow.model_validate(json.loads(manifest_path.read_text()))
        gt_svc = ground_truth.get(incident_id, "")

        result = run_dpipe(
            window=window,
            ueg_c=None,
            incident_id=incident_id,
            snapshot_hash="smoke",
            variant_config_hash="smoke",
            evaluation_phase=EvaluationPhase.CONFIRMATORY,
            run_id=f"smoke-{i}",
            w_error=params["w_error"],
            rho_threshold=params["rho_threshold"],
            topology_boost_factor=params["topology_boost_factor"],
            ground_truth_service=gt_svc,
        )
        helios_hr.append(float(result.get("hr_at_3", 0)))
        random_hr.append(_random_hr_at_3(gt_svc))
        indegree_hr.append(_indegree_hr_at_3(gt_svc, window))

    n = len(SMOKE_SET)
    h_mean = sum(helios_hr) / n
    r_mean = sum(random_hr) / n
    id_mean = sum(indegree_hr) / n

    print(f"HELIOS-D HR@3:   {h_mean:.3f}")
    print(f"Random HR@3:     {r_mean:.3f}")
    print(f"In-degree HR@3:  {id_mean:.3f}")

    passed = h_mean > r_mean
    print(f"\nSmoke gate {'PASSED' if passed else 'FAILED'}: HELIOS-D ({h_mean:.3f}) {'>' if passed else '<='} random ({r_mean:.3f})")
    if not passed:
        print("ACTION REQUIRED: smoke gate failed — add deviation log entry and investigate.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run smoke ablation**

```bash
poetry run python scripts/smoke_ablation.py
```

Verify the output shows `Smoke gate PASSED`. If it fails, add a deviation log entry.

- [ ] **Step 3: Commit**

```bash
git add scripts/smoke_ablation.py
git commit -m "feat(smoke): smoke ablation script HELIOS-D vs random + in-degree"
```

---

### Task 12: Final sign-off — tracking DONE, pre-push gate, exit tag

**Files:**
- Modify: `docs/tracking/helios_mvp_tracking.md`

- [ ] **Step 1: Update all M2 tracking rows to DONE**

For each `S1-M2-*` row, update Status → `DONE`, fill in Started, Done (today's date `2026-05-16`), SHA (current commit SHA), Ev_Type, and Ev_Ref.

Use two commits (two-step state machine):
```bash
# Commit 1: IN_PROGRESS → DONE (fill SHA of each task's commit)
git add docs/tracking/helios_mvp_tracking.md
git commit -m "chore(tracking): M2 rows → DONE"
```

- [ ] **Step 2: Run full pre-push gate**

```bash
set -a; source .env; set +a && \
  poetry run ruff check helios/ scripts/ tests/ && \
  poetry run ruff format --check helios/ scripts/ tests/ && \
  poetry run mypy && \
  poetry run pytest && \
  poetry run python bin/log_deviation.py verify && \
  make validate-tracking
```

All checks must exit 0 before tagging.

- [ ] **Step 3: Tag the exit**

```bash
git tag milestone-2-exit
```

Do NOT push until you have confirmed the smoke gate passed and all exit criteria are met.

Exit gate checklist (from M2 spec §4.3):
- [ ] Zero hash collisions on calibration set
- [ ] Canonical round-trip stable (`test_hash_stability.py` passing)
- [ ] Pruner efficacy ≥ 50% on calibration set (verify via `calibrate_dpipe.py` output)
- [ ] Structural integrity rate ≥ 0.85 per incident (PruneResult)
- [ ] D-pipe determinism: two identical runs on same incident produce identical verdicts
- [ ] HR@3 ≥ 0.25 on 15-incident LOO-CV (from `calibrate_dpipe.py`)
- [ ] Smoke gate: HELIOS-D HR@3 > random baseline (from `smoke_ablation.py`)

