# S2.5 MAHC with calibrated confidence (IN2) and S2.6 vote-only Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** HELIOS publishes one fused root-cause list per incident: MAHC (σ-weighted Borda under signal-type priors, a calibrated confidence and a CONFIRMED / PROVISIONAL state) when `mahc_hierarchical` is on, plain vote-only Borda when it is off; HR@k is scored on it.

**Architecture:** New `helios/telemetry/signal_type.py` (label-free signal type of the trigger); `helios/consensus/` gains `mahc.py` (votes, weights, fusion), `vote_only.py` (S2.6), `priors.py`, `calibration.py` (features, logistic + isotonic, floor), `timing.py` (replayed concurrency), `params.py` (frozen file). The runner fuses after the three pipelines and stores a `fusion_row` per run; the scorer reads it as the FUSED list. A build tool cross-fits priors and calibration and chooses the floor. PR 1 builds everything with provisional parameters and records the rules; PR 2 runs, freezes, records.

**Tech Stack:** Python 3.11, numpy, scipy (optimize), pandas, pydantic v2, duckdb; pytest. No scikit-learn (isotonic by pool-adjacent-violators).

**Spec:** `docs/sprints/s2-reasoning/s2_5_mahc_design.md` (approved 2026-10-30). Rows **S2-M7-ENG05** (MAHC) and **S2-M7-ENG06** (vote-only).

## Global Constraints

- No label, fault type, injection time or system name reaches any fusion input; system name is used only by the build tool's fold scheme (build labels).
- Priors keyed on signal type ∈ {resource, latency, error, unclassified} → global; back-off below **30** cases; Beta smoothing toward global with strength **10** (M-a).
- w_p = π_p / (σ_p² + ε), ε = 10⁻⁴, normalised over pipelines that returned a list; σ None → 1; SKIPPED / FAILED / ABSTAINED contribute nothing.
- Borda: rank r of n scores (n − r + 1)/n, unlisted 0; ties by name; out-of-scope services dropped first. Fused σ = √(Σ w_p σ_p²).
- Features: top-1 share, normalised entropy, fused σ, contributing pipelines, top-1s agree. Logistic score then isotonic to P(root in fused top 3), nested cross-fitted on the same outer folds (OTel by root service, RCAEval by system).
- Floor: per corpus, the lowest c with held-out HR@3 ≥ **0.80** among cases with confidence ≥ c; the floor is the larger; no qualifying c in a corpus → stop and report (exit 3), no fallback (M-c, M-e).
- Timing: first publication at min(30 s, all done) from the pipelines done by then; terminal when all done within 90 s; else non-convergence (PROVISIONAL + HITL). Scored list = terminal; TTT = first publication of any state; timing fields outside rerun equality.
- Vote-only: same lists, equal weights, no priors, σ or confidence, always CONFIRMED, same 90 s cutoff.
- Every new module references the VCL; MAHC under `VCLFlag.MAHC_HIERARCHICAL`; never edit `variants.py`, `research/osf/*`, `metric_contract.md`, the seed register, frozen pipeline parameters.
- Deviation entries via the CLI after owner review; tracking rows IN_PROGRESS → DONE in separate commits (rebuild rows by header index and check the validator parses them); never `cd`; never `git commit -a`; check exit codes; **no push** — full local gate, then a local `--no-ff` merge on the owner's go-ahead.

## Review Focus

1. **One pipeline only** (G-pipe gated off, L-pipe abstained): fusion is that list, fused σ = its σ, features defined (entropy of one list), no division by zero. *(Task 3 test)*
2. **Every pipeline empty or failed**: no fused list; the run stores a fusion row with an empty list and state PROVISIONAL, never crashes the runner. *(Task 7 test)*
3. **A signal-type context with fewer than 30 build cases for a pipeline**: the prior backs off to global and the fusion evidence records level "global". *(Task 4 test)*
4. **All held-out confidences tie** (isotonic flat): the floor rule still returns a value or None deterministically. *(Task 5 test)*
5. **A fallback trigger** (no series crossed): signal type "unclassified", not an error. *(Task 2 test)*

---

## PR 1 — signal type, fusion, priors, calibration, timing, wiring, build tool, rules entry

### Task 1: Open the rows

- [ ] **Step 1:** Branch `s2/mahc` from local `main`. Commit the design note and this plan.
- [ ] **Step 2:** Add rows S2-M7-ENG05 and S2-M7-ENG06 as IN_PROGRESS (Started 2026-10-30, Deps S2-M7-ENG04 / S2-M7-ENG05); validator exit 0 and both rows parsed; commit `tracking: S2-M7-ENG05, ENG06 IN_PROGRESS (S2.5 MAHC, S2.6 vote-only)`.

