# HELIOS Ablation Architecture — Living ADR

**Document Version:** v0.4
**Date:** 2026-05-14
**Status:** §1 frozen at Stage 0. §2 schemas frozen at Stage 0 (builder sub-sections remain stubs until Stage 3). §3.0 frozen at Stage 0 (registry + stubs). §3.1–§3.3 stubs. §4 frozen at Milestone 1. §5–§7 stubs.
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

- **Orchestrator** *(Milestone 1)*: `variant = get_variant(name); set_current_manifest(variant)` — `RunOrchestrator` in `helios/orchestrator/runner.py` (see §4).
- **Telemetry & Pipelines**: Every consumer calls `get_current_manifest()` and records consumed `snapshot_hash`.
- **Metric Integrity Gate** *(Milestone 1)*: Verifies matching `variant_config_hash` + `snapshot_hash` across all active pipelines.
- **Disjointness Audit** *(Milestone 1)*: Static (CI) + dynamic (`coverage.py` ON/OFF diffs) — both driven by decorator registration (see §4, §7).

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

## 3. Peer Pipelines (D-pipe, G-pipe, L-pipe)   [§3.0 FROZEN — Stage 0 | §3.1–§3.3 STUB — Stages 1–5]

### 3.0 Stage 0 Pipeline Foundation   [FROZEN — Stage 0]

Stage 0 establishes two gate-level artefacts that pipeline stages 1–5 will consume without modification:
the **SnapshotRegistry** (L2 analysis identity gate) and **gated null stubs** for G-pipe and L-pipe.
D-pipe has no stub; it is the first non-trivial implementation target (Stage 1).

#### Ingest-to-Analysis Flow (as of Stage 0)

```
L0  CaptureReader       helios/telemetry/reader.py
      │  TelemetryWindow Parquets (5 recordings, schema-validated)
      │
      ▼  [D-pipe gap — Stage 1]
      ·  Statistical anomaly detection → UEGCSnapshot construction (not yet built)
      │
      ▼
L2  SnapshotRegistry    helios/vcl/snapshot_registry.py
      │  Content-addressable JSONL; snapshot_hash must be registered before any pipeline run
      │
      ▼
    Pipeline dispatch   helios/pipelines/{g,l}_pipe/stub.py
      │  G-pipe (Stage 4) + L-pipe (Stage 5) — gated null stubs at Stage 0
```

`CaptureReader` guards **L0 data integrity** (telemetry recording hash round-trip).
`SnapshotRegistry` guards **L2 analysis integrity** (UEGCSnapshot identity before pipeline invocation).
These are complementary layers; the Stage 1 D-pipe bridges the gap between them.

#### SnapshotRegistry (`helios/vcl/snapshot_registry.py`)   [FROZEN — Stage 0]

Content-addressable, append-only JSONL mapping `snapshot_hash → (variant_config_hash, registered_at)`.
SHA-256 identity is proved by hash content — no HMAC chain (unlike the deviation log).

| Method | Behaviour |
|---|---|
| `register(snapshot_hash, variant_config_hash)` | Appends entry; raises `DuplicateSnapshotError` if hash already registered |
| `contains(snapshot_hash)` | O(n) scan; returns `True` if hash present |
| `all_hashes()` | Returns all hashes in insertion order |
| `verify()` | Raises `DuplicateSnapshotError` on any duplicate — called at pipeline entry |

Both `snapshot_hash` and `variant_config_hash` must be 64-character lowercase hex; `_validate_hex64`
enforces this at `register()` time, preventing malformed entries from contaminating the registry.

The registry is a **pre-condition gate** for all three peer pipelines: every `run_{d,g,l}pipe` call must
pass a `snapshot_hash` that `SnapshotRegistry.contains()` returns `True` for. This enforcement is
wired in the Stage 1 metric integrity gate (not yet implemented); the Stage 0 E2E smoke test
exercises the registry in isolation via direct `register()` + `verify()` calls.

#### Pipeline Null Stubs   [FROZEN — Stage 0]

G-pipe and L-pipe are implemented as gated null stubs. Each stub:
- Is decorated with `@gated_by(VCLFlag.X)` — raises `GatedComponentInactiveError` when invoked
  with the controlling flag inactive (e.g., in `HELIOS-noLLM`, `lpipe=False` blocks `run_lpipe`)
- Returns a sentinel `PipelineVerdict`-shaped dict (empty `ranked_candidates`, narrative `"stub"`)
  when the flag is active — preserving the E2E smoke contract without real computation
- Records `variant_config_hash` from the active `VCLManifest` via `get_current_manifest()`

| Stub | Path | Gated by | Implemented at |
|---|---|---|---|
| `run_gpipe` | `helios/pipelines/g_pipe/stub.py` | `VCLFlag.L2B_GRAPH` | Stage 4 |
| `run_lpipe` | `helios/pipelines/l_pipe/stub.py` | `VCLFlag.L2C_LLM` | Stage 5 |

D-pipe (`dpipe` flag) has no stub. It is the first non-trivial pipeline (Stage 1): statistical anomaly
detection on `TelemetryWindow` Parquets → `UEGCSnapshot` hash computation → `SnapshotRegistry.register()`.
Until Stage 1, D-pipe runs are simulated in the E2E smoke test via a synthetic snapshot fixture.

*Traceability: EG4 smoke test (`tests/test_e2e_smoke.py`) validates the full Stage 0 flow — manifest set,
synthetic snapshot registered, both stubs invoked, `PipelineVerdict` row inserted into DuckDB result store.*

