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

---

## §3 Variant × Flag Matrix   [FROZEN: Stage 0 | 2026-05-12]

Flag column key: `l2c` = l2c_llm, `p4c` = p4_cognitive, `l2b` = l2b_graph, `rec` = reconcile,
`ueg` = ueg_c_structural, `dpi` = dpipe, `dpp` = dpipe_propagation, `gpi` = gpipe,
`lpi` = lpipe, `rtr` = router.

### 3.1 Confirmatory Variants (8)

| Variant | l2c | p4c | mahc | cbr | l2b | acp | rec | ueg | dpi | dpp | gpi | lpi | rtr | Status | Hypothesis |
|---------|:---:|:---:|:----:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|--------|-----------|
| HELIOS-Full | T | T | T | T | T | T | T | T | T | T | T | T | T | Confirmatory | A-H1, A-H3, B-H1..B-H8 |
| HELIOS-noLLM | F | T | T | T | T | T | T | T | T | T | T | F | T | Confirmatory | A-H7 |
| HELIOS-noGraph | T | T | T | T | F | T | T | T | T | T | F | T | T | Exploratory | A-H2 sensitivity |
| HELIOS-D | F | T | F | F | F | F | F | T | T | T | F | F | F | Confirmatory | A-H3 |
| HELIOS-G | F | T | F | F | T | F | F | T | T | F | T | F | F | Cond. Confirmatory | A-H6 |
| HELIOS-noConsensus | T | T | F | T | T | T | T | T | T | T | T | T | T | Exploratory | A-H4 |
| HELIOS-noRouter | T | T | T | T | T | T | T | T | T | T | T | T | F | Exploratory | A-H5 |
| HELIOS-noStructural | T | T | T | T | T | T | T | F | T | T | T | T | T | Exploratory | A-H8 |

### 3.2 Exploratory Variants (7)

Used for OTEL Demo calibration only (`evaluation_phase = "exploratory"`). Not included in any confirmatory analysis.

| Variant | Purpose | Key flags off |
|---------|---------|--------------|
| HELIOS-noP4 | Cognitive layer ablation | p4_cognitive=False |
| HELIOS-noMAHC | MAHC module ablation | mahc=False, cbr=False |
| HELIOS-noCBR | CBR ablation only | cbr=False |
| HELIOS-noACP | ACP ablation | acp=False |
| HELIOS-noReconcile | Reconciliation ablation | reconcile=False |
| HELIOS-live | Live ingest mode | ingest_mode="live" |
| HELIOS-noLLM-noGraph | Dual-ablation sensitivity | l2c_llm=False, lpipe=False, l2b_graph=False, gpipe=False |

### 3.3 Variant Config Hashes