### Task 2: Signal type

**Files:** Create `helios/telemetry/signal_type.py`; Modify `helios/graph/anomaly_intensity.py` (add `named_metric_series`, existing functions unchanged); Test `tests/telemetry/test_signal_type.py`.

**Interfaces — Produces:**
- `named_metric_series(metrics, window_start_iso, n_buckets, bucket_seconds) -> dict[str, list[tuple[str, Series]]]` — as `metric_series(..., fold_histograms=True)` but each series keeps its metric name.
- `class SignalType(StrEnum)`: RESOURCE, LATENCY, ERROR, UNCLASSIFIED.
- `RESOURCE_WORDS`, `LATENCY_WORDS`, `ERROR_WORDS: tuple[str, ...]` — resource: cpu, mem, memory, gc, thread, fd, disk, socket; latency: latency, duration, response_time; error: error, fail, 5xx (lower-case substring match; error checked first, then latency, then resource).
- `signal_type(window: TelemetryWindow, trigger: TriggerRecord, *, root: Path, bucket_seconds: int) -> SignalType` — top suspect = `trigger.suspects[0]`; its metric series' `causal_z` at the trigger bucket; the largest names the type. Fallback trigger, no suspect, no P1 or no finite z → UNCLASSIFIED.

- [ ] **Step 1: tests:** `test_cpu_spike_is_resource`, `test_latency_series_is_latency`, `test_error_counter_is_error` (hand P1 frames, trigger at bucket 10); `test_fallback_trigger_is_unclassified` (Review Focus 5); `test_words_order_error_before_latency` (`http_server_duration_errors` → ERROR); `test_never_reads_labels` (only P1 opened).
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

### Task 3: Votes, weights, MAHC fusion and vote-only

**Files:** Create `helios/consensus/mahc.py`, `helios/consensus/vote_only.py`; Test `tests/consensus/test_mahc_fusion.py`.

**Interfaces — Produces:**
- `@dataclass(frozen=True) class Vote`: `pipeline: str`, `ranked: tuple[str, ...]` (in scope only), `sigma: float` (None → 1); `votes_from(verdicts: Sequence[PipelineVerdict]) -> list[Vote]` (RANKED with a non-empty list only).
- `@dataclass(frozen=True) class Fusion`: `ranked`, `scores: dict[str, float]`, `weights: dict[str, float]`, `fused_sigma: float | None`, `contributing: tuple[str, ...]`, `top1s_agree: bool`.
- `fuse(votes: Sequence[Vote], priors: Mapping[str, float]) -> Fusion` (MAHC); `vote_only(votes: Sequence[Vote]) -> Fusion` (equal weights, `fused_sigma` None).
- `MAHC_EPSILON = 1e-4`.

- [ ] **Step 1: tests:**
  - `test_ch3_counterexample_same_ranking_different_sigma`: three votes [A, B] at σ 0.1 vs three at σ 0.8, equal priors → same `ranked`; fused σ 0.1 vs 0.8 (approx).
  - `test_disagreement_counterexample`: D [A, B] σ 0.8, L [A, B] σ 0.8, G [B, A] σ 0.1, equal priors → MAHC ranks B first; `vote_only` ranks A first (A 2.5, B 2).
  - `test_none_sigma_counts_as_one`; `test_priors_shift_weight` (prior 0.9 vs 0.3, equal σ → weights 3:1); `test_single_vote` (Review Focus 1: ranked = the list, fused σ = its σ); `test_ties_by_name`; `test_skipped_and_abstained_excluded` (`votes_from`); `test_out_of_scope_dropped`.
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

### Task 4: Hierarchical priors

**Files:** Create `helios/consensus/priors.py`; Test `tests/consensus/test_priors.py`.

**Interfaces — Produces:**
- `@dataclass(frozen=True) class PriorCase`: `signal: SignalType`, `hits: Mapping[str, int | None]` (pipeline → 1/0 top-3 hit; None if the pipeline gave no list).
- `@dataclass(frozen=True) class PriorTable`: `global_: dict[str, float]`, `by_signal: dict[str, dict[str, float]]`, `counts: dict[str, dict[str, int]]`; `lookup(pipeline: str, signal: SignalType) -> tuple[float, str]` (value, "signal" | "global").
- `fit_priors(cases: Sequence[PriorCase]) -> PriorTable` — global = mean hit over cases where the pipeline gave a list; a pipeline never seen gets prior 1; signal = (hits + 10·global)/(n + 10), used only when n ≥ 30.
- `PRIOR_STRENGTH = 10`, `MIN_CASES = 30`.

