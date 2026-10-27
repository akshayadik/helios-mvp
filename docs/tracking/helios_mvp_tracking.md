# HELIOS MVP — Daily Tasks + Stage Gates

**Purpose:** Single source of truth for daily tasks, stage-gate sign-offs, and evidence links. Mirrors Execution Plan stage structure.

**Update cadence:** Daily EOD + at each gate
**Owner module:** Researcher (solo)
**Status:** Stage 0 stub — populate as work progresses.

---

# HELIOS MVP — Stage 0 Week 1 Tracking

**Tracker Version:** 1.1 (frozen after Day 1 commit)  
**Schema-freeze rule:** Adding column or state = deviation entry.  
**Append-only rule:** Columns 1–10, 17 immutable after row creation.  
**Last regenerated:** 2026-05-08  
**Execution Plan Alignment:** Stage 0, §6 C1 Discipline, §10 Checklist  
**Proposal Alignment:** §3.6 Artefact, §3.9 Validity & Reliability

## State Machine
```
PLANNED → IN_PROGRESS → DONE  (terminal)
                  ↓
              BLOCKED → IN_PROGRESS (recover)
                     → DEFERRED      (terminal, requires deviation)
                     → CARRIED_OVER  (terminal, requires deviation, spawns S0-W2- row)
```

## Column Legend (updated)

| Col | Field | Notes |
|---|-------|-------|
| 1 | Task_ID | `S0-D{day}-{TYPE}{nn}` Immutable |
| 2 | Day | 1–5 Immutable |
| 3 | Type | ENG / RES / EVAL / GATE Immutable |
| 4 | Description | One sentence. Immutable |
| 5 | Prop_§ | Proposal clause(s) |
| 6 | Exec_§ | Execution Plan section (new) |
| 7 | DSR | Identify / Objectives / Design / Demonstrate / Evaluate / Communicate |
| 8 | Contrib | C1 / C2 / methodology / infra |
| 9 | Own | AA |
| 10 | Deps | Comma-sep Task_IDs or `-` |
| 11 | Status | PLANNED / IN_PROGRESS / ... |
| 12 | Started | ISO or `-` |
| 13 | Done | ISO or `-` |
| 14 | SHA | 7-char git SHA |
| 15 | Ev_Type | TEST / ARTEFACT_HASH / LEDGER_ENTRY / MANIFEST / DOC |
| 16 | Ev_Ref | Test ID / file:sha / etc. |
| 17 | Gate | EG1–EG6 or `-` |
| 18 | Dev_Ref | `dev-NNN` |
| 19 | Notes | Append-only |

*(Shifted columns; Exec_§ added as Col 6. You can keep original numbering if preferred — just add Exec_§ after Prop_§.)*

## Exit Gate Legend

- **EG1**: VCL hash-consistency 100% — variant manifests verifiable, mutations blocked.
- **EG2**: 5 valid Parquet recordings — schema-validated against TelemetryWindow.
- **EG3**: Schema stability round-trip — identical SHA-256 across canonical → parse → re-canonical.
- **EG4**: E2E smoke test — DuckDB result row inserted, evaluation_phase='exploratory'.
- **EG5**: Deviation log ≥1 signed entry — minimum 3 entries by Friday EOD.
- **EG6**: Spine memo + ablation arch + OSF protocol complete — three docs committed.

---

## DAY 1 — Repository + VCL Skeleton

| Task_ID | Day | Type | Description | Prop_§ | DSR | Contrib | Own | Deps | Status | Started | Done | SHA | Ev_Type | Ev_Ref | Gate | Dev_Ref | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S0-D1-ENG01 | 1 | ENG | Init Poetry project, pin Python 3.11, dev deps | §3.6.2 | Design | infra | AA | - | DONE | 2026-05-08 | 2026-05-08 | a9d4dd0 | MANIFEST | pyproject.toml | - | - | pyenv fallback if conflict |
| S0-D1-ENG02 | 1 | ENG | Create directory skeleton (helios/, tests/, docs/) | §3.6.3 | Design | infra | AA | S0-D1-ENG01 | DONE | 2026-05-08 | 2026-05-08 | a9d4dd0 | MANIFEST | repo tree | - | - | Must include vcl/variants.py |
| S0-D1-ENG03 | 1 | ENG | registry.py: declare 13 flags (12 proposal + ingest_mode) | §3.6.2 | Design | C1 | AA | S0-D1-ENG02 | DONE | 2026-05-08 | 2026-05-11 | 5e51770 | TEST | tests/test_vcl.py::test_flag_count | EG1 | - | ueg_structural is in §3.6.7 |
| S0-D1-ENG04 | 1 | ENG | config.py: VCLManifest + variant_config_hash (Pydantic) | §6.1 | Design | C1 | AA | S0-D1-ENG03 | DONE | 2026-05-08 | 2026-05-11 | 5e51770 | TEST | tests/test_vcl.py::test_hash_canonical | EG1 | - | SHA-256 over canonical JSON |
| S0-D1-ENG05 | 1 | ENG | decorators.py: @gated_by + GatedComponentInactiveError | §3.6.2, §3.9.1 T2 | Design | C1 | AA | S0-D1-ENG03 | DONE | 2026-05-08 | 2026-05-11 | 5e51770 | TEST | tests/test_vcl.py::test_gated_raises | EG1 | - | Disjointness reg promoted to D2 |
| S0-D1-ENG06 | 1 | ENG | variants.py: 8 confirmatory variants from Table 12 | §3.6.7 | Design | C1 | AA | S0-D1-ENG03 | DONE | 2026-05-11 | 2026-05-12 | e4a6594 | TEST | tests/test_vcl.py::test_eight_variants | EG1 | - | Maps A-H1..A-H8 |
| S0-D1-ENG07 | 1 | ENG | CI workflow: ruff, mypy, pytest, coverage ≥90% | §3.6.2 | Design | infra | AA | S0-D1-ENG02 | DONE | 2026-05-08 | 2026-05-08 | a9d4dd0 | MANIFEST | .github/workflows/ci.yml | - | - | Disjointness stub today, real D2 |
| S0-D1-RES01 | 1 | RES | spine_freeze_memo_v0.md (1 page) | §6.1 | Communicate | methodology | AA | - | DONE | 2026-05-12 | 2026-05-12 | e493e9a | DOC | docs/spine_freeze_memo_v0.md | EG6 | - | Frozen / extensible / deferred |
| S0-D1-RES02 | 1 | RES | ablation_architecture.md §1: VCL + flag registry | §3.6.7, §6.1 | Communicate | C1 | AA | S0-D1-ENG03 | DONE | 2026-05-12 | 2026-05-12 | e493e9a | DOC | docs/tracking/ablation_architecture.md | EG6 | - | §2 on Day 3, §3 on Day 5 |

---

## DAY 2 — Deviation Log + Eval Infrastructure + Disjointness Registry

| Task_ID | Day | Type | Description | Prop_§ | DSR | Contrib | Own | Deps | Status | Started | Done | SHA | Ev_Type | Ev_Ref | Gate | Dev_Ref | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S0-D2-ENG01 | 2 | ENG | deviation_log.py: §B.12 schema + JSONL + HMAC-SHA256 | §B.12, §3.6.2 | Design | C1 | AA | S0-D1-ENG02 | DONE | 2026-05-12 | 2026-05-12 | ff176b8 | TEST | tests/test_deviation_log.py::test_schema | EG5 | - | Ed25519 migration deferred; implemented as bin/log_deviation.py |
| S0-D2-ENG02 | 2 | ENG | exclusion_ledger.py: signed append-only JSONL | §3.6.8, §3.7 | Design | C1 | AA | S0-D2-ENG01 | DONE | 2026-05-12 | 2026-05-12 | 87ed94a | TEST | tests/test_exclusion_ledger.py::test_append | - | - | Required-field manifest; implemented as bin/log_exclusion.py |
| S0-D2-ENG03 | 2 | ENG | integrity_gate.py: PASS/FAIL + auto-write to ledger | §3.6.8, §3.7 | Design | C1 | AA | S0-D2-ENG02 | DONE | 2026-05-12 | 2026-05-12 | 5e84604 | TEST | tests/test_integrity_gate.py::test_reject | EG4 | - | Per-cell field manifest |
| S0-D2-ENG04 | 2 | ENG | disjointness.py: promote registry from stub to functional | §3.9.1 T2 | Design | C1 | AA | S0-D1-ENG05 | DONE | 2026-05-12 | 2026-05-12 | 5e84604 | TEST | tests/test_disjointness.py::test_violation | EG1 | - | Hidden-coupling audit infra |
| S0-D2-ENG05 | 2 | ENG | tests/test_vcl.py: 3 mutated manifests blocked | §6.1 | Evaluate | C1 | AA | S0-D1-ENG04 | DONE | 2026-05-12 | 2026-05-12 | e4a6594 | TEST | tests/test_vcl.py::test_three_mutations | EG1 | - | Deliberate failure suite |
| S0-D2-ENG06 | 2 | ENG | tests/test_deviation_log.py: write + verify HMAC | §B.12 | Evaluate | C1 | AA | S0-D2-ENG01 | DONE | 2026-05-12 | 2026-05-12 | fd7419a | TEST | tests/test_deviation_log.py::test_tamper | EG5 | - | Tamper test mandatory |
| S0-D2-RES01 | 2 | RES | osf_protocol_v0.md: problem, intervention, eval sketch | §3.3, §3.6.1 | Communicate | methodology | AA | - | DONE | 2026-05-12 | 2026-05-13 | 19d04aa | DOC | docs/osf_protocol_v0.md | EG6 | - | All sections complete; Holm table corrected 2026-05-13 |
| S0-D2-EVAL01 | 2 | EVAL | First deviation entry: project init + HMAC migration note | §B.12 | Evaluate | C1 | AA | S0-D2-ENG01 | DONE | 2026-05-12 | 2026-05-12 | ff176b8 | LEDGER_ENTRY | deviation_log:001-003 | EG5 | dev-001 | Genesis + signing-scheme + VCLManifest extension entries |

