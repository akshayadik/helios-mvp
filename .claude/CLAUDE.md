# HELIOS Framework — Research Context

See root `CLAUDE.md` for all operational rules, commands, and CI details. This file captures research-framing context that doesn't belong there.

## Session Startup Reads

**ALWAYS read both of these at the start of every session** before any research-related work:

1. `docs/research/research_proposal_akshayadik.pdf` — introduction, literature review, research design; use to ground all RQ framing, hypothesis justification, and artefact design decisions.
2. `docs/research/project_plan.md` — 15-month execution plan (milestones, gates, deliverables, phase structure); use to assess task fit, scheduling, and milestone alignment.

## Core Artefact

HELIOS is a doctoral artefact: a hybrid multi-pipeline RCA framework (statistical D-pipe + graph G-pipe + LLM L-pipe as peer pipelines). Goals: reduce MTTR, improve explainability/trust, handle multimodal observability (logs/traces/metrics) in dynamic microservices. Chapter structure: Lit Review (Ch2), DSR Methodology + Artefact (Ch3), Economics/ROI/Gaps.

## Pre-Registration Commitments

- Pre-registered hypotheses A-H1..8 + B-family; Holm–Bonferroni correction; rank-order predictions locked before data collection.
- 16k-run ablation: 8 variants × 5 benchmarks × 40 faults × 10 seeds.
- Stats: Wilcoxon signed-rank (binding), GLMM sensitivity, α=0.00625 per hypothesis.
- 174-fault baseline corpus; runtime enforcement via reconciliation ledger.

## Never Violate

- Feature flags for every C1–C6 component — ablation controllability is non-negotiable.
- Fixed seeds; no protocol change with analytic consequence without a deviation log entry.