---

### 3.1 D-pipe — Statistical Anomaly Detection   [STUB — Stage 1]

> **Not yet implemented.** D-pipe will be written and frozen at the Stage 1 gate.
> Responsibility: ingest `TelemetryWindow` Parquets → detect anomalies → produce `UEGCSnapshot` →
> register `snapshot_hash` in `SnapshotRegistry`. This bridges the L0→L2 gap shown in §3.0.
> Cross-reference: `spine_freeze_memo_v0.md` + `docs/tracking/hypothesis_variant_metric_mapping.md` (A-H3).

---

### 3.2 G-pipe — Graph Causal Inference   [STUB — Stage 4]

> **Not yet implemented.** G-pipe will be written and frozen at the Stage 4 gate.
> Responsibility: consume registered `UEGCSnapshot` → graph-based causal ranking → `PipelineVerdict`.
> Gated by `VCLFlag.L2B_GRAPH`; ablation variant `HELIOS-noGraph` disables this path.
> Cross-reference: `spine_freeze_memo_v0.md` + `docs/tracking/hypothesis_variant_metric_mapping.md` (A-H6).

---

### 3.3 L-pipe — LLM Explanation   [STUB — Stage 5]

> **Not yet implemented.** L-pipe will be written and frozen at the Stage 5 gate.
> Responsibility: consume `PipelineVerdict` from D/G-pipe → generate Chain of Explanation (CoE) narrative.
> Gated by `VCLFlag.L2C_LLM`; ablation variant `HELIOS-noLLM` disables this path.
> Cross-reference: `spine_freeze_memo_v0.md` + `docs/tracking/hypothesis_variant_metric_mapping.md` (A-H1).

---

## 4. Orchestration & C1 Enforcement   [FROZEN — Milestone 1]

### 4.0 Orchestrator Flow

`helios run` (`bin/helios_run.py`) is the single entry point for corpus runs.
It wires the following C1 path for each incident:

```
CorpusLoader → CaptureReader (L0 hash verify) → SnapshotRegistry (L2 register)
  → run_dpipe + run_gpipe + run_lpipe (three-pipeline dispatch)
  → MetricIntegrityGate.check_consistency()
  → ResultStore.insert() ×3 (PASS) / ExclusionLedger.append() (FAIL)
  → ReconciliationLedger.record(outcome)
```

### 4.1 C1 Sub-artefact Status (Milestone 1)

| Sub-artefact | Module | Stage frozen |
|---|---|---|
| VCL (variant control layer) | `helios/vcl/` | Stage 0 |
| Deviation log (HMAC-chained) | `bin/log_deviation.py` | Stage 0 |
| SnapshotRegistry (L2 guard) | `helios/vcl/snapshot_registry.py` | Stage 0 |
| MetricIntegrityGate | `helios/integrity_gate.py` | Milestone 1 |
| ExclusionLedger | `bin/log_exclusion.py` | Milestone 1 |
| ReconciliationLedger | `helios/orchestrator/ledger.py` | Milestone 1 |
| DisjointnessAuditor | `helios/vcl/disjointness.py` | Milestone 1 |

### 4.2 Schema Freeze (Milestone 1)

All three schemas tagged `schema-draft-v0.1`. CI round-trip enforcement:
`tests/test_schema_roundtrip.py` serializes → deserializes → hash-compares
all three schemas on every push. Any field addition breaks the test.

- `TelemetryWindow` — L0 window with `compute_window_hash()`
- `UEGCSnapshot` — L1/L2 graph snapshot with `compute_snapshot_hash()`;
  `UEGCEdge.edge_class` is a computed field auto-derived from `edge_type` (semantic layer)
- `PipelineVerdict` — L2/L3 result row with `compute_verdict_hash()`

---

## 5. Consensus & Routing Layer   [STUB — Stage 6]

> **Not yet implemented.** This section will be written and frozen at the Stage 6 gate.
> No implementation claims may be added before that gate passes.
> Cross-reference: `spine_freeze_memo_v0.md` (canonical).

---

## 6. Snapshot Gating, Metric Integrity Gate & Evaluation Plane   [STUB — Stage 1 & 6]

> **Not yet implemented.** Snapshot gating scaffolding is targeted for Stage 1; full evaluation plane at Stage 6.
> No implementation claims may be added before the respective gate passes.
> Cross-reference: `spine_freeze_memo_v0.md §3` (Research Progress Tracking).

---

## 7. Schema Evolution, Disjointness Audit & C1 Evidence   [STUB — Stage 7]

> **Not yet implemented.** This section will be written and frozen at the Stage 7 gate, consolidating the full C1 audit trail.
> No implementation claims may be added before that gate passes.
> Cross-reference: `spine_freeze_memo_v0.md` (canonical) + `deviation_log.jsonl` (HMAC chain).

---

**Document History**
- v0.1 (2026-05-12): §1 (VCL/C1) written and frozen at Stage 0. §2–§6 stubs added.
- v0.2 (2026-05-13): §2.1–§2.4 schema tables written and frozen (schema-draft-v0.1). Builder stubs remain.
- v0.3 (2026-05-14): §3.0 written and frozen (Stage 0). SnapshotRegistry, G/L-pipe stubs, ingest-to-analysis flow. §3.1–§3.3 sub-stubs added for D/G/L-pipe.
- v0.4 (2026-05-14): §4 written and frozen (Milestone 1). Orchestration flow, C1 sub-artefact status table, schema freeze summary. Old §4–§6 renumbered to §5–§7. §1.6 integration points updated.