Hash computation: SHA-256 of `canonical_json(manifest.model_dump())` where `canonical_json` sorts
keys and rounds floats to 6 decimal places. All hashes computed at commit `573c82f` (post-PR #12).
Source of truth: `docs/tracking/vcl_manifest_tracking.md`.

| Variant | variant_config_hash |
|---------|-------------------|
| HELIOS-Full | `20ab0977d268d0441364f39380cd62b5de94d030a0a70f3c68ec04eaa27db472` |
| HELIOS-noLLM | `84b80788261fb97b562edeae9bddb06fb53c4c18d88df9c1c505e7e12aa87bdc` |
| HELIOS-noGraph | `beb9869d764a2edce8cd7c938cde375f0cdfdcebd249c7a39f9b2110ca08aaca` |
| HELIOS-noConsensus | `5e95946bd5d5be76271082c840a500403379762d5da621fac68fd2202b95e9fb` |
| HELIOS-noRouter | `1ab2b9c0888841ce7fd759032dd78e7acb76a3f9b89f2bcb3c9c1d225bfa87c0` |
| HELIOS-noStructural | `f13360dcaa47132086b94bd743ce1ad90a75dc23e90a9a29356dd64dce7016d0` |
| HELIOS-D | `615bdbb7f18dc963da8e1348e4927c2f766e92e8f49032d6f9fe5dfea67599a7` |
| HELIOS-G | `7a0df90d85909a58480b1331ba3f703f01c98d52e0822231e7d45ba515681b0a` |

---

## §4 Statistical Analysis Plan   [FROZEN: Stage 0 | 2026-05-12]

### 4.1 Primary Tests

| Metric | Test | Pairing | Sidedness | Notes |
|--------|------|---------|-----------|-------|
| HR@3 (continuous) | Wilcoxon signed-rank | Incident-level pairs | One-sided | Primary for A-H1..A-H8 |
| HR@3 (binary threshold pass/fail) | McNemar's exact | Incident-level pairs | One-sided | Pre-registered sensitivity check |
| Token efficiency (ordinal) | Sign test | Incident-level pairs | One-sided | Primary for A-H7 |
| CpR | Wilcoxon signed-rank | Incident-level pairs | One-sided | Primary for A-H2, A-H3 |
| Family E metrics | BCa bootstrap | N/A | Two-sided | 95% BCa CI; seed deferred to Stage 5 |
| GLMM sensitivity | Mixed-effects Poisson | Nested (incident + variant) | N/A | Supplementary only — no binding inference status |

All primary tests computed with `scipy.stats.wilcoxon(alternative="greater")`,
`statsmodels.stats.contingency_tables.mcnemar`, and `scipy.stats.sign_test`.

### 4.2 Error Control

**Strategy:** Holm–Bonferroni within each confirmatory family independently. Families A and B are
corrected separately; cross-family multiplicity is not controlled (families are conceptually
orthogonal).

**Adjusted α values — Family A (n = 8 hypotheses):**

| Rank | Adjusted α = 0.05 / (9 − rank) | Bound hypothesis |
|------|----------------------------------|-----------------|
| 1 | 0.00625 | A-H3 |
| 2 | 0.00714 | A-H7 |
| 3 | 0.00833 | A-H1 |
| 4 | 0.0125 | A-H2 |
| 5 | 0.0167 | A-H6 |
| 6 | 0.025 | A-H5 |
| 7 | 0.0357 | A-H4 |
| 8 | 0.05 | A-H8 |

The same rank structure applies to Family B (B-H1 at rank 1 → α = 0.00625).

### 4.3 Effect Size Commitment

**Pre-registered MDE:** Cohen's h ≥ 0.276.
**Derivation:** n = 174 incident pairs, one-sided α = 0.00625, ρ = one-half (equal allocation),
80-percent power.
**Concrete target:** HELIOS HR@3 = 0.73 vs AIOpsLab-equivalent CHASE baseline HR@3 = 0.60.
This commitment is binding. Post-hoc power reduction requires a deviation log entry.

### 4.4 Asymmetric Inferential Rule

Applies to A-H4 and A-H8 only (underpowered-disclosed at Stage 0):

- **Rejection** of the null → supports the contribution claim at the stated power.
- **Non-rejection** → "inconclusive at delivered power" — not a falsification.

This rule is binding from this Stage 0 deposit. It cannot be invoked post-hoc for any hypothesis
not listed here.

---

## §5 Inclusion/Exclusion and Exclusion-Ledger Rules   [FROZEN: Stage 0 | 2026-05-12]

### 5.1 Run-Level Inclusion Criteria

All three criteria must hold for a run to enter an analysis cell:

1. **VCL hash match** — `row.variant_config_hash` equals the registered hash for that variant
   (source: `docs/tracking/vcl_manifest_tracking.md`).
2. **Snapshot hash match** — `row.snapshot_hash` matches the corpus snapshot hash for that
   incident at replay.
3. **L-pipe Protocol A conformance** — Token sequence matches Protocol A exactly (temperature =
   zero, top-p = one, top-k = one, enforce_eager = True, single-replica deployment).

### 5.2 Run-Level Exclusion Triggers

Each failure is logged to `exclusion_ledger.jsonl` with a `gate_check` label:

| Trigger | gate_check value | Analytic consequence |
|---------|-----------------|----------------------|
| VCL hash mismatch | `variant_config_hash_match` | Run excluded; variant-identity rate decremented |
| Snapshot hash mismatch | `cross_pipeline_snapshot_hash_match` | Run excluded; snapshot-consistency rate decremented |
| Protocol A token deviation | `protocol_a_deviation` | Run excluded; L-pipe integrity failure logged |
| Cell completion below threshold | `cell_completion_threshold` | Cell excluded; C1 completion rate decremented |
| Missing required field | `required_field_present` | Run excluded immediately |

### 5.3 Exclusion-Ledger Entry Fields (7 required)

Every exclusion-ledger entry must contain exactly these 7 fields:

| Field | Description |
|-------|-------------|
| `variant_config_hash` | Hash of the manifest that produced the run |
| `snapshot_hash` | Hash of the telemetry snapshot for this incident |
| `run_id` | Unique identifier of this execution |
| `incident_id` | Corpus incident identifier |
| `gate_check` | One of the labels from §5.2 |
| `reason` | Human-readable description of the failure |
| `analytic_consequence` | Impact on C1 evidence rates |

This schema is binding. Adding fields requires a deviation log entry. Removing fields is not
permitted.

### 5.4 Corpus-Level Inclusion

**Fault taxonomy:** 6 categories — resource, network, dependency, config, code, external.
Incidents outside this taxonomy are excluded and logged.

**Label requirement:** Single-cause ground-truth labels only. Multi-cause incidents are excluded
(logged with `gate_check = "multi_cause_label"`).

**Pairing requirement:** All 8 confirmatory variants must be evaluated on every included incident.
Partial evaluations are excluded.

**Cell-completion threshold:** ≥ 80-percent of cells per incident must have valid runs before the
incident enters the confirmatory analysis matrix. Enforced at runtime by the metric integrity gate
(Stage 1+ implementation; gate logic pre-registered here).

---

## §6 Scope Contraction Register   [FROZEN: Stage 0 | 2026-05-12]

This register tracks evidential-status changes from the original proposal Table 15 commitments.
It is a scientific audit tool — it records hypothesis evidential status and the analytic
consequences of known power shortfalls. It is not a project-planning document.

| Entry | Original scope | Status at Stage 0 | Asymmetric rule? | Rationale |
|-------|--------------|------------------|-----------------|-----------|
| A-H4 | Consensus HR@3 (confirmatory) | Underpowered-disclosed (~65% power) | Yes — non-rejection ≠ falsification | n = 174 pairs at α = 0.00625 yields only ~65-percent power for the expected consensus effect size |
| A-H8 | Structural edges HR@3 (confirmatory) | Underpowered-disclosed (~62% power) | Yes — non-rejection ≠ falsification | Same n; smaller expected effect size for structural-edge contribution |
| E-H1 | HELIOS-noGraph sensitivity (originally ablation-adjacent) | Reclassified exploratory | No | Tier 4 incident subset, n = 12 — insufficient power for confirmatory claim |
| E-H4 | Cross-service topology sensitivity | Exploratory (synthetic injection required) | No | Requires AIOpsLab synthetic fault injection; targeted for Stage 2+ |
| E-H6 | Token efficiency sensitivity | Exploratory | No | Ordinal measurement requires sign test; separate power analysis in progress |
| E-H7 | Human-in-loop feedback loop | Deferred | No | Human-participant data collection pending IRB approval |
| C1 | Runtime-enforced ablation discipline | Descriptive by design | N/A | C1 is the audit infrastructure; evidenced via VCL verification-rate, completion-rate, and ledger entry counts — not via statistical inference |
| C3' | Extended graph causal inference | Exploratory empirical validation | No | Full causal identification requires Stage 4 G-pipe + ORAR pre-training |
| C5 | Auto-remediation scaffolding | Exploratory empirical validation | No | Stage 4+ artefact; confirmatory evaluation not feasible in MVP phase |

**Reactivation rule:** Any entry may be moved from exploratory to confirmatory in a future
protocol revision, provided that revision is deposited at OSF before data collection for that
hypothesis begins, and a deviation log entry is filed recording the analytic consequence.

---

## §7 Reproducibility Manifest   [STUB — frozen at Stage 5]

The following artefacts are deferred to the Stage 5 OSF full freeze. They MUST NOT be committed
to this document earlier — premature commitment would introduce corpus selection bias.

**Deferred to Stage 5:**
- Corpus manifest SHA-256 (174 incidents, AIOpsLab)
- BCa bootstrap seed (10,000 resamples for Family E)
- L-pipe prompt SHA (SHA-256 of the frozen prompt template)
- Container image digests (vLLM version, Ollama version)
- AIOpsLab incident selection seed

**Frozen at Stage 0 — L-pipe Protocol A parameters:**

| Parameter | Value |
|-----------|-------|
| Model | Llama-3.1-70B-Instruct |
| Serving | vLLM 0.6.x |
| temperature | zero |
| top-p | one |
| top-k | one |
| enforce_eager | True |
| deployment | single-replica |
| Contrast model (exploratory only) | Qwen-2.5-72B-Instruct |

**Stage 5 procedure:**
1. Compute and record corpus manifest SHA-256.
2. Draw and record BCa bootstrap seed.
3. Record L-pipe prompt SHA.
4. Record container image digests.
5. Commit this section and upload to OSF.
6. Record the OSF DOI in `deviation_log.jsonl` as a protocol freeze event with
   `--analytic-consequence "Stage 5 OSF full freeze deposited"`.
