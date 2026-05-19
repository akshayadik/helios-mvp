# G-pipe Re-capture + Structural Fix + Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix structural edge derivation using `parent_span_id`, implement the conditional G-pipe pipeline with PPR disagreement entry gate, and extend PipelineVerdict to schema-draft-v0.2.

**Architecture:** Three layers: (1) re-capture all 20 incidents with `parent_span_id` column and `snapshot_hash` in manifests; (2) rewrite `_structural_edges()` to use OTEL parent-child linkage with temporal containment as a named fallback; (3) implement the full G-pipe pipeline with disagreement entry gate, PPR traversal, sequential orchestrator dispatch, and PipelineVerdict v0.2.

**Tech Stack:** Python 3.11, pandas 2.2, pyarrow 18, networkx 3.6, Pydantic v2, pytest, HELIOS VCL/deviation-log toolchain

---

## Pre-conditions (verify before starting)

```bash
poetry run pytest        # must be green on main
git log --oneline -3     # confirm on feature/gpipe_lpipe_osf branch
set -a; source .env; set +a && poetry run python bin/log_deviation.py verify
```

---

## File Map

| File | Action |
|---|---|
| `helios/telemetry/otel_demo_capture.py` | Add `parent_span_id` extraction to `JaegerTracesFetcher.fetch()` |
| `bin/run_capture.py` | Add schema constants; add `_write_snapshot_hash()` post-processing |
| `helios/graph/ueg_c_builder.py` | SpanRecord fields; `_structural_edges()` rewrite; `_psid()`; pd.read_parquet |
| `helios/schemas/verdict.py` | PipelineVerdict v0.2: `ppr_scores`, `prompt_version`, `VERDICT_SCHEMA_VERSION` |
| `helios/pipelines/g_pipe/gpipe_config.py` | **New** — frozen after calibration |
| `helios/pipelines/g_pipe/pipeline.py` | **New** — entry gate + PPR traversal + sentinel |
| `helios/pipelines/g_pipe/stub.py` | **Delete** |
| `helios/pipelines/g_pipe/__init__.py` | Update docstring |
| `helios/orchestrator/runner.py` | Sequential D→G(conditional)→L dispatch |
| `helios/integrity_gate.py` | Conditional G-pipe row handling |
| `scripts/calibrate_gpipe.py` | **New** — G-pipe LOO-CV threshold sweep |
| `tests/test_capture.py` | 4 new tests for parent_span_id + snapshot_hash |
| `tests/graph/test_ueg_c_builder.py` | 8 new parent_span_id tests; update existing helpers |
| `tests/pipelines/test_gpipe_pipeline.py` | **New** — gate boundary, PPR, sentinel, determinism |
| `tests/test_orchestrator_runner.py` | 2 new integration tests for sequential dispatch |
| `tests/test_integrity_gate.py` | new test for conditional G-pipe row |
| `tests/test_schema_stability.py` | Update `_make_verdict()` for v0.2 fields |
| `docs/tracking/ablation_architecture.md` | §3.2 written |
| `docs/tracking/hypothesis_variant_metric_mapping.md` | A-H6 sentinel filter added |
| `docs/tracking/helios_mvp_tracking.md` | M3 ENG/GATE rows added |

---

## Task 1: Add `parent_span_id` to JaegerTracesFetcher

**Files:** `helios/telemetry/otel_demo_capture.py`, `tests/test_capture.py`

- [ ] **Step 1: Write the failing tests**

Add to `TestJaegerTracesFetcher` in `tests/test_capture.py`:

```python
def test_fetch_includes_parent_span_id_column(self, window_bounds):
    """JaegerTracesFetcher produces an 8-column table including parent_span_id."""
    start, end = window_bounds
    payload = {
        "data": [
            {
                "traceID": "abc123",
                "spans": [
                    {
                        "spanID": "def456",
                        "operationName": "/GetProduct",
                        "startTime": 1715000000000000,
                        "duration": 1500,
                        "tags": [{"key": "otel.status_code", "value": "OK"}],
                        "references": [
                            {"refType": "CHILD_OF", "traceID": "abc123", "spanID": "aaa111"}
                        ],
                    }
                ],
            }
        ]
    }
    with patch("urllib.request.urlopen", return_value=_http_mock(payload)):
        table = JaegerTracesFetcher("http://jaeger:16686").fetch(start, end)

    assert "parent_span_id" in table.column_names
    assert table.column("parent_span_id")[0].as_py() == "aaa111"


def test_fetch_root_span_has_empty_parent_span_id(self, window_bounds):
    """A span with no CHILD_OF reference gets parent_span_id='' (root span)."""
    start, end = window_bounds
    payload = {
        "data": [
            {
                "traceID": "abc123",
                "spans": [
                    {
                        "spanID": "root001",
                        "operationName": "/root",
                        "startTime": 1715000000000000,
                        "duration": 500,
                        "tags": [],
                        "references": [],
                    }
                ],
            }
        ]
    }
    with patch("urllib.request.urlopen", return_value=_http_mock(payload)):
        table = JaegerTracesFetcher("http://jaeger:16686").fetch(start, end)

    assert table.column("parent_span_id")[0].as_py() == ""
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
poetry run pytest tests/test_capture.py::TestJaegerTracesFetcher::test_fetch_includes_parent_span_id_column tests/test_capture.py::TestJaegerTracesFetcher::test_fetch_root_span_has_empty_parent_span_id -v
```

Expected: FAIL — `parent_span_id` not in column_names.

- [ ] **Step 3: Update `JaegerTracesFetcher.fetch()` in `helios/telemetry/otel_demo_capture.py`**

Add `parent_ids: list[str] = []` alongside the other accumulators. Inside the span loop, after `span_ids.append(...)`:

```python
parent_id = ""
for ref in span.get("references", []):
    if ref.get("refType") == "CHILD_OF" and ref.get("traceID") == tid:
        parent_id = str(ref.get("spanID", ""))
        break
parent_ids.append(parent_id)
```

Update the `return pa.table(...)` to include the new column:

```python
return pa.table(
    {
        "trace_id": pa.array(trace_ids, type=pa.string()),
        "span_id": pa.array(span_ids, type=pa.string()),
        "parent_span_id": pa.array(parent_ids, type=pa.string()),
        "operation_name": pa.array(ops, type=pa.string()),
        "service_name": pa.array(services, type=pa.string()),
        "start_time_us": pa.array(start_times, type=pa.int64()),
        "duration_us": pa.array(durations, type=pa.int64()),
        "status_code": pa.array(statuses, type=pa.string()),
    }
)
```

- [ ] **Step 4: Update column-check tests and test-double helper**

In `tests/test_capture.py`, update `test_fetch_returns_expected_columns` to include `"parent_span_id"` in the expected set. Update `_traces_table()` helper:

```python
def _traces_table() -> pa.Table:
    return pa.table(
        {
            "trace_id": pa.array(["abc123"], type=pa.string()),
            "span_id": pa.array(["def456"], type=pa.string()),
            "parent_span_id": pa.array([""], type=pa.string()),
            "operation_name": pa.array(["/GetProduct"], type=pa.string()),
            "service_name": pa.array(["productcatalogservice"], type=pa.string()),
            "start_time_us": pa.array([1715000000000000], type=pa.int64()),
            "duration_us": pa.array([1500], type=pa.int64()),
            "status_code": pa.array(["OK"], type=pa.string()),
        }
    )
```

Update `test_validate_traces_round_trip` expected set to include `"parent_span_id"`.

- [ ] **Step 5: Run tests to confirm they pass**

```bash
poetry run pytest tests/test_capture.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add helios/telemetry/otel_demo_capture.py tests/test_capture.py
git commit -m "feat(capture): add parent_span_id column to JaegerTracesFetcher Parquet output"
```

---

## Task 2: bin/run_capture.py — snapshot_hash post-processing

**Files:** `bin/run_capture.py`, `tests/test_capture.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_capture.py` (module level, outside class blocks):

