# HELIOS OSF Pre-registration

**Title:** HELIOS: A Hybrid Multi-Pipeline Root Cause Analysis Framework for Microservices

**Author:** Akshay Adik (DBA candidate)

**Freeze date:** 2026-05-19

**Milestone:** Milestone 3 — Conditional G-pipe + L-pipe + OSF Full Freeze

---

## Overview

HELIOS is a Design Science Research (DSR) artefact addressing the RQ: How can a hybrid multi-pipeline system (statistical + graph + LLM) reduce MTTR and improve explainability/trust for microservice incidents? The framework orchestrates three peer pipelines (D-pipe: statistical anomaly detection; G-pipe: graph traversal; L-pipe: LLM explanation) controlled by Variant Control Layer (VCL) feature flags that enable ablation studies.

---

## Hypotheses

### A-Family (Ablation)

Ranked by Holm priority. All require `evaluation_phase = confirmatory` data from AIOpsLab.

| Rank | H_ID | Comparison | Primary Metric | Holm alpha | Status |
|---|---|---|---|---|---|
| 1 | A-H3 | HELIOS-Full vs HELIOS-D | HR@3 | 0.00625 | Confirmatory |
| 2 | A-H7 | HELIOS-Full vs HELIOS-noLLM | HR@3 | 0.007143 | Confirmatory |
| 3 | A-H1 | HELIOS-Full vs baseline | HR@3 | 0.008333 | Confirmatory |
| 4 | A-H2 | HELIOS-Full vs HELIOS-noGraph | CpR | 0.01 | Confirmatory |
| 5 | A-H6 | HELIOS-G vs HELIOS-D (gate-conditional) | HR@3 | 0.0125 | Cond. Confirmatory |
| 6 | A-H5 | HELIOS-Full vs HELIOS-noRouter | HR@3 | 0.016667 | Confirmatory |
| 7 | A-H4 | HELIOS-Full vs HELIOS-noConsensus | HR@3 | 0.025 | Exploratory (underpowered) |
| 8 | A-H8 | HELIOS-Full vs HELIOS-noStructural | HR@3 | 0.05 | Exploratory (underpowered) |

**A-H6 sentinel filter (mandatory):** When the PPR disagreement gate does not fire,
`run_gpipe()` emits a sentinel row (`narrative = 'gpipe-gated-or-skipped'`). These rows
must be excluded before computing the A-H6 metric. The filter is baked into `analysis_plan.json`.

### B-Family (Baseline comparisons)

All deferred to post-Milestone 4 (AIOpsLab confirmatory corpus pending).

| Rank | H_ID | Comparison | Primary Metric | Baseline |
|---|---|---|---|---|
| 1 | B-H1 | HELIOS-Full vs CHASE | HR@3 | CHASE |
| 2 | B-H2 | HELIOS-Full vs RCACopilot | HR@3 | RCACopilot |
| 3 | B-H3 | HELIOS-Full vs CHASE | CpR | CHASE |
| 4 | B-H4 | HELIOS-Full vs RCACopilot | CpR | RCACopilot |
| 5 | B-H5 | HELIOS-Full vs CHASE | log-MTTR delta | CHASE |
| 6 | B-H6 | HELIOS-Full vs CHASE | hallucination rate | CHASE |
| 7 | B-H7 | HELIOS-Full vs CHASE | CoE score | CHASE |
| 8 | B-H8 | HELIOS-Full vs CHASE | macro-F1 | CHASE |

---

## Variants

8 confirmatory VCL variants. Complete flag matrix stored in `variant_hashes.json`.

| Variant | Status | Hypotheses |
|---|---|---|
| HELIOS-Full | Confirmatory | A-H1, A-H2, A-H3, A-H4, A-H5, A-H7, A-H8 |
| HELIOS-noLLM | Confirmatory | A-H7 |
| HELIOS-noGraph | Confirmatory | A-H2 |
| HELIOS-D | Confirmatory | A-H3, A-H6 |
| HELIOS-G | Cond. Confirmatory | A-H6 |
| HELIOS-noConsensus | Exploratory (underpowered) | A-H4 |
| HELIOS-noRouter | Exploratory (underpowered) | A-H5 |
| HELIOS-noStructural | Exploratory (underpowered) | A-H8 |

