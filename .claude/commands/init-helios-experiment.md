Create a new ablation experiment:
- Generate variant name (HELIOS-{flags})
- Update feature flags in main config
- Create experiment directory under experiments/
- Initialise ablation_matrix.csv row with seed, commit SHA, timestamp
- Run baseline with fixed seed 42
- Output full reproduction command