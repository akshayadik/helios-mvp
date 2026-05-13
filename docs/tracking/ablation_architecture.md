# HELIOS Ablation Architecture — Living ADR

**Document Version:** v0.2
**Date:** 2026-05-13
**Status:** §1 frozen at Stage 0. §2 schemas frozen at Stage 0 (builder sub-sections remain stubs until Stage 3). §3–§6 stubs.
**Canonical Reference:** `docs/memos/spine_freeze_memo_v0.md`
**Update Cadence:** After every pipeline-stage change.

**Rule:** No section may claim implementation details not yet past their stage gate. Cross-references to `spine_freeze_memo_v0.md` are mandatory for all frozen elements.

---

## 1. Variant Control Layer (VCL) + Flag Registry (C1 Core)   [FROZEN — Stage 0]

The **Variant Control Layer (VCL)** is the primary methodological contribution (**C1**) of this dissertation: a runtime-enforced ablation discipline mechanism that guarantees deterministic, auditable, and tamper-evident execution of every experimental variant.

VCL ensures that:
- Every measurement run is tagged with a unique, content-hashed `variant_config_hash`.
- Ablation code paths are provably disjoint (except for explicitly allow-listed shared infrastructure).
- Snapshot identity and metric integrity are enforced at runtime.
- The full ablation matrix is reproducible and pre-registered.

This satisfies the requirements of Design Science Research (DSR) construct validity and the asymmetric inferential rule defined in the OSF protocol.

### 1.1 Design Principles (Binding)

| Principle                  | Enforcement in VCL                                                                 |
|---------------------------|------------------------------------------------------------------------------------|
| Single Source of Truth    | All flags declared in one `VCLManifest` (Pydantic `BaseModel`)                     |
| Deterministic Identity    | `variant_config_hash = SHA-256(canonical_json(manifest))`                         |
| Runtime Enforcement       | `@gated_by(flag)` decorator + `ContextVar` + `GatedComponentInactiveError`        |
| Auditability              | Decorator registration (`__gated_by__`) + static CI + dynamic coverage-diff audit |
| Immutability              | `ConfigDict(frozen=True, extra="forbid")`                                          |
| Reproducibility           | Canonical JSON rules (sorted keys, 6-decimal floats, no whitespace)                |

### 1.2 Flag Registry (`helios/vcl/registry.py`)

**14 binding flags** (12 from proposal Table 12 + `router` + `ingest_mode`):

**Boolean flags (13)** — eligible for `@gated_by`:
- `l2c_llm`, `p4_cognitive`, `mahc`, `cbr`, `l2b_graph`, `acp`, `reconcile`,
- `ueg_c_structural`, `dpipe`, `dpipe_propagation`, `gpipe`, `lpipe`, `router`

**Operational flag (1)**:
- `ingest_mode` ∈ {`"recorded"`, `"live"`} (checked directly, never via decorator)

See full registry and `bool_flags()` / `all_flags()` methods in `helios/vcl/registry.py`.

### 1.3 Configuration Manifest (`helios/vcl/config.py`)

```python
class VCLManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # 13 boolean flags + ingest_mode (see spine_freeze_memo_v0.md §2.1)
    ...

    def compute_variant_config_hash(self) -> str:
        ...
```

Full implementation: `helios/vcl/config.py`. Hash derivation: `helios/vcl/utils.py`.

### 1.4 Gating Mechanism (`helios/vcl/decorators.py`)

```python
@gated_by(VCLFlag.LPIPE)
def run_lpipe(...):
    ...
```

- Decoration-time validation prevents non-boolean flags from being gated.
- `GatedComponentInactiveError` raised when a gated component is invoked with its flag inactive.
  *(Stage 1+ integration: this error will be caught by the metric integrity gate and logged to the exclusion ledger — not yet implemented at Stage 0.)*
- All gated functions register `__gated_by__` for static disjointness audit.

### 1.5 Confirmatory, Conditional Confirmatory & Exploratory Variants (Frozen)

**Full Flag Matrix** — column abbreviations: `l2c` = l2c_llm, `p4c` = p4_cognitive, `l2b` = l2b_graph, `rec` = reconcile, `ueg` = ueg_c_structural, `dpi` = dpipe, `dpp` = dpipe_propagation, `gpi` = gpipe, `lpi` = lpipe, `rtr` = router.

