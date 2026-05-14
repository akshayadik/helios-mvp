# Milestone 1 Design Spec — Telemetry Pipeline + Full C1 Foundations

**Date:** 2026-05-14  
**Branch:** `feature/stage0_vlc_foundation`  
**Milestone:** 1 — Weeks 3–6  
**Status:** Approved — ready for implementation planning  

---

## Objective

Deliver reliable telemetry replay, full C1 runtime enforcement, and schema freezes. The Week 5 gate is an end-to-end result row through the complete C1 path with all three pipeline stubs active.

---

## Pre-conditions (what already exists — do not rebuild)

| Artefact | Path | Notes |
|---|---|---|
| MetricIntegrityGate | `helios/integrity_gate.py` | Fully implemented + 249 test lines |
| ExclusionLedger | `bin/log_exclusion.py` | HMAC-chained JSONL; CLI + verify; 141 test lines |
| UEGCSnapshot, UEGCNode, UEGCEdge | `helios/schemas/ueg_c.py` | Schema-draft-v0.1; needs `edge_class` field added |
| PipelineVerdict | `helios/schemas/verdict.py` | Schema-draft-v0.1; frozen |
| TelemetryWindow | `helios/schemas/telemetry.py` | Schema-draft-v0.1; frozen |
| ResultStore + schema.sql | `helios/store/` | DuckDB; fully implemented |
| CaptureReader | `helios/telemetry/reader.py` | L0 hash round-trip; fully implemented |
| OTEL Demo capture | `helios/telemetry/otel_demo_capture.py` | 5 exploratory Parquets exist |
| G-pipe stub | `helios/pipelines/g_pipe/stub.py` | `@gated_by(VCLFlag.L2B_GRAPH)` |
| L-pipe stub | `helios/pipelines/l_pipe/stub.py` | `@gated_by(VCLFlag.L2C_LLM)` |
| VCL core | `helios/vcl/` | 14 flags; deviation log; SnapshotRegistry |

---

## Module Map

Four parallel-capable modules. M4 depends on M1 CLI; all others are independent.

### Module 1 — Orchestrator & Ledgers `[ENG]`

**Context:** The metric integrity gate and exclusion ledger exist, but there is no entry point to run the pipeline loop and no artefact recording per-incident outcomes.

**New files:**

| File | Responsibility |
|---|---|
| `helios/pipelines/d_pipe/stub.py` | D-pipe null stub; `@gated_by(VCLFlag.DPIPE)`; returns sentinel `PipelineVerdict(pipeline="dpipe")` |
| `helios/orchestrator/__init__.py` | Package init |
| `helios/orchestrator/corpus.py` | `CorpusLoader` — auto-detects directory vs. YAML manifest; yields `incident_id` strings |
| `helios/orchestrator/runner.py` | `RunOrchestrator` — wires CaptureReader → SnapshotRegistry → 3-pipeline dispatch → MetricIntegrityGate → ResultStore |
| `helios/orchestrator/ledger.py` | `ReconciliationLedger` — HMAC-chained JSONL; one row per incident: `outcome ∈ {attempted, passed, excluded, skipped}` |
| `bin/helios_run.py` | CLI: `helios run --variant NAME --corpus PATH`; thin argparse delegating to `RunOrchestrator` |

**Dependencies:** None — build first.

---

### Module 2 — Disjointness Audit `[ENG / DEVOPS]`

**Context:** `.github/workflows/disjointness_audit.yml` is a stub that exits 0 on `ImportError`. Full static + dynamic enforcement is required for the M1 exit gate.

**New files:**

| File | Responsibility |
|---|---|
| `helios/vcl/disjointness.py` | Static AST scan: asserts every `@gated_by` function is covered by exactly one boolean flag; no two mutually exclusive flags invoked in the same call path |

**Modified files:**

| File | Change |
|---|---|
| `.github/workflows/disjointness_audit.yml` | Replace stub with: (1) `python -m helios.vcl.disjointness` static check; (2) `coverage.py` run with flag-context tags; assert symmetric difference of executed lines proves disjoint ablation paths |

**Dependencies:** None — parallel with M1.

---

### Module 3 — Schema Freeze & Research Artefacts `[RES / DEVOPS]`

**Context:** Schemas exist but are not formally locked. The UEG-C schema requires an `edge_class` semantic layer (Option C) before freezing.

**Modified files:**

| File | Change | Activity |
|---|---|---|
| `helios/schemas/ueg_c.py` | Add `EdgeClass` enum (`STRUCTURAL`, `BEHAVIOURAL`, `CAUSAL`, `ECONOMIC`); add `edge_class: EdgeClass` field to `UEGCEdge`; `@field_validator` enforces `EdgeType → EdgeClass` mapping: `STRUCTURAL→STRUCTURAL`, `CALL→BEHAVIOURAL`, `METRIC→CAUSAL`, `LOG→ECONOMIC` | ENG |
| `.github/workflows/ci.yml` | Add schema round-trip step: serialize all three schemas → deserialize → recompute SHA-256 canonical hash → assert no drift | DEVOPS |
| `docs/tracking/ablation_architecture.md` | Write §4: orchestrator flow diagram, reconciliation ledger role, C1 gate evidence, three-pipeline dispatch | RES |
| `docs/osf_protocol_v0.md` | Expand §2: corpus inclusion/exclusion rules (evaluation_phase=exploratory for M1; gate compliance required for inclusion); reconciliation ledger reference; corpus terminology | RES |

