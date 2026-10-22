# HELIOS — Feature Implementation Summary
**Stage 0 through Milestone 4 (current state as of 2026-05-26)**

---

## Quick Status Summary

| Phase | Milestone | Status | Gate |
|---|---|---|---|
| Stage 0 | Repo + VCL + Harness + Schemas | ✅ COMPLETE | tag `stage-0-exit` SHA `541a670` |
| Milestone 1 | Telemetry Pipeline + Full C1 Foundations | ✅ COMPLETE | tag `milestone-1-exit` SHA `f11c529` |
| Milestone 2 | D-pipe + UEG-C Builder | ✅ COMPLETE | PR #23 merged |
| Milestone 3 | G-pipe + L-pipe + OSF Freeze | ✅ COMPLETE | PR #24 merged; OSF sig `e93b5b88` |
| Milestone 4 | Consensus + Ablation Run Prep | ✅ Design frozen | Arch review SHA `9042f21`; run blocked pending `llama3.1:8b` pull |

---

## Stage 0 — Repo Spine, VCL, Harness, Schemas

**Objective:** Establish the ablation-first research spine and enforce C1 before any pipeline code is written.

### Feature 1: VCL Flag Registry
- **Feature:** `helios/vcl/registry.py` — `VCLFlag` enum with 14 flags
- **Purpose:** Single source of truth for all feature flags; enables `@gated_by` to validate at decoration time
- **Status:** ✅ Frozen (Stage 0)
- **Capabilities:** 13 boolean flags + 1 operational string flag; `bool_flags()` excludes `INGEST_MODE` for safe iteration; OCP — adding a flag requires only editing the enum
- **Dependencies:** Required by `config.py`, `decorators.py`, `variants.py` — all consumers import from this enum

### Feature 2: VCLManifest (Configuration + Hash)
- **Feature:** `helios/vcl/config.py` — `VCLManifest` Pydantic model
- **Purpose:** Immutable variant configuration; `compute_variant_config_hash()` produces the run-level cryptographic identity
- **Status:** ✅ Frozen (Stage 0)
- **Capabilities:** `frozen=True, extra="forbid"`; `SHA-256(canonical_json(manifest))`; `@field_validator` on `ingest_mode`; `from_flags()` factory method
- **Dependencies:** `utils.py` (canonical_json); consumed by orchestrator, all pipelines, and metric integrity gate

### Feature 3: Canonical JSON Utility
- **Feature:** `helios/vcl/utils.py` — `canonical_json()`
- **Purpose:** Deterministic serialisation — sorted keys, 6-decimal float normalisation, no whitespace
- **Status:** ✅ Frozen (Stage 0)
- **Capabilities:** Pre-normalises floats recursively before `json.dumps` (required because `json.dumps` never calls `default()` for native Python `float`)
- **Dependencies:** Used by `config.py` (manifest hash) and all schema `compute_*_hash()` methods

### Feature 4: Gating Decorator
- **Feature:** `helios/vcl/decorators.py` — `@gated_by(VCLFlag.X)`
- **Purpose:** Runtime enforcement that gated components only execute when their controlling flag is active
- **Status:** ✅ Frozen (Stage 0)
- **Capabilities:** Decoration-time `TypeError` if non-boolean flag passed; call-time `GatedComponentInactiveError`; `__gated_by__` attribute registration for static audit; `ContextVar` for thread/async safety
- **Dependencies:** Requires `set_current_manifest()` call before any gated component invocation

### Feature 5: Pre-registered Ablation Variants
- **Feature:** `helios/vcl/variants.py` — `CONFIRMATORY_VARIANTS` + `EXPLORATORY_VARIANTS`
- **Purpose:** Pre-registered, version-controlled variant definitions; any change is visible in git diff
- **Status:** ✅ Frozen (Stage 0 definition; hashes locked at OSF freeze Milestone 3)
- **Capabilities:** 8 confirmatory variants + 7 exploratory variants; `get_variant(name)` resolver; all hashes unique (CI-enforced)
- **Dependencies:** `VCLManifest.from_flags()` factory