- [ ] **Step 1: tests:** `test_global_is_mean_of_given_lists`; `test_signal_prior_smoothed_exact` (n 40, 30 hits, global 0.6 → (30 + 6)/50 = 0.72); `test_backs_off_below_30` (Review Focus 3: level "global"); `test_missing_lists_excluded`; `test_unseen_pipeline_prior_one`.
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

### Task 5: Features, calibration, floor, state

**Files:** Create `helios/consensus/calibration.py`; Test `tests/consensus/test_calibration.py`.

**Interfaces — Produces:**
- `features(f: Fusion) -> tuple[float, float, float, float, float]` — top-1 share, entropy / log(n) (0 for one candidate), fused σ (1 if None), contributing count, 1 if top-1s agree else 0.
- `@dataclass(frozen=True) class Calibrator`: `coef: tuple[float, ...]`, `intercept: float`, `knots: tuple[tuple[float, float], ...]` (isotonic breakpoints on the logistic score); `fit(xs, ys) -> Calibrator` (logistic by `scipy.optimize.minimize`, L2 strength 1, then pool-adjacent-violators); `predict(x) -> float` (step interpolation, deterministic).
- `choose_floor(conf: Sequence[float], hit: Sequence[int], corpus: Sequence[str], target: float = 0.8) -> float | None` — per corpus the lowest c with mean hit ≥ target over conf ≥ c; the larger; None if any corpus has none.
- `class State(StrEnum)`: CONFIRMED, PROVISIONAL, NON_CONVERGED; `state(conf: float | None, floor: float | None, all_in: bool) -> State` (floor None or conf None → PROVISIONAL).

