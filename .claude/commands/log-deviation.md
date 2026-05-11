/log-deviation variant=... component=... deviation=... impact=...
Generate structured deviation record for ablation_matrix.csv + experiment_log.csv + commit message.

Output format (exact):

**Deviation Log — [VARIANT] @ [SHA]**
- Component: [LLM / Graph / Stats / MAHC / etc.]
- Change: [short description]
- Reason: [ablation hypothesis or bug fix]
- Expected Impact: [HR@3 / CpR / Hallucination / MTTR delta]
- Flags Updated: [HELIOS_ENABLE_XXX=OFF etc.]
- Reproducibility: seed=42 | fixed random sources
- Validity Note: [none / minor internal validity threat]

Append to experiments/deviation_log.md and suggest commit message.