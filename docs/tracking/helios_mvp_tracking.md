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
| S0-D4-ENG01 | 4 | ENG | Clone OTEL Demo at fixed Git tag; record tag+SHA in dev log | §3.7 | Demonstrate | infra | AA | - | IN_PROGRESS | 2026-05-14 | - | - | LEDGER_ENTRY | deviation_log:NNN | EG2 | - | Tag=2.2.0 SHA=b74a7bc pinned in external/; awaiting commit |
| S0-D4-ENG02 | 4 | ENG | docker compose up -d; verify all services healthy | §3.7 | Demonstrate | infra | AA | S0-D4-ENG01 | IN_PROGRESS | 2026-05-14 | - | - | ARTEFACT_HASH | docker-compose.yml | EG2 | - | Evidenced by 5 successful captures; awaiting commit |
| S0-D4-ENG03 | 4 | ENG | Identify fault-injection mechanism (featureflagservice) | §3.7 | Demonstrate | infra | AA | S0-D4-ENG02 | IN_PROGRESS | 2026-05-14 | - | - | DOC | docs/fault_catalogue_v0.md | EG2 | - | fault_catalogue_v0.md written with 5 incidents + naming convention; awaiting commit |
| S0-D4-ENG04 | 4 | ENG | telemetry/otel_demo_capture.py: 5min window → Parquet | §3.7 | Design | infra | AA | S0-D3-ENG03 | IN_PROGRESS | 2026-05-14 | - | - | TEST | tests/test_capture.py::test_window | - | - | 25 tests green; helios/telemetry/otel_demo_capture.py implemented; awaiting commit |
| S0-D4-ENG05 | 4 | ENG | Capture 5 Parquet recordings, ≥3 fault classes | §3.7 | Demonstrate | infra | AA | S0-D4-ENG04 | IN_PROGRESS | 2026-05-14 | - | - | ARTEFACT_HASH | data/captures/*.parquet | EG2 | - | 5 directories recorded: adhc/cart/imgsl/pcat/rcf; awaiting commit |
| S0-D4-ENG06 | 4 | ENG | telemetry/parquet_reader.py: read + validate against schema | §3.7 | Design | infra | AA | S0-D4-ENG04 | IN_PROGRESS | 2026-05-14 | - | - | TEST | tests/test_capture.py::test_validate | EG2 | - | helios/telemetry/reader.py; 8 reader tests green; bin/verify_captures.py added; awaiting commit |
| S0-D4-EVAL01 | 4 | EVAL | Verify 5 Parquets: schema-valid, non-empty, fault-active | §3.7 | Evaluate | infra | AA | S0-D4-ENG05 | IN_PROGRESS | 2026-05-14 | - | - | DOC | data/captures/data-capture-steps.md | EG2 | - | verify_captures.py all-OK; hash round-trip confirmed; awaiting D4 code commit |

---

## DAY 5 — Snapshot Registry + Null Stubs + E2E + Exit Gate

| Task_ID | Day | Type | Description | Prop_§ | DSR | Contrib | Own | Deps | Status | Started | Done | SHA | Ev_Type | Ev_Ref | Gate | Dev_Ref | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S0-D5-ENG01 | 5 | ENG | vcl/snapshot_registry.py: register/verify (append-only JSONL) | §6.2, §3.6.5 | Design | C1 | AA | S0-D3-ENG01 | DONE | 2026-05-13 | 2026-05-13 | f628102 | TEST | tests/test_snapshot_registry.py | EG4 | - | 15 tests; content-addressable JSONL |
| S0-D5-ENG02 | 5 | ENG | pipelines/{g,l}_pipe/stub.py: gated null stubs | §3.6.7 | Design | infra | AA | S0-D1-ENG05 | DONE | 2026-05-13 | 2026-05-13 | f628102 | TEST | tests/test_pipelines.py::test_gated | - | - | 7 tests; g_pipe + l_pipe stubs |
| S0-D5-ENG03 | 5 | ENG | store/result_store.py: DuckDB insert + inclusion-rate helper | §3.7 | Design | infra | AA | S0-D3-ENG05 | DONE | 2026-05-13 | 2026-05-13 | f628102 | TEST | tests/test_result_store.py | EG4 | - | 11 tests; DuckDB insert + inclusion_rate() |
| S0-D5-ENG04 | 5 | ENG | tests/test_e2e_smoke.py: full pipeline (Parquet → DuckDB row) | §6.1-§6.4 | Evaluate | C1 | AA | S0-D5-ENG01,S0-D5-ENG03 | DONE | 2026-05-13 | 2026-05-13 | f628102 | TEST | tests/test_e2e_smoke.py::test_full_pipeline_exploratory_row_inserted | EG4 | - | 4 tests; EG4 binding integration test |
| S0-D5-RES01 | 5 | RES | ablation_architecture.md §3 (snapshot registry, stubs, flow) | §6.2 | Communicate | C1 | AA | S0-D5-ENG01 | IN_PROGRESS | 2026-05-14 | - | - | DOC | docs/tracking/ablation_architecture.md | EG6 | - | §3.0 written (frozen); §3.1-3.3 sub-stubs added; v0.3 |
| S0-D5-RES02 | 5 | RES | osf_protocol_v0.8.md: full structure populated | §3 (all) | Communicate | methodology | AA | S0-D2-RES01 | IN_PROGRESS | 2026-05-14 | - | - | DOC | docs/osf_protocol_v0.md | EG6 | - | D2-RES01 delivered full structure ahead of schedule; v0.md has all 7 sections + deferred stubs marked [STAGE-N]; v0.8 naming was a planning artifact |
| S0-D5-GATE01 | 5 | GATE | EG1: VCL hash-consistency check (100%) | §6.1 | Evaluate | C1 | AA | S0-D2-ENG05 | IN_PROGRESS | 2026-05-14 | - | - | TEST | pytest -k test_vcl | EG1 | - | 3 mutations + 1 valid manifest |
| S0-D5-GATE02 | 5 | GATE | EG2: 5 Parquet recordings valid | §3.7 | Evaluate | infra | AA | S0-D4-EVAL01 | IN_PROGRESS | 2026-05-14 | - | - | DOC | docs/fault_catalogue_v0.md | EG2 | - | Recordings done; blocked on D4 code commit for SHA |
| S0-D5-GATE03 | 5 | GATE | EG3: Schema stability round-trip GREEN | §6.2 | Evaluate | C1 | AA | S0-D3-ENG04 | IN_PROGRESS | 2026-05-14 | - | - | TEST | pytest tests/test_schema_stability.py | EG3 | - | Identical SHA-256 |
| S0-D5-GATE04 | 5 | GATE | EG4: E2E smoke result row in DuckDB | §6.1-§6.4 | Evaluate | C1 | AA | S0-D5-ENG04 | IN_PROGRESS | 2026-05-14 | - | - | TEST | tests/test_e2e_smoke.py | EG4 | - | evaluation_phase=exploratory |
| S0-D5-GATE05 | 5 | GATE | EG5: Deviation log ≥1 signed entry (target 3+) | §B.12 | Evaluate | C1 | AA | S0-D2-EVAL01 | IN_PROGRESS | 2026-05-14 | - | - | LEDGER_ENTRY | deviation_log.jsonl | EG5 | - | Genesis + HMAC + tag entries |
| S0-D5-GATE06 | 5 | GATE | EG6: Spine memo + ablation arch + OSF v0.8 committed | §6.1 | Evaluate | methodology | AA | S0-D5-RES02 | PLANNED | - | - | - | DOC | docs/*.md (3 files) | EG6 | - | Blocked: osf_protocol_v0.8.md missing; ablation_architecture.md §3 is a stub |
| S0-D5-EVAL01 | 5 | EVAL | Stage 0 W1 exit gate sign-off entry | §B.12 | Evaluate | C1 | AA | S0-D5-GATE01..06 | PLANNED | - | - | - | LEDGER_ENTRY | deviation_log:NNN | EG5 | - | PASS or CARRY_OVER decision |

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