```python
def test_manifest_has_snapshot_hash_after_write(config, window_bounds):
    """After _write_snapshot_hash(), manifest.json has a 64-char hex snapshot_hash."""
    from bin.run_capture import _write_snapshot_hash  # noqa: PLC0415
    from helios.vcl import set_current_manifest

    start, end = window_bounds
    set_current_manifest(config.manifest)
    window = TelemetryCapture(
        config=config, fetchers=_three_stubs(), writer=ParquetWriter()
    ).run(start, end)

    manifest_path = config.output_dir / config.incident_id / "manifest.json"
    _write_snapshot_hash(window, manifest_path)

    data = json.loads(manifest_path.read_text())
    assert "snapshot_hash" in data
    assert len(data["snapshot_hash"]) == 64
    assert all(c in "0123456789abcdef" for c in data["snapshot_hash"])


def test_manifest_schema_version_updated_to_v0_2(config, window_bounds):
    """_write_snapshot_hash() sets schema_version to 'schema-draft-v0.2'."""
    from bin.run_capture import _write_snapshot_hash  # noqa: PLC0415
    from helios.vcl import set_current_manifest

    start, end = window_bounds
    set_current_manifest(config.manifest)
    window = TelemetryCapture(
        config=config, fetchers=_three_stubs(), writer=ParquetWriter()
    ).run(start, end)

    manifest_path = config.output_dir / config.incident_id / "manifest.json"
    _write_snapshot_hash(window, manifest_path)
    data = json.loads(manifest_path.read_text())
    assert data.get("schema_version") == "schema-draft-v0.2"


def test_manifest_window_hash_and_snapshot_hash_are_distinct(config, window_bounds):
    """window_hash (L0 raw data) and snapshot_hash (graph topology) are distinct."""
    from bin.run_capture import _write_snapshot_hash  # noqa: PLC0415
    from helios.vcl import set_current_manifest

    start, end = window_bounds
    set_current_manifest(config.manifest)
    window = TelemetryCapture(
        config=config, fetchers=_three_stubs(), writer=ParquetWriter()
    ).run(start, end)

    manifest_path = config.output_dir / config.incident_id / "manifest.json"
    _write_snapshot_hash(window, manifest_path)
    data = json.loads(manifest_path.read_text())
    assert data["window_hash"] != data["snapshot_hash"]
```

- [ ] **Step 2: Confirm tests fail**

```bash
poetry run pytest tests/test_capture.py::test_manifest_has_snapshot_hash_after_write -v
```

Expected: FAIL — `ImportError: cannot import name '_write_snapshot_hash'`.

- [ ] **Step 3: Update `bin/run_capture.py`**

Add imports near top:

```python
from typing import Any

from helios.graph.ueg_c_builder import build_ueg_c

P2_TRACES_SCHEMA_VERSION = "v2"
MANIFEST_SCHEMA_VERSION = "schema-draft-v0.2"
```

Add `_write_snapshot_hash()` function:

```python
def _write_snapshot_hash(window: Any, manifest_path: Path) -> None:
    """Compute UEGCSnapshot hash and patch manifest with snapshot_hash + schema_version.

    build_ueg_c() may return None when l2b_graph flag is off — snapshot_hash is
    omitted in that case. Requires set_current_manifest() to have been called.
    """
    import json as _json

    manifest_data = _json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshot = build_ueg_c(window, manifest_data["variant_config_hash"])
    if snapshot is not None:
        manifest_data["snapshot_hash"] = snapshot.compute_snapshot_hash()
    manifest_data["schema_version"] = MANIFEST_SCHEMA_VERSION
    manifest_path.write_text(_json.dumps(manifest_data, indent=2), encoding="utf-8")
```

Update `main()`: after `window = capture.run(start, end)`, add:

```python
from helios.vcl.decorators import set_current_manifest
set_current_manifest(manifest)
incident_dir = Path(str(window.p1_metrics_path)).parent
_write_snapshot_hash(window, incident_dir / "manifest.json")
```

- [ ] **Step 4: Run tests**

```bash
poetry run pytest tests/test_capture.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add bin/run_capture.py tests/test_capture.py
git commit -m "feat(capture): write snapshot_hash + schema-draft-v0.2 to manifest post-capture"
```

---

## Task 3: SpanRecord extension + `_structural_edges()` rewrite

**Files:** `helios/graph/ueg_c_builder.py`, `tests/graph/test_ueg_c_builder.py`

- [ ] **Step 1: Add `import warnings` to test file and update `_span()` helper**

In `tests/graph/test_ueg_c_builder.py`, add `import warnings` at top. Replace the `_span()` helper:

```python
def _span(
    trace: str,
    svc: str,
    start: int,
    dur: int,
    span_id: str = "",
    parent_span_id: str | None = None,
) -> SpanRecord:
    return SpanRecord(
        trace_id=trace,
        span_id=span_id,
        service_name=svc,
        parent_span_id=parent_span_id,
        start_us=start,
        end_us=start + dur,
    )
```

- [ ] **Step 2: Write the 8 new failing tests**

Add to `tests/graph/test_ueg_c_builder.py`:

```python
def test_structural_root_span_has_no_incoming_edge() -> None:
    spans = [
        _span("t1", "frontend", 0, 1000, span_id="s1", parent_span_id=None),
        _span("t1", "checkout", 1_00, 800, span_id="s2", parent_span_id="s1"),
    ]
    snap = UEGCBuilder(enable_structural=True).build(
        spans, incident_id="inc", variant_config_hash=_HASH, captured_at_iso=_AT,
        parent_span_id_col_present=True,
    )
    s_edges = [e for e in snap.edges if e.edge_type == EdgeType.STRUCTURAL]
    assert len(s_edges) == 1
    assert s_edges[0].source == "frontend"
    assert s_edges[0].target == "checkout"


def test_structural_cross_service_edge() -> None:
    spans = [
        _span("t1", "api", 0, 1000, span_id="A", parent_span_id=None),
        _span("t1", "db", 1_00, 200, span_id="B", parent_span_id="A"),
    ]
    snap = UEGCBuilder(enable_structural=True).build(
        spans, incident_id="inc", variant_config_hash=_HASH, captured_at_iso=_AT,
        parent_span_id_col_present=True,
    )
    s_edges = [e for e in snap.edges if e.edge_type == EdgeType.STRUCTURAL]
    assert any(e.source == "api" and e.target == "db" for e in s_edges)


def test_structural_same_service_skipped() -> None:
    spans = [
        _span("t1", "svc", 0, 1000, span_id="A", parent_span_id=None),
        _span("t1", "svc", 1_00, 200, span_id="B", parent_span_id="A"),
    ]
    snap = UEGCBuilder(enable_structural=True).build(
        spans, incident_id="inc", variant_config_hash=_HASH, captured_at_iso=_AT,
        parent_span_id_col_present=True,
    )
    s_edges = [e for e in snap.edges if e.edge_type == EdgeType.STRUCTURAL]
    assert len(s_edges) == 0


def test_structural_multi_level_chain() -> None:
    spans = [
        _span("t1", "A", 0, 1000, span_id="s1", parent_span_id=None),
        _span("t1", "B", 1_00, 500, span_id="s2", parent_span_id="s1"),
        _span("t1", "C", 200, 200, span_id="s3", parent_span_id="s2"),
    ]
    snap = UEGCBuilder(enable_structural=True).build(
        spans, incident_id="inc", variant_config_hash=_HASH, captured_at_iso=_AT,
        parent_span_id_col_present=True,
    )
    s_edges = [e for e in snap.edges if e.edge_type == EdgeType.STRUCTURAL]
    pairs = {(e.source, e.target) for e in s_edges}
    assert ("A", "B") in pairs
    assert ("B", "C") in pairs


def test_structural_fallback_on_missing_column() -> None:
    spans = [
        _span("t1", "frontend", 0, 1000, span_id="s1"),
        _span("t1", "checkout", 1_00, 800, span_id="s2"),
    ]
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        snap = UEGCBuilder(enable_structural=True).build(
            spans, incident_id="inc", variant_config_hash=_HASH, captured_at_iso=_AT,
            parent_span_id_col_present=False,
        )
    assert any("parent_span_id absent" in str(warning.message) for warning in w)
    s_edges = [e for e in snap.edges if e.edge_type == EdgeType.STRUCTURAL]
    assert len(s_edges) >= 1


def test_structural_root_only_v2_no_temporal_fallback() -> None:
    spans = [
        _span("t1", "svc_a", 0, 1000, span_id="s1", parent_span_id=""),
        _span("t1", "svc_b", 1_00, 800, span_id="s2", parent_span_id=""),
    ]
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        snap = UEGCBuilder(enable_structural=True).build(
            spans, incident_id="inc", variant_config_hash=_HASH, captured_at_iso=_AT,
            parent_span_id_col_present=True,
        )
    assert not any("parent_span_id absent" in str(warning.message) for warning in w)
    s_edges = [e for e in snap.edges if e.edge_type == EdgeType.STRUCTURAL]
    assert len(s_edges) == 0


def test_structural_empty_spans_returns_empty_edges() -> None:
    snap = UEGCBuilder(enable_structural=True).build(
        [], incident_id="inc", variant_config_hash=_HASH, captured_at_iso=_AT,
        parent_span_id_col_present=True,
    )
    assert not any(e.edge_type == EdgeType.STRUCTURAL for e in snap.edges)


def test_structural_parquet_null_variants() -> None:
    import math

    import pandas as pd

    from helios.graph.ueg_c_builder import _psid

    assert _psid(None) == ""
    assert _psid(float("nan")) == ""
    assert _psid(pd.NA) == ""
    assert _psid(pd.NaT) == ""
    assert _psid(math.nan) == ""
    assert _psid("abc123") == "abc123"
    assert _psid("") == ""
```

