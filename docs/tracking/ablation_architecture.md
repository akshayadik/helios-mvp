# HELIOS Ablation Architecture — Living ADR

**Document Version:** v0.6
**Date:** 2026-05-19
**Status:** §1 frozen at Stage 0. §2 schemas frozen at Stage 0; §2.6 UEG-C Builder implemented and frozen at Milestone 2. §3.0 frozen at Stage 0 (registry + stubs). §3.1 D-pipe implemented and frozen at Milestone 2. §3.2 G-pipe implemented and frozen at Milestone 3. §3.3 stub. §4 frozen at Milestone 1. §5–§7 stubs.
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

## 2. L0-L3 Canonical Data Contracts   [SCHEMAS FROZEN — Stage 0 | Builder IMPLEMENTED — Milestone 2]

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

### 2.6 UEG-C Builder   [IMPLEMENTED — Milestone 2]

Graph construction is implemented in `helios/graph/ueg_c_builder.py` (`build_ueg_c()`) and the K-hop PPR pruner in `helios/graph/ppr_pruner.py` (`prune_graph()`). Frozen at Milestone 2 (SHA `1b5fd30`; PPR fix SHA `d0e8576`).

#### Edge Construction (`build_ueg_c`)

Edges are derived from OTEL traces Parquet (`p2_traces_path`) using **temporal containment**:
- **STRUCTURAL edge** (`ueg_c_structural` flag): span A contains span B's time window → A structurally calls B. Weight = 1 (binary topology signal).
- **CALL edge** (`l2b_graph` flag): span A contains span B and both share the same trace → A calls B in observed traffic. Weight = call-proportion (normalised by span count).

Both edge types are gated independently — `HELIOS-noStructural` (flag `ueg_c_structural=False`) runs with CALL-only edges, removing topology from PPR seeding.

*Deviation §2.2 (sig `5655ff9fbeeabfaf`): `parent_span_id` is absent from the Parquet schema; temporal containment is the only available heuristic. Misattribution risk bounded to deeply nested same-service call stacks. Pre-M3 gate requires replacement with `parent_span_id` linkage.*

#### K-hop PPR Pruner (`prune_graph`)

Personalized PageRank (alpha=0.85) seeded from structural entry points identifies low-relevance nodes for removal.

**Entry-point detection rule (Milestone 2 fix, SHA `d0e8576`):**
- Entry point = `structural_in_degree == 0` AND `out_degree > 0`
- Isolated nodes with no outgoing edges (async Kafka consumers: `accounting`, `fraud-detection`) are excluded — seeding from them forces uniform-PageRank fallback
- Hub fallback: if no valid structural root exists (e.g., graph has only CALL edges), seed from the highest out-degree node

Nodes with PPR score below `PRUNER_THRESHOLD = 0.02` are removed from the snapshot before D-pipe / G-pipe dispatch.

**Gate values (calibrated on 15-incident OTEL demo corpus):**

| Parameter | Value | Calibration source |
|---|---|---|
| PPR restart probability (alpha) | 0.85 | Spec §2.4; not data-derived |
| `PRUNER_THRESHOLD` | 0.02 | OTEL 15-incident corpus; removes isolated islands while retaining active path |
| `PRUNER_EFFICACY_GATE` | 0.20 | Observed min 0.214 (3/14 pruned on sparse captures); deviation §2.4-gate-2 |
| `INTEGRITY_RATE_GATE` | 0.40 | Observed min 0.429 (s0-cart-001); efficacy/integrity incompatible on 14-node graph; deviation §2.4-gate-2 |

*Deviation §2.4-gate (sig `766ee8e1fc60`): efficacy gate lowered 0.50→0.25; threshold raised 0.01→0.02; entry-point bug fixed.*  
*Deviation §2.4-gate-2 (sig `1737fc5b33ab`): efficacy gate further lowered 0.25→0.20; integrity gate lowered 0.85→0.40; both gates incompatible on a 14-node graph at 20%+ efficacy.*

Cross-reference: `docs/tracking/calibration_thresholds.md` (frozen values) + `spine_freeze_memo_v0.md`.

---

## 3. Peer Pipelines (D-pipe, G-pipe, L-pipe)   [§3.0 FROZEN — Stage 0 | §3.1 IMPLEMENTED — Milestone 2 | §3.2 IMPLEMENTED — Milestone 3 | §3.3 STUB — Stage 5]

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

### 3.1 D-pipe — Statistical Anomaly Detection   [IMPLEMENTED — Milestone 2]

D-pipe is a four-stage statistical anomaly detection pipeline frozen at Milestone 2. Entry point: `helios/pipelines/d_pipe/pipeline.py::run_dpipe()`, gated by `VCLFlag.DPIPE`. Calibrated parameters frozen in `helios/pipelines/d_pipe/dpipe_config.py`.

#### Pipeline Stages

| Stage | Module | Responsibility | Key algorithm |
|---|---|---|---|
| A | `a_metrics_parser.py` | Ingest Prometheus metrics Parquet; compute wm90 (weighted 90th-percentile latency) and error rate per service | Histogram bin interpolation over `LE_BOUNDARIES` |
| B | `b_anomaly_scorer.py` | Score each service on latency + error rate deviation from baseline | Pearson/Spearman correlation + `w_error`-weighted composite |
| C | `c_propagation_engine.py` | Propagate anomaly scores along CALL edges using `rho_threshold` damping | Breadth-first edge traversal with topology boost (`topology_boost_factor`) |
| D | `d_verdict.py` | Rank services; produce `PipelineVerdict` with `ranked_candidates`, `hr_at_3`, `cpr` | Descending score sort; top-3 extraction |