| Variant                | l2c | p4c | mahc | cbr | l2b | acp | rec | ueg | dpi | dpp | gpi | lpi | rtr | Status                   | Hypothesis               |
|------------------------|:---:|:---:|:----:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|--------------------------|--------------------------|
| HELIOS-Full            | T   | T   | T    | T   | T   | T   | T   | T   | T   | T   | T   | T   | T   | Confirmatory             | A-H1, A-H3               |
| HELIOS-noLLM           | F   | T   | T    | T   | T   | T   | T   | T   | T   | T   | T   | F   | T   | Confirmatory             | A-H1                     |
| HELIOS-noGraph         | T   | T   | T    | T   | F   | T   | T   | T   | T   | T   | F   | T   | T   | Exploratory              | — ¹                      |
| HELIOS-D               | F   | T   | F    | F   | F   | F   | F   | T   | T   | T   | F   | F   | F   | Confirmatory             | A-H3                     |
| HELIOS-G               | F   | T   | F    | F   | T   | F   | F   | T   | T   | F   | T   | F   | F   | Conditional Confirmatory | A-H6 (entry-gate)        |
| HELIOS-noConsensus     | T   | T   | F    | T   | T   | T   | T   | T   | T   | T   | T   | T   | T   | Exploratory              | A-H4                     |
| HELIOS-noRouter        | T   | T   | T    | T   | T   | T   | T   | T   | T   | T   | T   | T   | F   | Exploratory              | A-H5                     |
| HELIOS-noStructural    | T   | T   | T    | T   | T   | T   | T   | F   | T   | T   | T   | T   | T   | Exploratory              | A-H8                     |

*Derived from `spine_freeze_memo_v0.md §2.2` (canonical source). Frozen variant hashes in `spine_freeze_memo_v0.md §2.3`.*

¹ HELIOS-noGraph is exploratory with no dedicated pre-registered hypothesis in the MVP confirmatory family. It serves as a supporting ablation for graph-related sensitivity analysis.

**Frozen Variant Hashes:** See `spine_freeze_memo_v0.md §2.3` — authoritative table with VCL Freeze SHA provenance.

### 1.6 Integration Points

- **Orchestrator** *(Stage 1+)*: `variant = get_variant(name); set_current_manifest(variant)` — not yet implemented.
- **Telemetry & Pipelines**: Every consumer calls `get_current_manifest()` and records consumed `snapshot_hash`.
- **Metric Integrity Gate** *(Stage 1+)*: Verifies matching `variant_config_hash` + `snapshot_hash` across all active pipelines.
- **Disjointness Audit** *(Stage 7)*: Static (CI) + dynamic (`coverage.py` ON/OFF diffs) — both driven by decorator registration.

---

**Traceability Note**
This section directly implements MVP Execution Plan §4 (Architecture) and §6 (C1 Discipline Specifications). The spine is frozen in `docs/memos/spine_freeze_memo_v0.md`.

---

## 2. L0-L3 Canonical Data Contracts   [SCHEMAS FROZEN — Stage 0 | Builder STUB — Stage 3]

Canonical schemas for all pipeline-crossing message types are frozen at `schema-draft-v0.1` (2026-05-13).
All models enforce `extra="forbid"` and `frozen=True` (Pydantic v2). Hash identity uses
`SHA-256(canonical_json(model.model_dump()))` where `canonical_json` sorts keys, rounds floats
to 6 decimal places, and emits no whitespace.

### 2.1 UEG-C Node Taxonomy (`helios/schemas/ueg_c.py`)   [FROZEN — Stage 0]

| NodeType value | Meaning | Used in |
|---|---|---|
| `service` | Microservice-level entity | D-pipe, G-pipe |
| `operation` | RPC/HTTP operation on a service | G-pipe edge endpoints |
| `pod` | Kubernetes pod instance | D-pipe anomaly source |
| `database` | Persistent store (SQL, Redis, etc.) | G-pipe causal paths |
| `external` | Third-party or out-of-mesh dependency | G-pipe boundary nodes |

### 2.2 UEG-C Edge Taxonomy (`helios/schemas/ueg_c.py`)   [FROZEN — Stage 0]

| EdgeType value | Meaning | Gated by flag |
|---|---|---|
| `structural` | Topology edge from K8s/service mesh config | `ueg_c_structural` |
| `call` | Observed RPC call (trace-derived) | `l2b_graph` |
| `metric` | Metric-correlation edge (D-pipe output) | `dpipe` |
| `log` | Log co-occurrence edge | `l2b_graph` |

`weight: float` is constrained to `[0, 1]`. Structural edges are enabled only when
`VCLFlag.UEG_C_STRUCTURAL` is active, maintaining the ablation boundary between
topology-aware and topology-agnostic graph variants.

### 2.3 UEGCSnapshot Contract (`helios/schemas/ueg_c.py`)   [FROZEN — Stage 0]

| Field | Type | Required | Notes |
|---|---|---|---|
| `incident_id` | `str` | Yes | Links to fault event |
| `variant_config_hash` | `str` (64-char hex) | Yes | VCLManifest identity |
| `nodes` | `list[UEGCNode]` | Yes | May be empty list |
| `edges` | `list[UEGCEdge]` | Yes | May be empty list |
| `captured_at_iso` | `str` (ISO 8601 UTC) | Yes | Capture timestamp |
| `schema_version` | `str` | Default `schema-draft-v0.1` | Bumped at OSF Stage 5 freeze |

`compute_snapshot_hash()` produces a SHA-256 snapshot identity used by `PipelineVerdict.snapshot_hash`
for deduplication and C1 run-level inclusion (§5.1). The snapshot itself does **not** store its own
hash (avoids circular dependency); callers inject the result into verdict rows.

### 2.4 PipelineVerdict Field Manifest (`helios/schemas/verdict.py`)   [FROZEN — Stage 0]