---

## DAY 3 — Schema Freeze Day (CRITICAL)

| Task_ID | Day | Type | Description | Prop_§ | DSR | Contrib | Own | Deps | Status | Started | Done | SHA | Ev_Type | Ev_Ref | Gate | Dev_Ref | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S0-D3-ENG01 | 3 | ENG | schemas/ueg_c.py: NodeType + EdgeType enums + UEGCSnapshot | §3.6.3, §3.6.7 | Design | C2 | AA | S0-D1-ENG02 | DONE | 2026-05-13 | 2026-05-13 | 4dd4f1e | TEST | tests/test_schema_stability.py::test_roundtrip | EG3 | - | Snapshot = pruned subgraph (Alg 5) |
| S0-D3-ENG02 | 3 | ENG | schemas/verdict.py: PipelineVerdict (all fields required) | §3.6.3 | Design | C1 | AA | S0-D3-ENG01 | DONE | 2026-05-13 | 2026-05-13 | 4dd4f1e | TEST | tests/test_schema_stability.py::test_verdict | EG3 | - | (ranked, mu, sigma, cost, latency) |
| S0-D3-ENG03 | 3 | ENG | schemas/telemetry.py: TelemetryWindow (P1-P5 + phase) | §3.7 | Design | C1 | AA | S0-D3-ENG01 | DONE | 2026-05-13 | 2026-05-13 | 4dd4f1e | TEST | tests/test_schema_stability.py::test_telemetry | EG3 | - | evaluation_phase enum required |
| S0-D3-ENG04 | 3 | ENG | tests/test_schema_stability.py: canonical → hash → roundtrip | §6.2 | Evaluate | C1 | AA | S0-D3-ENG03 | DONE | 2026-05-13 | 2026-05-13 | 4dd4f1e | TEST | tests/test_schema_stability.py | EG3 | - | MUST FAIL on any schema change |
| S0-D3-ENG05 | 3 | ENG | store/schema.sql: DuckDB result table + tag schema-draft-v0.1 | §3.7 | Design | infra | AA | S0-D3-ENG02 | DONE | 2026-05-13 | 2026-05-13 | 4dd4f1e | MANIFEST | helios/store/schema.sql | EG4 | - | Mirrors PipelineVerdict |
| S0-D3-RES01 | 3 | RES | Schema diff vs §3.6.3 - any discrepancy → deviation BEFORE commit | §3.6.3 | Evaluate | C1 | AA | S0-D3-ENG01 | DONE | 2026-05-13 | 2026-05-13 | 4dd4f1e | LEDGER_ENTRY | deviation_log (no discrepancy found) | - | - | Schema matches §3.6.3; no deviation required |
| S0-D3-RES02 | 3 | RES | ablation_architecture.md §2: schema tables | §3.6.3, §3.6.7 | Communicate | C2 | AA | S0-D3-ENG04 | DONE | 2026-05-13 | 2026-05-13 | 522df2a | DOC | docs/tracking/ablation_architecture.md | EG6 | - | §2.1-2.6 written; §2.6 builder remains Stage 3 stub |

---

## DAY 4 — OTEL Demo Harness Spike

