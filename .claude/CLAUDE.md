# HELIOS Framework — Research Context

See root `CLAUDE.md` for all operational rules, commands, and CI details. This file captures research-framing context that doesn't belong there.

## Session Startup Reads

**ALWAYS read both of these at the start of every session** before any research-related work:

1. `docs/research/research_proposal_akshayadik.pdf` — introduction, literature review, research design; use to ground all RQ framing, hypothesis justification, and artefact design decisions.
2. `docs/tracking/helios_e2e_product_plan_2026-10.md` — current end-to-end plan (Stage A sprints S0–S5 to the mid-February evidence freeze → evidence collection → analysis by 2027-03-31; Stage B completes the full product by end of July 2027); use for task fit, scheduling and phase gates. Its companion `docs/tracking/r1_traceability_matrix.md` maps the approved Ch3 against the code. (`docs/research/project_plan.md` is the original 15-month plan, kept for history.)

## Product Direction (owner, 2026-10-23)

- The aim is a **high-quality, production-grade observability product that shows innovation and creativity**.
- **Chapter 3 is the baseline, not the final verdict.** Where a different or more creative method gives a better or more production-ready result, propose and prefer it. The e2e plan and the R1 matrix are guides, not rigid specifications — do not refuse or water down a better design just because Ch3 describes another one.
- **Deadline: results ready (evidence collected + analysed) by 2027-03-31**; Chapters 4–5 are written after. The plan is re-baselined to 21 weeks (2026-10-23): recorded-dataset evaluation (RCAEval RE2 + AIOpsLab if feasible), 8B model for confirmatory runs, and three adopted innovations — evidence-grounded narratives, calibrated consensus confidence, cheap-first routing. **Full product scope is kept — nothing is cut**: Stage A (Tier 1, plus Tier 2 if ready) is frozen mid-February for the confirmatory evidence; Stage B builds the rest of the product February–July 2027 behind feature flags and is evaluated exploratorily after March. Never touch the frozen evidence build; if time is short, move Tier 2 to Stage B rather than rush Tier 1.
- The dissertation guide prefers details discussed **on a call**, not memos: prepare call-reference docs with an outcomes table.
- What does not bend is evidence integrity: a change that alters what a pre-registered test measures is recorded (deviation entry, pre-registration update) **before** confirmatory data is collected; build/calibration data stays separate from confirmatory data; every mechanism stays behind a feature flag so it can be ablated.

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