### Feature 6: HMAC-Chained Deviation Log
- **Feature:** `bin/log_deviation.py` + `helios/vcl/hmac_chain.py`
- **Purpose:** Cryptographically signed, append-only record of every protocol departure with analytic consequence
- **Status:** ✅ Operational (Stage 0); 18 entries, chain verified
- **Capabilities:** HMAC-SHA256 chain; `deviation_id` derived post-sign; `verify` subcommand; CLI append + verify
- **Dependencies:** `DEVIATION_HMAC_SECRET` from `.env`; required in GitHub Secrets for `ledger_verification.yml`

### Feature 7: Snapshot Registry
- **Feature:** `helios/vcl/snapshot_registry.py`
- **Purpose:** L2 analysis identity gate — every UEGCSnapshot must be registered before pipeline dispatch
- **Status:** ✅ Frozen (Stage 0); 20 entries in `data/snapshot_registry.jsonl`
- **Capabilities:** Append-only JSONL; `DuplicateSnapshotError` on collision; `_validate_hex64` on both hashes
- **Dependencies:** Consumed by orchestrator; pre-condition gate for all three peer pipelines

### Feature 8: Canonical Data Schemas (L0–L3)
- **Feature:** `helios/schemas/` — `TelemetryWindow`, `UEGCSnapshot`, `PipelineVerdict`
- **Purpose:** Frozen contracts for all pipeline-crossing message types; schema-round-trip CI enforcement
- **Status:** ✅ Frozen at `schema-draft-v0.1` (Stage 0)
- **Capabilities:** All `frozen=True, extra="forbid"`; `compute_*_hash()` on each schema; `evaluation_phase` enum enforces two-environment firewall; CI round-trip tests in `tests/test_schema_roundtrip.py`
- **Dependencies:** Consumed by all pipelines, orchestrator, metric integrity gate, result store

### Feature 9: Pipeline Null Stubs (G-pipe, L-pipe)
- **Feature:** `helios/pipelines/g_pipe/stub.py`, `helios/pipelines/l_pipe/stub.py`
- **Purpose:** Gated stubs at Stage 0 — enforce VCL gating contracts for pipelines not yet implemented
- **Status:** ✅ Replaced by real implementations at Milestones 2–3
- **Capabilities:** `@gated_by` applied; `GatedComponentInactiveError` when flag OFF; sentinel `PipelineVerdict` when flag ON (preserves E2E smoke contract)
- **Dependencies:** `VCLFlag.L2B_GRAPH` (G-pipe), `VCLFlag.L2C_LLM` (L-pipe)

### Feature 10: Tracking Validator + Pre-commit Hooks
- **Feature:** `scripts/validate_tracking.py`; `.claude/hooks/flag-guard.py`, `research-compliance.py`
- **Purpose:** Enforce schema rules R1–R8 on tracking docs; block commits that violate research integrity
- **Status:** ✅ Operational (Stage 0)
- **Capabilities:** R1–R8 schema enforcement; `make validate-tracking` + pre-commit gate; `flag-guard.py` ensures every new `def`/`class` outside `helios/vcl/` has VCL import or `HELIOS_ENABLE_*`
- **Dependencies:** Pre-commit hook + CI `validate-tracking` job

---

## Milestone 1 — Telemetry Pipeline + Full C1 Foundations

**Objective:** Wire C1 enforcement end-to-end; 20 incidents with full invariant compliance.

### Feature 11: Run Orchestrator
- **Feature:** `helios/orchestrator/runner.py` — `RunOrchestrator`; `bin/helios_run.py`
- **Purpose:** Single entry point for corpus runs; wires the complete C1 enforcement path
- **Status:** ✅ Frozen (Milestone 1; sequential dispatch updated Milestone 3)
- **Capabilities:** `CorpusLoader → CaptureReader → SnapshotRegistry → run_dpipe → run_gpipe(conditional) → run_lpipe → MetricIntegrityGate → ResultStore / ExclusionLedger → ReconciliationLedger`; `helios run --variant ... --corpus ...` CLI
- **Dependencies:** All three pipelines + VCL + all C1 sub-artefacts

### Feature 12: Metric Integrity Gate
- **Feature:** `helios/integrity_gate.py`
- **Purpose:** Runtime rejection of incomplete cells — enforces that every run has all required metrics before a result row is written
- **Status:** ✅ Frozen (Milestone 1)
- **Capabilities:** Verifies matching `variant_config_hash` + `snapshot_hash` across all active pipelines; routes failed runs to exclusion ledger
- **Dependencies:** Active `VCLManifest` (via `get_current_manifest()`); `PipelineVerdict` from all active pipelines

