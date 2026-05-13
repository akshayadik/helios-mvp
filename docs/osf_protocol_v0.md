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

---

## §2 Hypothesis Register   [FROZEN: Stage 0 | 2026-05-12]

### 2.1 Family A — Ablation (Confirmatory)

**Scope:** AIOpsLab only. Paired Wilcoxon signed-rank (one-sided), Holm–Bonferroni within this family.
**n:** 174 incident pairs.
**Holm rank order (binding from this deposit):** A-H3 > A-H7 > A-H1 > A-H2 > A-H6 > A-H5 > A-H4 > A-H8
**α at rank 1:** 0.00625

| Rank | ID | Null hypothesis | Comparison pair | Primary metric | Direction | Power note |
|------|----|----------------|----------------|----------------|-----------|-----------|
| 1 | A-H3 | Adding G+L to D-pipe does not improve HR@3 | HELIOS-Full vs HELIOS-D | HR@3 | Full > D | — |
| 2 | A-H7 | Removing L-pipe does not degrade HR@3 | HELIOS-Full vs HELIOS-noLLM | HR@3 | Full > noLLM | — |
| 3 | A-H1 | HELIOS-Full HR@3 does not exceed 0.73 | HELIOS-Full vs fixed threshold 0.60 | HR@3 | Full > 0.60 | — |
| 4 | A-H2 | Removing G-pipe does not degrade CpR | HELIOS-Full vs HELIOS-noGraph | CpR | Full > noGraph | — |
| 5 | A-H6 | When G entry gate fires, G-pipe does not improve HR@3 | HELIOS-G vs HELIOS-D (gate-conditional) | HR@3 | G > D | Conditional |
| 6 | A-H5 | Router does not improve HR@3 | HELIOS-Full vs HELIOS-noRouter | HR@3 | Full > noRouter | — |
| 7 | A-H4 | Consensus does not improve HR@3 | HELIOS-Full vs HELIOS-noConsensus | HR@3 | Full > noConsensus | ~65% power — underpowered-disclosed |
| 8 | A-H8 | Structural edges do not improve HR@3 | HELIOS-Full vs HELIOS-noStructural | HR@3 | Full > noStructural | ~62% power — underpowered-disclosed |

**Effect size commitment:** Cohen's h ≥ 0.276 (n = 174, one-sided α = 0.00625, ρ = one-half, 80-percent power).
HELIOS target: HR@3 = 0.73 vs AIOpsLab-equivalent CHASE baseline: HR@3 = 0.60.

### 2.2 Family B — Baseline Comparison (Confirmatory)

**Scope:** AIOpsLab only. Same statistical method as Family A, independent Holm correction.
**Holm rank order (binding from this deposit):** B-H1 > B-H2 > B-H3 > B-H4 > B-H5 > B-H6 > B-H7 > B-H8
**α at rank 1:** 0.00625

| Rank | ID | Null hypothesis | Baseline | Primary metric | Direction |
|------|----|----------------|---------|----------------|-----------|
| 1 | B-H1 | HELIOS-Full HR@3 does not exceed CHASE | CHASE | HR@3 | HELIOS > CHASE |
| 2 | B-H2 | HELIOS-Full HR@3 does not exceed RCACopilot | RCACopilot | HR@3 | HELIOS > RCACopilot |
| 3 | B-H3 | HELIOS-Full CpR does not exceed CHASE | CHASE | CpR | HELIOS > CHASE |
| 4 | B-H4 | HELIOS-Full CpR does not exceed RCACopilot | RCACopilot | CpR | HELIOS > RCACopilot |
| 5 | B-H5 | HELIOS-Full MTTR reduction does not exceed CHASE | CHASE | log-MTTR delta | HELIOS > CHASE |
| 6 | B-H6 | HELIOS-Full hallucination rate is not lower than CHASE | CHASE | hallucination rate | HELIOS < CHASE |
| 7 | B-H7 | HELIOS-Full CoE quality does not exceed CHASE | CHASE | CoE score | HELIOS > CHASE |
| 8 | B-H8 | HELIOS-Full macro-F1 does not exceed CHASE | CHASE | macro-F1 | HELIOS > CHASE |

### 2.3 Family E — Exploratory

**Scope:** OTEL Demo + AIOpsLab subsets. BCa bootstrap, 10,000 resamples, seed deferred to Stage 5. No Holm correction. 95% BCa CI reported.

| ID | Topic | Condition |
|----|-------|-----------|
| E-H1 | HELIOS-noGraph sensitivity on Tier 4 incidents | Reclassified exploratory (n = 12) |
| E-H2 | UEG-C graph hash stability under replay | Structural |
| E-H3 | UEG-C edge taxonomy coverage | Structural |
| E-H4 | Cross-service topology sensitivity | Requires synthetic fault injection (Stage 2+) |
| E-H5 | Latency vs HR@3 trade-off | Operational |
| E-H6 | Token efficiency sensitivity | Sign test, ordinal |
| E-H7 | Human-in-loop feedback loop | Deferred — IRB pending |
| E-H8 | Noise tolerance (telemetry gap injection) | Operational |
| E-H9 | Seed stability (HR@3 variance across seeds) | Reproducibility |
| E-H10 | Multi-fault exclusion sensitivity | Corpus |
