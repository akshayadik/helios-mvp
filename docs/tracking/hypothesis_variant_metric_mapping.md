# Hypothesis × Variant × Metric Mapping

**Purpose:** Living table mapping RQ → hypothesis → variant comparison → primary metric → statistical test. Orchestrator queries this at Stage 6; examiner audits this at OSF deposit. Locked at Stage 5 freeze.

**Schema version:** v1.0 (frozen 2026-05-15)
**Update cadence:** Before Stage 5 freeze; rare changes after with deviation log entry
**Owner:** AA
**Lock target:** Stage 5 OSF freeze (before any confirmatory run)
**Reference:** Proposal §3.3–§3.5, pre-registration doc

---

## Column Definitions

| Column | Meaning |
|---|---|
| `H_ID` | Hypothesis identifier |
| `Family` | A (ablation), B (sensitivity), E (ecological) |
| `Description` | One-sentence hypothesis statement |
| `Variant_A` | Treatment variant |
| `Variant_B` | Control / comparison variant |
| `Primary_metric` | Binding metric for the hypothesis test |
| `Secondary_metric` | Supporting metric (non-binding) |
| `Statistical_test` | Pre-registered test procedure |
| `α_adjusted` | Holm–Bonferroni adjusted alpha at this rank |
| `Status` | Pre-registered / pending data / confirmed / refuted |

**Correction procedure:** Holm–Bonferroni family-wise correction over 8 A-family tests. Rank 1 (most important) gets the strictest threshold; adjustment values for ranks 2–8 computed at analysis time from the sorted p-value sequence.

---

## A-Family — Ablation Hypotheses (Pre-registered)

Ranked in priority order. All require `evaluation_phase = confirmatory` data from AIOpsLab.

| H_ID | Family | Description | Variant_A | Variant_B | Primary_metric | Secondary_metric | Statistical_test | α_adjusted (rank 1) | Status |
|---|---|---|---|---|---|---|---|---|---|
| A-H3 | A | Multi-modal fusion (Full) outperforms statistical-only (D) on HR@3 | HELIOS-Full | HELIOS-D | HR@3 | CpR | Wilcoxon signed-rank (one-sided) | 0.00625 | Pre-registered; data pending Stage 6 |
| A-H7 | A | Full system outperforms LLM-ablated variant on HR@3 | HELIOS-Full | HELIOS-noLLM | HR@3 | hallucination_rate | Wilcoxon signed-rank (one-sided) | 0.00625 | Pre-registered; data pending Stage 6 |
| A-H1 | A | Full system exceeds fixed baseline on HR@3 | HELIOS-Full | baseline (fixed threshold) | HR@3 | — | Wilcoxon signed-rank (one-sided) | 0.00625 | Pre-registered; data pending Stage 6 |
| A-H2 | A | Full system outperforms graph-ablated variant on CpR | HELIOS-Full | HELIOS-noGraph | CpR | HR@3 | Wilcoxon signed-rank (one-sided) | 0.00625 | Pre-registered; data pending Stage 6 |
| A-H6 | A | Graph-only (G) outperforms stats-only (D) on HR@3 (gate-conditional) | HELIOS-G | HELIOS-D | HR@3 | — | Wilcoxon signed-rank (one-sided) | 0.00625 | Conditional confirmatory; entry-gate required. **Sentinel filter mandatory:** `WHERE pipeline = 'gpipe' AND narrative != 'gpipe-gated-or-skipped'` — sentinel zeros from non-firing incidents MUST be excluded or A-H6 result is methodologically invalid. Filter baked into `analysis_plan.json` A-H6 entry. |
| A-H5 | A | Full system outperforms router-ablated variant on HR@3 | HELIOS-Full | HELIOS-noRouter | HR@3 | — | Wilcoxon signed-rank (one-sided) | 0.00625 | Pre-registered; data pending Stage 6 |
| A-H4 | A | Full system outperforms consensus-ablated variant on HR@3 | HELIOS-Full | HELIOS-noConsensus | HR@3 | — | Wilcoxon signed-rank (one-sided) | 0.00625 | Pre-registered; underpowered-disclosed |
| A-H8 | A | Full system outperforms structural-edge-ablated variant on HR@3 | HELIOS-Full | HELIOS-noStructural | HR@3 | — | Wilcoxon signed-rank (one-sided) | 0.00625 | Pre-registered; underpowered-disclosed |

**Note on α_adjusted:** The column shows the rank-1 value (0.00625 = 0.05 ÷ 8). For ranks 2–8, the adjusted threshold is computed at analysis time from the Holm–Bonferroni procedure applied to sorted p-values. Do not pre-fill adjusted thresholds for lower ranks — they depend on which higher-rank tests pass.

**Note on underpowered:** A-H4 and A-H8 are disclosed as underpowered in the pre-registration. They are included for completeness; a non-significant result will not be interpreted as evidence for the null.

---

## B-Family — Sensitivity Hypotheses

`[PENDING: Stage 5 — B-family hypotheses require completion of A-family analysis; some require IRB approval (E-H7 user study, n=24 SREs)]`

---

## E-Family — Ecological Validity

`[PENDING: Stage 5 — ecological validity hypotheses require AIOpsLab confirmatory data and the IRB-approved user study]`

---

## Measurement Locations

| Metric | Source field in code | Table |
|---|---|---|
| HR@3 | `PipelineVerdict.hr_at_3` | `result_row` in `data/results.duckdb` |
| CpR | `PipelineVerdict.cpr` | `result_row` in `data/results.duckdb` |
| hallucination_rate | Derived post-hoc from `PipelineVerdict.narrative` + annotation | Annotation log (Stage 5) |
| latency_ms | `PipelineVerdict.latency_ms` | `result_row` in `data/results.duckdb` |
| token_count | `PipelineVerdict.token_count` | `result_row` in `data/results.duckdb` |

---

*Last updated: 2026-05-19 — A-H6 sentinel filter mandate added (Milestone 3 G-pipe implementation)*