- [ ] **Step 3: Run new tests to confirm they fail**

```bash
poetry run pytest tests/graph/test_ueg_c_builder.py -v -k "root_span or cross_service or same_service_skip or multi_level or fallback or root_only or empty_spans or parquet_null"
```

Expected: FAIL — `SpanRecord() got unexpected keyword argument 'span_id'`.

- [ ] **Step 4: Update `SpanRecord` in `helios/graph/ueg_c_builder.py`**

```python
@dataclass(frozen=True)
class SpanRecord:
    trace_id: str
    span_id: str                  # required for parent_span_id lookup
    service_name: str
    parent_span_id: str | None    # None or "" for root spans
    start_us: int
    end_us: int
```

- [ ] **Step 5: Rename existing `_structural_edges()` to `_structural_edges_temporal()`**

Inside `UEGCBuilder`, rename the current body of `_structural_edges()` to a new method:

```python
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
                    continue
                if span_p.start_us <= span_s.start_us and span_p.end_us >= span_s.end_us:
                    pairs.add((span_p.service_name, span_s.service_name))
                    break
    return [
        UEGCEdge(source=src, target=tgt, edge_type=EdgeType.STRUCTURAL, weight=1)
        for src, tgt in sorted(pairs)
    ]
```

- [ ] **Step 6: Rewrite `_structural_edges()` to use parent_span_id**

```python
def _structural_edges(
    self, spans: list[SpanRecord], parent_span_id_col_present: bool
) -> list[UEGCEdge]:
    # Fallback only when the column was structurally ABSENT from Parquet (schema v1).
    # A root-only schema v2 trace (all parent_span_id="") is a valid topology and must
    # return an empty edge list — NOT invoke temporal fallback. The caller-supplied flag
    # distinguishes absent-column v1 from root-only v2 — span data alone cannot.
    if not spans or not parent_span_id_col_present:
        import warnings
        warnings.warn(
            "parent_span_id absent — falling back to temporal containment",
            stacklevel=3,
        )
        return self._structural_edges_temporal(spans)
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
```

- [ ] **Step 7: Add `parent_span_id_col_present` parameter to `UEGCBuilder.build()`**

```python
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
```

The default `parent_span_id_col_present=False` ensures existing tests that don't pass this parameter use the temporal-fallback path (with a warning).

- [ ] **Step 8: Update the two existing temporal-containment tests to suppress the expected warning**

In `test_structural_edge_parent_encloses_child` and `test_structural_scan_skips_same_service_spans`, wrap the `build()` call:

```python
with warnings.catch_warnings(record=True):
    warnings.simplefilter("always")
    snap = _builder_structural().build(
        spans, incident_id="inc", variant_config_hash=_HASH, captured_at_iso=_AT
    )
```

- [ ] **Step 9: Run all UEG-C tests**

```bash
poetry run pytest tests/graph/test_ueg_c_builder.py -v
```

Expected: all 14 tests PASS.

- [ ] **Step 10: Run full suite**

```bash
poetry run pytest -x
```

Expected: green.

- [ ] **Step 11: Commit**

```bash
git add helios/graph/ueg_c_builder.py tests/graph/test_ueg_c_builder.py
git commit -m "feat(ueg-c): SpanRecord parent_span_id fields + _structural_edges parent-child rewrite"
```

---

## Task 4: `_psid()` helper + `build_ueg_c()` pd.read_parquet update

**Files:** `helios/graph/ueg_c_builder.py`

The `test_structural_parquet_null_variants` test (Task 3) already covers `_psid()` — it will pass once this task is done.

- [ ] **Step 1: Verify the null-variants test currently fails**

```bash
poetry run pytest tests/graph/test_ueg_c_builder.py::test_structural_parquet_null_variants -v
```

Expected: FAIL — `cannot import name '_psid'`.

- [ ] **Step 2: Add module-level imports to `helios/graph/ueg_c_builder.py`**

Add near the top alongside existing imports:

```python
import math

import pandas as pd
```

Remove `import pyarrow.parquet as pq` (no longer needed after this task).

- [ ] **Step 3: Add `_psid()` at module level (before `SpanRecord`)**

```python
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
```

- [ ] **Step 4: Update `build_ueg_c()` to use `pd.read_parquet`**

```python
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
```

- [ ] **Step 5: Run tests**

```bash
poetry run pytest tests/graph/ -v && poetry run pytest -x
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add helios/graph/ueg_c_builder.py
git commit -m "feat(ueg-c): _psid() null normalisation + build_ueg_c pd.read_parquet + has_psid flag"
```

---

## Task 5: PipelineVerdict schema v0.2

**Files:** `helios/schemas/verdict.py`, `tests/test_schema_stability.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_schema_stability.py`:

```python
def test_verdict_v0_2_has_ppr_scores_and_prompt_version() -> None:
    from helios.schemas.verdict import VERDICT_SCHEMA_VERSION

    v = PipelineVerdict(
        run_id="run-001",
        incident_id="inc-001",
        variant_config_hash=_FAKE_HASH,
        snapshot_hash=_FAKE_SNAP_HASH,
        pipeline="gpipe",
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        ranked_candidates=["svc-A"],
        latency_ms=12.5,
        token_count=0,
        narrative="test",
        ppr_scores={"svc-A": 0.75, "svc-B": 0.25},
        prompt_version=None,
    )
    assert v.ppr_scores == {"svc-A": 0.75, "svc-B": 0.25}
    assert v.prompt_version is None
    assert v.schema_version == VERDICT_SCHEMA_VERSION
    assert VERDICT_SCHEMA_VERSION == "schema-draft-v0.2"


def test_verdict_v0_2_hr_at_3_defaults_to_zero() -> None:
    v = PipelineVerdict(
        run_id="run-001",
        incident_id="inc-001",
        variant_config_hash=_FAKE_HASH,
        snapshot_hash=_FAKE_SNAP_HASH,
        pipeline="gpipe",
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        ranked_candidates=[],
        latency_ms=0.00,
        token_count=0,
        narrative="gpipe-gated-or-skipped",
    )
    assert v.hr_at_3 == 0.00
    assert v.cpr == 0.00


def test_verdict_schema_version_constant_matches_default() -> None:
    from helios.schemas.verdict import VERDICT_SCHEMA_VERSION

    v = _make_verdict()
    assert v.schema_version == VERDICT_SCHEMA_VERSION
```

- [ ] **Step 2: Confirm tests fail**

```bash
poetry run pytest tests/test_schema_stability.py::test_verdict_v0_2_has_ppr_scores_and_prompt_version -v
```

Expected: FAIL — `cannot import name 'VERDICT_SCHEMA_VERSION'` or ValidationError.

- [ ] **Step 3: Update `helios/schemas/verdict.py`**

```python
"""PipelineVerdict — Pydantic model for per-pipeline evaluation result rows (§6.3)."""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict, Field

from helios.schemas.telemetry import EvaluationPhase
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

__all__ = ["PipelineVerdict", "VERDICT_SCHEMA_VERSION"]

VERDICT_SCHEMA_VERSION: str = "schema-draft-v0.2"


class PipelineVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    incident_id: str
    variant_config_hash: str
    snapshot_hash: str
    pipeline: str
    evaluation_phase: EvaluationPhase
    ranked_candidates: list[str]
    hr_at_3: float = Field(default=0.00, ge=0, le=1)
    cpr: float = Field(default=0.00, ge=0, le=1)
    latency_ms: float = Field(ge=0)
    token_count: int = Field(ge=0)
    narrative: str
    ppr_scores: dict[str, float] = Field(default_factory=dict)
    prompt_version: str | None = None
    schema_version: str = VERDICT_SCHEMA_VERSION

    def compute_verdict_hash(self) -> str:
        from helios.vcl import canonical_json
        return hashlib.sha256(canonical_json(self.model_dump()).encode()).hexdigest()
```

- [ ] **Step 4: Run full schema stability test suite**

