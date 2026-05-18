# G-pipe: Re-capture + Structural Edge Fix + Pipeline Design

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this spec task-by-task.

**Goal:** Fix structural edge derivation using `parent_span_id`, implement the conditional G-pipe pipeline with a PPR disagreement entry gate, and extend PipelineVerdict to schema-draft-v0.2.

**Milestone:** Milestone 3 — Spec 1 of 3
**Date:** 2026-05-18
**Depends on:** Milestone 2 exit (PR #24 merged, LOO-CV HR@3=0.5333, gates 15/15 PASS)
**Blocks:** Spec 3 (OSF freeze requires calibrated G-pipe thresholds)

---

## Pre-conditions (verify before starting)

- [ ] `parent_span_id` absent from existing `p2_traces.parquet` (confirmed: columns are `trace_id, span_id, operation_name, service_name, start_time_us, duration_us, status_code`)
- [ ] All 20 OTEL Demo incidents hash-verified in `data/snapshot_registry.jsonl`
- [ ] `poetry run pytest` green on `main`
- [ ] `.env` loaded (`set -a; source .env; set +a`) for deviation log CLI

---

## Architecture Overview

Three strictly ordered layers:

```
Layer 1 — Data re-capture
  bin/run_capture.py  →  p2_traces.parquet (v2, with parent_span_id)
  bin/log_deviation.py  →  deviation_log.jsonl (entry: re-capture + heuristic superseded)
  data/snapshot_registry.jsonl  →  purged + rebuilt (20 new hashes)

Layer 2 — Structural edge fix
  helios/graph/ueg_c_builder.py  →  SpanRecord.parent_span_id + _structural_edges() rewrite
  tests/graph/test_ueg_c_builder.py  →  parent_span_id edge cases

Layer 3 — G-pipe pipeline + schema v0.2
  helios/schemas/verdict.py  →  PipelineVerdict v0.2 (ppr_scores, prompt_version)
  helios/pipelines/g_pipe/gpipe_config.py  →  new constants (frozen after calibration)
  helios/pipelines/g_pipe/pipeline.py  →  replaces stub.py
  helios/orchestrator/runner.py  →  sequential D→G(conditional)→L dispatch
  helios/integrity_gate.py  →  conditional pipeline row handling
```

---

## Layer 1 — Data Re-capture

### 1.1 Parquet schema update (`bin/run_capture.py`)

Add `parent_span_id` to the trace Parquet output. OTEL emits `parent_span_id` on every span; root spans carry an empty string or null. Map this to the Parquet column.

Updated column set for `p2_traces.parquet` (schema version `v2`):
```
trace_id, span_id, parent_span_id, operation_name, service_name,
start_time_us, duration_us, status_code
```

Add schema version constants in `bin/run_capture.py`:
```python
P2_TRACES_SCHEMA_VERSION = "v2"
MANIFEST_SCHEMA_VERSION = "schema-draft-v0.2"
```

**`snapshot_hash` write (Spec 3 pre-condition):** After building the `UEGCSnapshot` from captured Parquet data, compute and write `snapshot_hash` to the capture manifest JSON. `corpus_manifest.json` generation (Spec 3) reads `cap["snapshot_hash"]` from each capture manifest — if this key is absent, `--generate` raises `KeyError`. Existing manifests at `schema-draft-v0.1` lack this field; the re-capture produces updated manifests at `schema-draft-v0.2`.

`UEGCSnapshot.compute_snapshot_hash()` already exists in `helios/schemas/ueg_c.py`. The complete `bin/run_capture.py` function body (showing all relevant fields):

```python
import json
from pathlib import Path

def capture_incident(incident_id: str, captures_dir: Path) -> None:
    incident_dir = captures_dir / incident_id
    manifest_path = incident_dir / "manifest.json"

    # Load existing manifest (written by OTEL capture step)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # window_hash is already written by the OTEL ingest step (SHA-256 of TelemetryWindow)
    # It is NOT the same as snapshot_hash — do not overwrite it.
    window_hash = manifest["window_hash"]

    parquet_paths = {
        "p2_traces": str(incident_dir / "p2_traces.parquet"),
        # ... other paths
    }

    # Build UEGCSnapshot (the compiled graph from all Parquet layers)
    from helios.schemas.telemetry import TelemetryWindow
    from helios.graph.ueg_c_builder import build_ueg_c
    window = TelemetryWindow(
        p1_metrics_path=...,
        p2_traces_path=str(incident_dir / "p2_traces.parquet"),
        ...
    )
    snapshot = build_ueg_c(window)

    # Compute and write snapshot_hash — required by Spec 3 corpus_manifest generation
    snapshot_hash = snapshot.compute_snapshot_hash()   # SHA-256 of graph topology
    manifest["snapshot_hash"] = snapshot_hash
    manifest["schema_version"] = MANIFEST_SCHEMA_VERSION   # "schema-draft-v0.2"

    # Write updated manifest atomically
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
```

`window_hash` (SHA-256 of the raw `TelemetryWindow` L0 data) is preserved — it is NOT the same as `snapshot_hash`. Both must be present and distinct in `schema-draft-v0.2` manifests. Re-capture loop (§1.2) must be re-run AFTER this code change is applied — not before.

Test: `tests/test_capture.py` — assert `parent_span_id` column present in written Parquet; assert `snapshot_hash` key present in manifest with a 64-char hex value; assert `window_hash` and `snapshot_hash` are distinct; assert `schema_version` is `"schema-draft-v0.2"`.

### 1.2 Re-capture all 20 incidents

Re-run all 20 incidents in `data/captures/`. Existing `p2_traces.parquet` files are replaced. Incident IDs and fault classes remain unchanged.

```bash
set -a; source .env; set +a
for incident in $(ls data/captures/); do
    poetry run python bin/run_capture.py --incident-id "$incident"
done
poetry run python bin/verify_captures.py
```

### 1.3 Deviation log entry (immediately after re-capture — before any code changes)

```bash
set -a; source .env; set +a
poetry run python bin/log_deviation.py \
  --stage "Stage 1 / M3-task0" \
  --clause "§2.2 Span Containment Heuristic" \
  --change "Re-captured all 20 incidents with parent_span_id field. Structural edges now derived from OTEL parent-child linkage, superseding temporal containment heuristic." \
  --reason "parent_span_id absent from original captures; required for correct structural edge derivation as specified in §2.2" \
  --analytic-consequence "Structural edge topology changes; PPR pruner entry-point detection improves; snapshot hashes change for all 20 incidents (registry rebuilt); exploratory corpus only — no confirmatory inference affected"
```

### 1.4 Snapshot registry rebuild

After re-capture, purge and rebuild `data/snapshot_registry.jsonl`:
```bash
rm data/snapshot_registry.jsonl
poetry run python bin/verify_captures.py   # re-registers all 20 incidents
```

Test: `tests/test_snapshot_registry.py` — verify 20 entries, HMAC chain clean, all hashes differ from pre-re-capture values.

---

## Layer 2 — Structural Edge Fix

### 2.1 SpanRecord update (`helios/graph/ueg_c_builder.py`)

`SpanRecord` gains two new fields. `span_id` is required to support parent_span_id matching (it is already present in the Parquet schema):

```python
@dataclass(frozen=True)
class SpanRecord:
    trace_id: str
    span_id: str                 # NEW — needed for parent_span_id lookup
    service_name: str
    parent_span_id: str | None   # NEW — None or "" for root spans
    start_us: int
    end_us: int
```

### 2.2 `_structural_edges()` rewrite

Replace temporal containment loop with parent_span_id linkage. Key invariants:

- Root spans (`parent_span_id is None` or `""`) have no incoming structural edge; they become graph roots.
- Same-service parent→child spans are skipped (intra-service calls excluded).
- Deduplication: one STRUCTURAL edge per (src, tgt) service pair per trace.

Algorithm sketch (key invariant: match `child.parent_span_id == parent.span_id` within the same trace):
```python
def _structural_edges(self, spans: list[SpanRecord]) -> list[UEGCEdge]:
    # Build lookup: (trace_id, span_id) → service_name
    span_svc: dict[tuple[str, str], str] = {
        (s.trace_id, s.span_id): s.service_name for s in spans
    }
    pairs: set[tuple[str, str]] = set()
    for child in spans:
        if not child.parent_span_id:
            continue  # root span — no incoming structural edge
        parent_svc = span_svc.get((child.trace_id, child.parent_span_id))
        if parent_svc and parent_svc != child.service_name:
            pairs.add((parent_svc, child.service_name))
    return [UEGCEdge(source=src, target=tgt, edge_type=EdgeType.STRUCTURAL, weight=1)
            for src, tgt in sorted(pairs)]
```

**Fallback:** If `parent_span_id` column is missing from the Parquet table (unexpected regression), `_structural_edges()` calls `_structural_edges_temporal()` and logs a `warnings.warn`. Never returns an empty graph silently.

`_structural_edges_temporal()` retains the original temporal containment logic verbatim — it must not be deleted when `_structural_edges()` is rewritten. It is a named, independently testable method on `UEGCBuilder`:

```python
def _structural_edges_temporal(self, spans: list[SpanRecord]) -> list[UEGCEdge]:
    """Original temporal-containment structural edge derivation (pre-parent_span_id).
    Kept as a named fallback; called by _structural_edges() when parent_span_id absent.
    """
    pairs: set[tuple[str, str]] = set()
    for i, outer in enumerate(spans):
        for inner in spans[i + 1:]:
            if outer.trace_id != inner.trace_id:
                continue
            if outer.service_name == inner.service_name:
                continue
            # containment: inner fully within outer
            if outer.start_us <= inner.start_us and inner.end_us <= outer.end_us:
                pairs.add((outer.service_name, inner.service_name))
    return [UEGCEdge(source=src, target=tgt, edge_type=EdgeType.STRUCTURAL, weight=1)
            for src, tgt in sorted(pairs)]
```

And the dispatch in `_structural_edges()`:
```python
def _structural_edges(self, spans: list[SpanRecord]) -> list[UEGCEdge]:
    # Universal-absence check: schema v1 files set every span's parent_span_id=None
    # (column absent → build_ueg_c() writes None). Schema v2 root spans get "" after
    # str() conversion of the Parquet null value. Both None and "" signal "no parent";
    # use a falsy test so that the fallback triggers when every span is parentless —
    # regardless of whether the column was absent (v1) or present-but-empty (v2 root-only).
    # A mixed v2 file always has at least one child span with a real span_id value,
    # so all(not ...) correctly evaluates to False and the fast path runs normally.
    if not spans or all(not s.parent_span_id for s in spans):
        import warnings
        warnings.warn("parent_span_id absent — falling back to temporal containment", stacklevel=3)
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
    return [UEGCEdge(source=src, target=tgt, edge_type=EdgeType.STRUCTURAL, weight=1)
            for src, tgt in sorted(pairs)]
```

### 2.3 `build_ueg_c()` factory update

Read both `span_id` and `parent_span_id` from Parquet (`span_id` already exists in schema v1). When `parent_span_id` column is absent, set `parent_span_id=None` for every span — `_structural_edges()` detects this and delegates to `_structural_edges_temporal()`.

**Null normalization — mandatory:** Parquet nullable columns surface as Python `None`, `float('nan')`, `pd.NA` (nullable integer/string dtypes), or `pd.NaT` (timestamp dtypes) when the cell is empty. A bare `str(None)` produces `"None"` and `str(float('nan'))` produces `"nan"` — both are truthy non-empty strings that cause phantom structural edges. `isinstance + math.isnan` only catches `float('nan')`; `pd.isna()` is required to cover `pd.NA`, `pd.NaT`, and other pandas null sentinels that appear in real Parquet data with nullable extension dtypes. Normalise via a helper before constructing `SpanRecord`:

```python
import math

import pandas as pd

def _psid(val: object) -> str:
    """Normalise a Parquet nullable parent_span_id cell to str or ''.

    Handles: None, float('nan'), pd.NA, pd.NaT, and other pandas nulls.
    The try/except guards against pd.isna raising TypeError on array inputs.
    """
    if val is None:
        return ""
    if isinstance(val, float) and math.isnan(val):
        return ""
    try:
        if pd.isna(val):  # handles pd.NA, pd.NaT and other pandas null variants
            return ""
    except (TypeError, ValueError):
        pass  # pd.isna raises on array inputs — treat as non-null
    return str(val)

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
```

With this normalization, root spans always receive `parent_span_id=""` (falsy), and the schema-v1 fallback path (`parent_span_id=None`) is preserved only when the column is structurally absent.
```

### 2.4 Test coverage (`tests/graph/test_ueg_c_builder.py`)

| Test | Scenario |
|---|---|
| `test_structural_root_span_has_no_incoming_edge` | Root span (parent_span_id=None) produces no incoming structural edge |
| `test_structural_cross_service_edge` | A→B parent linkage produces STRUCTURAL edge |
| `test_structural_same_service_skipped` | Intra-service spans produce no structural edge |
| `test_structural_multi_level_chain` | A→B→C chain produces A→B and B→C structural edges |
| `test_structural_fallback_on_missing_column` | Missing column → warning raised + temporal containment used |
| `test_structural_empty_spans` | Empty span list → empty edge list |
| `test_structural_parquet_null_variants` | `pd.NA`, `float('nan')`, `None`, `pd.NaT` in `parent_span_id` all normalise to `""` via `_psid()` → no phantom edges produced. Explicit assertions: `_psid(None) == ""`, `_psid(float("nan")) == ""`, `_psid(pd.NA) == ""`, `_psid(pd.NaT) == ""`, `_psid("abc123") == "abc123"` |

---

## Layer 3 — G-pipe Pipeline

### 3.1 PipelineVerdict schema v0.2 (`helios/schemas/verdict.py`)

Two optional pipeline-specific fields added; schema version bumped. A module-level constant is the single source of truth for the schema version string — all pipeline sentinel dicts import it rather than hard-coding the string, so a future schema bump updates in one place:

```python
VERDICT_SCHEMA_VERSION: str = "schema-draft-v0.2"

class PipelineVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    incident_id: str
    variant_config_hash: str
    snapshot_hash: str
    pipeline: str                   # dpipe | gpipe | lpipe
    evaluation_phase: EvaluationPhase
    ranked_candidates: list[str]
    hr_at_3: float = Field(default=0.0, ge=0, le=1)   # populated by eval harness; pipelines omit
    cpr: float = Field(default=0.0, ge=0, le=1)         # populated by eval harness; pipelines omit
    latency_ms: float = Field(ge=0)
    token_count: int = Field(ge=0)
    narrative: str
    # v0.2 additions
    ppr_scores: dict[str, float] = Field(default_factory=dict)   # G-pipe: PPR score per service
    prompt_version: str | None = None                             # L-pipe: frozen prompt version
    schema_version: str = VERDICT_SCHEMA_VERSION

    def compute_verdict_hash(self) -> str:
        return hashlib.sha256(canonical_json(self.model_dump()).encode()).hexdigest()
```

**Hash consequence:** All verdict hashes change (new fields in canonical JSON). Deviation entry required.

**Deviation entry (schema v0.2):**
```bash
poetry run python bin/log_deviation.py \
  --stage "Stage 1 / M3" \
  --clause "§3.6.3 PipelineVerdict schema" \
  --change "PipelineVerdict bumped to schema-draft-v0.2: added ppr_scores (dict[str,float], G-pipe only) and prompt_version (str|None, L-pipe only)." \
  --reason "G-pipe requires PPR score auditability; L-pipe requires prompt provenance tracking. Both are optional to preserve backward compatibility." \
  --analytic-consequence "All exploratory verdict hashes invalidated. Existing DuckDB rows are exploratory-phase only and excluded from confirmatory inference. Schema roundtrip test updated."
```

### 3.2 G-pipe config (`helios/pipelines/g_pipe/gpipe_config.py`)

```python
from helios.vcl import VCLFlag  # noqa: F401 — satisfies flag-guard

# PPR disagreement gate — swept in LOO-CV rerun; frozen after calibration
DISAGREEMENT_THRESHOLD: float = 0.30

# PPR alpha — reuses D-pipe pruner value (§2.4 spec)
GPIPE_PPR_ALPHA: float = 0.85

# Calibration sweep range
DISAGREEMENT_SWEEP: list[float] = [0.20, 0.25, 0.30, 0.35, 0.40]
```

**Freeze discipline:** After calibration rerun, update `DISAGREEMENT_THRESHOLD` to the LOO-CV-optimal value and commit. No subsequent changes without deviation entry — same discipline as `dpipe_config.py`.

### 3.3 PPR disagreement computation

```python
def compute_ppr_disagreement(ppr_scores: dict[str, float]) -> float:
    """Ratio of 3rd-ranked to top-ranked PPR score.

    Returns 0.00 when fewer than 3 candidates or top score is non-positive.
    Bounded [0.00, 1.00]: 1.00 means completely flat scores (maximum uncertainty).
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
```

**Test requirements:**
- Negative score input raises `ValueError` — explicitly tested
- Boundary tests: disagreement at 0.29 (gate does not trigger), 0.30 (gate triggers), 0.31 (gate triggers)
- Uniform scores (e.g. all 0.33): disagreement ≈ 1.00 — triggers gate
- Two-service graph (fewer than 3 candidates): returns 0.00 — gate does not trigger

### 3.4 G-pipe pipeline (`helios/pipelines/g_pipe/pipeline.py`)

**VCL flag model — dual dependency:**

`@gated_by(VCLFlag.GPIPE)` is the **primary pipeline gate** that the disjointness auditor and VCL decorator system recognise. A second flag, `VCLFlag.L2B_GRAPH`, controls whether behavioral/call edges are compiled into the `UEGCSnapshot` during capture. Without `L2B_GRAPH` active, the snapshot contains structural edges only — G-pipe will execute but with a structurally sparse graph. `should_run_gpipe()` therefore checks both:

```python
def should_run_gpipe(dpipe_verdict: dict[str, Any], manifest: VCLManifest) -> bool:
    if not manifest.gpipe:          # VCLFlag.GPIPE — primary gate; audited by disjointness
        return False
    if not manifest.l2b_graph:      # VCLFlag.L2B_GRAPH — no behavioral edges = sparse traversal
        return False
    dpipe_scores = dpipe_verdict.get("ppr_scores", {})
    return compute_ppr_disagreement(dpipe_scores) >= DISAGREEMENT_THRESHOLD
```

**Why not gate on `L2B_GRAPH` at the decorator level:** `@gated_by` registers the primary flag for static disjointness analysis. Changing the decorator to `L2B_GRAPH` would cause the disjointness auditor to attribute G-pipe lines to the behavioral-edge compilation path rather than the peer pipeline path — incorrect. `GPIPE` stays on the decorator; `L2B_GRAPH` is a soft guard inside `should_run_gpipe()`. Update `docs/tracking/vcl_manifest_tracking.md` to note this dual dependency.

```python
@gated_by(VCLFlag.GPIPE)
def run_gpipe(
    incident_id: str,
    snapshot: UEGCSnapshot,
    snapshot_hash: str,
    dpipe_scores: dict[str, float],
    evaluation_phase: str,   # passed from orchestrator; never hardcoded here
) -> dict[str, Any]:
    manifest = get_current_manifest()
    disagreement = compute_ppr_disagreement(dpipe_scores)
    if disagreement < DISAGREEMENT_THRESHOLD:
        return _sentinel_verdict(incident_id, snapshot_hash, manifest, evaluation_phase)
    ranked, ppr_out = _ppr_traverse(snapshot, seed_weights=dpipe_scores)
    return _build_verdict(incident_id, snapshot_hash, manifest, ranked, ppr_out, evaluation_phase)
```

**Sentinel verdict** (gate below threshold or `GPIPE` flag off):
```python
from helios.schemas.verdict import VERDICT_SCHEMA_VERSION

def _sentinel_verdict(incident_id, snapshot_hash, manifest, evaluation_phase: str):
    return {
        "pipeline": "gpipe",
        "incident_id": incident_id,
        "variant_config_hash": manifest.compute_variant_config_hash(),
        "snapshot_hash": snapshot_hash,
        "ranked_candidates": [],
        "ppr_scores": {},
        "hr_at_3": 0.00,
        "cpr": 0.00,
        "latency_ms": 0.00,
        "token_count": 0,
        "narrative": "gpipe-gated-or-skipped",
        "evaluation_phase": evaluation_phase,   # propagated from caller — never hardcoded
        "schema_version": VERDICT_SCHEMA_VERSION,  # single source of truth from verdict.py
    }
```

**Two-environment firewall:** `evaluation_phase` is never hardcoded inside `run_gpipe` or `_sentinel_verdict`. The orchestrator supplies it based on the run context (`"exploratory"` during OTEL Demo calibration, `"confirmatory"` during AIOpsLab runs). Hardcoding `"exploratory"` would silently tag confirmatory sentinel rows as exploratory, violating the OSF §1.4 firewall and making confirmatory result store queries return false results. The orchestrator snippet in §3.5 must pass this parameter explicitly:

```python
gpipe_verdict = run_gpipe(
    incident_id, snapshot, snapshot_hash,
    dpipe_scores=dpipe_verdict.get("ppr_scores", {}),
    evaluation_phase=evaluation_phase,   # from orchestrator run context
)
```

**PPR traversal — personalization filter:** Before calling `networkx.pagerank`, filter `dpipe_scores` to only nodes present in the graph. If a D-pipe score refers to a service that was pruned out by the K-hop pruner or is absent from the structural graph, passing it to NetworkX raises `KeyError`. Always filter:

```python
def _ppr_traverse(
    snapshot: UEGCSnapshot,
    seed_weights: dict[str, float],
) -> tuple[list[str], dict[str, float]]:
    graph = _build_nx_graph(snapshot)
    personalization = {k: v for k, v in seed_weights.items() if k in graph.nodes}
    # Zero-sum guard: if all matched nodes have D-pipe score == 0, the personalization
    # vector sums to zero. NetworkX pagerank normalises by dividing by the vector sum
    # and raises ZeroDivisionError. Fall back to uniform (None) in this case.
    if not personalization or sum(personalization.values()) <= 0:
        personalization = None  # NetworkX default: uniform over all nodes
    raw_scores = networkx.pagerank(graph, alpha=GPIPE_PPR_ALPHA, personalization=personalization)
    ranked = sorted(raw_scores, key=raw_scores.__getitem__, reverse=True)
    return ranked, raw_scores
```

Returns `(ranked_candidates: list[str], ppr_scores: dict[str, float])`. Same determinism caveat as D-pipe pruner.

**Test requirement:** `test_ppr_traverse_zero_sum_personalization` — all filtered node scores equal 0.00 → falls back to uniform personalization, no exception raised.

**Determinism test:** same `(snapshot, dpipe_scores)` input → identical `ranked_candidates` and `ppr_scores` on two sequential calls.

### 3.5 Orchestrator update (`helios/orchestrator/runner.py`)

Replace concurrent dispatch with sequential D→G(conditional)→L. The sentinel is **always emitted at the orchestrator level** — `run_gpipe()` is only called when the gate fires. This ensures `gpipe_verdict` is always a dict (never `None`) so that MetricIntegrityGate consistency checks always receive a G-pipe row:

```python
# Sequential dispatch — see deviation log and ablation_architecture.md §3.2
# run_dpipe is keyword-only (M2 frozen signature); accepts TelemetryWindow for
# raw metric streams AND UEGCSnapshot (ueg_c) for the graph topology.
dpipe_verdict = run_dpipe(
    window=window,                                             # TelemetryWindow from ingestion
    ueg_c=snapshot,                                           # UEGCSnapshot | None
    incident_id=incident_id,
    snapshot_hash=snapshot_hash,
    variant_config_hash=manifest.compute_variant_config_hash(),
    evaluation_phase=evaluation_phase,
    run_id=run_id,
)
# D-pipe is frozen at M2 and emits "schema-draft-v0.1". Normalize to v0.2 here
# so all pipeline rows for the same incident share a single schema_version tag
# in DuckDB. Pydantic would accept the mismatch silently; this explicit overwrite
# prevents version skew in downstream aggregation and preregistration audit queries.
dpipe_verdict["schema_version"] = "schema-draft-v0.2"

if should_run_gpipe(dpipe_verdict, manifest):
    gpipe_verdict = run_gpipe(
        incident_id, snapshot, snapshot_hash,
        dpipe_scores=dpipe_verdict.get("ppr_scores", {}),
        evaluation_phase=evaluation_phase,
    )
else:
    # Gate did not fire (or GPIPE/L2B_GRAPH flag off) — emit sentinel here, not inside
    # run_gpipe. This guarantees a G-pipe dict is always present for MetricIntegrityGate.
    gpipe_verdict = {
        "pipeline": "gpipe",
        "incident_id": incident_id,
        "variant_config_hash": manifest.compute_variant_config_hash(),
        "snapshot_hash": snapshot_hash,
        "ranked_candidates": [],
        "ppr_scores": {},
        "hr_at_3": 0.0,
        "cpr": 0.0,
        "latency_ms": 0.0,
        "token_count": 0,
        "narrative": "gpipe-gated-or-skipped",
        "evaluation_phase": evaluation_phase,
        "schema_version": VERDICT_SCHEMA_VERSION,  # imported from helios.schemas.verdict
    }

lpipe_verdict = run_lpipe(
    incident_id, snapshot, snapshot_hash, evaluation_phase=evaluation_phase
)   # independent of G-pipe
```

**Consequence for `run_gpipe()`:** The sentinel block in §3.4 (`_sentinel_verdict`) acts as a second-level safety net for unexpected sub-threshold cases that reach `run_gpipe()` (e.g., race conditions or direct test calls). The authoritative sentinel path is the orchestrator `else` branch above. Both paths must produce structurally identical dicts.

**Note on `.get()` call:** `run_dpipe()` returns `dict[str, Any]` (a plain dict, not a `PipelineVerdict` object). `.get("ppr_scores", {})` is therefore valid Python — no `AttributeError`. Do not call `.get()` on a `PipelineVerdict` instance; Pydantic v2 frozen models do not have a `.get()` method.

`should_run_gpipe()`: checks `VCLFlag.GPIPE` **and** `VCLFlag.L2B_GRAPH` active in manifest, AND `compute_ppr_disagreement(dpipe_scores) >= DISAGREEMENT_THRESHOLD`. See §3.4 for dual-flag rationale.

**Deviation entry (sequential dispatch):**
```bash
poetry run python bin/log_deviation.py \
  --stage "Stage 1 / M3" \
  --clause "§3.6.8 Orchestration — concurrent pipeline dispatch" \
  --change "RunOrchestrator changed from concurrent to sequential D→G(conditional)→L dispatch." \
  --reason "G-pipe entry gate requires D-pipe ppr_scores before G-pipe can decide whether to activate. Concurrent dispatch is incompatible with this conditional dependency." \
  --analytic-consequence "No impact on metric correctness. Pipeline isolation (C1 disjointness) preserved. L-pipe remains independent. Production re-parallelisation possible post-MVP via async dependency graph."
```

### 3.6 MetricIntegrityGate update (`helios/integrity_gate.py`)

Handle conditional G-pipe row:

- `GPIPE` flag off in manifest → no G-pipe row expected; skip G-pipe `snapshot_hash` check.
- `GPIPE` on but gate did not trigger → sentinel verdict present with `ranked_candidates=[]`; gate passes.
- `GPIPE` on and gate triggered → full verdict expected; validate `ppr_scores` is non-empty.

### 3.7 `ablation_architecture.md §3.2`

Write §3.2 covering: G-pipe architecture, PPR traversal algorithm, entry gate formula, sequential dispatch rationale, deviation entries. Cross-reference §2.6 (UEG-C Builder) and §4 (Orchestration).

**A-H6 sentinel filtering warning (mandatory — include verbatim in §3.2 and §3.7):**

Hypothesis A-H6 evaluates "G-pipe HR@3 ≥ D-pipe HR@3 on incidents where the entry gate fires." When the gate does not fire, `run_gpipe()` returns a sentinel with `hr_at_3=0.00` and `narrative="gpipe-gated-or-skipped"` — this row is written to the result store. Evaluation scripts that naively aggregate G-pipe metrics will contaminate A-H6 with sentinel zeros, making G-pipe appear worse than it is.

**Mandatory evaluation filter for all A-family metric queries on G-pipe results:**
```sql
SELECT AVG(hr_at_3)
FROM result_store
WHERE pipeline = 'gpipe'
  AND narrative != 'gpipe-gated-or-skipped'
```

This filter must appear in: (1) `scripts/evaluate_ablation.py`, (2) the ablation notebook's L2 section, (3) any analysis script that computes G-pipe HR@3 or CpR. Failure to filter produces a methodologically invalid A-H6 result. Document this in `ablation_architecture.md §3.7` and in `hypothesis_variant_metric_mapping.md` next to the A-H6 row.

---

## Calibration Rerun

After structural edge fix, run two calibration scripts in order:

1. **D-pipe stability check:** `poetry run python scripts/calibrate_dpipe.py` — verify LOO-CV HR@3 within ±0.01 of M2 value (0.5333). This script already exists from Milestone 2; it re-uses the existing 20-incident corpus without changes.

2. **G-pipe calibration (new script):** `poetry run python scripts/calibrate_gpipe.py` — see Files Modified. Skeleton:

```python
"""scripts/calibrate_gpipe.py — LOO-CV threshold sweep for G-pipe entry gate."""
import json
from pathlib import Path

from helios.pipelines.g_pipe.gpipe_config import DISAGREEMENT_SWEEP, GPIPE_PPR_ALPHA
from helios.pipelines.g_pipe.pipeline import _ppr_traverse, compute_ppr_disagreement
from helios.schemas.ueg_c import UEGCSnapshot

CALIBRATED_PATH = Path("data/calibrated_params.json")
CAPTURES_DIR = Path("data/captures")
# Load corpus ...
# For each threshold in DISAGREEMENT_SWEEP:
#   LOO-CV: for each incident i, train on {all}\{i}, evaluate on {i}
#   Compute g_hr_at_3 and d_hr_at_3 on held-out set
# Pick threshold maximising g_hr_at_3
# Write to calibrated_params.json:
params = json.loads(CALIBRATED_PATH.read_text())
params.update({
    "gpipe_hr_at_3_held_out": best_g_hr,
    "dpipe_hr_at_3_held_out": held_out_d_hr,
    "gate_passed": best_g_hr >= held_out_d_hr,
    "n_incidents_triggered": n_triggered,
})
CALIBRATED_PATH.write_text(json.dumps(params, indent=2))
```

The sweep logic mirrors `scripts/calibrate_dpipe.py` (LOO-CV pattern). Implement incrementally: start with a single threshold pass, then add the sweep loop.

3. If G-pipe HR@3 ≥ D-pipe HR@3 on held-out: A-H6 entry gate PASSES → freeze value in `gpipe_config.py`.
4. If G-pipe HR@3 < D-pipe HR@3: file deviation with power analysis note (corpus too small).

---

## Exit Gates (Spec 1)

| # | Gate | Evidence artefact |
|---|---|---|
| G1-1 | All structural edge tests pass (root span, cross-service, multi-level, fallback, empty) | `pytest tests/graph/test_ueg_c_builder.py -v` |
| G1-2 | Schema roundtrip green at v0.2 | `pytest tests/test_schema_stability.py -v` |
| G1-3 | Snapshot registry rebuilt — 20 entries, HMAC chain verified | `python bin/log_deviation.py verify` |
| G1-4 | Deviation log: re-capture + schema v0.2 + sequential dispatch (≥3 new entries) | `bin/log_deviation.py verify` |
| G1-5 | LOO-CV HR@3 stability ±0.01 post-recalibration; G-pipe fields written to `calibrated_params.json` | `scripts/calibrate_gpipe.py` output |
| G1-6 | A-H6: G-pipe HR@3 ≥ D-pipe on held-out OR deviation + power analysis | Calibration output |
| G1-7 | Disjointness audit green | `python -m helios.vcl.disjointness` |
| G1-8 | Dynamic coverage: zero line overlap between HELIOS-G and HELIOS-noGraph paths | CI disjointness workflow |
| G1-9 | E2E smoke: HELIOS-G variant runs end-to-end | `pytest tests/test_e2e_smoke.py -k helios_g` |
| G1-10 | PPR determinism: identical ranking on two sequential calls with same input | `pytest tests/pipelines/test_gpipe_pipeline.py::test_determinism` |

---

## Files Modified / Created

| File | Action |
|---|---|
| `bin/run_capture.py` | Add `parent_span_id` column; schema version constant `v2` |
| `helios/graph/ueg_c_builder.py` | `SpanRecord` + `_structural_edges()` rewrite + `build_ueg_c()` update |
| `helios/schemas/verdict.py` | Add `ppr_scores`, `prompt_version`; bump to `schema-draft-v0.2` |
| `helios/pipelines/g_pipe/stub.py` | **Delete** |
| `helios/pipelines/g_pipe/__init__.py` | Update export |
| `helios/pipelines/g_pipe/pipeline.py` | **New** — entry gate + PPR traversal + sentinel |
| `helios/pipelines/g_pipe/gpipe_config.py` | **New** — frozen after calibration |
| `helios/orchestrator/runner.py` | Sequential D→G(conditional)→L dispatch |
| `helios/integrity_gate.py` | Conditional G-pipe row handling |
| `tests/graph/test_ueg_c_builder.py` | 6 new parent_span_id tests |
| `tests/pipelines/test_gpipe_pipeline.py` | **New** — gate boundary, PPR traversal, determinism, sentinel |
| `tests/test_orchestrator_runner.py` | HELIOS-G integration test |
| `tests/test_schema_stability.py` | Update for v0.2 fields |
| `docs/tracking/ablation_architecture.md` | §3.2 written |
| `docs/tracking/helios_mvp_tracking.md` | M3 ENG/GATE rows added |
| `scripts/calibrate_gpipe.py` | **New** — G-pipe LOO-CV threshold sweep; writes `gpipe_hr_at_3_held_out`, `dpipe_hr_at_3_held_out`, `gate_passed`, `n_incidents_triggered` to `data/calibrated_params.json` |
| `data/snapshot_registry.jsonl` | Purge + rebuild after re-capture |
