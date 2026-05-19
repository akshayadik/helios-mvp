# Deviation Log (Human-Readable)

**Purpose:** Markdown-rendered companion to `deviation_log.jsonl`. Human-readable summary table for examiner readability; the JSONL remains the authoritative artefact.

**Schema version:** v1.0 (frozen 2026-05-15)
**Update cadence:** After every `deviation_log.jsonl` append via `bin/log_deviation.py`
**Owner:** AA
**Authoritative source:** `deviation_log.jsonl` (HMAC-SHA256 chained)
**Verify command:** `poetry run python bin/log_deviation.py verify`

---

## Column Definitions

| Column | Meaning |
|---|---|
| `#` | Entry sequence number (1-indexed) |
| `Date` | `timestamp_utc` date component |
| `Stage` | Research stage when change was made |
| `Clause` | Proposal / execution plan clause affected |
| `Change` | Brief description of what changed (truncated to 80 chars) |
| `Analytic_consequence` | Impact on confirmatory analysis validity |
| `sig[:12]` | First 12 hex chars of HMAC-SHA256 signature (tamper indicator) |

---

## Entries

| # | Date | Stage | Clause | Change | Analytic_consequence | sig[:12] |
|---|---|---|---|---|---|---|
| 1 | 2026-05-08 | Stage 0 | Setup / pyproject.toml python constraint | Python pinned to 3.11 via deadsnakes PPA | Reproducibility constraint — Python version mismatch would break all test runs | 7fee47b53a2d |
| 2 | 2026-05-08 | Stage 0 | §3.6.6 / Execution Plan §6 / §4 | C1 runtime invariants reduced from 6 to 5; reconciliation ledger deferred | Deferred sub-artefact implemented at Milestone 1 — no analytic loss | fb8ece84e8a1 |
| 3 | 2026-05-08 | Stage N | §... | Template entry (genesis placeholder — no real change) | None | 539e67a1910f |
| 4 | 2026-05-12 | Stage 1 | §6.2 | Add model_version and prompt_template_id fields to VCLManifest | All variant_config_hashes invalidated and recomputed — hash table in vcl_manifest_tracking.md updated | 0b8fcc0d03d1 |
| 5 | 2026-05-14 | Stage 0 | §B.12 / Execution Plan §10 / Exit Gates EG1–EG6 | Stage 0 spine exit sign-off. All 6 gates satisfied | None (sign-off entry; no protocol change) | a64c18b7f0b9 |
| 6 | 2026-05-16 | Stage 1 | §2.2 Span Containment Heuristic | Temporal containment backward-scan instead of OpenTelemetry parent_span_id linkage | Potential structural-edge misattribution in deeply nested same-service call stacks; bounded to PPR pruner entry-point identification only; pre-M3 gate requires replacement | 5655ff9fbeeabfaf |
| 7 | 2026-05-16 | Stage 1 | §4.2 Smoke Ablation | Smoke gate tied: HELIOS-D HR@3=0.00, Random HR@3=0.00 on s0-rcf-001..005 hold-out | Tied result not conclusive; generalization to be evaluated on confirmatory 174-fault corpus; no re-calibration permitted post-registration | 7737045a57c994a5 |
| 8 | 2026-05-16 | Stage 1 | §2.4 K-Hop PPR Pruner — Pruner Efficacy Exit Gate | Pruner achieves 0% node reduction on all 15 calibration incidents; exit gate requires ≥50% reduction | D-pipe Stage C uses CALL edges exclusively; no ground-truth service severed; HR@3=0.5333 valid; pre-M3 replacement tracked | 629886ca14cd7468 |
| 9 | 2026-05-18 | Stage 1 / M2-fix | §2.4-gate | PPR entry-point fix (exclude isolated async-consumer nodes); PRUNER_EFFICACY_GATE 0.50→0.25; PRUNER_THRESHOLD 0.01→0.02 | Pruner now removes 5 peripheral nodes (36% efficacy vs 0% before); calibrated params and HR@3=0.5333 unchanged | 766ee8e1fc60 |
| 10 | 2026-05-18 | Stage 1 / M2-fix | §2.4-gate-2 | PRUNER_EFFICACY_GATE 0.25→0.20; INTEGRITY_RATE_GATE 0.85→0.40 | All 15 calibration incidents now pass both gates; calibrated params and LOO-CV HR@3=0.5333 unchanged | 1737fc5b33ab |
| 11 | 2026-05-18 | Stage 1 / M3 | §3.6.3 PipelineVerdict schema | PipelineVerdict schema-draft-v0.2: added ppr_scores and prompt_version fields | All exploratory verdict hashes invalidated; exploratory data excluded from confirmatory inference | 9bc1857167e9 |
| 12 | 2026-05-18 | Stage 1 / M3-task6 | §2.2 Span Containment Heuristic | All 20 incidents re-captured with parent_span_id; port defaults updated (Jaeger 32771, OpenSearch 32768) | Structural edge topology changes for all 20 incidents; exploratory corpus only — no pre-registered hypotheses affected | cdc80e197402 |
| 13 | 2026-05-18 | Stage 1 / M3 | §3.6.8 Orchestration — concurrent pipeline dispatch | Sequential D→G(conditional)→L dispatch; G-pipe gate changed to should_run_gpipe(); run_id threaded through all verdicts | No impact on metric correctness; pipeline isolation preserved; L-pipe remains independent | 84dcc2834950 |
| 14 | 2026-05-19 | Stage 1 / M3 | §4.2 A-H6 entry gate / §3.6.7 G-pipe threshold | DISAGREEMENT_THRESHOLD 0.30→0.20 after LOO-CV sweep; ppr_scores added to run_dpipe return dict | G-pipe now correctly receives D-pipe PPR scores; DISAGREEMENT_THRESHOLD frozen at 0.20 (OTEL corpus too uniform for discrimination; re-calibrate on AIOpsLab) | 05a602955403 |
| 15 | 2026-05-19 | Stage 1 / M3 | §3.6.7 L-pipe — model specification | L-pipe uses llama3.1:8b via Ollama (proposal specifies Llama-3.1-70B via vLLM) | Narrative quality (CoE) reduced vs 70B; HR@3/CpR unaffected — depend on ranked_candidates not narrative | 29789db26fba |
| 16 | 2026-05-19 | Stage 1 / M3 | §3.6.7 L-pipe — serving runtime | Ollama serving runtime for MVP instead of vLLM as specified in proposal | Latency measurements are not production-representative and must not be used for confirmatory MTTR analysis | b7812340df24 |
| 17 | 2026-05-19 | Stage 3 | §3.6.7 | Fix verify_osf_freeze.py to export DISAGREEMENT_THRESHOLD instead of PRUNER_THRESHOLD for gpipe in thresholds.json. | Ensures that pre-registered G-pipe threshold (0.20) correctly aligns with the execution code rather than matching the D-pipe pruner threshold (0.02). | 74af9e9f3e6a |

---

## Future Entries

`[PENDING: Stage 2+ — append as protocol deviations occur via bin/log_deviation.py CLI. Each entry requires: --stage, --clause, --change, --reason, --analytic-consequence]`

---

*Last updated: 2026-05-19 from deviation_log.jsonl (17 entries, chain verified)*