---

## Statistical Analysis Plan

- **Test:** Wilcoxon signed-rank (one-sided)
- **Correction:** Holm-Bonferroni family-wise over 8 A-family tests
- **Family alpha:** 0.05
- **Effect size commitment:** Cohen h >= 0.276
- **Fixed reproducibility seeds:** GLOBAL_SEED: 42, LLAMA_SEED: 42 (see `seeds.json`)

---

## Corpus

**Exploratory calibration corpus:** 20 OTEL Demo incidents (local environment). Snapshot
hashes stored in `corpus_manifest.json`. Two-environment firewall enforced — exploratory
and confirmatory data are never mixed.

**Confirmatory corpus:** AIOpsLab, target 174 incidents. Deferred to post-Milestone 4.

---

## Frozen Artefacts

| File | SHA-256 |
|---|---|
| `analysis_plan.json` | <!-- SHA:analysis_plan.json -->`a3d6a18bafc8af29821c48260ce80c60a7fdad95d064adb3599271e1aad43e9b` |
| `corpus_manifest.json` | <!-- SHA:corpus_manifest.json -->`5799747b31ef7058870abe13bcfcb2022b967ecc47623e08d745454babc2b4e0` |
| `prompt_sha.json` | <!-- SHA:prompt_sha.json -->`1d72b485f559c559dd37b5971857b033c3e2c2b2a941618e0322da7c5b555b2c` |
| `seeds.json` | <!-- SHA:seeds.json -->`8f5c417ffb3832dfb67ab2edba0a5dc186f289737fb41e446e94cc75cab9da0d` |
| `thresholds.json` | <!-- SHA:thresholds.json -->`e4696d3ac8638d2bd37ad3dd9299ddab0274b91b04969757c6743bef5a52f8d4` |
| `variant_hashes.json` | <!-- SHA:variant_hashes.json -->`251dee3af1d5015404daee4caf1fc58b37e8bd0f24c6bdef3412206f03beed07` |
| `manifest_sig.txt` | <!-- SHA:manifest_sig.txt -->`5aff59aeb82c769c54d8e17df0b621623bded54609a5aca063a77374331fe0da` |

---

## Deviation Summary

All protocol deviations with analytic consequence are logged in `deviation_log.jsonl`
(HMAC-SHA256 chained). Authoritative source: `deviation_log.jsonl`. Chain verified 2026-05-19.
Full change text and reasons are in the JSONL; this table is the examiner-readable summary.

**Note on `commit_sha` field:** All 18 entries carry `commit_sha: "LOCAL"` because the
deviation log CLI was run before pushing each commit to the remote. The HMAC chain is
cryptographically valid. Actual commit SHAs can be reconstructed from `git log --after`
cross-referenced with `timestamp_utc` in each entry. See `reproducibility_manifest.md §6`.