**Git artefact:**
```bash
git tag schema-draft-v0.1
git push origin schema-draft-v0.1
```
Tag is applied after CI schema round-trip step is green.

**Dependencies:** None — parallel with M1 and M2.

---

### Module 4 — 20-Incident Calibration Run `[DATA]`

**Context:** 5 exploratory Parquet recordings exist. M1 exit requires 20 incidents with byte-equal replay verification — empirical proof the harness is deterministic.

**Tasks:**

| Task | Tool | Done signal |
|---|---|---|
| Record 15 additional incidents using OTEL Demo fault injection | `bin/run_capture.py --incident-id <id>` | 15 new sub-directories under `data/captures/` |
| Verify deterministic hash on all 20 incidents (run `bin/verify_captures.py` 3× on the same Parquet files; confirm identical hash each run) | `bin/verify_captures.py` | Exit 0 all 3 runs; all `hash_matches: True`; no hash drift across runs |
| Run `helios run` across full 20-incident corpus | `bin/helios_run.py` | ReconciliationLedger shows 20 `passed` rows |

**Dependencies:** Module 1 CLI must be complete before the `helios run` step.

---

## Data Flow — Single `helios run` Invocation

```
bin/helios_run.py
  │  --variant NAME  → get_variant(name) → VCLManifest
  │  --corpus PATH   → CorpusLoader → [incident_id, ...]
  │  set_current_manifest(manifest)
  │
  └─ RunOrchestrator.run(corpus):
       For each incident_id:
         │
         ├─ CaptureReader.read(incident_id)
         │    └─ hash_matches=False → ReconciliationLedger.record(skipped)
         │
         ├─ SnapshotRegistry.contains(snapshot_hash)?
         │    └─ False → register snapshot
         │
         ├─ Dispatch (all @gated_by active flags):
         │    ├─ d_pipe.run_dpipe(window) → PipelineVerdict(pipeline="dpipe")
         │    ├─ g_pipe.run_gpipe(window) → PipelineVerdict(pipeline="gpipe")
         │    └─ l_pipe.run_lpipe(window) → PipelineVerdict(pipeline="lpipe")
         │
         ├─ MetricIntegrityGate.check_consistency([d, g, l])
         │    ├─ PASS → ResultStore.insert() × 3
         │    │         ReconciliationLedger.record(passed)
         │    └─ FAIL → ExclusionLedger.append()
         │               ReconciliationLedger.record(excluded)
         │
       ReconciliationLedger.finalize()
```

**CorpusLoader auto-detection:**
- `--corpus data/captures/` → discovers all sub-directories containing `manifest.json`
- `--corpus corpus.yaml` → reads `incidents: [...]` list from YAML

**ReconciliationLedger row schema (HMAC-chained JSONL):**
```
run_id, incident_id, variant_config_hash, outcome, gate_check,
timestamp_utc, prev_signature, signature
```

---

## Exit Criteria Mapping

| Exit Criterion | Satisfied by | Module | Activity |
|---|---|---|---|
| 20 incidents with full VCL + snapshot hash + gate compliance | ReconciliationLedger: 20 `passed` rows; ExclusionLedger empty or deviations logged | M1 + M4 | ENG + DATA |
| Disjointness CI green | Static scan passes; `coverage.py` dynamic check passes in CI | M2 | ENG/DEVOPS |
| All schemas frozen (CI round-trip tests passing) | `schema-draft-v0.1` tag; CI hash-drift check passes | M3 | RES/DEVOPS |
| Ablation Notebook: C1 + Telemetry complete | `ablation_architecture.md` §4 written and committed | M3 | RES |
| Gate (Week 5): End-to-end result row through full C1 path | `helios run` on single incident → 3 `result_row` inserts + 1 ReconciliationLedger entry; `pytest tests/test_e2e_smoke.py` green | M1 | ENG |

---

## Track Sequencing

```
Week 3 ──────────────────────────────────── Week 5 GATE ──── Week 6
│
ENG-CORE (M1)   D-pipe stub → CorpusLoader → RunOrchestrator
                → ReconciliationLedger → CLI
                                              │
                                         e2e C1 row green
│
ENG-INFRA (M2)  disjointness.py (static)
                → coverage.py (dynamic) → CI wired
                                              │
                                         CI green
│
RES (M3)        UEG-C edge_class → schema CI → git tag
                → OSF §2 → ablation §4
                                                       done
│
DATA (M4)       [blocked on M1 CLI]
                15 new captures → 3× replay verify → helios run ×20
                                                       done
```

---

## Activity Summary

| Label | Modules | Deliverables |
|---|---|---|
| ENG | M1, M2, M3 | D-pipe stub, CorpusLoader, RunOrchestrator, ReconciliationLedger, CLI, DisjointnessAuditor, UEG-C edge_class + validator |
| DEVOPS | M2, M3 | Disjointness CI workflow, schema round-trip CI step, `schema-draft-v0.1` git tag |
| RES | M3 | OSF §2 inclusion/exclusion rules, ablation notebook §4 |
| DATA | M4 | 15 incident recordings, 3× replay verification, full corpus run |
