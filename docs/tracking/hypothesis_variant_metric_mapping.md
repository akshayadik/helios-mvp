# Hypothesis × Variant × Metric Mapping

**Purpose:** one readable view of which variant comparison, metric and test each hypothesis uses.

**Source of truth:** `helios/research/analysis_plan.py` (tested against Ch3 in `tests/research/test_analysis_plan.py`) and `docs/tracking/metric_contract.md`. The tables below are generated from the plan; if they disagree with it, the plan wins. Last regenerated 2026-10-24 (S0.7, metric contract); the May 2026 table (A-H2 vs noGraph, CpR as a ranking metric) is superseded by deviation entries 24, 25, 29, 31 and 32.

**Correction:** Holm–Bonferroni within family A and within family B (8 tests each); α by rank = 0.05 / (9 − rank). Family E is exploratory: estimates with BCa intervals, no p-value claims. Every variant is a `VCLManifest` configuration (`helios/vcl/variants.py`).

---

## Family A — ablation (confirmatory)

| H_ID | Rank | α | Comparison (a vs b) | Primary metric | Test | Stratum | Asymmetric rule | Expected effect | Ch3 |
|---|---|---|---|---|---|---|---|---|---|
| A-H3 | 1 | 0.00625 | HELIOS-Full vs HELIOS-D | HR@3 | wilcoxon_signed_rank | — | — | delta HR@3 >= 0.15 | Table 18 p.171 |
| A-H7 | 2 | 0.007143 | HELIOS-Full vs HELIOS-noLLM | H_fact, H_struct | sign_test | — | — | hallucination rates at or near zero without the L-pipe, above zero under Full | Table 18 p.179; power p.200 |
| A-H1 | 3 | 0.008333 | HELIOS-Full vs HELIOS-noLLM | HR@3 | wilcoxon_signed_rank | — | — | delta HR@3 >= 0.10 | Table 18 p.169 |
| A-H2 | 4 | 0.01 | HELIOS-Full vs HELIOS-LLM-only | HR@3 | wilcoxon_signed_rank | — | — | delta HR@3 >= 0.10 | Table 18 p.170 |
| A-H6 | 5 | 0.0125 | HELIOS-Full vs HELIOS-G | HR@3 | wilcoxon_signed_rank | narrative_heavy | — | delta HR@3 >= 0.12 | Table 18 p.178 |
| A-H5 | 6 | 0.016667 | HELIOS-noRouter vs HELIOS-Full | log-CpR at matched HR@3 | wilcoxon_signed_rank | — | — | delta log-CpR >= 0.60 (uniform routing costs more) | Table 18 p.172 |
| A-H4 | 7 | 0.025 | HELIOS-Full vs HELIOS-noConsensus | HR@3 | wilcoxon_signed_rank | ambiguous | yes | delta HR@3 >= 0.05 (underpowered, disclosed) | Table 18 p.177; p.191, p.195 |
| A-H8 | 8 | 0.05 | HELIOS-Full vs HELIOS-noStructural | HR@3 | wilcoxon_signed_rank | — | yes | delta HR@3 >= 0.08 (underpowered, disclosed) | Table 18 p.180; p.191, p.195 |

---

## Family B — HELIOS against baselines (confirmatory)

Baselines 1–5 are named before OSF deposit 1 (D5). "Best baseline" is the baseline with the highest HR@3.

