# HELIOS OSF Pre-registration

**Title:** HELIOS: A Hybrid Multi-Pipeline Root Cause Analysis Framework for Microservices

**Author:** Akshay Adik (PhD candidate)

**Freeze date:** 2026-05-18

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
| `analysis_plan.json` | <!-- SHA:analysis_plan.json -->`e1deb9a77efe0a32f7f89b5c1314392b95cd2652bd1d9a71acdc57577541899f` |
| `corpus_manifest.json` | <!-- SHA:corpus_manifest.json -->`361d392834aa5012f09858782277e4bffcad7aaa6f4b637d150c0997d27d377d` |
| `prompt_sha.json` | <!-- SHA:prompt_sha.json -->`cd50a6e3b9bd8fb4cf6896986fbe53006a9fa6c0b6cad422c6fed42f2698dedf` |
| `seeds.json` | <!-- SHA:seeds.json -->`bbb9879676cef62c36caf75453fd82b2db04a180f547afd223ff6806c5940bed` |
| `thresholds.json` | <!-- SHA:thresholds.json -->`31d92177d7f53785d1ee7e4558358d8df226a948f6f3cd9b9fffe097e7c65864` |
| `variant_hashes.json` | <!-- SHA:variant_hashes.json -->`0caf5192f0d2ab526f374aa8a22f395f8d4806642da2eada1537c7f1b87c7715` |
| `manifest_sig.txt` | <!-- SHA:manifest_sig.txt -->`bee226dd9f83b0e63bb73cf2f26e09031cde1b8c1f0e541a2b77bfc85c8b0c6e` |

---

## Deviation Summary

All protocol deviations with analytic consequence are logged in `deviation_log.jsonl`
(HMAC-SHA256 chained). List each entry by stage, clause, change, reason, and analytic
consequence. Entries 1-12 covering Milestones 1-3 must be listed before OSF deposit.

[Populate from deviation_log.jsonl before OSF deposit — no TBD sections permitted at G3-5 gate]

---

## OSF Deposit DOI

[to be added post-upload]