```bash
poetry run pytest tests/test_schema_stability.py -v
```

Expected: all PASS.

- [ ] **Step 5: Run deviation log for schema v0.2**

```bash
set -a; source .env; set +a
poetry run python bin/log_deviation.py \
  --stage "Stage 1 / M3" \
  --clause "§3.6.3 PipelineVerdict schema" \
  --change "PipelineVerdict bumped to schema-draft-v0.2: added ppr_scores (dict[str,float]) and prompt_version (str|None). hr_at_3 and cpr now have default=0.00. VERDICT_SCHEMA_VERSION constant added." \
  --reason "G-pipe requires PPR score auditability; L-pipe requires prompt provenance tracking." \
  --analytic-consequence "All exploratory verdict hashes invalidated. Existing DuckDB rows are exploratory-phase only and excluded from confirmatory inference."
```

- [ ] **Step 6: Run full suite and commit**

```bash
poetry run pytest -x
git add helios/schemas/verdict.py tests/test_schema_stability.py deviation_log.jsonl
git commit -m "feat(verdict): PipelineVerdict v0.2 — ppr_scores, prompt_version, VERDICT_SCHEMA_VERSION"
```

---

## Task 6: Data re-capture + deviation log + registry rebuild

**Operational task — requires Docker OTEL Demo running.**

- [ ] **Step 1: Verify containers are healthy**

```bash
docker ps | grep otel-demo
```

Expected: see jaeger, prometheus, opensearch containers running.

- [ ] **Step 2: Run re-capture loop**

```bash
set -a; source .env; set +a
for incident in $(ls data/captures/); do
    echo "[recapture] $incident"
    poetry run python bin/run_capture.py --incident-id "$incident"
done
```

If any incident fails mid-loop: restart the whole loop. `run_capture.py` overwrites manifests, so a full re-run is safe. Verify with `poetry run python bin/verify_captures.py` before proceeding.

- [ ] **Step 3: Log the re-capture deviation entry**

```bash
set -a; source .env; set +a
poetry run python bin/log_deviation.py \
  --stage "Stage 1 / M3-task0" \
  --clause "§2.2 Span Containment Heuristic" \
  --change "Re-captured all 20 incidents with parent_span_id field in p2_traces.parquet. Structural edges now use OTEL parent-child linkage, superseding temporal containment." \
  --reason "parent_span_id was absent from original captures; required for correct structural edge derivation" \
  --analytic-consequence "Structural edge topology changes; snapshot hashes change for all 20 incidents (registry rebuilt); exploratory corpus only"
```

- [ ] **Step 4: Rebuild snapshot registry**

```bash
rm data/snapshot_registry.jsonl
poetry run python bin/verify_captures.py
set -a; source .env; set +a && poetry run python bin/log_deviation.py verify
```

Expected: `Chain verification PASSED`.

- [ ] **Step 5: Commit**

```bash
git add data/snapshot_registry.jsonl deviation_log.jsonl
git commit -m "data(capture): re-capture 20 incidents with parent_span_id; registry rebuilt"
```

---

## Task 7: gpipe_config.py

**Files:** `helios/pipelines/g_pipe/gpipe_config.py`, `tests/pipelines/test_gpipe_config.py`

- [ ] **Step 1: Write failing test**

Create `tests/pipelines/test_gpipe_config.py`:

```python
"""Tests for gpipe_config constants."""

from __future__ import annotations

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def test_gpipe_config_constants_importable() -> None:
    from helios.pipelines.g_pipe.gpipe_config import (
        DISAGREEMENT_SWEEP,
        DISAGREEMENT_THRESHOLD,
        GPIPE_PPR_ALPHA,
    )

    assert isinstance(DISAGREEMENT_THRESHOLD, float)
    assert isinstance(GPIPE_PPR_ALPHA, float)
    assert isinstance(DISAGREEMENT_SWEEP, list)
    assert len(DISAGREEMENT_SWEEP) == 5
    assert DISAGREEMENT_THRESHOLD in DISAGREEMENT_SWEEP
```

- [ ] **Step 2: Confirm test fails**

```bash
poetry run pytest tests/pipelines/test_gpipe_config.py -v
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Create `helios/pipelines/g_pipe/gpipe_config.py`**

```python
"""G-pipe calibration constants — frozen after LOO-CV calibration rerun.

Do not change DISAGREEMENT_THRESHOLD after calibration without a deviation log entry.
"""

from __future__ import annotations

from helios.vcl import VCLFlag  # noqa: F401 — satisfies flag-guard

DISAGREEMENT_THRESHOLD: float = 0.30

GPIPE_PPR_ALPHA: float = 0.85

DISAGREEMENT_SWEEP: list[float] = [0.20, 0.25, 0.30, 0.35, 0.40]
```

- [ ] **Step 4: Run test, commit**

```bash
poetry run pytest tests/pipelines/test_gpipe_config.py -v
git add helios/pipelines/g_pipe/gpipe_config.py tests/pipelines/test_gpipe_config.py
git commit -m "feat(gpipe): gpipe_config.py with DISAGREEMENT_THRESHOLD=0.30"
```

---

## Task 8: G-pipe pipeline.py + tests

**Files:** `helios/pipelines/g_pipe/pipeline.py`, `tests/pipelines/test_gpipe_pipeline.py`, delete `stub.py`

### Part A — disagreement computation + gate

- [ ] **Step 1: Write failing tests**

Create `tests/pipelines/test_gpipe_pipeline.py`:

```python
"""Tests for helios.pipelines.g_pipe.pipeline."""

from __future__ import annotations

import pytest

from helios.vcl import VCLFlag, get_variant, set_current_manifest  # noqa: F401


class TestComputePprDisagreement:
    def test_below_threshold_returns_low_value(self) -> None:
        from helios.pipelines.g_pipe.pipeline import compute_ppr_disagreement

        scores = {"a": 0.60, "b": 0.25, "c": 0.15}
        # 3rd/top = 0.15/0.60 = 0.25 — below default threshold
        assert compute_ppr_disagreement(scores) == pytest.approx(0.25)

    def test_at_threshold_returns_exact(self) -> None:
        from helios.pipelines.g_pipe.pipeline import compute_ppr_disagreement

        # 3rd/top = 0.27/0.90 = 0.30 (exactly at threshold)
        scores = {"a": 0.90, "b": 0.45, "c": 0.27}
        assert compute_ppr_disagreement(scores) == pytest.approx(0.30)

    def test_above_threshold(self) -> None:
        from helios.pipelines.g_pipe.pipeline import compute_ppr_disagreement

        scores = {"a": 0.90, "b": 0.60, "c": 0.31}
        assert compute_ppr_disagreement(scores) > 0.30

    def test_uniform_scores_return_near_one(self) -> None:
        from helios.pipelines.g_pipe.pipeline import compute_ppr_disagreement

        scores = {"a": 0.33, "b": 0.33, "c": 0.33}
        assert compute_ppr_disagreement(scores) == pytest.approx(1, abs=0.01)

    def test_fewer_than_three_candidates_returns_zero(self) -> None:
        from helios.pipelines.g_pipe.pipeline import compute_ppr_disagreement

        assert compute_ppr_disagreement({"a": 0.80, "b": 0.20}) == 0.00
        assert compute_ppr_disagreement({}) == 0.00

    def test_negative_score_raises_value_error(self) -> None:
        from helios.pipelines.g_pipe.pipeline import compute_ppr_disagreement

        with pytest.raises(ValueError, match="negative"):
            compute_ppr_disagreement({"a": 0.80, "b": -0.10, "c": 0.30})

    def test_all_zero_scores_returns_zero(self) -> None:
        from helios.pipelines.g_pipe.pipeline import compute_ppr_disagreement

        assert compute_ppr_disagreement({"a": 0.00, "b": 0.00, "c": 0.00}) == 0.00


