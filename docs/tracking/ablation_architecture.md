# HELIOS Ablation Architecture — Living ADR

**Document Version:** v0.11
**Date:** 2026-10-26
**Status:** §1 frozen at Stage 0; flag and variant names synced to the D2 registry (2026-10-23, deviation entry 31). §2 schemas frozen at Stage 0; §2.6 UEG-C Builder implemented and frozen at Milestone 2. §3.0 frozen at Stage 0 (registry + stubs). §3.1 D-pipe implemented and frozen at Milestone 2. §3.2 G-pipe implemented and frozen at Milestone 3. §3.3 L-pipe implemented and frozen at Milestone 3. §4 frozen at Milestone 1. §5 Consensus design frozen at Milestone 4. §6–§7 stubs. UEG-C (§2.1–§2.3, §2.6) at schema-draft-v0.2 since S1.5; pruner replaced by Algorithm 5 in S1.7 (§2.6).
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

**17 flags** (owner decision D2, 2026-10-23, deviation entry 31): 13 Chapter 3 flags, 3 implementation flags and `ingest_mode`.

**Boolean flags (16)** — eligible for `@gated_by`; iterate them with `VCLFlag.bool_flags()`:

| Flag | Component | OFF means |
|---|---|---|
| `l2c_llm` | L-pipe (multi-agent LLM reasoning) | no L-pipe (HELIOS-noLLM) |
| `p4_cognitive` | Cognitive telemetry visible to the L-pipe | HELIOS-noCogni |
| `mahc_hierarchical` | MAHC consensus | vote-only fusion (HELIOS-noConsensus) |
| `cbr_routing` | Cost-based router (ORAR) | uniform routing (HELIOS-noRouter) |
| `l2b_graph` | UEG-C graph construction feeding the G-pipe | no graph |
| `acp_stateful` | Action-Class Predictor | uniform prior (HELIOS-noACP) |
| `reconcile_terminal` | Two-stage reward reconciliation | HELIOS-noReconcile |
| `fgsv_ks_gate` | Shadow validation behind the KS fidelity gate | HELIOS-noFGSV |
| `iol_self_telemetry` | HELIOS self-telemetry (tenant=self) | HELIOS-noIOL |
| `coe_narrative` | Chain-of-Evidence narrative | ranked list only (HELIOS-noExpl) |
| `his_tier` | Design-committed hardware isolation | HIS-3 (HELIOS-HIS3) |
| `sampling_regime_tag` | Tiered adaptive sampling and its covariate | not switched off by any of the 15 variants |
| `ueg_structural` | Typed structural edges, subgraph-aware training, ARS nodes | HELIOS-noStructural |
| `dpipe` | D-pipe entry point (implementation flag) | no D-pipe |
| `dpipe_propagation` | D-pipe graph propagation stage (implementation flag) | D-pipe without propagation |
| `gpipe` | G-pipe entry point (implementation flag) | no G-pipe |

The first 13 are the Chapter 3 flags (twelve on pp. 137–138, plus `ueg_structural`, p. 142). The May 2026 names `mahc`, `cbr`, `router`, `acp`, `reconcile`, `ueg_c_structural` and `lpipe` no longer exist: `cbr_routing` is the router, and the L-pipe is gated by `l2c_llm`.

**Operational flag (1)**:
- `ingest_mode` ∈ {`"recorded"`, `"live"`} (checked directly, never via decorator)

See full registry and `bool_flags()` / `all_flags()` methods in `helios/vcl/registry.py`.

### 1.3 Configuration Manifest (`helios/vcl/config.py`)

```python
class VCLManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # 16 boolean flags + ingest_mode (D2 registry, deviation entry 31)
    ...

    def compute_variant_config_hash(self) -> str:
        ...
```

Full implementation: `helios/vcl/config.py`. Hash derivation: `helios/vcl/utils.py`.

### 1.4 Gating Mechanism (`helios/vcl/decorators.py`)

```python
@gated_by(VCLFlag.L2C_LLM)
def run_lpipe(...):
    ...
```

- Decoration-time validation prevents non-boolean flags from being gated.
- `GatedComponentInactiveError` raised when a gated component is invoked with its flag inactive.
  *(Stage 1+ integration: this error will be caught by the metric integrity gate and logged to the exclusion ledger — not yet implemented at Stage 0.)*
- All gated functions register `__gated_by__` for static disjointness audit.

### 1.5 Confirmatory and Exploratory Variants