Per-pipeline result row for dpipe, gpipe, and lpipe. All fields required by the metric integrity gate
and result store (`helios/store/schema.sql`).

| Field | Type | Constraint | Notes |
|---|---|---|---|
| `run_id` | `str` | PK | Unique run identifier |
| `incident_id` | `str` | FK to snapshot | Links verdict to incident |
| `variant_config_hash` | `str` (64-char hex) | C1 invariant | Must match active manifest |
| `snapshot_hash` | `str` (64-char hex) | C1 invariant | SHA-256 of UEGCSnapshot |
| `pipeline` | `str` | `dpipe | gpipe | lpipe` | Source pipeline label |
| `evaluation_phase` | `EvaluationPhase` | Enum | `exploratory` or `confirmatory` |
| `ranked_candidates` | `list[str]` | Ordered | Top-k service names (HR@3 source) |
| `hr_at_3` | `float` | `[0, 1]` | Hit-Rate@3 |
| `cpr` | `float` | `[0, 1]` | Causal Precision-Recall |
| `latency_ms` | `float` | `>= 0` | Pipeline wall-clock latency |
| `token_count` | `int` | `>= 0` | LLM tokens consumed (L-pipe) or 0 |
| `narrative` | `str` | Non-empty | Chain of Explanation (CoE) text |
| `schema_version` | `str` | Default `schema-draft-v0.1` | Bumped at OSF Stage 5 freeze |

`compute_verdict_hash()` produces a SHA-256 row identity for deduplication and audit.

### 2.5 TelemetryWindow Contract (`helios/schemas/telemetry.py`)   [FROZEN — Stage 0]

L0 5-minute multi-modal observability window. Captures the P1-P5 stream paths and gates the
two-environment firewall (§1.4) via `evaluation_phase`.

| Field | Type | Required | Notes |
|---|---|---|---|
| `incident_id` | `str` | Yes | Fault event identity |
| `variant_config_hash` | `str` (64-char hex) | Yes | VCLManifest identity |
| `window_start_iso` | `str` (ISO 8601 UTC) | Yes | Window open timestamp |
| `window_end_iso` | `str` (ISO 8601 UTC) | Yes | Window close timestamp |
| `evaluation_phase` | `EvaluationPhase` | Yes | `exploratory` or `confirmatory` |
| `p1_metrics_path` | `str \| None` | Optional | Prometheus metrics Parquet |
| `p2_traces_path` | `str \| None` | Optional | OTEL traces Parquet |
| `p3_logs_path` | `str \| None` | Optional | Structured logs Parquet |
| `p4_events_path` | `str \| None` | Optional | K8s events Parquet |
| `p5_profiles_path` | `str \| None` | Optional | Profiling data Parquet |
| `schema_version` | `str` | Default `schema-draft-v0.1` | Bumped at OSF Stage 5 freeze |

Path fields are `None` when a stream is not captured in the current environment (e.g., no profiler in OTEL Demo).

### 2.6 UEG-C Builder   [STUB — Stage 3]

> **Not yet implemented.** Graph construction algorithm (Alg 5 in proposal), incremental update,
> pruned-subgraph generation, and snapshot registry will be written and frozen at the Stage 3 gate.
> Cross-reference: `spine_freeze_memo_v0.md` (canonical) + `docs/tracking/snapshot_integrity_tracking.md`.

---

## 3. Peer Pipelines (D-pipe, G-pipe, L-pipe)   [STUB — Stages 2–5]

> **Not yet implemented.** This section will be written and frozen incrementally: Stage 2 (D-pipe), Stage 4 (G-pipe), Stage 5 (L-pipe).
> No implementation claims may be added before the respective gate passes.
> Cross-reference: `spine_freeze_memo_v0.md` (canonical) + `docs/tracking/hypothesis_variant_metric_mapping.md`.

---

## 4. Consensus & Routing Layer   [STUB — Stage 6]

> **Not yet implemented.** This section will be written and frozen at the Stage 6 gate.
> No implementation claims may be added before that gate passes.
> Cross-reference: `spine_freeze_memo_v0.md` (canonical).

---

## 5. Snapshot Gating, Metric Integrity Gate & Evaluation Plane   [STUB — Stage 1 & 6]

> **Not yet implemented.** Snapshot gating scaffolding is targeted for Stage 1; full evaluation plane at Stage 6.
> No implementation claims may be added before the respective gate passes.
> Cross-reference: `spine_freeze_memo_v0.md §3` (Research Progress Tracking).

---

## 6. Schema Evolution, Disjointness Audit & C1 Evidence   [STUB — Stage 7]

> **Not yet implemented.** This section will be written and frozen at the Stage 7 gate, consolidating the full C1 audit trail.
> No implementation claims may be added before that gate passes.
> Cross-reference: `spine_freeze_memo_v0.md` (canonical) + `deviation_log.jsonl` (HMAC chain).

---

**Document History**
- v0.1 (2026-05-12): §1 (VCL/C1) written and frozen at Stage 0. §2–§6 stubs added.
- v0.2 (2026-05-13): §2.1–§2.4 schema tables written and frozen (schema-draft-v0.1). Builder stubs remain.