### Feature 13: Exclusion Ledger
- **Feature:** `bin/log_exclusion.py` — `AppendOnlyLedger` protocol
- **Purpose:** Transparent missingness record — every excluded run is signed and logged
- **Status:** 🟡 Partial (schema defined; CLI stub; auto-populated via `AppendOnlyLedger`)
- **Capabilities:** Signed JSONL; routes from metric integrity gate on FAIL
- **Dependencies:** `DEVIATION_HMAC_SECRET`; triggered by `MetricIntegrityGate`

### Feature 14: Reconciliation Ledger
- **Feature:** `helios/orchestrator/ledger.py`
- **Purpose:** Provisional + terminal reward correspondence audit for ORAR (L4 learning)
- **Status:** ✅ Frozen (Milestone 1); 25 entries, HMAC chain verified
- **Capabilities:** HMAC-chained append; `record(outcome)` called after every run
- **Dependencies:** HMAC chain (same mechanism as deviation log); consumed by ORAR parameter update at L4

### Feature 15: Disjointness Auditor
- **Feature:** `helios/vcl/disjointness.py`
- **Purpose:** Prove that each feature flag toggles exactly one disjoint code path
- **Status:** ✅ Frozen (Milestone 1); PASSED at Milestone 4 arch review (5 covered, 0 violations)
- **Capabilities:** Static inspection of `__gated_by__` attributes; CI workflow `disjointness_audit.yml`; hidden-coupling audit resolved one issue in `p4_cognitive` flag scope
- **Dependencies:** `@gated_by` decorator registration; `coverage.py` for dynamic audit

### Feature 16: DuckDB Result Store
- **Feature:** `helios/store/schema.sql`; result row DDL
- **Purpose:** Persistent storage of all pipeline verdicts and consensus verdicts for statistical analysis
- **Status:** ✅ Frozen (Milestone 1; schema-draft-v0.2 adds consensus_verdict table at Milestone 4)
- **Capabilities:** `PipelineVerdict` rows with `variant_config_hash` + `snapshot_hash` + `evaluation_phase`; two-environment firewall enforced by `evaluation_phase` column
- **Dependencies:** `PipelineVerdict` schema; populated by orchestrator

### Feature 17: 20-Incident OTEL Demo Corpus
- **Feature:** `data/` — Parquet recordings (P1 metrics, P2 traces, P3 logs)
- **Purpose:** Exploratory calibration corpus; 20 incidents with byte-equal replay across 3 replays
- **Status:** ✅ Recorded and verified (Milestone 1)
- **Capabilities:** Stable snapshot hashes across replays; `CaptureReader` verifies recording hash at every run
- **Dependencies:** OTEL Demo docker environment; `TelemetryWindow` schema

---

## Milestone 2 — D-pipe + UEG-C Builder

**Objective:** Statistical baseline pipeline + content-hashed graph construction.

### Feature 18: UEG-C Builder
- **Feature:** `helios/graph/ueg_c_builder.py` — `build_ueg_c()`
- **Purpose:** Construct the Unified Evidence Graph from telemetry data
- **Status:** ✅ Frozen (Milestone 2; SHA `1b5fd30`; PPR fix `d0e8576`)
- **Capabilities:** Structural edges (temporal containment = topology heuristic); call edges (trace-derived, normalised weight); independently gated by `ueg_c_structural` and `l2b_graph`
- **Dependencies:** OTEL traces Parquet (`p2_traces_path`); `UEGCSnapshot` schema

### Feature 19: K-hop PPR Pruner
- **Feature:** `helios/graph/ppr_pruner.py` — `prune_graph()`
- **Purpose:** Extract incident-relevant subgraph (50–200 nodes) from full UEG-C via personalised PageRank
- **Status:** ✅ Frozen (Milestone 2; calibrated on 15-incident corpus)
- **Capabilities:** PPR alpha=0.85; `PRUNER_THRESHOLD=0.02`; entry-point detection (`structural_in_degree==0 AND out_degree>0`); async consumer exclusion; hub fallback; efficacy gate 0.20; integrity gate 0.40
- **Dependencies:** `UEGCSnapshot`; D-pipe and G-pipe both consume the pruned subgraph