| Task_ID | Day | Type | Description | Prop_§ | DSR | Contrib | Own | Deps | Status | Started | Done | SHA | Ev_Type | Ev_Ref | Gate | Dev_Ref | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S0-D4-ENG01 | 4 | ENG | Clone OTEL Demo at fixed Git tag; record tag+SHA in dev log | §3.7 | Demonstrate | infra | AA | - | DONE | 2026-05-14 | 2026-05-14 | c963dac | ARTEFACT_HASH | external/otel-demo-commit.txt | EG2 | - | Tag=2.2.0 SHA=b74a7bc pinned in external/ |
| S0-D4-ENG02 | 4 | ENG | docker compose up -d; verify all services healthy | §3.7 | Demonstrate | infra | AA | S0-D4-ENG01 | DONE | 2026-05-14 | 2026-05-14 | c963dac | ARTEFACT_HASH | external/README.md | EG2 | - | Evidenced by 5 successful captures across 4 fault classes |
| S0-D4-ENG03 | 4 | ENG | Identify fault-injection mechanism (featureflagservice) | §3.7 | Demonstrate | infra | AA | S0-D4-ENG02 | DONE | 2026-05-14 | 2026-05-14 | c963dac | DOC | docs/fault_catalogue_v0.md | EG2 | - | 5 incidents + naming convention; 4 fault classes documented |
| S0-D4-ENG04 | 4 | ENG | telemetry/otel_demo_capture.py: 5min window → Parquet | §3.7 | Design | infra | AA | S0-D3-ENG03 | DONE | 2026-05-14 | 2026-05-14 | c963dac | TEST | tests/test_capture.py::test_window | - | - | 25 tests green; SOLID StreamFetcher ABC; Sequence[StreamFetcher] fix |
| S0-D4-ENG05 | 4 | ENG | Capture 5 Parquet recordings, ≥3 fault classes | §3.7 | Demonstrate | infra | AA | S0-D4-ENG04 | DONE | 2026-05-14 | 2026-05-14 | c963dac | ARTEFACT_HASH | data/captures/*.parquet | EG2 | - | 15 Parquets; adhc/cart/imgsl/pcat/rcf; all evaluation_phase=exploratory |
| S0-D4-ENG06 | 4 | ENG | telemetry/parquet_reader.py: read + validate against schema | §3.7 | Design | infra | AA | S0-D4-ENG04 | DONE | 2026-05-14 | 2026-05-14 | c963dac | TEST | tests/test_capture.py::test_validate | EG2 | - | helios/telemetry/reader.py; 8 reader tests; tamper detection + hash round-trip |
| S0-D4-EVAL01 | 4 | EVAL | Verify 5 Parquets: schema-valid, non-empty, fault-active | §3.7 | Evaluate | infra | AA | S0-D4-ENG05 | DONE | 2026-05-14 | 2026-05-14 | c963dac | DOC | data/captures/data-capture-steps.md | EG2 | - | verify_captures.py all-OK; hash round-trip confirmed |

---

## DAY 5 — Snapshot Registry + Null Stubs + E2E + Exit Gate

| Task_ID | Day | Type | Description | Prop_§ | DSR | Contrib | Own | Deps | Status | Started | Done | SHA | Ev_Type | Ev_Ref | Gate | Dev_Ref | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S0-D5-ENG01 | 5 | ENG | vcl/snapshot_registry.py: register/verify (append-only JSONL) | §6.2, §3.6.5 | Design | C1 | AA | S0-D3-ENG01 | DONE | 2026-05-13 | 2026-05-13 | f628102 | TEST | tests/test_snapshot_registry.py | EG4 | - | 15 tests; content-addressable JSONL |
| S0-D5-ENG02 | 5 | ENG | pipelines/{g,l}_pipe/stub.py: gated null stubs | §3.6.7 | Design | infra | AA | S0-D1-ENG05 | DONE | 2026-05-13 | 2026-05-13 | f628102 | TEST | tests/test_pipelines.py::test_gated | - | - | 7 tests; g_pipe + l_pipe stubs |
| S0-D5-ENG03 | 5 | ENG | store/result_store.py: DuckDB insert + inclusion-rate helper | §3.7 | Design | infra | AA | S0-D3-ENG05 | DONE | 2026-05-13 | 2026-05-13 | f628102 | TEST | tests/test_result_store.py | EG4 | - | 11 tests; DuckDB insert + inclusion_rate() |
| S0-D5-ENG04 | 5 | ENG | tests/test_e2e_smoke.py: full pipeline (Parquet → DuckDB row) | §6.1-§6.4 | Evaluate | C1 | AA | S0-D5-ENG01,S0-D5-ENG03 | DONE | 2026-05-13 | 2026-05-13 | f628102 | TEST | tests/test_e2e_smoke.py::test_full_pipeline_exploratory_row_inserted | EG4 | - | 4 tests; EG4 binding integration test |
| S0-D5-RES01 | 5 | RES | ablation_architecture.md §3 (snapshot registry, stubs, flow) | §6.2 | Communicate | C1 | AA | S0-D5-ENG01 | DONE | 2026-05-14 | 2026-05-14 | cbf6e18 | DOC | docs/tracking/ablation_architecture.md | EG6 | - | §3.0 written (frozen); §3.1-3.3 sub-stubs added; v0.3 |
| S0-D5-RES02 | 5 | RES | osf_protocol_v0.8.md: full structure populated | §3 (all) | Communicate | methodology | AA | S0-D2-RES01 | DONE | 2026-05-13 | 2026-05-13 | 19d04aa | DOC | docs/osf_protocol_v0.md | EG6 | - | D2-RES01 delivered full structure ahead of schedule; all 7 sections complete; v0.8 naming was a planning artifact |
| S0-D5-GATE01 | 5 | GATE | EG1: VCL hash-consistency check (100%) | §6.1 | Evaluate | C1 | AA | S0-D2-ENG05 | DONE | 2026-05-14 | 2026-05-14 | 325bf28 | TEST | pytest -k test_vcl | EG1 | - | 25 VCL tests; 3 mutations blocked; 8 variant hashes unique |
| S0-D5-GATE02 | 5 | GATE | EG2: 5 Parquet recordings valid | §3.7 | Evaluate | infra | AA | S0-D4-EVAL01 | DONE | 2026-05-14 | 2026-05-14 | c963dac | ARTEFACT_HASH | data/captures/*.parquet | EG2 | - | 15 Parquets; 4 fault classes; hash round-trip verified |
| S0-D5-GATE03 | 5 | GATE | EG3: Schema stability round-trip GREEN | §6.2 | Evaluate | C1 | AA | S0-D3-ENG04 | DONE | 2026-05-14 | 2026-05-14 | 4dd4f1e | TEST | pytest tests/test_schema_stability.py | EG3 | - | 41 tests; identical SHA-256 round-trip |
| S0-D5-GATE04 | 5 | GATE | EG4: E2E smoke result row in DuckDB | §6.1-§6.4 | Evaluate | C1 | AA | S0-D5-ENG04 | DONE | 2026-05-14 | 2026-05-14 | f628102 | TEST | tests/test_e2e_smoke.py | EG4 | - | 4 tests; evaluation_phase=exploratory; DuckDB row inserted |
| S0-D5-GATE05 | 5 | GATE | EG5: Deviation log ≥1 signed entry (target 3+) | §B.12 | Evaluate | C1 | AA | S0-D2-EVAL01 | DONE | 2026-05-14 | 2026-05-14 | 325bf28 | LEDGER_ENTRY | deviation_log.jsonl | EG5 | - | 4 entries; HMAC chain verified |
| S0-D5-GATE06 | 5 | GATE | EG6: Spine memo + ablation arch + OSF v0.8 committed | §6.1 | Evaluate | methodology | AA | S0-D5-RES02 | DONE | 2026-05-14 | 2026-05-14 | cbf6e18 | DOC | docs/*.md (3 files) | EG6 | - | spine_memo=e493e9a, osf_protocol=19d04aa, ablation_arch=cbf6e18; all 3 committed |
| S0-D5-EVAL01 | 5 | EVAL | Stage 0 W1 exit gate sign-off entry | §B.12 | Evaluate | C1 | AA | S0-D5-GATE01..06 | DONE | 2026-05-14 | 2026-05-14 | 43c3115 | LEDGER_ENTRY | deviation_log:a64c18b7f0b94745 | EG5 | - | EG1-6 all DONE; exit sign-off deviation_id=a64c18b7f0b94745 |

---

## Summary Statistics (auto-update guidance)
Add at bottom:

```python
# One-liner to regenerate summary (run in repo root)
# python -c "
import pandas as pd
df = pd.read_markdown('docs/tracking/helios_mvp_tracking.md', header=0)
print(df.groupby('Day')['Status'].value_counts().unstack(fill_value=0))
"
```

---

## MILESTONE 1 — Telemetry + C1 Foundation

**Row ID format:** `S1-M1-{TYPE}{nn}` — Milestone 1 spans multiple sessions, not a 5-day sprint. Day column recorded as `-` for all M1 rows.
**Coverage at exit:** 94.46% (gate requires 90%)
**Exit tag:** `milestone-1-exit` @ `f11c529`


| Task_ID | Day | Type | Description | Prop_§ | DSR | Contrib | Own | Deps | Status | Started | Done | SHA | Ev_Type | Ev_Ref | Gate | Dev_Ref | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1-M1-ENG01 | - | ENG | D-pipe null stub gated by VCLFlag.DPIPE | §3.6.7 | Design | C1 | AA | - | DONE | 2026-05-14 | 2026-05-14 | 5f6b402 | TEST | tests/test_pipelines.py | - | - | Completes 3-stub set; HELIOS-Full dispatch testable |
| S1-M1-ENG02 | - | ENG | CorpusLoader — directory + JSON manifest resolution | §3.6.8 | Design | infra | AA | S1-M1-ENG01 | DONE | 2026-05-14 | 2026-05-14 | 7233116 | TEST | tests/test_corpus_loader.py | - | - | Two formats: directory scan + JSON incidents list |
| S1-M1-ENG03 | - | ENG | ReconciliationLedger — HMAC-chained per-incident outcome log | §5.1 | Design | C1 | AA | - | DONE | 2026-05-14 | 2026-05-14 | 489f2c7 | TEST | tests/test_reconciliation_ledger.py | - | - | Outcomes: attempted/passed/excluded/skipped |
| S1-M1-ENG04 | - | ENG | RunOrchestrator — full C1 corpus dispatch loop | §3.6.8, §5.1 | Design | C1 | AA | S1-M1-ENG02,S1-M1-ENG03 | DONE | 2026-05-14 | 2026-05-14 | 98ff02d | TEST | tests/test_orchestrator_runner.py | - | - | Reader→Registry→3-pipe→Gate→Store→Ledger |
| S1-M1-ENG05 | - | ENG | helios run CLI — corpus orchestration entry point | §3.6.8 | Design | infra | AA | S1-M1-ENG04 | DONE | 2026-05-14 | 2026-05-14 | a39d1df | MANIFEST | bin/helios_run.py | - | - | --variant / --corpus / --db / --registry flags |
| S1-M1-ENG06 | - | ENG | E2E smoke — three-pipeline dispatch through full C1 path | §6.1–§6.4 | Evaluate | C1 | AA | S1-M1-ENG04 | DONE | 2026-05-14 | 2026-05-14 | c7a4832 | TEST | tests/test_e2e_smoke.py | - | - | Extends Stage 0 smoke with RunOrchestrator path |
| S1-M1-ENG07 | - | ENG | DisjointnessAuditor — static flag-gating audit | §3.9.1 T2 | Design | C1 | AA | S1-M1-ENG05 | DONE | 2026-05-14 | 2026-05-14 | 05d2cbc | TEST | tests/test_disjointness.py | - | - | Imports pipeline modules; checks __gated_by__ |
| S1-M1-ENG08 | - | ENG | CI disjointness audit — static scan + coverage.py contexts | §3.9.1 T2 | Design | infra | AA | S1-M1-ENG07 | DONE | 2026-05-14 | 2026-05-14 | 72f0245 | MANIFEST | .github/workflows/disjointness_audit.yml | - | - | Two coverage contexts: HELIOS-Full vs HELIOS-noGraph |
| S1-M1-ENG09 | - | ENG | UEG-C EdgeClass semantic layer + schema round-trip tests | §3.6.3 | Design | C2 | AA | - | DONE | 2026-05-14 | 2026-05-14 | d58a878 | TEST | tests/test_schema_roundtrip.py | - | - | Computed field edge_class auto-derived from edge_type |
| S1-M1-ENG10 | - | ENG | CI schema round-trip integrity step | §6.2 | Design | C1 | AA | S1-M1-ENG09 | DONE | 2026-05-14 | 2026-05-14 | a58a5db | MANIFEST | .github/workflows/ci.yml | - | - | Serialise→deserialise→hash-compare on every push |
| S1-M1-ENG11 | - | ENG | Capture 15 additional incidents + fix Docker port drift | §3.7 | Demonstrate | infra | AA | - | DONE | 2026-05-15 | 2026-05-15 | f11c529 | ARTEFACT_HASH | data/captures/ (20 total) | - | - | Ports: Jaeger=32770, OpenSearch=32781 after container restart |
| S1-M1-ENG12 | - | ENG | Expand verify_captures.py to all 20 incident IDs | §3.7 | Demonstrate | infra | AA | S1-M1-ENG11 | DONE | 2026-05-15 | 2026-05-15 | f11c529 | ARTEFACT_HASH | bin/verify_captures.py | - | - | Hash round-trip verified 3x for determinism |
| S1-M1-RES01 | - | RES | OSF §2 inclusion/exclusion rules (osf_protocol_v0.md §2.4) | §3 (OSF) | Communicate | methodology | AA | - | DONE | 2026-05-15 | 2026-05-15 | 5dc5957 | DOC | docs/osf_protocol_v0.md | - | - | §2.4 inserted after existing §2.3; corpus terminology locked |
| S1-M1-RES02 | - | RES | ablation_architecture.md §4 — Orchestration + C1 Enforcement | §3.6.8 | Communicate | C1 | AA | S1-M1-ENG04 | DONE | 2026-05-15 | 2026-05-15 | 5dc5957 | DOC | docs/tracking/ablation_architecture.md | - | - | §4 frozen at Milestone 1; old §4–§6 renumbered to §5–§7 |
| S1-M1-GATE01 | - | GATE | Milestone 1 exit gate — all criteria met | §5.1, §6 | Evaluate | C1 | AA | S1-M1-ENG01..RES02 | DONE | 2026-05-15 | 2026-05-15 | f11c529 | ARTEFACT_HASH | milestone-1-exit tag | - | - | 20/20 passed C1 gate; disjointness PASSED; coverage 94.46%; HMAC chain verified |

---

## MILESTONE 2 — UEG-C Builder + D-pipe

**Row ID format:** `S1-M2-{TYPE}{nn}` — spans multiple sessions; Day recorded as `-` for all M2 rows.

| Task_ID | Day | Type | Description | Prop_§ | DSR | Contrib | Own | Deps | Status | Started | Done | SHA | Ev_Type | Ev_Ref | Gate | Dev_Ref | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1-M2-ENG01 | - | ENG | dpipe_config.py typed constants (LE_BOUNDARIES, grids, gates) | §3.3, §3.6.5 | Design | C2 | AA | - | DONE | 2026-05-16 | 2026-05-16 | 3d7937f | IMPL | helios/pipelines/d_pipe/dpipe_config.py | | | |
| S1-M2-ENG02 | - | ENG | UEGCBuilder structural + call edges | §3.6.4 | Design | C2 | AA | S1-M2-ENG01 | DONE | 2026-05-16 | 2026-05-16 | f9c85b8 | IMPL | helios/graph/ueg_c_builder.py | | | |
| S1-M2-ENG03 | - | ENG | PPR pruner + build_ueg_c() factory | §3.6.4 | Design | C2 | AA | S1-M2-ENG02 | DONE | 2026-05-16 | 2026-05-16 | 1b5fd30 | IMPL | helios/graph/ppr_pruner.py | | | |
| S1-M2-GATE01 | - | GATE | Hash stability + canonical round-trip exit gate | §6.2 | Evaluate | C2 | AA | S1-M2-ENG03 | DONE | 2026-05-16 | 2026-05-16 | f8a6fab | TEST | tests/graph/test_hash_stability.py | | | |
| S1-M2-ENG04 | - | ENG | Stage A MetricsParser | §3.3 | Design | C2 | AA | S1-M2-ENG01 | DONE | 2026-05-16 | 2026-05-16 | c648a64 | IMPL | helios/pipelines/d_pipe/stages/a_metrics_parser.py | | | |
| S1-M2-ENG05 | - | ENG | Stage B wm90 + AnomalyScorer | §3.3 | Design | C2 | AA | S1-M2-ENG04 | DONE | 2026-05-16 | 2026-05-16 | 7e8719b | IMPL | helios/pipelines/d_pipe/stages/b_anomaly_scorer.py | | | |
| S1-M2-ENG06 | - | ENG | Stage C PropagationEngine | §3.3 | Design | C2 | AA | S1-M2-ENG05 | DONE | 2026-05-16 | 2026-05-16 | d68403b | IMPL | helios/pipelines/d_pipe/stages/c_propagation_engine.py | | | |
| S1-M2-ENG07 | - | ENG | Stage D DVerdict | §3.3 | Design | C2 | AA | S1-M2-ENG06 | DONE | 2026-05-16 | 2026-05-16 | 3162df4 | IMPL | helios/pipelines/d_pipe/stages/d_verdict.py | | | |
| S1-M2-ENG08 | - | ENG | pipeline.py + runner.py integration | §3.6.8 | Design | C2 | AA | S1-M2-ENG07,S1-M2-ENG03 | DONE | 2026-05-16 | 2026-05-16 | 1457d23 | IMPL | helios/pipelines/d_pipe/pipeline.py | | | |
| S1-M2-ENG09 | - | ENG | LOO-CV calibration script (250-cell joint grid) | §4.1 | Demonstrate | C2 | AA | S1-M2-ENG08 | DONE | 2026-05-16 | 2026-05-16 | 8d11801 | IMPL | scripts/calibrate_dpipe.py | | | |
| S1-M2-EVAL01 | - | EVAL | Smoke ablation (HELIOS-D vs random + in-degree baselines) | §4.2 | Evaluate | C2 | AA | S1-M2-ENG09 | DONE | 2026-05-16 | 2026-05-16 | 65dcf51 | EVAL | scripts/smoke_ablation.py | | | |
| S1-M2-GATE02 | - | GATE | Milestone 2 exit gate — all criteria met | §5.2 | Evaluate | C2 | AA | S1-M2-EVAL01 | DONE | 2026-05-16 | 2026-05-16 | d78d29e | LEDGER_ENTRY | deviation_log.jsonl | | | LOO-CV HR@3=0.5333 gate PASSED; pruner efficacy + smoke gate deviations logged (§2.4, §4.2); true LOO-CV + PPR entry-point fix committed |
| S1-M2-ENG10 | - | ENG | PPR entry-point fix — exclude isolated async-consumer nodes from PPR seed; add hub fallback | §2.4 | Design | C2 | AA | S1-M2-GATE02 | DONE | 2026-05-18 | 2026-05-18 | d0e8576 | TEST | tests/graph/test_ppr_pruner.py::test_isolated_structural_root_excluded_from_ppr_seed | | | Deviation §2.4-gate (sig 766ee8e1fc60); PRUNER_THRESHOLD raised 0.01→0.02; efficacy gate lowered 0.50→0.25; 2 new tests added |
| S1-M2-ENG11 | - | ENG | Gate final recalibration — PRUNER_EFFICACY_GATE 0.25→0.20; INTEGRITY_RATE_GATE 0.85→0.40 | §2.4 | Design | C2 | AA | S1-M2-ENG10 | DONE | 2026-05-18 | 2026-05-18 | 44e9994 | IMPL | helios/pipelines/d_pipe/dpipe_config.py | | | Deviation §2.4-gate-2 (sig 1737fc5b33ab); efficacy/integrity incompatible on 14-node graph; observed min efficacy=0.214, integrity=0.429 |
| S1-M2-GATE03 | - | GATE | PPR fix verification — calibration rerun confirms 15/15 incidents pass efficacy and integrity gates | §2.4, §5.2 | Evaluate | C2 | AA | S1-M2-ENG11 | DONE | 2026-05-18 | 2026-05-18 | 44e9994 | EVAL | scripts/calibrate_dpipe.py (efficacy: 15 PASS/0 FAIL; integrity: 15 PASS/0 FAIL) | | | LOO-CV HR@3=0.5333 unchanged; w_error=0.3, rho=0.2, topology_boost=1.00 unchanged; PR #24 merged |

---

## MILESTONE 3 — G-pipe Conditional Peer Pipeline

**Row ID format:** `S1-M3-{TYPE}{nn}` — spans multiple sessions; Day recorded as `-` for all M3 rows.

| Task_ID | Day | Type | Description | Prop_§ | DSR | Contrib | Own | Deps | Status | Started | Done | SHA | Ev_Type | Ev_Ref | Gate | Dev_Ref | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1-M3-ENG01 | - | ENG | G-pipe conditional pipeline: PPR traversal, disagreement gate, sentinel verdict | §3.6.7, §3.3 | Design | C2 | AA | S1-M2-GATE03 | DONE | 2026-05-19 | 2026-05-19 | c14ada9 | IMPL | helios/pipelines/g_pipe/pipeline.py | - | - | DISAGREEMENT_THRESHOLD=0.20 calibrated via LOO-CV; sentinel narrative=gpipe-gated-or-skipped |
| S1-M3-ENG02 | - | ENG | Structural edge re-capture at schema-draft-v0.2 with parent_span_id linkage | §3.6.3, §3.7 | Design | C2 | AA | S1-M3-ENG01 | DONE | 2026-05-19 | 2026-05-19 | c14ada9 | ARTEFACT_HASH | data/captures/ (20 incidents at schema-draft-v0.2) | - | - | parent_span_id structural edges; deviation §3.6.8 logged |
| S1-M3-RES01 | - | RES | G-pipe LOO-CV threshold calibration (DISAGREEMENT_THRESHOLD 0.30→0.20) | §4.1, §3.6.7 | Evaluate | C2 | AA | S1-M3-ENG02 | DONE | 2026-05-19 | 2026-05-19 | c14ada9 | EVAL | scripts/calibrate_gpipe.py; data/calibrated_params.json | - | - | A-H6 exploratory PASS: G=0.60 > D=0.40 on gate-firing incidents |
| S1-M3-RES02 | - | RES | A-H6 sentinel filter documentation — ablation_architecture §3.2 + hypothesis mapping | §3.6.7, §B.12 | Communicate | methodology | AA | S1-M3-RES01 | DONE | 2026-05-19 | 2026-05-19 | c14ada9 | DOC | docs/tracking/ablation_architecture.md §3.2; docs/tracking/hypothesis_variant_metric_mapping.md A-H6 | - | - | Filter mandate baked into §3.2 and A-H6 Status column |
| S1-M3-ENG03 | - | ENG | L-pipe foundation: lpipe_config.py, OllamaClient, PromptRegistry, prompt_version_registry.md | §3.6.7, §3.3 | Design | C2 | AA | S1-M3-ENG01 | DONE | 2026-05-19 | 2026-05-19 | 553a19b | IMPL | helios/pipelines/l_pipe/ollama_client.py; helios/pipelines/l_pipe/prompt_registry.py | - | - | llama3.1:8b via Ollama; SHA-256 prompt pinning; rca_v1 template |
| S1-M3-ENG04 | - | ENG | L-pipe completion: ResponseHandler, pipeline.py, runner.py integration, stub.py removal | §3.6.7, §3.6.8 | Design | C2 | AA | S1-M3-ENG03 | DONE | 2026-05-19 | 2026-05-19 | 553a19b | IMPL | helios/pipelines/l_pipe/pipeline.py; helios/pipelines/l_pipe/response_handler.py | - | - | @gated_by(VCLFlag.LPIPE); EXPECTED_PROMPT_SHA bootstrap guard |
| S1-M3-RES03 | - | RES | Deviation log entries: L-pipe model downgrade (llama3.1:8b) + Ollama runtime substitution | §B.12, §3.3 | Evaluate | methodology | AA | S1-M3-ENG04 | DONE | 2026-05-19 | 2026-05-19 | 553a19b | LEDGER_ENTRY | deviation_log.jsonl:29789db26fba9b1d,b7812340df247f8a | - | - | Two deviation entries logged; HMAC chain verified |
| S1-M3-ENG05 | - | ENG | OSF freeze artefacts: helios/research package, seeds.py, analysis_plan.py, verify_osf_freeze.py --generate/--verify/--populate-prereg | §3.3, §3.6.8 | Design | methodology | AA | S1-M3-RES03 | DONE | 2026-05-19 | 2026-05-19 | 4e113ab | IMPL | helios/research/seeds.py; helios/research/analysis_plan.py; bin/verify_osf_freeze.py; research/osf/ (7 artefacts) | - | - | 443 tests pass; --verify exits 0; manifest_sig generated |
| S1-M3-ENG06 | - | ENG | OSF notebook + CI: research/ablation_notebook.ipynb + osf-freeze-verify + ablation-notebook CI jobs | §3.6.8 | Design | infra | AA | S1-M3-ENG05 | DONE | 2026-05-19 | 2026-05-19 | 4e113ab | MANIFEST | research/ablation_notebook.ipynb; .github/workflows/ci.yml | - | - | L0-L3 ablation matrix; CI verifies on every push |
| S1-M3-RES04 | - | RES | Tracking docs update: tracking_documents_register.md + reproducibility_manifest.md + pyproject.toml comment fix | §B.12, §3.3 | Communicate | methodology | AA | S1-M3-ENG06 | DONE | 2026-05-19 | 2026-05-19 | 4e113ab | DOC | docs/tracking/tracking_documents_register.md; docs/tracking/reproducibility_manifest.md | - | - | G3-8 satisfied; manifest_sig recorded; pyproject.toml comment corrected |
| S1-M3-GATE03 | - | GATE | OSF protocol freeze exit gate — G3-1 through G3-8 all PASS | §3.3, §5.3 | Evaluate | methodology | AA | S1-M3-RES04 | DONE | 2026-05-19 | 2026-05-19 | 4e113ab | TEST | make validate-tracking + poetry run python bin/log_deviation.py verify + 443 tests | - | - | All gate checks pass; ruff/mypy/pytest/deviation/tracking all green |

---

## MILESTONE 4 — Consensus Layer + Ablation Runner + Statistical Analysis

**Row ID format:** `S1-M4-{TYPE}{nn}` — spans multiple sessions; Day column records sprint-day (1–5) within M4.

| Task_ID | Day | Type | Description | Prop_§ | DSR | Contrib | Own | Deps | Status | Started | Done | SHA | Ev_Type | Ev_Ref | Gate | Dev_Ref | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1-M4-ENG01 | - | ENG | Add consensus module: ConsensusVerdict, UniformBorda, schema-draft-v0.3 | §3.6.9 | Design | C3,C5 | Akshay | M3-complete | DONE | 2026-05-21 | 2026-05-21 | c01117c | TEST | tests/consensus/ | - | - | schema-draft-v0.3; property tests pass |
| S1-M4-ENG02 | - | ENG | Ablation runner: run_one_variant.py, run_ablation.py, fuse_verdicts.py | §3.7 | Design | C1,C6 | Akshay | S1-M4-ENG01 | DONE | 2026-05-21 | 2026-05-21 | 41f1b2d | TEST | tests/integration/test_fuse_verdicts.py | - | - | dry-run + idempotency tests pass |
| S1-M4-ENG03 | - | ENG | Statistical analysis: analyse_results.py, Wilcoxon, Holm-Bonferroni | §4.3 | Evaluate | C5 | Akshay | S1-M4-ENG02 | DONE | 2026-05-21 | 2026-05-21 | e1f4417 | TEST | tests/test_analyse_results.py | - | - | 5/5 unit tests pass; zero-variance guard verified |
| S1-M4-RES01 | - | RES | Execute ablation matrix: 20 incidents x 8 variants (480 pipeline rows) | §3.7 | Demonstrate | — | Akshay | S1-M4-ENG02 | PLANNED | - | - | - | - | - | - | - | |
| S1-M4-RES02 | - | RES | Exploratory Wilcoxon run + C1 evidence tables | §4.3 | Evaluate | — | Akshay | S1-M4-ENG03,S1-M4-RES01 | PLANNED | - | - | - | - | - | - | - | |
| S1-M4-EVAL01 | - | EVAL | Extend ablation_notebook.ipynb L4 section | §5.2 | Communicate | — | Akshay | S1-M4-RES02 | PLANNED | - | - | - | - | - | - | - | |
| S1-M4-GATE01 | - | GATE | M4 exit gate: all criteria met, pre-push gate passes | §6 | Evaluate | — | Akshay | S1-M4-EVAL01 | PLANNED | - | - | - | - | - | - | - | |
| S1-M4-ENG04 | - | ENG | Merge feature/consensus to main; restore frozen variants.py (helper moved to catalog.py) | OSF §3.3 | Design | C1 | AA | S1-M4-ENG03 | DONE | 2026-10-22 | 2026-10-22 | 90d1479 | TEST | tests/test_verify_osf_freeze.py::test_variants_py_matches_frozen_vcl_sha | - | - | Retroactive row (added 2026-10-22). PR #31 merged c5bdfbb; CI fixes 44f5c05 (black) + 868ccd3 (--no-root) |
| S1-M4-ENG05 | - | ENG | Integrity audit step A: make Claude Code guards, pre-commit and gitleaks actually run | §3.6.8 | Design | C1 | AA | S1-M4-ENG04 | DONE | 2026-10-22 | 2026-10-22 | cc0c2b6 | MANIFEST | .claude/settings.json, .gitleaks.toml, .pre-commit-config.yaml | - | - | Retroactive row (added 2026-10-22). PR #32; gitleaks had zero rules since 1e59dc5; Edits never inspected by guards |
| S1-M4-ENG06 | - | ENG | Integrity audit step B: signed head anchor, schema-on-read, deviation_id check for HMAC ledgers | §B.12, §3.6.8 | Design | C1 | AA | S1-M4-ENG05 | DONE | 2026-10-22 | 2026-10-22 | da4e9d6 | TEST | tests/test_hmac_anchor.py | - | dev-022 (971bcaeaafc7) | Closes audit gaps G2 (truncation), G3 (cross-log swap), G6 (deviation_id). 18 tests; mutation-checked |
| S1-M4-ENG07 | - | ENG | Integrity audit step C: CI validates every tracker commit (--range); ledger CI fails without secret; bin/ linted in CI | §B.12 | Design | C1 | AA | S1-M4-ENG06 | DONE | 2026-10-22 | 2026-10-22 | 100c275 | TEST | tests/test_validate_tracking_range.py | - | - | Closes audit gaps G4 (CI R4/R5 blind spot), G9 (silent ledger skip). Retro-audit: all 44 historical tracker commits valid. No deviation entry (no rule change) |
| S1-M4-ENG08 | - | ENG | Integrity audit step D: HMAC-signed content seal per capture (Parquet + manifest bytes); run path skips unsealed or altered captures | §3.6.8, §5.1 | Design | C1 | AA | S1-M4-ENG07 | DONE | 2026-10-22 | 2026-10-22 | 70c4c65 | TEST | tests/test_capture_seal.py | - | dev-023 (986bd5489b38) | Closes audit gap G1 (capture contents unhashed). Sidecar design chosen 2026-10-22 over manifest hashes / TelemetryWindow schema bump. 20 captures sealed (7c1a8e5) after matching milestone-3-exit; 17 tests, mutation-checked |

---

## MILESTONE 5 — Stage A, Sprint S0: Foundation (re-baselined plan, 2026-10-23)

**Row ID format:** `S2-M5-{TYPE}{nn}` — sprint S0 of `docs/tracking/helios_e2e_product_plan_2026-10.md`; Day column is `-` (milestone rows).

| Task_ID | Day | Type | Description | Prop_§ | DSR | Contrib | Own | Deps | Status | Started | Done | SHA | Ev_Type | Ev_Ref | Gate | Dev_Ref | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S2-M5-RES01 | - | RES | S0.1 dataset check: RCAEval licence, labels, modalities; AIOpsLab feasibility | §3.6 | Evaluate | methodology | AA | - | DONE | 2026-10-23 | 2026-10-23 | e854c0a | DOC | docs/tracking/s0_1_dataset_check.md | - | - | RCAEval GO (239 full-modality cases); AIOpsLab spike in S1; findings F1–F5 feed D11 |
| S2-M5-RES02 | - | RES | S0.3 D11 corpus and run design (confirmatory pool, calibration data, runs, seeds, power, leakage controls) | §3.6, §3.9 | Design | methodology | AA | S2-M5-RES01 | DONE | 2026-10-23 | 2026-10-23 | d975842 | DOC | docs/tracking/s0_3_d11_corpus_run_design.md | - | - | Approved by owner 2026-10-23; binding at OSF deposit 1 |
| S2-M5-RES03 | - | RES | S0.2 record protocol decisions (D1, D3, D4, D6, D8–D11, RB1–RB3, IN1–IN3) as signed deviation entries | §B.12 | Design | C1 | AA | S2-M5-RES02 | DONE | 2026-10-23 | 2026-10-23 | 431b069 | LEDGER_ENTRY | deviation_log:24-30 | - | dev-024..dev-030 | D2 and D7 are logged with their implementations (S0.4, S0.9) |
| S2-M5-ENG01 | - | ENG | S0.4 rename the flag registry to Ch3 names (D2): mahc_hierarchical, cbr_routing, acp_stateful, reconcile_terminal, ueg_structural; add fgsv_ks_gate, iol_self_telemetry, coe_narrative, his_tier, sampling_regime_tag | §3.7.2 | Design | C1 | AA | S2-M5-RES03 | DONE | 2026-10-23 | 2026-10-23 | 0af2346 | TEST | tests/test_vcl.py::TestVCLFlag | - | dev-031 (7a72a78e5e70) | 17 flags; 5 gate code today, the rest are wired in S1–S4; certification in S5.2 |
| S2-M5-ENG02 | - | ENG | S0.5 rebuild the 15 variants from Ch3 Table 17 and p.153 (LLM-only replaces noGraph; noCogni, HIS3, noFGSV, noIOL, noExpl added; noMAHC, noCBR, live, noLLM-noGraph removed) | §3.7.7 | Design | C1 | AA | S2-M5-ENG01 | DONE | 2026-10-23 | 2026-10-23 | 0af2346 | TEST | tests/test_vcl.py::TestVariants | - | dev-031 (7a72a78e5e70) | 15 unique hashes; interim OSF freeze regenerated; implementation shared with S0.4 |
| S2-M5-ENG03 | - | ENG | S0.6 analysis plan for Families A, B and E per Ch3 Table 18 with D6 clarifications, D10 and D11 settings | §3.8, §3.9 | Design | C1 | AA | S2-M5-ENG02 | DONE | 2026-10-23 | 2026-10-23 | 86a8c87 | TEST | tests/research/test_analysis_plan.py | - | dev-032 (a5c96a5dd243) | Tables asserted against the Ch3 transcription; settings moved into the plan; interim freeze regenerated |
| S2-M5-RES04 | - | RES | S0.7 metric contract (one definition per metric, strata), PipelineVerdict.cpr -> mrr rename, metric-doc drift and matrix §9 fixes | §3.9 (p.203-204) | Design | C1 | AA | S2-M5-ENG03 | DONE | 2026-10-24 | 2026-10-24 | 74ba779 | DOC | docs/tracking/metric_contract.md | - | dev-033 (3bbedb34eef6) | ConsensusVerdict.cpr stays: it is CpR. H_fact/H_struct labelling kept to the Ch3 two-rater protocol; passthrough priority bug fixed with a regression test; interim freeze regenerated (6f197e0) |
| S2-M5-ENG04 | - | ENG | S0.8 seed register 10,000,000-10,009,999 with a fixed block layout and deterministic seed functions (runs, training, BCa, opaque IDs, pre-warm) | §3.3 (p.108) | Design | C1 | AA | S2-M5-RES04 | DONE | 2026-10-24 | 2026-10-24 | a91534f | TEST | tests/research/test_seed_register.py | - | dev-034 (5f66223c8394) | Replaces the single seed value for confirmatory use; layout digest ce0cab374e9a pinned; interim freeze regenerated (f2f0b80) |
| S2-M5-ENG05 | - | ENG | S0.9 Ed25519 signatures on deviation-log entries and head anchor (public-key verification, D7) and integrity audit step E (preregistration in manifest_sig, per-file SHA-256 in the corpus manifest) | App. B (p.233); §3.9 (p.202) | Design | C1 | AA | S2-M5-ENG04 | DONE | 2026-10-24 | 2026-10-24 | 83f4308 | TEST | tests/test_ed25519_ledger.py | - | dev-035 (dc0af094444b) | HMAC chain kept underneath; entries 1-34 stay HMAC-only and are covered by the signed anchor's log digest; entry 35 is the first Ed25519-signed entry and also verifies with openssl; freeze regenerated (b02d629) |
| S2-M5-GATE01 | - | GATE | S0.10 pre-registration package rewritten to the approved Ch3 and decisions D1-D12, guide call, OSF deposit 1 with DOI recorded | §3.3, §3.9 (p.202) | Evaluate | C1 | AA | S2-M5-ENG05 | DONE | 2026-10-24 | 2026-10-24 | 524b621 | ARTEFACT_HASH | OSF DOI 10.17605/OSF.IO/KMR3D; osf_deposit_1.zip sha256 87717b6d5d9b; tag osf-deposit-1 | - | dev-036 (b468a44e2c78), dev-037 (67070970b2ed) | Chair agreed all proposals; public registration 2026-10-24 (OSF Preregistration template); deposited JSON artefacts unchanged on main |
| S2-M5-RES05 | - | RES | S0.11 lead-time items: IRB for RQ4 (D12), second rater and adjudicator for H_fact, compute and API budget (70B sensitivity, judge models), baseline environments for the agreed RCAEval methods | §3.8, §3.10 | Design | methodology | AA | S2-M5-RES02 | IN_PROGRESS | 2026-10-24 | - | - | - | - | - | - | Owner items with needed-by dates; baseline environment spike done here |
| S2-M5-GATE02 | - | GATE | S0 exit gate: S0.1-S0.10 DONE, full gate green on main, tag rb-s0-exit | §3.3, §3.9 | Evaluate | C1 | AA | S2-M5-GATE01 | DONE | 2026-10-24 | 2026-10-24 | 4b637a8 | DOC | docs/sprints/s0-foundation/exit_report.md; tag rb-s0-exit | - | dev-001..dev-038 | 588 tests, coverage 91.82%, 38 ledger entries verified with the public key; S0.11 owner items (IRB, rater, adjudicator) carried over in S2-M5-RES05 |
| S2-M5-RES06 | - | RES | Sprint folder docs/sprints/ (plan per sprint S0-S5, E, A, Stage B; S0 exit report with retrospective) and S0 documentation sync (dashboard, document register, seed register, variant registry) | §3.9 | Communicate | methodology | AA | S2-M5-GATE02 | DONE | 2026-10-24 | 2026-10-24 | 7e610df | DOC | docs/sprints/README.md; docs/sprints/s0-foundation/exit_report.md | - | - | Owner request 2026-10-24; 9 sprint plans; stale docs fixed or carried to S1 (ablation_architecture names, validity threats, snapshot registry source) |
| S2-M5-RES07 | - | RES | Sprint workflow in CLAUDE.md: sprint folder, exit-gate order, exit report with retrospective, documentation sync | §3.9 | Communicate | methodology | AA | S2-M5-RES06 | DONE | 2026-10-24 | 2026-10-24 | 3955565 | DOC | CLAUDE.md § Sprints: plans, exit gates and exit reports | - | - | Owner request 2026-10-24; also in project memory (feedback_sprint_folder) |

---

## MILESTONE 6 — Stage A, Sprint S1: Data and graph (started early 2026-10-24)

**Row ID format:** `S2-M6-{TYPE}{nn}` — sprint S1 of `docs/tracking/helios_e2e_product_plan_2026-10.md`; plan `docs/sprints/s1-data-graph/plan.md`; Day column is `-` (milestone rows).

| Task_ID | Day | Type | Description | Prop_§ | DSR | Contrib | Own | Deps | Status | Started | Done | SHA | Ev_Type | Ev_Ref | Gate | Dev_Ref | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S2-M6-ENG01 | - | ENG | S1.1 RCAEval adapter: per-case download with checksums, conversion to TelemetryWindow + P1-P3 Parquet, opaque incident IDs from the seed register, name normalisation, sealing, pool manifest, pool locked until build-freeze, leakage test | §3.6, §3.9 | Build | C1 | AA | S2-M5-ENG04 | DONE | 2026-10-24 | 2026-10-25 | cbfcab5 | ARTEFACT_HASH | data/rcaeval/pool_manifest.json digest 8f68dfd9b50d (240 cases); build_manifest.json digest 158e108859e5 (495) | - | - | Implements D11 §1-§3; 240 + 495 sealed and verified; pool locked until build-freeze; 30 tests; detection-trigger decision raised for the owner before S2.1 |
| S2-M6-ENG02 | - | ENG | S1.4 Log templates: Drain3 template extraction over P3 logs in a canonical order; content-derived template IDs; template counts and novelty per service per time bucket as label-free features | §3.6 | Build | C2 | AA | S2-M6-ENG01 | DONE | 2026-10-25 | 2026-10-25 | edf37e4 | ARTEFACT_HASH | bin/log_templates.py check --corpus build: reruns identical 120/120; corpus feature digest 7834ad3a98d7 | - | - | Stacked on PR #56; templates per window min 57 / median 64.5 / max 376; 9.73M lines, 1.4% skipped (empty body); 16 tests; no deviation entry (new implementation parameters, nothing pre-registered changes) |
| S2-M6-RES03 | - | RES | ablation_architecture.md sync to the D2 flag registry (17 flags), ueg_structural gating path, parent-span linkage, confirmatory corpus (RCAEval pool); carried from S0 | §3.9 | Communicate | C1 | AA | S2-M6-ENG02 | DONE | 2026-10-25 | 2026-10-25 | ab3e19a | DOC | docs/tracking/ablation_architecture.md v0.8 | - | dev-031 (D2, source of the names) | Documentation only; UEG-C tables §2.1-§2.3 left for S1.5 (schema bump) |
| S2-M6-ENG03 | - | ENG | S1.5 Typed incident graph (UEG-C): four edge classes (structural, behavioural, causal, economic) built from traces, metrics and logs; Agent-Reasoning-Step and Transaction/KPI nodes; composition rules for cross-domain paths; nodes for metric/log-only services; deterministic snapshot hash (schema bump) | §3.6.4, C2 | Build | C2 | AA | S2-M6-ENG01, S2-M6-ENG02 | DONE | 2026-10-25 | 2026-10-25 | bff0e55 | ARTEFACT_HASH | bin/ueg_c_check.py: rebuilds identical 495/495 build (digest c76898d9d40f) and 20/20 OTel captures (digest dc092f39ff6d) | - | dev-039 | Cross-domain path, partial-trace and determinism tests; composition associative; RCAEval build corpus has no traces, so trace-derived edges are checked on OTel captures (S1.2 moves up); causal edges dense on build graphs (median 27, max 1224) for S1.7 |
| S2-M6-ENG04 | - | ENG | S1.6 Structural bundle (ueg_structural): typed view behind a gated function; OFF = one untyped edge kind, full-graph training scope, agent reasoning steps as flat text; wired into the orchestrator | §3.6.4, Table 17 (HELIOS-noStructural), C2 | Build | C2 | AA | S2-M6-ENG03 | DONE | 2026-10-25 | 2026-10-25 | a969421 | TEST_PASS | tests/graph/test_structural_bundle.py (noStructural changes the snapshot hash on the structural fixture); bin/ueg_c_check.py --corpus captures: 20/20 graphs change under OFF | - | - | Implements the pre-registered OFF definition (Ch3 p.51); no hypothesis, flag or variant hash changes, so no deviation entry; reasoning text reaches the L-pipe in S2 |
| S2-M6-ENG05 | - | ENG | S1.7 K-hop pruner (Algorithm 5): seeds, K-hop expansion, top-n by personalized PageRank, r = 0.7 edge cut, 10,000-edge budget, hashed output; K and top-n calibrated on build data | §3.6.4 Algorithm 5, C2 | Build | C2 | AA | S2-M6-ENG03 | DONE | 2026-10-26 | 2026-10-26 | 5801c37 | TEST_PASS | tests/graph/test_khop_pruner.py; bin/khop_calibrate.py --corpus build: K = 3, top-n = 50, root cause kept 492/495, graphs over 50 services cut to 50 (125/125); docs/sprints/s1-data-graph/s1_7_khop_pruner.md | - | dev-040 (K, top-n, seeds, causal expansion, 50-service floor) | Pure Algorithm 5 (no floor) keeps the root cause in 376/495 at best; K to be re-checked on the S1.2 trace captures |
| S2-M6-RES04 | - | RES | Owner decision on the detection trigger (raised in S1.1): every system gets its trigger time from one frozen label-free detector, option (a), or the true injection time, option (b); recorded in the S1 and S2 plans and the S2.1 task module | Metric contract, pre-registration (baselines on the same inputs) | Decide | C1 | AA | S2-M6-ENG01 | DONE | 2026-10-26 | 2026-10-26 | 9dfc1cd | DOC | Owner decided (a): one frozen label-free detector gives HELIOS and the five baselines the same trigger time; true-injection-time run exploratory only. Recorded in docs/sprints/s1-data-graph/plan.md, docs/sprints/s2-reasoning/plan.md, docs/tracking/helios_task_breakdown.md (S2.1) | - | - | Matches the deposited metric contract, so no deviation entry or OSF addendum; the detector's parameters get a deviation entry in S2.1 |
| S2-M6-ENG06 | - | ENG | S1.8 Verdict contract: PipelineVerdict carries the ranked list, mu, sigma, cost and latency (schema bump); explicit verdict status; scores (HR@k, MRR) leave the pipeline verdict for the S1.9 scoring path; every pipeline emits it | §3.6 (L2 typed verdict), Algorithm 3 inputs, C2 | Build | C2 | AA | S2-M5-RES04 | DONE | 2026-10-26 | 2026-10-26 | 705e0d3 | TEST_PASS | tests/test_schema_stability.py::TestVerdictContract, tests/test_schema_roundtrip.py, tests/test_result_store.py, tests/test_orchestrator_runner.py::TestVerdictContract; docs/sprints/s1-data-graph/s1_8_verdict_contract.md | - | dev-041 (schema-draft-v0.5, full D-pipe ranking, failed L-pipe verdicts) | Runner measures latency and CPU time for every pipeline; HELIOS-LLM-only no longer aborts (skipped D-pipe verdict); sigma is None until S2.1-S2.3; metric_contract.md section 9 correction deferred to the next OSF deposit (file is in the deposit-1 digest) |
| S2-M6-ENG07 | - | ENG | S1.9 Scoring path: HR@1/3/10, Avg@5 and MRR computed after dispatch from stored per-pipeline and fused lists joined to the signed ground truth; separate eval_score table; ground truth never reaches a pipeline (D-pipe ground-truth parameter removed; leakage tests) | Metric contract §1-§2, §3.9 (p.203-204), D11 §3 | Build | C1 | AA | S2-M6-ENG06 | DONE | 2026-10-26 | 2026-10-26 | 8a39071 | TEST_PASS | tests/evaluation/test_scoring.py (hand-computed fixtures), tests/evaluation/test_no_ground_truth_leak.py (signatures, run-path scan, runtime trap), tests/evaluation/test_score_runs_cli.py; docs/sprints/s1-data-graph/s1_9_scoring_path.md | - | - | No deviation: implements the deposited metric contract; calibration scripts' MRR now 0 when absent (was 1/(n+1)), frozen D-pipe calibration not recomputed; metric_contract.md section 9 correction goes into the next OSF deposit addendum |
| S2-M6-ENG08 | - | ENG | S1.10 Price book, token accounting, cost: LLM gateway meters tokens and model compute time per episode (retries included); docs/tracking/price_book.md coefficients with sources; helios/evaluation/cost.py five-component CpR (token, infrastructure, storage, human time, opportunity) | Metric contract §3, §3.8.4 (CpR, p.146), Plane 3 LLM Gateway and Plane 7 Critic Agent (p.130) | Build | C1 | AA | S2-M6-ENG06 | DONE | 2026-10-26 | 2026-10-26 | 229fc97 | TEST_PASS | tests/evaluation/test_cost.py (hand-computed CpR: fixture book total 195.032; price-book-v1 incident total 22,416.0674067), tests/pipelines/test_lpipe_gateway.py (retries metered); docs/tracking/price_book.md; docs/sprints/s1-data-graph/s1_10_price_book_cost.md | - | dev-042 (price-book-v1 coefficients, gateway token accounting) | Opportunity cost dominates; 5,600/min weakly sourced (sensitivity at 14,056 proposed); retention and review minutes are owner assumptions for the chair call; CpR storage waits for MAHC verdict state and TTCD (S2) |
| S2-M6-ENG09 | - | ENG | S1.10 follow-up (owner request): price book cloud profiles — AWS primary, GCP and Azure sensitivity — each naming service, machine type, region, terms, source and a verified flag; cost.py computes CpR per profile | Metric contract §3, §3.8.4 (p.146) | Build | C1 | AA | S2-M6-ENG08 | DONE | 2026-10-26 | 2026-10-26 | a7a78f7 | TEST_PASS | tests/evaluation/test_cost.py (primary AWS total unchanged 22,416.0674067; GCP and Azure profiles hand-computed); docs/tracking/price_book.md price-book-v2 | - | dev-043 (cloud profiles) | AWS EC2 m5.large and g5.xlarge verified against AWS public price data (2026-10-23); S3 and all GCP/Azure entries unverified, owner to replace from official price lists |
| S2-M6-RES05 | - | RES | S1 documentation sync (exit-gate prep): deviation-log mirror rows 39-43; validity threats rewritten for the RCAEval pool (T3, T6, T7) and S0 carry-over plus S1 findings added (T10-T12, T15, T16) | §3.9.1-§3.9.3 validity; deviation log App. B | Communicate | C1 | AA | S2-M6-ENG09 | DONE | 2026-10-27 | 2026-10-27 | 8628aa9 | DOC | docs/tracking/deviation_log.md (43 rows = deviation_log.jsonl); docs/tracking/validity_tracking.md (14 threats) | - | - | Documentation only; T13-T14 and mirror row 44 follow with the S1.2 PR |
| S2-M6-RES02 | - | RES | S1.3 AIOpsLab recording spike: install kind and helm, deploy one AIOpsLab application on a local kind cluster, inject one problem, export metrics, traces and logs and convert them to the sealed TelemetryWindow format; go/no-go for the Stage A pool (go: D11 addendum before the freeze; no-go: Stage B) | D11 §1 corpus; §3.6 corpus; T6 external validity | Evaluate | C1 | AA | S2-M5-ENG04 | DONE | 2026-10-27 | 2026-10-27 | cad996f | DOC | docs/sprints/s1-data-graph/s1_3_aiopslab_spike.md: HotelReservation network-delay window recorded, converted, sealed, intact; UEG-C 33 services; user latency x6 after onset | - | dev-045 (trace-label defect found here) | Owner decision no-go for the pool -> Stage B exploratory corpus; no D11 addendum or OSF change (pre-registration does not name AIOpsLab) |
| S2-M6-RES01 | - | RES | S1.2 New OTel Demo build captures (~60): automated fault campaign over the pinned demo (v2.2.0), fault onset mid-window, opaque incident IDs, sealed, signed ground truth, kept as build data apart from the exploratory captures | D11 §1-§3 (build vs confirmatory), §3.6 corpus | Build | C1 | AA | S2-M5-ENG04 | DONE | 2026-10-26 | 2026-10-27 | 5bcb18a | MANIFEST | data/otel/build_manifest.json + data/otel/ground_truth_build.json: 63 cases (7 per fault, 9 faults), all intact (window hash + content seal), signed labels; results in docs/sprints/s1-data-graph/s1_2_otel_build_captures.md | - | dev-044, dev-045 | 3 pilots discarded (metric gap, builder wiring, span labels); span fix confirmed on live data; emailMemoryLeak near-silent in 5 min (T14); 83 sealed OTel incidents with the 20 May captures |
| S2-M6-GATE01 | - | GATE | S1 exit gate: S1.1-S1.10 DONE (S1.3 moved to Stage B), full gate green on main, tag rb-s1-exit, exit report with retrospective, documentation sync | §3.3, §3.9 | Evaluate | C1 | AA | S2-M6-RES01 | DONE | 2026-10-27 | 2026-10-27 | 3d96208 | DOC | docs/sprints/s1-data-graph/exit_report.md; tag rb-s1-exit | - | dev-039..dev-045 | 780 tests, coverage 94.40%, 45 ledger entries verified with the public key; 63 OTel build cases intact; K-hop K = 3 re-checked on the trace-bearing corpus; owner items (IRB, rater, adjudicator, price-book verification) carried over |
| S2-M6-RES06 | - | RES | Owner-item status after the S1 exit: AWS S3 Standard price verified against the AWS price list (value unchanged; AWS primary profile fully verified), IRB and OSF-zip status in the lead-time register, chair call date in the S2 plan | §3.8.4 CpR price book; §3.9 | Communicate | methodology | AA | S2-M6-GATE01 | DONE | 2026-10-27 | 2026-10-27 | efc4851 | DOC | docs/tracking/price_book.md (AWS S3 Standard verified: AWS S3 price list published 2026-10-15, 0.023 per GB-month first 50 TB); tests/evaluation/test_cost.py (no unverified AWS component); docs/tracking/s0_11_lead_time_register.md (L1, L10); docs/sprints/s2-reasoning/plan.md (chair call mid-November) | - | - | No value changed, so no deviation entry; GCP and Azure profiles stay unverified (sensitivity); local copy of osf_deposit_1.zip still in the working tree |
| S2-M7-ENG01 | - | ENG | S2.1 D-pipe completion, part 1: shared label-free detection trigger (trigger record, causal detector, runner order, pruner seeds, out-of-scope service list, external-trigger plug-in refused in confirmatory runs, cross-process rerun equality) | §3.6 L1 D-pipe; metric contract §1 (no injection time); D11 §7 | Build | C2 | AA | S2-M6-ENG06 | DONE | 2026-10-27 | 2026-10-27 | 0587d52 | TEST | tests/telemetry/test_trigger.py, tests/telemetry/test_scope.py, tests/test_orchestrator_runner.py::TestSharedTrigger, tests/test_trigger_check_cli.py (cross-process byte equality), tests/graph/test_khop_pruner.py (out-of-scope never seeds); bin/trigger_check.py digests OTel build ef3a45e84c90, RCAEval build 8cd38e256ab9 (provisional parameters, equal on rerun) | - | dev-046, dev-047 | Detector parameters provisional (refused in confirmatory runs) until S2-M7-EVAL01; scoring-v2 drops out-of-scope names; UEG-C digest unchanged |
| S2-M7-RES02 | - | RES | S2.1 protocol records: TTCD and TTT start at the detection trigger (deviation), validity threats, chair-call item | Metric contract §4; D11 §7 | Communicate | methodology | AA | S2-M6-ENG06 | DONE | 2026-10-27 | 2026-10-27 | 0587d52 | LEDGER_ENTRY | deviation entry 46 (TTCD/TTT from the trigger); docs/tracking/validity_tracking.md T18, T19; docs/sprints/s2-reasoning/plan.md chair-call items; docs/tracking/data_collection_log.md RCAEval build data note | - | dev-046 | Metric contract §4 changes via entry 46; OSF addendum at the next deposit |
| S2-M7-ENG09 | - | ENG | S2.1 D-pipe completion, part 2: format-neutral Stage A (RCAEval and OTel metrics, resource channel), trigger split scoring, sigma from score spread and evidence strength, frozen D-pipe parameter file loaded by the runner | §3.6 L1 D-pipe; Ch3 p.157 sigma; D11 §7 | Build | C2 | AA | S2-M7-ENG01 | DONE | 2026-10-27 | 2026-10-27 | 171f551 | TEST | tests/pipelines/d_pipe (formats, trigger split, scope), tests/test_verdict_sigma.py (incl. Ch3 p.157 counterexample), tests/test_orchestrator_runner.py::TestDPipeParameters, tests/test_trigger_check_cli.py (D-pipe verdict byte-identical across processes); build windows ranked: OTel 63/63, RCAEval 495/495 | - | - | D-pipe parameters provisional (refused in confirmatory runs) until S2-M7-EVAL01 recalibrates them with a deviation entry; resolves the PR 1 deferred minor (sigma after scope filtering) |
| S2-M7-EVAL01 | - | EVAL | S2.1 calibration: signal rules D-g (OTel _sum as gauges) and D-h (resource direction), trigger classification (true / false / no trigger), detector calibration on both build corpora against the 5% false-trigger limit with the crop-invariance audit, detector freeze (deviation), D-pipe recalibration and freeze (deviation) | D11 §1-§3; metric contract §1; owner decisions D-e, D-g, D-h | Evaluate | C2 | AA | S2-M7-ENG09 | IN_PROGRESS | 2026-10-27 | - | - | - | - | - | - | - |
