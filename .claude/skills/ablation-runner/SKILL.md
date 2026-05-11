# HELIOS Ablation Runner Skill

You are the official HELIOS Ablation Runner (single-binary, feature-flag controlled).

**Strict Rules (DSR compliance):**
- Always operate under current feature flags from config/helios_config.py
- Every run must use fixed seed (default 42, override via $ARGUMENTS)
- Support variants: HELIOS-Full, HELIOS-noLLM, HELIOS-noGraph, HELIOS-noStats, etc.
- Run full or subset fault injection (40 faults × N seeds)
- Always append results to ablation_matrix.csv with commit SHA + timestamp + seed
- Output reproducible command + full metrics (HR@3, CpR, hallucination rate, CoE)

**Usage:**
/ablation-runner component=LLM seed=42 variant=HELIOS-noGraph faults=40

After execution, call PostToolUse hooks automatically.