class TestShouldRunGpipe:
    def _dpipe_dict(self, scores: dict) -> dict:
        return {"ppr_scores": scores, "pipeline": "dpipe"}

    def test_gpipe_flag_off_returns_false(self) -> None:
        from helios.pipelines.g_pipe.pipeline import should_run_gpipe

        manifest = get_variant("HELIOS-noGraph")
        result = should_run_gpipe(
            self._dpipe_dict({"a": 0.34, "b": 0.33, "c": 0.33}), manifest
        )
        assert result is False

    def test_l2b_graph_flag_off_returns_false(self) -> None:
        from unittest.mock import MagicMock

        from helios.pipelines.g_pipe.pipeline import should_run_gpipe

        m = MagicMock()
        m.gpipe = True
        m.l2b_graph = False
        result = should_run_gpipe(
            self._dpipe_dict({"a": 0.34, "b": 0.33, "c": 0.33}), m
        )
        assert result is False

    def test_disagreement_below_threshold_returns_false(self) -> None:
        from helios.pipelines.g_pipe.pipeline import should_run_gpipe

        manifest = get_variant("HELIOS-Full")
        set_current_manifest(manifest)
        # 3rd/top = 0.10/0.80 = 0.125 → below 0.30
        result = should_run_gpipe(
            self._dpipe_dict({"a": 0.80, "b": 0.10, "c": 0.10}), manifest
        )
        assert result is False

    def test_disagreement_at_threshold_returns_true(self) -> None:
        from helios.pipelines.g_pipe.pipeline import should_run_gpipe

        manifest = get_variant("HELIOS-Full")
        set_current_manifest(manifest)
        # 3rd/top = 0.27/0.90 = 0.30 → at threshold
        result = should_run_gpipe(
            self._dpipe_dict({"a": 0.90, "b": 0.45, "c": 0.27}), manifest
        )
        assert result is True
```

- [ ] **Step 2: Confirm tests fail**

```bash
poetry run pytest tests/pipelines/test_gpipe_pipeline.py -v
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Create `helios/pipelines/g_pipe/pipeline.py` Part 1**

```python
"""G-pipe — conditional PPR-traversal peer pipeline (§3.6.7, §3.4).

Gated by VCLFlag.GPIPE. Entry gate: PPR disagreement >= DISAGREEMENT_THRESHOLD.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import networkx as nx

from helios.pipelines.g_pipe.gpipe_config import DISAGREEMENT_THRESHOLD, GPIPE_PPR_ALPHA
from helios.schemas.verdict import VERDICT_SCHEMA_VERSION
from helios.vcl import VCLFlag, gated_by
from helios.vcl.decorators import get_current_manifest

if TYPE_CHECKING:
    from helios.schemas.ueg_c import UEGCSnapshot
    from helios.vcl.config import VCLManifest

__all__ = ["compute_ppr_disagreement", "run_gpipe", "should_run_gpipe"]

HELIOS_ENABLE_GPIPE: bool = True


def compute_ppr_disagreement(ppr_scores: dict[str, float]) -> float:
    """Ratio of 3rd-ranked to top-ranked PPR score.

    Returns 0.00 when fewer than 3 candidates or top score is non-positive.
    Raises ValueError on any negative score — D-pipe PPR scores must be non-negative.
    """
    if any(v < 0.00 for v in ppr_scores.values()):
        raise ValueError(f"ppr_scores contains negative values: {ppr_scores}")
    if len(ppr_scores) < 3:
        return 0.00
    sorted_scores = sorted(ppr_scores.values(), reverse=True)
    top = sorted_scores[0]
    if top <= 0.00:
        return 0.00
    return sorted_scores[2] / top


def should_run_gpipe(dpipe_verdict: dict[str, Any], manifest: VCLManifest) -> bool:
    if not manifest.gpipe:
        return False
    if not manifest.l2b_graph:
        return False
    dpipe_scores = dpipe_verdict.get("ppr_scores", {})
    return compute_ppr_disagreement(dpipe_scores) >= DISAGREEMENT_THRESHOLD
```

- [ ] **Step 4: Run Part A tests**

```bash
poetry run pytest tests/pipelines/test_gpipe_pipeline.py::TestComputePprDisagreement tests/pipelines/test_gpipe_pipeline.py::TestShouldRunGpipe -v
```

Expected: all PASS.

### Part B — PPR traversal + run_gpipe

- [ ] **Step 5: Add PPR traversal + run_gpipe tests**

Add to `tests/pipelines/test_gpipe_pipeline.py`:

```python
def _make_snap() -> "UEGCSnapshot":
    from helios.schemas.ueg_c import EdgeType, NodeType, UEGCEdge, UEGCNode, UEGCSnapshot

    return UEGCSnapshot(
        incident_id="inc-001",
        variant_config_hash="a" * 64,
        nodes=[
            UEGCNode(node_id="A", node_type=NodeType.SERVICE, service_name="A"),
            UEGCNode(node_id="B", node_type=NodeType.SERVICE, service_name="B"),
            UEGCNode(node_id="C", node_type=NodeType.SERVICE, service_name="C"),
        ],
        edges=[
            UEGCEdge(source="A", target="B", edge_type=EdgeType.CALL, weight=0.80),
            UEGCEdge(source="B", target="C", edge_type=EdgeType.CALL, weight=0.60),
        ],
        captured_at_iso="2026-01-01T00:00:00+00:00",
    )


class TestPprTraverse:
    def test_returns_ranked_list_and_scores(self) -> None:
        from helios.pipelines.g_pipe.pipeline import _ppr_traverse

        ranked, scores = _ppr_traverse(_make_snap(), seed_weights={"A": 0.80, "B": 0.20})
        assert set(ranked) == {"A", "B", "C"}
        assert all(isinstance(v, float) for v in scores.values())

    def test_deterministic_on_same_input(self) -> None:
        from helios.pipelines.g_pipe.pipeline import _ppr_traverse

        seeds = {"A": 0.70, "B": 0.30}
        ranked_a, scores_a = _ppr_traverse(_make_snap(), seed_weights=seeds)
        ranked_b, scores_b = _ppr_traverse(_make_snap(), seed_weights=seeds)
        assert ranked_a == ranked_b
        assert scores_a == scores_b

    def test_zero_sum_personalization_no_error(self) -> None:
        from helios.pipelines.g_pipe.pipeline import _ppr_traverse

        # All matched node scores are zero — falls back to uniform, no ZeroDivisionError
        ranked, _ = _ppr_traverse(
            _make_snap(), seed_weights={"A": 0.00, "B": 0.00, "C": 0.00}
        )
        assert len(ranked) == 3

    def test_unknown_seed_nodes_filtered(self) -> None:
        from helios.pipelines.g_pipe.pipeline import _ppr_traverse

        ranked, _ = _ppr_traverse(_make_snap(), seed_weights={"A": 0.80, "PHANTOM": 0.20})
        assert "PHANTOM" not in ranked


class TestRunGpipe:
    def test_sentinel_when_below_threshold(self) -> None:
        from helios.pipelines.g_pipe.pipeline import run_gpipe

        manifest = get_variant("HELIOS-Full")
        set_current_manifest(manifest)
        result = run_gpipe(
            incident_id="inc-001",
            snapshot=_make_snap(),
            snapshot_hash="b" * 64,
            dpipe_scores={"A": 0.80, "B": 0.15, "C": 0.05},
            evaluation_phase="exploratory",
            run_id="run-001",
        )
        # 3rd/top = 0.05/0.80 = 0.0625 — below threshold
        assert result["narrative"] == "gpipe-gated-or-skipped"
        assert result["ranked_candidates"] == []

    def test_full_result_when_above_threshold(self) -> None:
        from helios.pipelines.g_pipe.pipeline import run_gpipe

        manifest = get_variant("HELIOS-Full")
        set_current_manifest(manifest)
        result = run_gpipe(
            incident_id="inc-001",
            snapshot=_make_snap(),
            snapshot_hash="b" * 64,
            dpipe_scores={"A": 0.90, "B": 0.45, "C": 0.36},
            evaluation_phase="exploratory",
            run_id="run-001",
        )
        # 3rd/top = 0.36/0.90 = 0.40 — above threshold
        assert result["narrative"] != "gpipe-gated-or-skipped"
        assert len(result["ranked_candidates"]) > 0

    def test_sentinel_has_all_required_fields(self) -> None:
        from helios.pipelines.g_pipe.pipeline import run_gpipe

        manifest = get_variant("HELIOS-Full")
        set_current_manifest(manifest)
        result = run_gpipe(
            incident_id="inc-001",
            snapshot=_make_snap(),
            snapshot_hash="b" * 64,
            dpipe_scores={"A": 0.90, "B": 0.08, "C": 0.02},
            evaluation_phase="confirmatory",
            run_id="run-xyz",
        )
        for field in (
            "pipeline", "incident_id", "run_id", "variant_config_hash",
            "snapshot_hash", "ranked_candidates", "ppr_scores",
            "hr_at_3", "cpr", "latency_ms", "token_count",
            "narrative", "evaluation_phase", "schema_version",
        ):
            assert field in result, f"missing field: {field}"
        assert result["evaluation_phase"] == "confirmatory"
        assert result["run_id"] == "run-xyz"
```

- [ ] **Step 6: Confirm new tests fail**