| H_ID | Rank | α | Comparison (a vs b) | Primary metric | Test | Asymmetric rule | Expected effect | Ch3 |
|---|---|---|---|---|---|---|---|---|
| B-H1 | 1 | 0.00625 | HELIOS-Full vs BASELINE-1 | HR@3 (paired binary) | mcnemar_exact_mid_p | yes | powered region p_disc >= 0.30 with r >= 0.70 | Table 18 p.173; Panel D p.200-201; clarification D6 item 8 |
| B-H2 | 2 | 0.007143 | HELIOS-Full vs BASELINE-2 | HR@3 (paired binary) | mcnemar_exact_mid_p | yes | powered region p_disc >= 0.30 with r >= 0.70 | Table 18 p.173; Panel D p.200-201; clarification D6 item 8 |
| B-H3 | 3 | 0.008333 | HELIOS-Full vs BASELINE-3 | HR@3 (paired binary) | mcnemar_exact_mid_p | yes | powered region p_disc >= 0.30 with r >= 0.70 | Table 18 p.173; Panel D p.200-201; clarification D6 item 8 |
| B-H4 | 4 | 0.01 | HELIOS-Full vs BASELINE-4 | HR@3 (paired binary) | mcnemar_exact_mid_p | yes | powered region p_disc >= 0.30 with r >= 0.70 | Table 18 p.173; Panel D p.200-201; clarification D6 item 8 |
| B-H5 | 5 | 0.0125 | HELIOS-Full vs BASELINE-5 | HR@3 (paired binary) | mcnemar_exact_mid_p | yes | powered region p_disc >= 0.30 with r >= 0.70 | Table 18 p.173; Panel D p.200-201; clarification D6 item 8 |
| B-H7 | 6 | 0.016667 | BEST-BASELINE vs HELIOS-Full | log-CpR | wilcoxon_signed_rank | — | delta = 0.80 (HELIOS costs less) | Table 18 p.174 |
| B-H6 | 7 | 0.025 | BEST-BASELINE vs HELIOS-Full | log time to correct diagnosis | wilcoxon_signed_rank | — | delta = 0.60 (HELIOS diagnoses faster) | Table 18 p.174; D10 (deviation 29) replaces log-MTTR on recorded data |
| B-H8 | 8 | 0.05 | HELIOS-Full vs BEST-BASELINE | Avg@5 | wilcoxon_signed_rank | — | delta Avg@5 >= 0.10 | Table 18 p.175; Avg@5 defined in the metric contract (D6 item 2) |

---

## Family E — exploratory

| H_ID | Comparison | Primary metric | Method | Stage | Status | Ch3 |
|---|---|---|---|---|---|---|
| E-H1 | HELIOS-Full vs HELIOS-noCogni | HR@3 on Tier-4 cognitive faults | bca | B | exploratory | Table 18 p.181 |
| E-H2 | HELIOS-noRouter vs HELIOS-Full | time to triage | bca | A | exploratory | Table 18 p.182 |
| E-H3 | HELIOS-Full vs HELIOS-noACP | latency-constraint satisfaction | bca | — | retired | Table 18 p.183; duplicate of E-H8 (D6 item 5) |
| E-H4 | HELIOS-noFGSV vs HELIOS-Full | false-accept rate under fidelity-break perturbation | bca | A (lite, if built) / B (full twin) | exploratory | Table 18 p.184 |
| E-H5 | HELIOS-noReconcile vs HELIOS-Full | reward reconciliation error on the delayed-label subset | bca | A | exploratory | Table 18 p.185 |
| E-H6 | HELIOS-noIOL vs HELIOS-Full | detection latency under injected control-plane degradation | bca | A (lite, if built) / B (full) | exploratory | Table 18 p.176 |
| E-H7 | HELIOS-Full vs HELIOS-noExpl | correct interpretation; time to decision; trust (RQ4 user study) | wilcoxon_paired_with_bca | A (if IRB approved) | exploratory | Table 18 p.189; p.163-165; D6 items 10 and 12 |
| E-H8 | HELIOS-Full vs HELIOS-noACP | latency-constraint satisfaction | bca | A | exploratory | Table 18 p.186 |
| E-H9 | HELIOS-HIS3 vs HELIOS-Full | per-incident latency by isolation tier | bca | B | exploratory | Table 18 p.187 |
| E-H10 | HELIOS-Full vs HELIOS-noStructural | delta HR@3 attributed across the structural sub-mechanisms | descriptive_with_bca | A | exploratory | Table 18 p.188 |

---

## Where each metric comes from

Definitions are in `metric_contract.md`; this table only says where the inputs live.

| Metric | Computed from | Stored in |
|---|---|---|
| HR@k, Avg@5, MRR | Fused ranked list (consensus output) joined to the sealed ground truth | `eval_score` (S1.9) |
| Per-pipeline MRR (diagnostic) | `PipelineVerdict.mrr` | `result_row` |
| CpR | Run telemetry (tokens, CPU/GPU-seconds, bytes, verdict state, TTCD) × price book | `eval_score` (S1.9); `ConsensusVerdict.cpr` holds it per case |
| Time to correct diagnosis, time to triage | Verdict publication timestamps relative to invocation | `eval_score` (S1.9) |
| H_fact, H_struct | Grounding verifier labels + rater sample | `eval_score` (S1.9) and the annotation log |
| Strata (ambiguous, narrative-heavy) | Per-pipeline top-1s; input log templates | `eval_score` (S1.9) |
| latency_ms, token_count | `PipelineVerdict` | `result_row` |