**Gating:** Stage C propagation is independently gated by `VCLFlag.DPIPE_PROPAGATION`. When `dpipe_propagation=False` (e.g., ablation study), propagation is skipped and raw Stage B scores are ranked directly.

#### Calibrated Parameters (Milestone 2)

Calibrated via LOO-CV on the 15-incident OTEL Demo exploratory corpus (250-cell joint grid: 5×5×10).

| Parameter | Frozen value | Grid searched over |
|---|---|---|
| `w_error` | 0.30 | {0.3, 0.50, 0.6, 0.7, 0.9} |
| `rho_threshold` | 0.20 | {0.2, 0.4, 0.6, 0.7, 0.8} |
| `topology_boost_factor` | 1.00 | {1.00, 1.2, 1.4, 1.6, 1.8, 2.00, 2.2, 2.4, 2.6, 2.8} |

LOO-CV HR@3 = 0.5333; in-sample HR@3 = 0.5333 (no optimism gap on this corpus size).
LOO-CV gate threshold: HR@3 ≥ 0.25. Deviation §4.2 filed for smoke gate tie on rcf hold-out.

Cross-reference: `docs/tracking/calibration_thresholds.md` (frozen parameter table) + `docs/tracking/hypothesis_variant_metric_mapping.md` (A-H3, HELIOS-D variant).

---

### 3.2 G-pipe — Conditional PPR-Traversal Peer Pipeline   [IMPLEMENTED — Milestone 3]

**Architecture:** G-pipe activates when D-pipe PPR disagreement exceeds
DISAGREEMENT_THRESHOLD (calibrated via LOO-CV). It re-runs Personalised PageRank on
the UEG-C snapshot using D-pipe scores as seed weights, producing an alternative
ranked candidate list.

**Entry gate formula:**
```
disagreement = ppr_scores_sorted[rank_2] / ppr_scores_sorted[rank_0]
gate_fires   = disagreement >= DISAGREEMENT_THRESHOLD
```

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

```sql
WHERE pipeline = 'gpipe' AND narrative != 'gpipe-gated-or-skipped'
```

Failure to filter produces a methodologically invalid A-H6 result. This filter is
baked into `analysis_plan.json` (A-H6 filter field) and must appear in
`scripts/evaluate_ablation.py` and the ablation notebook L2 section.

**Calibrated parameters (Milestone 3):**

| Parameter | Value | Calibration source |
|---|---|---|
| `DISAGREEMENT_THRESHOLD` | 0.20 | LOO-CV sweep on 20-incident corpus; lowered from 0.30 |
| `GPIPE_PPR_ALPHA` | 0.85 | Matches D-pipe PPR alpha; not re-calibrated |

LOO-CV result: G-pipe HR@3 = 0.60, D-pipe HR@3 = 0.40 on gate-firing incidents — A-H6 PASS signal (exploratory; confirmatory requires AIOpsLab Stage 6 data).

**Cross-references:** §2.6 (UEG-C Builder), §4 (Orchestration), §5 (Verdicts).
Deviation log entries: schema v0.2 re-capture, sequential dispatch.

Implementation: `helios/pipelines/g_pipe/pipeline.py`. Config: `helios/pipelines/g_pipe/gpipe_config.py`.

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

## 5. Consensus & Routing Layer   [DESIGN FROZEN — Milestone 4]

**Decision:** `UniformBordaConsensus` is the sole fusion algorithm for the OTEL exploratory run.
The `fusion_algorithm` field in `ConsensusVerdict` is an immutable tamper-anchor; any post-freeze
change requires a deviation log entry.

**Variants and passthrough:** Variants with the consensus flag disabled (e.g., `HELIOS-noConsensus`)
route through `PassthroughConsensus`, which propagates the top-ranked `PipelineVerdict` directly.
The `ConsensusVerdict.fusion_algorithm` is set to `"passthrough"` in this case.

**AST fingerprint:** `FUSION_ALGORITHM_SHA` is computed at module import via `ast.dump(ast.parse(source))`
with docstrings stripped. It is stored in every `ConsensusVerdict` row and verified by
`ConsensusIntegrityGate` before any row is written.

**Schema version:** `schema-draft-v0.3` adds the `consensus_verdict` table.
`result_row` (schema-draft-v0.2) is unchanged; the two schemas coexist in the same DuckDB file.

**Two-environment firewall:** All M4 runs use the OTEL Demo corpus (exploratory).
AIOpsLab corpus runs (confirmatory, Phase 2) must never share a DuckDB file with OTEL results.

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
- v0.5 (2026-05-18): §2.6 UEG-C Builder written and frozen (Milestone 2) — edge construction algorithm, PPR pruner, entry-point detection fix, gate values. §3.1 D-pipe written and frozen (Milestone 2) — four-stage pipeline, calibrated parameters, LOO-CV results.
- v0.6 (2026-05-19): §3.2 G-pipe written and frozen (Milestone 3) — conditional PPR-traversal pipeline, disagreement gate, sequential dispatch rationale, sentinel filter mandate, calibrated parameters.