```bash
poetry run pytest tests/pipelines/test_gpipe_pipeline.py::TestPprTraverse tests/pipelines/test_gpipe_pipeline.py::TestRunGpipe -v
```

Expected: FAIL.

- [ ] **Step 7: Append full implementation to `pipeline.py`**

```python
def _build_nx_graph(snapshot: UEGCSnapshot) -> nx.DiGraph:
    graph: nx.DiGraph = nx.DiGraph()
    for node in snapshot.nodes:
        graph.add_node(node.service_name)
    for edge in snapshot.edges:
        graph.add_edge(edge.source, edge.target, weight=edge.weight)
    return graph


def _ppr_traverse(
    snapshot: UEGCSnapshot,
    seed_weights: dict[str, float],
) -> tuple[list[str], dict[str, float]]:
    graph = _build_nx_graph(snapshot)
    personalization: dict[str, float] | None = {
        k: v for k, v in seed_weights.items() if k in graph.nodes
    }
    if not personalization or sum(personalization.values()) <= 0.00:
        personalization = None
    raw_scores: dict[str, float] = nx.pagerank(
        graph, alpha=GPIPE_PPR_ALPHA, personalization=personalization
    )
    ranked = sorted(raw_scores, key=raw_scores.__getitem__, reverse=True)
    return ranked, raw_scores


def _sentinel_verdict(
    incident_id: str,
    snapshot_hash: str,
    manifest: VCLManifest,
    evaluation_phase: str,
    run_id: str,
) -> dict[str, Any]:
    return {
        "pipeline": "gpipe",
        "incident_id": incident_id,
        "run_id": run_id,
        "variant_config_hash": manifest.compute_variant_config_hash(),
        "snapshot_hash": snapshot_hash,
        "ranked_candidates": [],
        "ppr_scores": {},
        "hr_at_3": 0.00,
        "cpr": 0.00,
        "latency_ms": 0.00,
        "token_count": 0,
        "narrative": "gpipe-gated-or-skipped",
        "evaluation_phase": evaluation_phase,
        "schema_version": VERDICT_SCHEMA_VERSION,
    }


def _build_gpipe_verdict(
    incident_id: str,
    snapshot_hash: str,
    manifest: VCLManifest,
    ranked: list[str],
    ppr_scores: dict[str, float],
    evaluation_phase: str,
    run_id: str,
) -> dict[str, Any]:
    import time

    start = time.monotonic()
    latency_ms = (time.monotonic() - start) * 1000
    return {
        "pipeline": "gpipe",
        "incident_id": incident_id,
        "run_id": run_id,
        "variant_config_hash": manifest.compute_variant_config_hash(),
        "snapshot_hash": snapshot_hash,
        "ranked_candidates": ranked,
        "ppr_scores": ppr_scores,
        "hr_at_3": 0.00,
        "cpr": 0.00,
        "latency_ms": latency_ms,
        "token_count": 0,
        "narrative": "gpipe-traversal-complete",
        "evaluation_phase": evaluation_phase,
        "schema_version": VERDICT_SCHEMA_VERSION,
    }


@gated_by(VCLFlag.GPIPE)
def run_gpipe(
    incident_id: str,
    snapshot: UEGCSnapshot,
    snapshot_hash: str,
    dpipe_scores: dict[str, float],
    evaluation_phase: str,
    run_id: str,
) -> dict[str, Any]:
    manifest = get_current_manifest()
    assert manifest is not None
    disagreement = compute_ppr_disagreement(dpipe_scores)
    if disagreement < DISAGREEMENT_THRESHOLD:
        return _sentinel_verdict(
            incident_id, snapshot_hash, manifest, evaluation_phase, run_id
        )
    ranked, ppr_out = _ppr_traverse(snapshot, seed_weights=dpipe_scores)
    return _build_gpipe_verdict(
        incident_id, snapshot_hash, manifest, ranked, ppr_out, evaluation_phase, run_id
    )
```

- [ ] **Step 8: Run all pipeline tests**

```bash
poetry run pytest tests/pipelines/test_gpipe_pipeline.py -v
```

Expected: all PASS.

- [ ] **Step 9: Update `__init__.py`, delete `stub.py`**

Update `helios/pipelines/g_pipe/__init__.py` docstring:

```python
"""helios.pipelines.g_pipe — PPR-traversal causal peer pipeline (Milestone 3).

Entry gate: D-pipe PPR disagreement >= DISAGREEMENT_THRESHOLD.
Gated by VCLFlag.GPIPE.
"""
```

Delete stub:

```bash
git rm helios/pipelines/g_pipe/stub.py
```

- [ ] **Step 10: Run full suite and commit**

```bash
poetry run pytest -x
git add helios/pipelines/g_pipe/pipeline.py helios/pipelines/g_pipe/__init__.py tests/pipelines/test_gpipe_pipeline.py tests/pipelines/test_gpipe_config.py
git commit -m "feat(gpipe): G-pipe pipeline — PPR disagreement gate + traversal + sentinel verdict"
```

---

## Task 9: Orchestrator sequential dispatch

**Files:** `helios/orchestrator/runner.py`, `tests/test_orchestrator_runner.py`

- [ ] **Step 1: Write failing integration test**

Add to `tests/test_orchestrator_runner.py` inside `TestRunOrchestrator`:

```python
def test_all_three_pipeline_verdicts_share_run_id(self, tmp_path: Path) -> None:
    """D-pipe, G-pipe, and L-pipe verdicts for one incident share the same run_id."""
    from helios.store.result_store import ResultStore

    captures = tmp_path / "captures"
    _make_capture(captures, "inc-runid-001")
    orch = _make_orchestrator(tmp_path, captures)
    orch.run(captures)

    store = ResultStore(tmp_path / "results.duckdb")
    rows = store.fetch_all_for_incident("inc-runid-001")
    run_ids = {r.run_id for r in rows}
    assert len(run_ids) == 1, f"Expected 1 run_id, got: {run_ids}"
```

Note: check `helios/store/result_store.py` for the correct API to fetch rows by incident. If `fetch_all_for_incident()` doesn't exist, use whatever query method is available, or add it.

- [ ] **Step 2: Confirm test fails**

```bash
poetry run pytest tests/test_orchestrator_runner.py::TestRunOrchestrator::test_all_three_pipeline_verdicts_share_run_id -v
```

Expected: FAIL.

- [ ] **Step 3: Update imports in `helios/orchestrator/runner.py`**

Replace:
```python
from helios.pipelines.g_pipe.stub import run_gpipe
```
With:
```python
from helios.pipelines.g_pipe.pipeline import run_gpipe, should_run_gpipe
from helios.schemas.verdict import VERDICT_SCHEMA_VERSION
```

- [ ] **Step 4: Rewrite `_process_incident()` sequential dispatch**

Replace the three concurrent pipeline calls with:

```python
evaluation_phase = window.evaluation_phase.value

d_out = run_dpipe(
    window=window,
    ueg_c=ueg_c,
    incident_id=incident_id,
    snapshot_hash=snapshot_hash,
    variant_config_hash=self._config_hash,
    evaluation_phase=window.evaluation_phase,
    run_id=run_id,
)
# Normalise schema version: D-pipe is frozen at v0.1; all rows for this run get v0.2
d_out["schema_version"] = VERDICT_SCHEMA_VERSION

if should_run_gpipe(d_out, self._manifest):
    g_out = run_gpipe(
        incident_id=incident_id,
        snapshot=ueg_c,
        snapshot_hash=snapshot_hash,
        dpipe_scores=d_out.get("ppr_scores", {}),
        evaluation_phase=evaluation_phase,
        run_id=run_id,
    )
else:
    g_out = {
        "pipeline": "gpipe",
        "incident_id": incident_id,
        "run_id": run_id,
        "variant_config_hash": self._config_hash,
        "snapshot_hash": snapshot_hash,
        "ranked_candidates": [],
        "ppr_scores": {},
        "hr_at_3": 0.00,
        "cpr": 0.00,
        "latency_ms": 0.00,
        "token_count": 0,
        "narrative": "gpipe-gated-or-skipped",
        "evaluation_phase": evaluation_phase,
        "schema_version": VERDICT_SCHEMA_VERSION,
    }

l_out = run_lpipe(incident_id=incident_id, snapshot_hash=snapshot_hash)
l_out["schema_version"] = VERDICT_SCHEMA_VERSION
l_out["run_id"] = run_id
```

- [ ] **Step 5: Update `_build_verdict()` to use `run_id` from `stub_out`**

