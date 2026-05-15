# Stage 0 Gap Analysis — Research Proposal vs. Delivered

**Date:** 2026-05-14  
**Branch:** `feature/stage0_vlc_foundation` (tag: `stage-0-exit`, SHA: `541a670`)  
**Purpose:** Reference for items to revisit after MVP completion. Not a task tracker — see `helios_mvp_tracking.md` for that.

---

## What Stage 0 Delivered

Stage 0 (M0 in the execution plan) was scoped as "Repo + C1 foundation + OTEL Demo harness proven + first research docs."

| Item | Status |
|---|---|
| VCL core — 14 flags, `@gated_by`, `VCLManifest`, hash stability | Done |
| HMAC-chained deviation log | Done |
| SnapshotRegistry (L2 identity guard) | Done |
| CaptureReader + L0 hash round-trip | Done |
| ResultStore (DuckDB PipelineVerdict) | Done |
| 5 OTEL Demo Parquet recordings (≥3 fault classes) | Done |
| Ablation Architecture Notebook — §1–§3.0 frozen | Done |
| OSF protocol v0 draft | Done |
| Pipeline stubs (g\_pipe, l\_pipe gated) | Done |
| HMAC chain verified (5 entries) | Done |

---

## Gap 1 — UEG-C Schema Draft (M0 scope, missed)

The execution plan listed "Draft UEG-C canonical JSON schema (4 typed edge classes declared) + verdict schema (Pydantic)" as a Milestone 0 deliverable. This was not done in Stage 0.

**What it is:** The canonical JSON representation for the Unified Error-Cause Graph (C2), with four typed edge classes: structural, behavioural, causal, economic. Every pipeline (D-pipe, G-pipe, L-pipe) writes output into this schema.

**Impact:** Low for now (pipelines are stubs), but this schema must exist before Milestone 2 starts D-pipe + UEG-C builder work. Without it, D-pipe output has no contract to validate against.

**Revisit at:** Start of Stage 1 / Milestone 1, before Milestone 2 begins.

---

## Gap 2 — Full C1 Not Complete (Milestone 1 scope, planned)

C1 in the proposal covers six sub-artefacts. Three implemented; three not:

| C1 Sub-artefact | Status | Planned stage |
|---|---|---|
| VCL (variant control layer) | Done | M0 |
| Deviation log (HMAC-chained) | Done | M0 |
| SnapshotRegistry (snapshot hash guard) | Done | M0 |
| Metric integrity gate | Not built | Milestone 1 |
| Exclusion ledger (`exclusion_ledger.jsonl`) | Not built | Milestone 1 |
| Reconciliation ledger | Not built | Milestone 1 |

Additionally:

- **Full disjointness audit** (static + `coverage.py` CI): `disjointness_audit.yml` is a stub that exits 0 on `ImportError`. Real enforcement (every pipeline function provably covered by exactly one flag) is a Milestone 1 item.
- **Orchestrator CLI** (`helios run --variant ... --corpus ...`): Not built. Wires `get_variant()` → `set_current_manifest()` → pipeline dispatch.

**Impact:** Until the metric integrity gate and exclusion ledger exist, the "20 incidents with full VCL + snapshot hash + gate compliance" Milestone 1 exit criterion cannot be met. C1 is the headline novelty — this is the most important gap.

---

## Gap 3 — Incident Corpus Size (Milestone 1 scope, planned)

5 exploratory Parquet recordings exist. Milestone 1 requires 20 incidents with byte-equal replay verification. The 174-fault confirmatory corpus is a Phase 2 (Milestone 8) item.

**Revisit at:** Milestone 1 — record 15 more incidents and verify replay determinism.

---

## Gap 4 — C2 through C6 (Milestones 2–9, all planned)

These were never in Stage 0 scope. Listed here to distinguish from missed items.

| Contribution | Content | Milestone |
|---|---|---|
| C2: UEG-C | Graph builder (PPR traversal, K-hop pruner / Alg 5), 4 edge classes, content-hashed | Milestone 2 |
| C2: Cognitive nodes | Agent-Reasoning-Step nodes in UEG-C | Phase 2 / M7 |
| C3': FGSV | KS-gated shadow validation (Alg 4) | Phase 2 / M7 |
| C4: MAHC | Multi-agent consensus with (μ,σ) votes + hierarchical priors (Alg 3); Milestone 4 uses uniform Borda as proxy | Phase 2 / M7 |
| C5: IOL | Self-telemetry under `tenant=self` in UEG-C | Phase 2 / M7 |
| C6: ORAR | LinUCB bandit router (Alg 1) + Action-Class Predictor (Alg 2) | Phase 2 / M7 |
| G-pipe | PPR graph traversal behind `L2B_GRAPH` flag | Milestone 3 |
| L-pipe | Ollama + frozen prompt-SHA + JSON schema | Milestone 3 |
| D-pipe | Statistical anomaly detection bridging L0→L2 | Milestone 2 |

---