Regenerated 2026-10-24 from `helios/vcl/variants.py` (owner decision D2, deviation entry 31): 16 boolean flags, 8 confirmatory and 7 exploratory variants. Each variant is HELIOS-Full with the listed flags switched off. The May 2026 13-flag table (`router`, `lpipe`, `ueg_c_structural`, HELIOS-noGraph) is superseded; flag names follow `helios/vcl/registry.py`.

| Variant | Flags off (vs HELIOS-Full) | Status | Hypothesis | Hash (first 12) |
|---|---|---|---|---|
| HELIOS-Full | all 16 boolean flags on | Confirmatory | A-H1, A-H2, A-H3, A-H4, A-H5, A-H6, A-H7, A-H8, B-H1..B-H8 | `5382fafae6db` |
| HELIOS-noLLM | `l2c_llm` | Confirmatory | A-H1, A-H7 | `7f82c31138c7` |
| HELIOS-LLM-only | `acp_stateful`, `cbr_routing`, `dpipe`, `dpipe_propagation`, `gpipe`, `l2b_graph`, `mahc_hierarchical`, `reconcile_terminal` | Confirmatory | A-H2 | `b16c8aa62dfa` |
| HELIOS-D | `acp_stateful`, `cbr_routing`, `gpipe`, `l2b_graph`, `l2c_llm`, `mahc_hierarchical`, `reconcile_terminal` | Confirmatory | A-H3 | `794a1bab0b82` |
| HELIOS-noConsensus | `mahc_hierarchical` | Confirmatory | A-H4 | `40360d2e8e84` |
| HELIOS-noRouter | `cbr_routing` | Confirmatory | A-H5, E-H2 | `69a0ed936c92` |
| HELIOS-G | `acp_stateful`, `cbr_routing`, `dpipe_propagation`, `l2c_llm`, `mahc_hierarchical`, `reconcile_terminal` | Confirmatory | A-H6 | `7b3c08e169c2` |
| HELIOS-noStructural | `ueg_structural` | Confirmatory | A-H8, E-H10 | `a6a64740c315` |
| HELIOS-noCogni | `p4_cognitive` | Exploratory | E-H1 | `77393185f21c` |
| HELIOS-noACP | `acp_stateful` | Exploratory | E-H8 (E-H3 retired) | `2f4866e6e670` |
| HELIOS-noReconcile | `reconcile_terminal` | Exploratory | E-H5 | `003940202112` |
| HELIOS-HIS3 | `his_tier` | Exploratory | E-H9 | `b6f325139863` |
| HELIOS-noFGSV | `fgsv_ks_gate` | Exploratory | E-H4 | `4b7d1c9aa21f` |
| HELIOS-noIOL | `iol_self_telemetry` | Exploratory | E-H6 | `af55fe7c0181` |
| HELIOS-noExpl | `coe_narrative` | Exploratory | E-H7 | `e65e0d47a54e` |

Hypothesis IDs come from `helios/research/analysis_plan.py`; metrics from `docs/tracking/metric_contract.md`. Full hashes are in `research/osf/variant_hashes.json`.

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

### 2.1 UEG-C Node Taxonomy (`helios/schemas/ueg_c.py`)   [schema-draft-v0.2 — S1.5]

UEG-C moved from `schema-draft-v0.1` to `schema-draft-v0.2` in S1.5 (design: `docs/sprints/s1-data-graph/s1_5_ueg_c_design.md`; deviation entry 39). The other schemas in §2 are unchanged.

| NodeType value | Meaning | Used in |
|---|---|---|
| `service` | Microservice seen in any modality (metadata `modalities`); the only root-cause candidates (`candidate_ids()`, tenant `prod`) | D-pipe, G-pipe |
| `operation`, `pod`, `database`, `external` | Kept from v0.1; not built for RCAEval | — |
| `transaction_kpi` *(v0.2)* | User-facing transaction of an entry service (`kpi:<service>`) | economic edges |
| `agent_reasoning_step` *(v0.2)* | One agent reasoning step (P4), tenant `self` | L-pipe (S2) |