### Feature 20: D-pipe Statistical Pipeline
- **Feature:** `helios/pipelines/d_pipe/pipeline.py` — `run_dpipe()` (gated by `VCLFlag.DPIPE`)
- **Purpose:** Statistical anomaly detection and root-cause ranking from multimodal telemetry
- **Status:** ✅ Frozen (Milestone 2; SHA `8d11801`)
- **Capabilities (four stages):**
  - **A** `a_metrics_parser.py`: ingest Prometheus Parquet; compute wm90 latency + error rate per service (histogram bin interpolation)
  - **B** `b_anomaly_scorer.py`: Pearson/Spearman correlation + `w_error`-weighted composite score
  - **C** `c_propagation_engine.py`: propagate scores along CALL edges with `rho_threshold=0.20` damping (gated by `VCLFlag.DPIPE_PROPAGATION`)
  - **D** `d_verdict.py`: rank services; emit `PipelineVerdict` with `ranked_candidates`, `hr_at_3`, `cpr`
- **Calibration:** LOO-CV HR@3=0.5333 on 15-incident corpus; `w_error=0.30`, `topology_boost_factor=1.00`
- **Dependencies:** `UEGCSnapshot` (pruned); `dpipe_config.py` (frozen parameters); `VCLFlag.DPIPE` + `VCLFlag.DPIPE_PROPAGATION`

---

## Milestone 3 — G-pipe + L-pipe + OSF Protocol Freeze

**Objective:** All three peer pipelines running; protocol locked before any confirmatory data collection.

