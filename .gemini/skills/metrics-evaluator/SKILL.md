---
name: metrics-evaluator
description: Analyzing RCA metrics (HR@3, CpR, hallucination rate) and interpreting ablation-first logic results.
---
# Instructions
- **Metric Definitions:** Refer to `docs/evaluation/` for authoritative definitions of HR@3, CpR, and CoE quality.
- **Result Interpretation:** Analyze `experiments/experiment_log.csv` and DuckDB result stores to evaluate hypothesis performance.
- **Statistical Integrity:** Adhere to the pre-registered Holm–Bonferroni corrections and α thresholds.
- **Confirmatory vs Exploratory:** Strictly enforce the firewall between OTEL Demo (exploratory) and AIOpsLab (confirmatory) data.