Every node has a `tenant` (*v0.2*, default `prod`; `self` for HELIOS's own telemetry and reasoning steps, C5).

### 2.2 UEG-C Edge Taxonomy (`helios/schemas/ueg_c.py`)   [schema-draft-v0.2 — S1.5]

`edge_type` is the relation; `edge_class` is derived from it and never stored apart from it.

| Class | EdgeType value | Meaning | Gated by flag |
|---|---|---|---|
| structural | `structural` | Parent → child span, different services | `ueg_structural` |
| structural | `precedes` | Reasoning step → next step | `ueg_structural` |
| behavioural | `call` | Observed call traffic; weight = share of traces; `correlation` = caller vs callee latency | `l2b_graph` |
| behavioural | `invokes` | Reasoning step → service it acted on | `l2b_graph` |
| causal | `anomaly_leads` | Anomaly intensity of source leads target (`correlation`, `lag_seconds`) | `l2b_graph` |
| causal | `anomaly_co_moves` | Same without a lead; both directions | `l2b_graph` |
| economic | `serves_kpi` | Service → KPI node; weight = share of the entry's traces through the service | `l2b_graph` |

Composition rules (`helios/graph/composition.py`): classes ordered structural < behavioural < causal < economic; composing two edges gives the larger class, and nothing may follow an economic edge. The rule is associative; a path's weight is the product of its edge weights; `typed_paths()` answers cross-domain path queries.

`weight: float` is constrained to `[0, 1]`. Structural edges are enabled only when
`VCLFlag.UEG_STRUCTURAL` is active, maintaining the ablation boundary between
topology-aware and topology-agnostic graph variants. The gate is applied by the
orchestrator, not by `@gated_by`: `RunOrchestrator` passes `manifest.ueg_structural`
to `build_ueg_c(enable_structural=...)` (`helios/orchestrator/runner.py`), while
`build_ueg_c` itself is gated by `l2b_graph`.

### 2.3 UEGCSnapshot Contract (`helios/schemas/ueg_c.py`)   [schema-draft-v0.2 — S1.5]

| Field | Type | Required | Notes |
|---|---|---|---|
| `incident_id` | `str` | Yes | Links to fault event |
| `variant_config_hash` | `str` (64-char hex) | Yes | VCLManifest identity |
| `nodes` | `list[UEGCNode]` | Yes | Sorted by (type, id) |
| `edges` | `list[UEGCEdge]` | Yes | Sorted by (relation, source, target); optional `correlation`, `lag_seconds` |
| `captured_at_iso` | `str` (ISO 8601 UTC) | Yes | Window end (v0.2; v0.1 used the build time, so its hash changed on every build) |
| `schema_version` | `str` | Default `schema-draft-v0.2` | Bumped at OSF Stage 5 freeze |

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
| `mrr` | `float` | `[0, 1]` | Reciprocal rank of the ground-truth service (descriptive; named `cpr` before schema-draft-v0.4) |
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

*S1.5 (schema-draft-v0.2) extends the builder to all three modalities; the design is in `docs/sprints/s1-data-graph/s1_5_ueg_c_design.md`.*

- **STRUCTURAL edge** (`ueg_structural` flag): the parent span's service calls the child span's service, linked by `parent_span_id` within the same trace. Weight = 1 (binary topology signal).
- **CALL edge** (`l2b_graph` flag): the same parent/child calls as observed traffic. Weight = share of traces containing the call; `correlation` = Pearson r of caller and callee mean span duration per 30 s bucket.
- **Causal edges**: per-service anomaly intensity per bucket (`helios/graph/anomaly_intensity.py`: robust z-scores of the service's metric series, counters differenced, and of its S1.4 log-line and new-template counts); lagged Pearson r up to four buckets; kept at r ≥ 0.6. Metric-only and log-only services are nodes and get their edges here.
- **Economic edges**: each entry service (owner of root spans) gets a `transaction_kpi` node; every service on its traces links to it with its share of those traces.
- **Agent-Reasoning-Step nodes**: added when `reasoning_steps` are passed (none before the S2 L-pipe).
- The snapshot is deterministic (window end as `captured_at_iso`, sorted nodes and edges); the inputs are only the window's own streams.

**Structural bundle (S1.6, `helios/graph/structural_bundle.py`).** The builder always produces the typed graph; `apply_structural_bundle()` then gives the view for the current variant. ON (HELIOS-Full): `typed_view()` — the gated component (`@gated_by(VCLFlag.UEG_STRUCTURAL)`) — keeps the four classes, structured reasoning-step nodes and subgraph-aware training (training scope = pruned subgraph). OFF (HELIOS-noStructural, Ch3 p. 51, A-H8): `flatten()` merges every edge between the same two nodes into one `untyped` edge (largest weight), removes reasoning-step nodes and returns them as flat text lines for the L-pipe, and sets the training scope to the full graph. Untyped edges compose only with each other; the pruner and D-pipe propagation treat all of them as topology. The orchestrator applies the bundle before pruning. Check: the noStructural view changes the snapshot hash on 20/20 OTel captures.

*Deviation §2.2 (sig `5655ff9fbeeabfaf`) recorded that the May captures had no `parent_span_id`, so structural edges came from temporal containment. That gap is closed: the builder links parent and child spans (commit `b82cb90`), and both trace writers store `parent_span_id` (OTel captures, and the RCAEval adapter from S1.1). Temporal containment remains only as a fallback, with a warning, for trace files without the column.*

#### K-hop PPR Pruner (`prune_graph`)

Personalized PageRank (alpha=0.85) seeded from structural entry points identifies low-relevance nodes for removal.

**Entry-point detection rule (Milestone 2 fix, SHA `d0e8576`):**
- Entry point = `structural_in_degree == 0` AND `out_degree > 0`
- Isolated nodes with no outgoing edges (async Kafka consumers: `accounting`, `fraud-detection`) are excluded — seeding from them forces uniform-PageRank fallback
- Hub fallback: if no valid structural root exists (e.g., graph has only CALL edges), seed from the highest out-degree node

Nodes with PPR score below `PRUNER_THRESHOLD = 0.02` are removed from the snapshot before D-pipe / G-pipe dispatch.

*v0.2 graphs (S1.5):* PageRank runs over the structural and behavioural edges between production services only. Services without traces, the KPI nodes of kept services and tenant-`self` nodes are always kept; causal and economic edges between kept nodes stay. S1.7 replaces this pruner with Algorithm 5.

#### K-hop Pruner, Algorithm 5 (`khop_prune`, S1.7) — replaces `prune_graph` in the orchestrator

`helios/graph/khop_pruner.py`; design and calibration in `docs/sprints/s1-data-graph/s1_7_khop_pruner.md`. Seeds are label-free: the three services with the highest peak anomaly intensity (builder metadata `anomaly_peak`), else call-graph entry points, else every service; the D-pipe trigger (S2.1) may pass its own. The seeds are expanded by K hops over structural, behavioural (untyped when `VCLFlag.UEG_STRUCTURAL` is OFF) and — beyond Chapter 3, so trace-less services stay reachable — causal edges with \|r\| ≥ 0.7. Services are kept seeds first, then the K-hop neighbourhood by personalized PageRank (restart 0.15), filled to Chapter 3's 50-service floor when the neighbourhood is smaller and capped at top-n. Causal and behavioural edges with \|r\| below 0.7 are dropped, at most 10,000 edges stay (strongest first), and the result carries its snapshot hash. K = 3, top-n = 50, calibrated on the 495 build windows (deviation entry 40). `prune_graph` and its frozen `PRUNER_THRESHOLD` stay for the Milestone 2 evidence only; the pruner serves every variant and is not itself a flag.

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

## 3. Peer Pipelines (D-pipe, G-pipe, L-pipe)   [§3.0 FROZEN — Stage 0 | §3.1 IMPLEMENTED — Milestone 2 | §3.2 IMPLEMENTED — Milestone 3 | §3.3 IMPLEMENTED — Milestone 3]

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
  with the controlling flag inactive (e.g., in `HELIOS-noLLM`, `l2c_llm=False` blocks `run_lpipe`)
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
| D | `d_verdict.py` | Rank services; produce `PipelineVerdict` with `ranked_candidates`, `hr_at_3`, `mrr` | Descending score sort; top-3 extraction |

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

### 3.3 L-pipe — LLM Explanation Pipeline   [IMPLEMENTED — Milestone 3]

**Architecture:** L-pipe consumes a `UEGCSnapshot` and produces a Chain of Explanation (CoE) narrative plus a ranked service candidate list. It operates independently of G-pipe results — both receive the same snapshot; the orchestrator runs them in sequence D→G(conditional)→L but L-pipe does not read G-pipe output.

**Entry point:** `helios/pipelines/l_pipe/pipeline.py::run_lpipe()`, gated by `@gated_by(VCLFlag.L2C_LLM)`.

#### Protocol A (frozen at Milestone 3)

| Parameter | Value | Notes |
|---|---|---|
| Model | `llama3.1:8b` | Via Ollama; 70B/vLLM deferred (deviation 15) |
| Serving runtime | Ollama (`http://localhost:11434`) | vLLM deferred to production stage (deviation 16) |
| Temperature | `0.00` | Greedy decoding — determinism invariant |
| `top_p` | `1.00` | Greedy decoding |
| `top_k` | `1` | Greedy decoding |
| `LLAMA_SEED` | `42` | Determinism seed SEED-S1-01 |
| Timeout | `120.0 s` | Per inference call |
| Max retries | `1` | Via `ResponseHandler` |

All Protocol A constants are frozen in `helios/pipelines/l_pipe/lpipe_config.py`. Any change requires a deviation log entry before the constant is updated.

#### Prompt Governance

`PromptRegistry` (`helios/pipelines/l_pipe/prompt_registry.py`) loads `prompts/rca_v1.txt` and computes `SHA-256(text.encode("utf-8"))` at construction time. `run_lpipe` calls `registry.verify_sha_or_raise(EXPECTED_PROMPT_SHA)` before every inference — if the file has been modified the run aborts with `PromptTamperError`.

`EXPECTED_PROMPT_SHA = "376e555b0bd07a14667c9d5f09275ce5507ddce443fa01781bd7dc40a9365e47"` is the frozen hash of `rca_v1.txt`, set at Milestone 3 and recorded in `research/osf/prompt_sha.json`.

The rendered prompt injects `incident_id`, `service_list`, and `anomaly_summary` (derived from snapshot nodes) into the template. `prompt_version` (`"rca_v1"`) is written into every `PipelineVerdict` row for audit traceability.

#### Response Parsing

`ResponseHandler` (`helios/pipelines/l_pipe/response_handler.py`) wraps `OllamaClient.generate()` with:
- Markdown fence stripping (`sanitize_llm_output`)
- Pydantic schema validation against `LPipeResponse` (`ranked_candidates`, `narrative`, `confidence`)
- One retry on validation failure, then fallback to `ranked_candidates=["l-pipe-fallback"]`

#### Ablation Gating

When `VCLFlag.L2C_LLM` is inactive (variants `HELIOS-noLLM`, `HELIOS-D`, `HELIOS-G`), `@gated_by` raises `GatedComponentInactiveError` and the orchestrator emits a sentinel verdict with `narrative="lpipe-gated-or-skipped"`. Evaluation queries must filter this sentinel for A-H1 metric computation (same pattern as the G-pipe sentinel filter in §3.2).

**Deviation log entries:**

| # | Deviation ID | Stage | Clause | Summary |
|---|---|---|---|---|
| 15 | `29789db26fba` | Stage 1/M3 | §3.6.7 model specification | `llama3.1:8b` used instead of Llama-3.1-70B; CoE narrative quality reduced; HR@3/CpR unaffected |
| 16 | `b7812340df24` | Stage 1/M3 | §3.6.7 serving runtime | Ollama used instead of vLLM; latency metrics not production-representative |

**Cross-references:** §4 (Orchestration), §5 (Consensus), `docs/tracking/hypothesis_variant_metric_mapping.md` (A-H1), `docs/tracking/prompt_version_registry.md` (rca_v1 freeze), `research/osf/prompt_sha.json`.

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
Confirmatory runs use the 240-case RCAEval pool (D11, OSF deposit 1), which stays locked until
tag `build-freeze`; they must never share a DuckDB file with build or exploratory results.
AIOpsLab is a Tier 2 recording spike (S1.3), not the confirmatory corpus.

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
- v0.7 (2026-05-21): §3.3 L-pipe written and frozen (Milestone 3) — Protocol A parameters, PromptRegistry tamper-guard, ResponseHandler retry/fallback, ablation gating, deviation entries 15–16. §5 Consensus design notes added (Milestone 4). Section header updated to reflect implementation status.
- v0.8 (2026-10-25, S2-M6-RES03): §1.2–§1.3 synced to the D2 registry (17 flags; deviation entry 31); §1.5 had been regenerated from `variants.py` on 2026-10-24. §2.2 and §2.6 use `ueg_structural` and say how the orchestrator applies it; §2.6 records that structural edges now use `parent_span_id` linkage. §5 names the RCAEval pool as the confirmatory corpus. §2.1–§2.3 (UEG-C schema) are left for the S1.5 schema bump.
- v0.9 (2026-10-25, S2-M6-ENG03): §2.1–§2.3 and §2.6 rewritten for UEG-C schema-draft-v0.2 (S1.5): four edge classes from traces, metrics and logs, KPI and reasoning-step nodes, tenant, composition rules, deterministic snapshot; pruner note for v0.2 graphs (deviation entry 39).
- v0.10 (2026-10-25, S2-M6-ENG04): §2.6 structural bundle (S1.6): ueg_structural OFF = one untyped edge kind, full-graph training scope, reasoning steps as flat text; gated typed_view; applied by the orchestrator before pruning.