```python
def _build_verdict(self, stub_out: dict[str, Any]) -> PipelineVerdict:
    return PipelineVerdict(
        run_id=str(stub_out.get("run_id", str(uuid.uuid4()))),
        incident_id=stub_out["incident_id"],
        variant_config_hash=stub_out["variant_config_hash"],
        snapshot_hash=stub_out["snapshot_hash"],
        pipeline=stub_out["pipeline"],
        evaluation_phase=EvaluationPhase(
            stub_out.get("evaluation_phase", "exploratory")
        ),
        ranked_candidates=stub_out.get("ranked_candidates", []),
        hr_at_3=float(stub_out.get("hr_at_3", 0.00)),
        cpr=float(stub_out.get("cpr", 0.00)),
        latency_ms=float(stub_out.get("latency_ms", 0.00)),
        token_count=int(stub_out.get("token_count", 0)),
        narrative=stub_out.get("narrative", "stub"),
        ppr_scores=stub_out.get("ppr_scores", {}),
        prompt_version=stub_out.get("prompt_version"),
        schema_version=stub_out.get("schema_version", VERDICT_SCHEMA_VERSION),
    )
```

- [ ] **Step 6: Log deviation for sequential dispatch**

```bash
set -a; source .env; set +a
poetry run python bin/log_deviation.py \
  --stage "Stage 1 / M3" \
  --clause "§3.6.8 Orchestration — concurrent pipeline dispatch" \
  --change "RunOrchestrator changed from concurrent to sequential D→G(conditional)→L dispatch." \
  --reason "G-pipe entry gate requires D-pipe ppr_scores before G-pipe can decide whether to activate." \
  --analytic-consequence "No impact on metric correctness. Pipeline isolation preserved. L-pipe remains independent."
```

- [ ] **Step 7: Run full suite and commit**

```bash
poetry run pytest -x
git add helios/orchestrator/runner.py tests/test_orchestrator_runner.py deviation_log.jsonl
git commit -m "feat(orchestrator): sequential D→G(conditional)→L dispatch + run_id threading"
```

---

## Task 10: MetricIntegrityGate — conditional G-pipe row

**Files:** `helios/integrity_gate.py`, `tests/test_integrity_gate.py`

- [ ] **Step 1: Check whether sentinel test already passes**

```bash
poetry run pytest tests/test_integrity_gate.py -v
```

If all pass (the gate handles sentinel rows fine with its current logic): no code change needed — add the sentinel test and commit it as a verification.

- [ ] **Step 2: Add sentinel test**

Add to `tests/test_integrity_gate.py`:

```python
def test_check_consistency_passes_gpipe_sentinel_row() -> None:
    """Sentinel verdict (narrative='gpipe-gated-or-skipped') must pass the gate."""
    from unittest.mock import MagicMock

    from helios.integrity_gate import AppendOnlyLedger, MetricIntegrityGate

    cfg_hash = "cfg1" * 16
    snap_hash = "snap" * 16
    gate = MetricIntegrityGate(
        expected_config_hash=cfg_hash,
        ledger=MagicMock(spec=AppendOnlyLedger),
        run_id="run-001",
        analytic_consequence="test",
    )
    rows = [
        {"pipeline": "dpipe", "variant_config_hash": cfg_hash,
         "snapshot_hash": snap_hash, "run_id": "run-001"},
        {"pipeline": "gpipe", "variant_config_hash": cfg_hash,
         "snapshot_hash": snap_hash, "run_id": "run-001",
         "narrative": "gpipe-gated-or-skipped", "ranked_candidates": []},
        {"pipeline": "lpipe", "variant_config_hash": cfg_hash,
         "snapshot_hash": snap_hash, "run_id": "run-001"},
    ]
    result = gate.check_consistency(rows, incident_id="inc-001")
    assert result.status == "PASS"
```

- [ ] **Step 3: Run test**

```bash
poetry run pytest tests/test_integrity_gate.py -v
```

If PASS: no code change needed. If FAIL: the gate is missing a field from sentinel rows — add that field to the sentinel dicts in `runner.py` and `pipeline.py`, then re-run.

- [ ] **Step 4: Commit**

```bash
git add tests/test_integrity_gate.py
git commit -m "test(gate): verify MetricIntegrityGate passes G-pipe sentinel row"
```

---

## Task 11: calibrate_gpipe.py + calibration rerun

**Files:** `scripts/calibrate_gpipe.py`

- [ ] **Step 1: Create `scripts/calibrate_gpipe.py`**

```python
#!/usr/bin/env python3
"""G-pipe LOO-CV threshold sweep — writes calibrated fields to data/calibrated_params.json.

Usage:
    poetry run python scripts/calibrate_gpipe.py

Requires re-captured corpus (schema-draft-v0.2 manifests) at data/captures/.
"""

from __future__ import annotations

import json
from pathlib import Path

from helios.pipelines.g_pipe.gpipe_config import DISAGREEMENT_SWEEP
from helios.pipelines.g_pipe.pipeline import _ppr_traverse, compute_ppr_disagreement
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.variants import CONFIRMATORY_VARIANTS

CALIBRATED_PATH = Path("data/calibrated_params.json")
CAPTURES_DIR = Path("data/captures")
DB_PATH = Path("data/results.duckdb")

HELIOS_ENABLE_CALIBRATE_GPIPE: bool = True


def _load_corpus() -> list[dict]:
    from helios.graph.ppr_pruner import prune_graph
    from helios.graph.ueg_c_builder import build_ueg_c
    from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
    from helios.store.result_store import ResultStore
    from helios.vcl.decorators import set_current_manifest

    store = ResultStore(DB_PATH)
    manifest = CONFIRMATORY_VARIANTS["HELIOS-Full"]
    set_current_manifest(manifest)
    corpus = []

    for d in sorted(CAPTURES_DIR.iterdir()):
        cap_path = d / "manifest.json"
        if not cap_path.exists():
            continue
        cap = json.loads(cap_path.read_text())
        if cap.get("schema_version") != "schema-draft-v0.2":
            print(f"[skip] {d.name}: not schema-draft-v0.2")
            continue

        p2 = d / "p2_traces.parquet"
        if not p2.exists():
            continue

        window = TelemetryWindow(
            incident_id=cap["incident_id"],
            variant_config_hash=cap["variant_config_hash"],
            window_start_iso=cap.get("window_start_iso", ""),
            window_end_iso=cap.get("window_end_iso", ""),
            evaluation_phase=EvaluationPhase.EXPLORATORY,
            p1_metrics_path=str(d / "p1_metrics.parquet"),
            p2_traces_path=str(p2),
            p3_logs_path=str(d / "p3_logs.parquet"),
        )

        snapshot = build_ueg_c(window, cap["variant_config_hash"])
        if snapshot is None:
            continue
        snapshot, _ = prune_graph(snapshot)

        dpipe_rows = store.fetch_all_for_incident(cap["incident_id"])
        dpipe_row = next(
            (r for r in dpipe_rows if r.pipeline == "dpipe"), None
        )
        if dpipe_row is None:
            continue

        dpipe_scores = dpipe_row.ppr_scores or {}
        ground_truth = cap.get("ground_truth_service", "")
        corpus.append({
            "incident_id": cap["incident_id"],
            "snapshot": snapshot,
            "dpipe_scores": dpipe_scores,
            "ground_truth": ground_truth,
        })

    return corpus


def _loo_cv(corpus: list[dict], threshold: float) -> tuple[float, float, int]:
    """Returns (g_hr_at_3, d_hr_at_3, n_triggered)."""
    g_hits, d_hits, n_triggered = 0, 0, 0
    n = len(corpus)
    if n == 0:
        return 0.00, 0.00, 0
    for held_out in corpus:
        dpipe_scores = held_out["dpipe_scores"]
        gt = held_out["ground_truth"]
        disagreement = compute_ppr_disagreement(dpipe_scores)
        if disagreement >= threshold and held_out["snapshot"] is not None:
            n_triggered += 1
            ranked, _ = _ppr_traverse(held_out["snapshot"], dpipe_scores)
            g_hits += int(gt in ranked[:3])
        d_ranked = sorted(dpipe_scores, key=dpipe_scores.get, reverse=True)  # type: ignore[arg-type]
        d_hits += int(gt in d_ranked[:3])
    return g_hits / max(n_triggered, 1), d_hits / n, n_triggered


def main() -> None:
    corpus = _load_corpus()
    if not corpus:
        print("[calibrate_gpipe] ERROR: empty corpus — re-capture first")
        raise SystemExit(1)

    print(f"[calibrate_gpipe] corpus: {len(corpus)} incidents")
    best_threshold, best_g_hr, best_n = DISAGREEMENT_SWEEP[0], 0.00, 0

    for threshold in DISAGREEMENT_SWEEP:
        g_hr, d_hr, n = _loo_cv(corpus, threshold)
        print(f"  t={threshold:.2f}  G={g_hr:.4f}  D={d_hr:.4f}  triggered={n}")
        if g_hr > best_g_hr:
            best_threshold, best_g_hr, best_n = threshold, g_hr, n

    _, best_d_hr, _ = _loo_cv(corpus, best_threshold)
    gate_passed = best_g_hr >= best_d_hr

    print(f"\n[calibrate_gpipe] best t={best_threshold:.2f}  G={best_g_hr:.4f}  D={best_d_hr:.4f}  A-H6={'PASS' if gate_passed else 'FAIL'}")

    params = json.loads(CALIBRATED_PATH.read_text()) if CALIBRATED_PATH.exists() else {}
    params.update({
        "gpipe_hr_at_3_held_out": best_g_hr,
        "dpipe_hr_at_3_held_out": best_d_hr,
        "gate_passed": gate_passed,
        "n_incidents_triggered": best_n,
        "gpipe_disagreement_threshold_calibrated": best_threshold,
    })
    CALIBRATED_PATH.write_text(json.dumps(params, indent=2))
    print(f"[calibrate_gpipe] written → {CALIBRATED_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run D-pipe stability check**

```bash
poetry run python scripts/calibrate_dpipe.py
```

Expected: LOO-CV HR@3 within ±0.01 of the M2 value. If it regresses more, investigate structural edge changes before continuing.

- [ ] **Step 3: Run G-pipe calibration**

```bash
poetry run python scripts/calibrate_gpipe.py
```

Note: best threshold, G-pipe HR@3, D-pipe HR@3, n_triggered.

- [ ] **Step 4: Update `DISAGREEMENT_THRESHOLD` if calibration yields a different optimal**

If best threshold ≠ 0.30, update `helios/pipelines/g_pipe/gpipe_config.py`:
```python
DISAGREEMENT_THRESHOLD: float = <calibrated_value>
```

If G-pipe HR@3 < D-pipe HR@3 (A-H6 fails):
```bash
set -a; source .env; set +a
poetry run python bin/log_deviation.py \
  --stage "Stage 1 / M3" \
  --clause "§4.2 A-H6 entry gate" \
  --change "A-H6 calibration: G-pipe HR@3 < D-pipe HR@3 on 20-incident corpus." \
  --reason "Corpus too small for reliable LOO-CV; OTEL Demo incidents share structural patterns." \
  --analytic-consequence "A-H6 deferred to AIOpsLab confirmatory phase. DISAGREEMENT_THRESHOLD frozen at calibrated value."