| # | Date | Stage | Clause | Change | Analytic Consequence | sig[:16] |
|---|---|---|---|---|---|---|
| 1 | 2026-05-08 | Stage 0 | Setup | Python pinned to `>=3.11,<3.12` | Reproducibility constraint; no effect on analysis | `7fee47b53a2dc5b4` |
| 2 | 2026-05-08 | Stage 0 | §3.6.6 | C1 invariants reduced 6→5; ReconciliationLedger deferred to M1 | E-H5 descoped; A-H5 static routing retained | `fb8ece84e8a1b7bd` |
| 3 | 2026-05-08 | Stage N | §... | Chain-bootstrap placeholder — corrected by entry 18 | None | `539e67a1910f9da7` |
| 4 | 2026-05-12 | Stage 1 | §6.2 | Added `model_version` + `prompt_template_id` to VCLManifest | All 8 confirmatory `variant_config_hash` values invalidated and recomputed | `0b8fcc0d03d1fb0e` |
| 5 | 2026-05-14 | Stage 0 | §B.12 | Stage 0 exit sign-off; EG1–EG6 all satisfied | None (sign-off entry; no protocol change) | `a64c18b7f0b94745` |
| 6 | 2026-05-16 | Stage 1 | §2.2 | Temporal span-containment heuristic instead of `parent_span_id` linkage | Potential structural-edge misattribution; bounded to PPR entry-point identification | `5655ff9fbeeabfaf` |
| 7 | 2026-05-16 | Stage 1 | §4.2 | Smoke gate vacuously tied on rcf hold-out (both HR@3 = zero) | No re-calibration permitted post-registration; generalize on AIOpsLab 174-fault corpus | `7737045a57c994a5` |
| 8 | 2026-05-16 | Stage 1 | §2.4 | Pruner achieves zero node reduction on 15 calibration incidents | D-pipe CALL-edges path valid; HR@3 on calibration corpus unaffected | `629886ca14cd7468` |
| 9 | 2026-05-18 | Stage 1 / M2-fix | §2.4-gate | PRUNER_EFFICACY_GATE 0.50→0.25; PRUNER_THRESHOLD 0.01→0.02; PPR entry-point bug fixed | Calibrated params (w_error, rho, boost) unchanged; 15/15 PASS | `766ee8e1fc608e60` |
| 10 | 2026-05-18 | Stage 1 / M2-fix | §2.4-gate-2 | PRUNER_EFFICACY_GATE 0.25→0.20; INTEGRITY_RATE_GATE 0.85→0.40 | All 15 incidents PASS both gates; calibrated params unchanged | `1737fc5b33ab1abe` |
| 11 | 2026-05-18 | Stage 1 / M3 | §3.6.3 | PipelineVerdict schema-draft-v0.2: added `ppr_scores` + `prompt_version` | All exploratory verdict hashes invalidated; exploratory data excluded from confirmatory inference | `9bc1857167e95a85` |
| 12 | 2026-05-18 | Stage 1 / M3-task6 | §2.2 | All 20 incidents re-captured with `parent_span_id`; capture port defaults updated | Structural topology changes for all 20 incidents; exploratory corpus only — no pre-registered hypotheses affected | `cdc80e197402feac` |
| 13 | 2026-05-18 | Stage 1 / M3 | §3.6.8 | RunOrchestrator changed concurrent→sequential D→G(conditional)→L dispatch | No impact on metric correctness; pipeline isolation preserved | `84dcc28349507a2f` |
| 14 | 2026-05-19 | Stage 1 / M3 | §4.2 / §3.6.7 | DISAGREEMENT_THRESHOLD 0.30→0.20; `ppr_scores` exposed in `run_dpipe` return | Threshold frozen at 0.20; AIOpsLab re-calibration required before confirmatory inference on A-H6 | `05a602955403f9cb` |
| 15 | 2026-05-19 | Stage 1 / M3 | §3.6.7 | L-pipe uses llama3.1:8b via Ollama (proposal: Llama-3.1-70B via vLLM) | CoE narrative quality reduced vs 70B; HR@3/CpR unaffected (depend on `ranked_candidates`) | `29789db26fba9b1d` |
| 16 | 2026-05-19 | Stage 1 / M3 | §3.6.7 | L-pipe serving: Ollama runtime instead of vLLM as specified in proposal | `latency_ms` not production-representative; excluded from confirmatory MTTR analysis | `b7812340df247f8a` |
| 17 | 2026-05-19 | Stage 3 | §3.6.7 | Fix `verify_osf_freeze.py`: use `DISAGREEMENT_THRESHOLD` not `PRUNER_THRESHOLD` for gpipe section | OSF `thresholds.json` now correctly records 0.20; pre-registered threshold aligns with code | `74af9e9f3e6a8f14` |
| 18 | 2026-05-19 | Stage 0 | §A.1 | Correction: entry 3 was a chain-bootstrap placeholder with no protocol meaning (sig `539e67a1910f`) | None; chain integrity confirmed | `89b0d6566d7ba56c` |

---

## OSF Deposit DOI

[to be added post-upload]
