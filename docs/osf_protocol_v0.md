# OSF Pre-Registration Protocol — HELIOS MVP (v0)

**Status:** Stage 0 draft. Becomes binding at Stage 5 freeze.

## Sections (to be populated)

1. **Hypotheses** — A-H1..A-H8 (ablation), B-H1..B-H8 (baseline), E-H1..E-H10 (exploratory)
2. **Variants** — confirmatory + exploratory (with feature-flag matrix)
3. **Metrics** — HR@3, MRR, macro-F1, CpR, log-MTTR, hallucination rates, etc.
4. **Statistical Analysis Plan**
   - Wilcoxon signed-rank (paired continuous)
   - McNemar's exact (paired binary)
   - Holm–Bonferroni rank-ordered FWE control (separate ablation/baseline families)
   - BCa bootstrap (exploratory)
   - MDE recomputed at MVP corpus size
5. **Inclusion / exclusion criteria** — 80% cell-completion threshold etc.
6. **Scope contraction register** — proposal commitment → MVP status → reactivation trigger
7. **Reproducibility manifest** — SHA-256 of corpus, container digests, model identifiers, seeds

_(Populate fully before Stage 5 freeze. Each section is its own commit so the
git diff is the freeze audit trail.)_