```

- [ ] **Step 5: Run full suite and commit**

```bash
poetry run pytest -x
git add scripts/calibrate_gpipe.py helios/pipelines/g_pipe/gpipe_config.py data/calibrated_params.json
git commit -m "feat(calibration): calibrate_gpipe.py LOO-CV sweep; DISAGREEMENT_THRESHOLD updated"
```

---

## Task 12: Pre-push gate

- [ ] **Step 1: Run full gate sequence**

```bash
set -a; source .env; set +a && \
  poetry run ruff check helios/ scripts/ tests/ && \
  poetry run ruff format --check helios/ scripts/ tests/ && \
  poetry run mypy && \
  poetry run pytest && \
  poetry run python bin/log_deviation.py verify && \
  make validate-tracking
```

- [ ] **Step 2: Fix lint issues**

```bash
poetry run ruff check --fix helios/ scripts/ tests/
poetry run ruff format helios/ scripts/ tests/
```

Common mypy issues: `UEGCSnapshot` used at runtime in `pipeline.py` — remove from `TYPE_CHECKING` if so. `__all__` sort order (ruff RUF022).

- [ ] **Step 3: Commit fixes**

```bash
git add -u
git commit -m "chore(lint): ruff/mypy fixes post-M3-gpipe implementation"
```

---

## Task 13: Documentation + tracking rows

**Files:** `docs/tracking/ablation_architecture.md`, `docs/tracking/hypothesis_variant_metric_mapping.md`, `docs/tracking/helios_mvp_tracking.md`

- [ ] **Step 1: Tracking rows → IN_PROGRESS (separate commit)**

Add M3 rows at `IN_PROGRESS` status to `helios_mvp_tracking.md`. Run `make validate-tracking`. Commit.

- [ ] **Step 2: Write §3.2 in `ablation_architecture.md`**

Add under the §3 heading:

```markdown
### §3.2 G-pipe — Conditional PPR-Traversal Peer Pipeline

**Architecture:** G-pipe activates when D-pipe PPR disagreement exceeds
DISAGREEMENT_THRESHOLD (calibrated via LOO-CV). It re-runs Personalised PageRank on
the UEG-C snapshot using D-pipe scores as seed weights, producing an alternative
ranked candidate list.

**Entry gate formula:**
  disagreement = ppr_scores_sorted[rank_2] / ppr_scores_sorted[rank_0]
  gate_fires   = disagreement >= DISAGREEMENT_THRESHOLD

**Sequential dispatch rationale:** G-pipe requires D-pipe `ppr_scores` before it can
evaluate the entry gate. RunOrchestrator was changed from concurrent to sequential
D→G(conditional)→L dispatch (deviation logged §3.6.8, Stage 1/M3). L-pipe remains
independent of G-pipe results.

**Dual VCL flag dependency:** `@gated_by(VCLFlag.GPIPE)` registers the primary pipeline
flag for disjointness analysis. VCLFlag.L2B_GRAPH is a soft guard inside
`should_run_gpipe()` — if absent, behavioral edges are missing and G-pipe is skipped.
The disjointness auditor attributes G-pipe code to GPIPE.

**A-H6 sentinel filtering (mandatory):** When the gate does not fire, G-pipe emits a
sentinel with `narrative="gpipe-gated-or-skipped"` and `hr_at_3=0.00`. Evaluation
scripts MUST filter sentinel rows for A-H6 metric queries:

  WHERE pipeline = 'gpipe' AND narrative != 'gpipe-gated-or-skipped'

Failure to filter produces a methodologically invalid A-H6 result. This filter is
baked into `analysis_plan.json` (A-H6 filter field) and must appear in
`scripts/evaluate_ablation.py` and the ablation notebook L2 section.

**Cross-references:** §2.6 (UEG-C Builder), §4 (Orchestration), §5 (Verdicts).
Deviation log entries: schema v0.2, sequential dispatch, re-capture.
```

- [ ] **Step 3: Add A-H6 sentinel filter note to `hypothesis_variant_metric_mapping.md`**

Find the A-H6 row and add sentinel filter documentation:

```markdown
| A-H6 | ... | **Sentinel filter required:** WHERE narrative != 'gpipe-gated-or-skipped'.
Without this filter, sentinel zeros contaminate the A-H6 metric. |
```

- [ ] **Step 4: Validate and commit docs**

```bash
make validate-tracking
git add docs/tracking/ablation_architecture.md docs/tracking/hypothesis_variant_metric_mapping.md docs/tracking/helios_mvp_tracking.md
git commit -m "docs(m3): ablation_architecture §3.2 + A-H6 sentinel filter + tracking rows IN_PROGRESS"
```

- [ ] **Step 5: Mark tracking rows DONE**

Update rows to DONE with date, SHA, Ev_Type, Ev_Ref. Run `make validate-tracking`. Commit.

---

## Exit Gate Checklist

```bash
# G1-1: structural edge tests (14 tests)
poetry run pytest tests/graph/test_ueg_c_builder.py -v

# G1-2: schema roundtrip at v0.2
poetry run pytest tests/test_schema_stability.py -v

# G1-3: registry 20 entries + chain verified
set -a; source .env; set +a && poetry run python bin/log_deviation.py verify

# G1-4: ≥3 new deviation log entries (re-capture + schema v0.2 + sequential dispatch)
# (verified by log_deviation.py verify above)

# G1-5: calibrated_params.json has G-pipe fields
python3 -c "import json; d=json.load(open('data/calibrated_params.json')); print(d.get('gpipe_disagreement_threshold_calibrated'))"

# G1-10: PPR determinism test
poetry run pytest tests/pipelines/test_gpipe_pipeline.py::TestPprTraverse::test_deterministic_on_same_input -v

# Full suite
poetry run pytest -v --tb=short
```

All gates must pass before invoking `superpowers:finishing-a-development-branch`.
