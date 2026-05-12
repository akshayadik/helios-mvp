# HELIOS Ablation Architecture — Living ADR

**Document Version:** v0.1
**Date:** 2026-05-12
**Status:** Section 1 frozen at Stage 0. §2–§6 stubs — populated and frozen incrementally at their respective stage gates.
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

## 2. UEG-C Builder & Snapshot Hashing   [STUB — Stage 3]

> **Not yet implemented.** This section will be written and frozen at the Stage 3 gate.
> No implementation claims may be added before that gate passes.
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
- v0.1 (2026-05-12): Section 1 (VCL/C1) written and frozen at Stage 0. §2–§6 stubs added.
