# OSF Pre-Registration Protocol — HELIOS MVP (v0)

**Framework:** HELIOS — Hybrid Explainable Learning for Incident Observability and Supervision
**Deposit type:** Stage 0 — Protocol only (no corpus)
**Status:** Stage 0 frozen 2026-05-12. Full corpus freeze deferred to Stage 5.
**DOI:** [to be assigned at OSF deposit]
**Binding from:** 2026-05-12
**Repository:** `docs/tracking/vcl_manifest_tracking.md` (canonical hash source)

---

## §1 Study Declaration   [FROZEN: Stage 0 | 2026-05-12]

### 1.1 Problem

Microservice outages in production cloud environments require Root Cause Analysis (RCA) that spans
three evidence modalities simultaneously: distributed traces, structured logs, and time-series
metrics. Existing tools treat these modalities in isolation, producing partial diagnoses that
lengthen Mean Time to Resolution (MTTR). The diagnostic gap is widest for cross-service cascading
failures where the causal signal is distributed across the observability stack
(proposal §1.4, p. 15).

### 1.2 Artefact

HELIOS is a hybrid multi-pipeline RCA framework built around three peer pipelines:

- **D-pipe** — statistical correlation and propagation (Pearson/Spearman, PPR)
- **G-pipe** — graph-based causal traversal (UEG-C canonical graph + PPR)
- **L-pipe** — LLM-assisted explanation and hypothesis generation (Protocol A)

All pipelines are controlled by the Variant Control Layer (VCL), a runtime feature-flag system.
The Uniform Borda consensus layer fuses per-pipeline ranked candidate lists into a single verdict.

### 1.3 Design Science Research Framing

This study follows Design Science Research (DSR) methodology (Hevner et al., 2004). The artefact
(HELIOS) is the unit of analysis. Construct validity is enforced by **C1 — Runtime-Enforced
Ablation Discipline** (proposal §3.6.7–3.6.8): a system of VCL, snapshot hashing, metric
integrity gate, exclusion ledger, deviation log, and disjointness audit that guarantees every
measurement run is tagged with a content-hashed variant identity and that ablation code paths are
provably disjoint.

### 1.4 Two-Environment Firewall

All confirmatory inference is drawn from **AIOpsLab** runs only. OTEL Demo runs are exploratory
calibration exclusively. Every result row carries an `evaluation_phase` column; rows with
`evaluation_phase = "exploratory"` are excluded from all confirmatory analyses. This firewall is
enforced at the data-collection layer and cannot be relaxed post-hoc without a deviation log entry
recording the analytic consequence.

### 1.5 Contributions and Evidential Status

| ID | Contribution | Evidential status |
|----|-------------|------------------|
| C1 | Runtime-enforced ablation discipline (VCL + C1 artefacts) | Descriptive — evidenced via verification-rate, completion-rate, ledger-entry-count |
| C2 | Hybrid multi-pipeline RCA (D+G+L peer pipelines) | Confirmatory — A-H3 (primary), B-H1 |
| C3 | UEG-C canonical graph with content-hashed identity | Exploratory — E-H2, E-H3 |
| C4 | Uniform Borda consensus fusion | Exploratory — A-H4 (underpowered-disclosed) |
| C5 | Auto-remediation scaffolding | Exploratory empirical validation (Stage 4+) |
| C6 | LLM-assisted explanation (L-pipe + P4 cognitive layer) | Confirmatory — A-H7 |