### Feature 21: G-pipe — Conditional PPR-Traversal Pipeline
- **Feature:** `helios/pipelines/g_pipe/pipeline.py` — `run_gpipe()` (gated by `VCLFlag.GPIPE`)
- **Purpose:** Graph-based peer pipeline that activates when D-pipe produces ambiguous results
- **Status:** ✅ Frozen (Milestone 3; SHA `8759d6f`)
- **Capabilities:** Entry gate (`disagreement = ppr_scores[rank_2] / ppr_scores[rank_0] ≥ 0.20`); re-runs PPR seeded from D-pipe scores; sentinel emission when gate does not fire (`narrative="gpipe-gated-or-skipped"`); LOO-CV HR@3=0.60 on gate-firing incidents; mandatory sentinel filter for A-H6 metric queries
- **Calibration:** `DISAGREEMENT_THRESHOLD=0.20`; `GPIPE_PPR_ALPHA=0.85` (lowered from 0.30 — deviation #14)
- **Dependencies:** D-pipe `ppr_scores` (sequential dispatch); `l2b_graph` flag as soft guard inside `should_run_gpipe()`; `VCLFlag.GPIPE`

### Feature 22: L-pipe — LLM Explanation Pipeline
- **Feature:** `helios/pipelines/l_pipe/pipeline.py` — `run_lpipe()` (gated by `VCLFlag.L2C_LLM`)
- **Purpose:** Generate Chain-of-Evidence (CoE) narrative and ranked candidate list from LLM reasoning
- **Status:** ✅ Frozen (Milestone 3; SHA `25fcd2b`)
- **Capabilities (Protocol A):**
  - Model: `llama3.1:8b` via Ollama; greedy decoding (`temperature=0, top_p=1, top_k=1`); seed 42
  - `PromptRegistry`: loads `prompts/rca_v1.txt`; verifies `SHA-256 = 376e555b...` before every inference — `PromptTamperError` on mismatch
  - `ResponseHandler`: markdown fence stripping → Pydantic `LPipeResponse` validation → 1 retry → fallback to `["l-pipe-fallback"]`
  - Sentinel: `narrative="lpipe-gated-or-skipped"` when flag OFF (mandatory filter for A-H1 metric queries)
- **Deviations:** #15 (llama3.1:8b instead of Llama-3.1-70B); #16 (Ollama instead of vLLM — latency not production-representative)
- **Dependencies:** Ollama running on `localhost:11434`; `VCLFlag.L2C_LLM` (= `lpipe`); `UEGCSnapshot`

### Feature 23: OSF Pre-registration Protocol Freeze
- **Feature:** `research/osf/` — 6 JSON artefacts + `manifest_sig.txt`
- **Purpose:** Lock all pre-registration commitments before any confirmatory data collection
- **Status:** ✅ Frozen (Milestone 3; `manifest_sig = e93b5b88`)
- **Capabilities:** Hypotheses, variant hashes, corpus seeds, prompt SHA, calibration thresholds all locked; CI job `osf-freeze-verify` validates integrity on every push
- **Contents:** `hypotheses.json`, `variant_hashes.json`, `corpus_seeds.json`, `prompt_sha.json`, `calibration_thresholds.json`, `analysis_plan.json`, `manifest_sig.txt`
- **Dependencies:** All upstream parameter freezes (D-pipe, G-pipe, L-pipe, VCL variant hashes)

---

## Milestone 4 — Consensus Layer + Ablation Run Preparation

**Objective:** Multi-pipeline verdict aggregation; prepare full ablation matrix run.

### Feature 24: Uniform Borda Consensus
- **Feature:** `helios/consensus/protocol.py` + `helios/consensus/fuse_verdicts.py` — `UniformBordaConsensus`
- **Purpose:** Aggregate verdicts from all active pipelines into a single ranked root-cause list
- **Status:** ✅ Design frozen (Milestone 4; arch review SHA `9042f21`)
- **Capabilities:** Weighted Borda aggregation; `ConsensusVerdict` with `fusion_algorithm` immutable tamper-anchor; AST fingerprint (`FUSION_ALGORITHM_SHA`) stored in every row; `PassthroughConsensus` for single-pipeline variants; `ConsensusIntegrityGate` verifies `fusion_algorithm_sha` before every write
- **Dependencies:** `PipelineVerdict` from all active pipelines; `schema-draft-v0.3` adds `consensus_verdict` table to DuckDB

### Feature 25: Exploratory Ablation Notebook (L4 Analysis Section)
- **Feature:** `docs/tracking/ablation_architecture.md` §5; `experiments/experiment_log.csv`
- **Purpose:** Structured analysis section for L4 exploratory results
- **Status:** ✅ Design section complete (Milestone 4); run results pending full ablation
- **Capabilities:** Documents fusion algorithm decision, sentinel handling, two-environment firewall enforcement
- **Dependencies:** Full corpus run (currently blocked — `llama3.1:8b` model pull pending)

---

## Features Not Yet Implemented (Phase 2 — AIOpsLab Stage 6+)

| Feature | Target Milestone | Dependency |
|---|---|---|
| AIOpsLab corpus migration | Milestone 6 | `ingest_mode` extension; service-name registry |
| ORAR bandit router (LinUCB) | Milestone 7 | Pre-warmed ACP weights + OSF confirmatory freeze |
| Action-Class Predictor (ACP) | Milestone 7 | AIOpsLab incident corpus for training |
| Full disjointness audit (all 13 flags) | Milestone 7 | All pipelines + L4 implemented |
| FGSV shadow validator (KS-gated) | Milestone 8 | AIOpsLab digital twin environment |
| HITL gate | Milestone 8 | Production-adjacent evaluation |
| Confirmatory 16,000-run ablation | Milestone 8 | AIOpsLab corpus + OSF confirmatory pre-reg |
| Snapshot gating (full) | Stage 6 | Metric integrity gate extension |
| C1 evidence tables (Chapter 4) | Milestone 5 / 9 | Full run completion |

---

## Implementation Health Summary

| Category | Count | Status |
|---|---|---|
| C1 sub-artefacts implemented | 8 of 8 | ✅ All operational |
| Ablation variants defined | 15 (8 confirmatory + 7 exploratory) | ✅ All hashes unique, CI-enforced |
| OTEL incidents recorded | 20 | ✅ Byte-equal replay verified |
| Deviation log entries | 18 | ✅ Chain verified |
| Reconciliation ledger entries | 25 | ✅ HMAC chain verified |
| Test coverage gate | ≥90% (enforced in CI) | ✅ Passing |
| OSF freeze artefacts | 6 JSON + manifest_sig | ✅ `e93b5b88` |
| Pre-registered hypotheses (A-family) | A-H1 through A-H8 | ✅ Locked at OSF freeze |