- [ ] **Step 1: tests:** `test_features_single_candidate`; `test_isotonic_is_monotone`; `test_floor_exact` (two corpora, hand values → the stricter corpus's c); `test_floor_none_when_a_corpus_cannot_reach_target`; `test_floor_with_tied_confidences` (Review Focus 4); `test_state_rules`; `test_fit_deterministic` (twice → equal).
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

### Task 6: Replayed timing

**Files:** Create `helios/consensus/timing.py`; Test `tests/consensus/test_timing.py`.

**Interfaces — Produces:** `@dataclass(frozen=True) class Schedule`: `first_ms: float`, `first_pipelines: tuple[str, ...]`, `terminal_ms: float | None`, `non_converged: bool`; `schedule(latency_ms: Mapping[str, float]) -> Schedule` — `PROVISIONAL_MS = 30_000`, `CONVERGE_MS = 90_000`.

- [ ] **Step 1: tests:** all done by 30 s → first = max latency, terminal = same; L at 45 s → first 30 s from D, G; terminal 45 s; L at 95 s → non-converged, terminal None; no pipelines → first 0, terminal 0.
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

### Task 7: Parameters and the fusion entry point

**Files:** Create `helios/consensus/params.py`, `data/frozen/mahc_params.json` (provisional); Modify `helios/consensus/mahc.py`; Test `tests/consensus/test_mahc_run.py`.

**Interfaces — Produces:**
- `@dataclass(frozen=True) class MAHCParams`: `priors: PriorTable`, `calibrator: Calibrator | None`, `floor: float | None`, `provisional: bool`; `load_mahc_params(path=...)`, `mahc_params_hash(p) -> str`. Provisional file: every prior 1, no calibrator, no floor.
- `@dataclass(frozen=True) class FusedVerdict`: `method` ("mahc" | "vote_only"), `ranked`, `scores`, `confidence: float | None`, `fused_sigma`, `state: State`, `schedule: Schedule`, `first_ranked`, `evidence: dict` (weights, prior and level per pipeline, features, signal type, disagreeing pipelines).
- `@gated_by(VCLFlag.MAHC_HIERARCHICAL) run_mahc(verdicts, signal: SignalType, params: MAHCParams, *, confirmatory: bool) -> FusedVerdict` — refuses provisional params when confirmatory; `run_vote_only(verdicts) -> FusedVerdict` (not gated).

- [ ] **Step 1: tests:** `test_provisional_params_refused_in_confirmatory`; `test_no_votes_gives_empty_provisional` (Review Focus 2); `test_state_uses_calibrator_and_floor`; `test_vote_only_always_confirmed_unless_non_converged`; `test_first_publication_fuses_only_early_pipelines`; `test_gated_off_raises_inactive`.
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

### Task 8: Store and scorer

**Files:** Modify `helios/store/schema.sql` (table `fusion_row`, tag `fusion-v1`), `helios/store/result_store.py` (`insert_fusion`, `fetch_fusion`, `fetch_all_fusion_rows`), `helios/evaluation/scoring.py` (FUSED list = `fusion_row.ranked` terminal; `consensus_verdict` still read for old databases); Test `tests/test_result_store.py`, `tests/evaluation/test_scoring.py`.

`fusion_row`: run_id (PK), incident_id, variant_config_hash, method, ranked JSON, scores JSON, confidence, fused_sigma, state, first_ms, first_ranked JSON, terminal_ms, non_converged, evidence JSON.

- [ ] **Step 1: tests:** `test_fusion_round_trip`; `test_scorer_scores_fusion_rows_as_fused` (hand row + labels → HR@3 of the terminal list).
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

### Task 9: Runner wiring

**Files:** Modify `helios/orchestrator/runner.py` (signal type after the trigger; fuse after the three pipelines with per-pipeline latencies from the verdicts; MAHC when `mahc_hierarchical`, else vote-only; store in the PASS branch; `mahc_params` constructor argument; confirmatory refuses provisional); Modify `tests/evaluation/test_no_ground_truth_leak.py` (fusion module and signal type in the run path; entry points gain no label parameter); Test `tests/test_runner_mahc.py`.

- [ ] **Step 1: tests:** `test_full_stores_a_mahc_fusion_row`; `test_no_consensus_stores_vote_only` (HELIOS-noConsensus); `test_no_consensus_differs_from_full_on_a_fixture` (S2.6 done-when: fake pipelines with the disagreement counterexample); `test_excluded_run_has_no_fusion_row`; `test_rerun_equal_fusion` (terminal list, confidence, state; timing excluded).
- [ ] **Step 2–4:** FAIL → implement → PASS; full suite and the CI simulation (`data/rcaeval/build` hidden). Commit.

### Task 10: Build-run tool

**Files:** Create `helios/evaluation/mahc_calibration.py`, `bin/mahc_build_run.py`; Test `tests/evaluation/test_mahc_calibration.py`, `tests/test_mahc_build_run_cli.py`.

**Interfaces — Produces:**
- `outer_folds(cases) -> list[list[int]]` — OTel by root service, RCAEval by system (labels' `system`).
- `cross_fit(cases: Sequence[BuildCase]) -> list[float]` — nested: per outer fold, inner folds give the training cases' priors; fit the calibrator on them; score the held-out fold.
- `bin/mahc_build_run.py`: refuses the pool and provisional pipeline parameters; per case runs the frozen trigger, signal type, D, G (routing gate as the runner), L (cache; `--no-llm-calls` refuses a cache miss); computes votes; cross-fits; chooses the floor; writes `docs/sprints/s2-reasoning/calibration/mahc_run1.json` (aggregates: calibration curve in 10 bins, floor, confirmed share and HR@3 among confirmed per corpus, HR@3 of MAHC, vote-only and each pipeline per corpus, prior table refit on all, signal-type counts, hashes). Exit 3 and a message when the floor is unreachable (M-e).

- [ ] **Step 1: tests:** `test_folds_hold_out_root_services_and_systems`; `test_cross_fit_never_scores_a_case_with_a_model_that_saw_it` (spy on training indices); `test_tool_refuses_the_pool`; `test_unreachable_floor_exits_3` (synthetic); `test_report_has_no_incident_ids`.
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

### Task 11: Rules entry; close PR 1

- [ ] **Step 1:** Draft the pre-run entry (M-a…M-e, keyword lists, priors, weights, features, calibration, floor rule, folds, timing and the TTT reading, vote-only, fusion_row as the scored list). **Owner signs**; CLI → verify → verify-public → ledgers → deviation tests; mirror; commit. No fit before the entry is signed.
- [ ] **Step 2:** Full local gate; CI simulation; fresh whole-branch review (most capable model); fixes test-first; owner go-ahead → local `--no-ff` merge.

## PR 2 — build run, freeze, entry

### Task 12: Build run

- [ ] **Step 1:** New branch from local `main`. Run `bin/mahc_build_run.py`; commit the report. Exit 3 → stop and report to the owner (M-e). **Bring the result to the owner before freezing.**

### Task 13: Freeze

- [ ] **Step 1 (after owner OK):** Test `test_frozen_mahc_params_match_the_report` (prior table, calibrator, floor, hash); write `data/frozen/mahc_params.json` (provisional false); full suite; commit.
- [ ] **Step 2:** Design §10 (curve, floor, confirmed shares, HR@3 table); freeze entry drafted → owner signs → CLI → verify → mirror; rows ENG05 and ENG06 DONE in their own commits (parsed); full local gate; fresh review; owner go-ahead → local merge.
