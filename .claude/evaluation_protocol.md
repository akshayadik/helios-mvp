# Evaluation Protocol
- Primary: HR@3 (Hit Rate @3), CpR, MTTR, Hallucination rate
- Ablation: 8 variants × 5 benchmarks × 40 faults × 10 seeds = 16k runs
- Stats: Wilcoxon signed-rank (binding), GLMM sensitivity
- Power: Per-hypothesis audit at α=0.00625