## Gap 5 — Research Process Items (Phase 2 prerequisites)

Not code gaps — research infrastructure required before confirmatory work.

| Item | Status | Required by |
|---|---|---|
| OSF pre-registration (full freeze) | v0 draft only | Milestone 3 (protocol freeze) / Milestone 8 (confirmatory pre-reg) |
| IRB approval for RQ4 user study (n=24 SREs) | Not started | Must be approved before Phase 2 user study |
| AIOpsLab migration | Not started | Milestone 6 — confirmatory environment |
| Weekly status docs (`docs/weekly_status_YYYY-WW.md`) | Not established | Should start now |
| Prompt SHA locking (L-pipe model + prompt frozen) | Not applicable yet | Milestone 3 |

The RQ4 user study (correct-interpretation rate, time-to-decision, trust calibration, n=24 SREs, within-subjects) requires IRB approval. IRB applications typically take 4–8 weeks — initiate before Milestone 7 when the L-pipe explanation layer is built.

---

## Revisit Priority Summary

| Priority | Item | When |
|---|---|---|
| 1 | UEG-C canonical JSON schema draft (4 edge classes + verdict schema) | Stage 1 / M1 start |
| 2 | Metric integrity gate + exclusion ledger + reconciliation ledger | Stage 1 / M1 |
| 3 | Orchestrator CLI (`helios run`) + full disjointness CI | Stage 1 / M1 |
| 4 | 15 additional incident recordings (→ 20 total) | Stage 1 / M1 |
| 5 | Start IRB application for user study | Before M7 |
| 6 | Weekly status docs discipline | Now |
| 7–N | C2–C6, G/L-pipe, FGSV, MAHC, ORAR, IOL, AIOpsLab | M2–M9 as planned |

Nothing in the full proposal was accidentally skipped that should have been in Stage 0. The UEG-C schema draft is the only M0-scoped item that did not make it in. Everything else is correctly staged.

## Structured summary

```


  Here is a summary of the scope from the complete research proposal that has been intentionally deferred and will need to be revisited in Phase 2 (Post-MVP):

  1. Confirmatory Data & Environment (The "Two-Environment Firewall")
   * AIOpsLab Migration: The MVP relies entirely on the OTEL Demo. According to OSF Protocol §1.4, OTEL Demo data is strictly for exploratory calibration. All binding, confirmatory statistical inferences
     (the 174-incident corpus) must be executed on AIOpsLab, which is scheduled for Milestone 6.
   * Synthetic Fault Injection (E-H4): Testing cross-service topology sensitivity requires AIOpsLab's synthetic fault injection capabilities, which are unavailable in the basic OTEL Demo docker-compose
     setup.

  2. Advanced Pipeline Implementations (The "Body" Extensions)
  The MVP pipelines (Milestone 2 & 3) are functional baselines. The advanced theoretical models from your research proposal are deferred to Milestone 7:
   * G-pipe (GNNs): The MVP will implement a basic PPR (Personalized PageRank) traversal for the graph pipeline. The advanced Graph Neural Network (GNN) implementation is deferred.
   * L-pipe (M2 Migration): The MVP locks in a basic Ollama prompt/schema setup. Advanced migration to the M2 framework for the LLM pipeline is a Phase 2 task.
   * Pre-training (ORAR/MAHC): Full Multimodal Attributed Hierarchical Context (MAHC) and ORAR pre-training are completely deferred to Phase 2.

  3. Scope Contractions & Underpowered Hypotheses
  As noted in OSF Protocol §6 (Scope Contraction Register), certain analyses have been downgraded or deferred due to power or logistical constraints in the MVP:
   * Consensus (A-H4) & Structural Edges (A-H8): Both are acknowledged as "underpowered-disclosed" (~65% and ~62% power respectively) in the MVP.
   * Human-in-the-Loop Feedback (E-H7): Deferred indefinitely pending IRB approval for human participant data collection.
   * Auto-Remediation Scaffolding (C5): Targeted for Stage 4+; confirmatory evaluation is deemed unfeasible during the MVP phase.

  4. The Reproducibility Manifest (OSF Protocol §7)
  Stage 0 locks the L-pipe Protocol A parameters (temperature, models), but the actual binding cryptographic commitments for your dissertation defense are deferred:
   * Deferred to Stage 5 / Milestone 8: You still need to lock and publish the corpus manifest SHA-256, the BCa bootstrap seed (for Family E metrics), the final L-pipe prompt SHA, and the specific
     container image digests. 
   * Binding Statistical Analysis: The MVP (Milestone 4) only executes exploratory Wilcoxon tests. The rigorous, Holm–Bonferroni corrected hypothesis testing against the CHASE/RCACopilot baselines happens
     in Milestone 8.

  Summary: Your MVP perfectly achieves its goal of building the unshakeable C1 Ablation Spine. After Month 6, your engineering focus will shift from infrastructure (VCL, Parquet, logging) to data science
  (GNNs, AIOpsLab ingestion, rigorous statistical proof).
```