# S3.1 Router with cheap-first gate (IN3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** With `cbr_routing` ON, HELIOS runs the D-pipe, decides whether to add the G-pipe, publishes from that cheap arm at once, and escalates to the L-pipe only on D/G disagreement or when its frozen accuracy estimate is too low. With `cbr_routing` OFF (uniform), every incident runs every enabled pipeline, G-pipe ungated, with today's concurrent publication timing.

**Architecture:** `helios/consensus/` gains `router_features.py` (label-free features from the D and G verdicts), `router_params.py` (frozen LinUCB file, load/write/hash), `router.py` (arms, G decision, escalation decision, `constraint_empty`). `timing.py` gains a staged schedule beside the unchanged concurrent one; `mahc.py` gains a staged publication that reuses `_publish`'s fusion. The runner branches on `cbr_routing`. A build tool runs HELIOS-noRouter over both build corpora (that run *is* the full-information pass: every pipeline, G ungated), evaluates every arm per case with the frozen MAHC, cross-fits the per-arm models and picks τ_acc. PR 1 builds everything with provisional parameters and records the rules; PR 2 runs, freezes, records.

**Tech Stack:** Python 3.11, numpy (ridge solve), pydantic v2, duckdb; pytest. No new dependency.

**Spec:** `docs/sprints/s3-routing/s3_1_router_design.md` (approved 2026-11-06, R-a…R-e). Row **S2-M8-ENG01**.

## Global Constraints

- Router inputs are the D-pipe verdict and its in-scope candidate scores, the G-pipe verdict when run, the PPR disagreement value, the frozen signal type and whether traces are present. **Never** the fusion output, the label, fault type, injection time, system name or any pool case.
- Arms recorded: D, G, L, D+G, D+L, G+L, Full. Selectable: D, D+G, D+L, Full (R-c). Cost order fixed: D < D+G < D+L < Full.
- Per arm a: A_a = λI + Σ x xᵀ, b_a = Σ r x, θ_a = A_a⁻¹ b_a; p̂ = θ_aᵀx; LCB = p̂ − α √(xᵀ A_a⁻¹ x). r = HR@3 hit of arm a's fused list under the frozen MAHC. λ and α are fixed in the pre-run entry.
- G decision: run G-pipe if a graph exists and (LCB(D+G) ≥ τ_acc and D+G is cheaper than any other feasible arm, or LCB(D) < τ_acc).
- Escalate to the L-pipe if D and G both ran and their top-1s differ (`disagreement`), or LCB(cheap arm) < τ_acc (`low_confidence`); else `none`. L-pipe off → reason recorded as `llm_off`, no escalation. No feasible arm → Full with `constraint_empty`.
- τ_lat: an arm whose staged build-median finish exceeds `CONVERGE_MS` (90 s) is infeasible.
- τ_acc rule (R-d): the lowest value for which routed held-out HR@3 ≥ uniform held-out HR@3 − one percentage point **in each corpus**; none → the build tool exits 3 and reports (no fallback).
- Staged timing: first publication when the cheap arm finishes; L-pipe dispatched after the decision, terminal = cheap finish + L latency; non-convergence if that exceeds 90 s. Concurrent `schedule()` unchanged for uniform runs.
- R-e: a terminal or first publication with exactly one contributing pipeline is PROVISIONAL with a human request, under MAHC and vote-only alike.
- MAHC parameters, detector, pipelines, `variants.py`, `research/osf/*`, `metric_contract.md`, the seed register and `DISAGREEMENT_THRESHOLD` are not edited. The threshold stays as the gate value's reference in the record.
- Every new module references the VCL; the router entry point is `@gated_by(VCLFlag.CBR_ROUTING)`.
- Deviation entries via the CLI after owner review; tracking row IN_PROGRESS → DONE in separate commits; never `git commit -a`; check exit codes; full pre-push gate before each PR; PRs to `main` (protected), no direct push.

## Review Focus

1. **Router reads no fusion:** the same fixture under Full and noConsensus chooses the same arms and escalation reasons. *(Task 6 test)*
2. **One pipeline only** (D-only stop, or G and L both failed): publication PROVISIONAL, no division by zero in features or LCB. *(Tasks 2, 5 tests)*
3. **No graph** (RCAEval build has no traces): G features zero with a `g_ran = 0` indicator; D+G infeasible, not an error. *(Task 2 test)*
4. **Provisional router parameters in a confirmatory run:** refused before any incident writes. *(Task 6 test)*
5. **τ_acc search with ties and an unattainable corpus:** deterministic value, or exit 3. *(Task 8 test)*
6. **Rerun equality:** routing record and terminal list bitwise equal across reruns; stage times outside it, as S2.5 timing. *(Task 6 test)*

---

## PR 1 — features, parameters, policy, staged publication, wiring, build tool, rules entry

### Task 1: Open the row

- [ ] **Step 1:** Branch `s3/router` from `main` (the design commit on `s3/router-design` merges first, or is cherry-picked). Commit this plan.
- [ ] **Step 2:** Add row S2-M8-ENG01 as IN_PROGRESS (Started = the day work starts, Deps S2-M7-ENG05, S2-M6-ENG08); validator exit 0 and the row parsed; commit `tracking: S2-M8-ENG01 IN_PROGRESS (S3.1 router)`. S3 sprint start also adds rows ENG02–ENG05 and GATE01 as PLANNED in the same commit.

### Task 2: Router features

**Files:** Create `helios/consensus/router_features.py`; Test `tests/consensus/test_router_features.py`.

**Interfaces — Produces:**
- `FEATURE_NAMES: tuple[str, ...]` — fixed order; the bias term first.
- `cheap_features(d: PipelineVerdict, d_scores: Mapping[str, float], *, gate_value: float | None, signal: SignalType, traces: bool) -> tuple[float, ...]` — D-pipe μ, σ (None → 1), top-1 share, top-1/top-2 margin, gate value (None → 0), four signal indicators, traces, G block zeroed with `g_ran = 0`.
- `with_gpipe(x: tuple[float, ...], g: PipelineVerdict, d: PipelineVerdict) -> tuple[float, ...]` — fills G σ, G top-1 margin, D/G top-1 agreement, D/G top-3 overlap, `g_ran = 1`.
- Values rounded to 6 digits (`canonical_json` convention) so reruns are bitwise equal.

- [ ] **Step 1: tests:** fixed length and order; D σ None → 1; one-candidate list → margin defined; G skipped or failed → G block zero and `g_ran = 0` (Review Focus 3); signature check that no parameter carries a label (as `test_no_ground_truth_leak.py`).
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

### Task 3: Router parameters

**Files:** Create `helios/consensus/router_params.py`, `data/frozen/router_params.json` (provisional); Test `tests/consensus/test_router_params.py`.

**Interfaces — Produces:**
- `class Arm(StrEnum)`: D, G, L, D_G, D_L, G_L, FULL; `SELECTABLE = (Arm.D, Arm.D_G, Arm.D_L, Arm.FULL)` in cost order.
- `@dataclass(frozen=True) class ArmModel`: `a_inv: tuple[tuple[float, ...], ...]`, `theta: tuple[float, ...]`, `n: int`; `estimate(x) -> tuple[float, float]` (p̂, LCB given α).
- `@dataclass(frozen=True) class RouterParams`: `feature_names`, `arms: dict[Arm, ArmModel]`, `lam`, `alpha`, `tau_acc: float | None`, `stage_median_ms: dict[str, float]`, `price_book_digest`, `provisional: bool`.
- `load_router_params(path=ROUTER_PARAMS_PATH)`, `write_router_params(params, path)`, `router_params_hash(params) -> str` (SHA-256 of canonical JSON).
- Loading refuses a file whose `feature_names` differ from `FEATURE_NAMES`.
- Provisional file: every arm A = λI, b = 0, `tau_acc` None (the policy then escalates every case; uniform-like behaviour until frozen).

- [ ] **Step 1: tests:** round trip; hash stable across load/write; feature-name mismatch refused; provisional default escalates.
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

### Task 4: Policy

**Files:** Create `helios/consensus/router.py`; Test `tests/consensus/test_router.py`.

**Interfaces — Produces:**
- `@dataclass(frozen=True) class GDecision`: `run_g: bool`, `estimates: dict[str, list[float]]`, `feasible: list[str]`.
- `@dataclass(frozen=True) class Escalation`: `escalate: bool`, `reason: Literal["disagreement", "low_confidence", "none", "llm_off", "constraint_empty"]`, `arm: Arm`, `estimates: dict[str, list[float]]`.
- `@gated_by(VCLFlag.CBR_ROUTING) def decide_g(x, params, *, graph: bool) -> GDecision`.
- `def decide_escalation(x, params, *, d_top: str | None, g_top: str | None, llm_on: bool) -> Escalation`.
- Feasibility: LCB ≥ τ_acc and the staged median finish ≤ `CONVERGE_MS`; `tau_acc` None → nothing feasible below Full.

- [ ] **Step 1: tests:** D/G top-1s differ → `disagreement` even with high LCB; high LCB on D+G and agreement → `none`, arm D+G; LCB below τ → `low_confidence`, arm Full (or D+L when G did not run); `llm_on=False` → `llm_off`, no escalation; no feasible arm → `constraint_empty`, arm Full; τ_lat excludes an arm whose median finish is over 90 s; determinism (same x, same output).
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

### Task 5: Staged schedule and publication

**Files:** Modify `helios/consensus/timing.py` (add, do not change `schedule`), `helios/consensus/mahc.py` (add a staged publisher; `_publish` gains the R-e rule); Test `tests/consensus/test_timing.py`, `tests/consensus/test_mahc_staged.py`.

**Interfaces — Produces:**
- `staged_schedule(stage1_ms: Mapping[str, float], stage2_ms: Mapping[str, float] | None) -> Schedule` — stage-1 finish = max of the cheap arm's finish times (G after D, as `finish_times`); first publication there; terminal = stage-1 finish if no stage 2, else stage-1 finish + the L-pipe latency; non-convergence if the terminal exceeds `CONVERGE_MS`.
- `publish_staged(method, stage1, stage2, combine, score, floor, extra) -> FusedVerdict` — first list and state from the cheap arm's fusion, terminal list and state from all pipelines that ran; schedule from `staged_schedule`. `run_mahc` and `run_vote_only` take `staged: tuple[...] | None = None` and call it when given.
- R-e in `_publish` and `publish_staged`: one contributing pipeline → `State.PROVISIONAL`.

- [ ] **Step 1: tests:** first at cheap finish; terminal at cheap + L; no stage 2 → terminal = first; cheap + L over 90 s → non-converged; one contributing pipeline → PROVISIONAL under MAHC and vote-only (Review Focus 2); the existing concurrent tests unchanged and passing (uniform path untouched).
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

> Changing `_publish` for R-e changes the S2 behaviour of every non-routed variant that can end on one pipeline (HELIOS-D publishes through vote-only and becomes always PROVISIONAL; HELIOS-G likewise). That is what R-e says, and it moves CpR's human component for those variants. List it in the pre-run entry.

### Task 6: Runner wiring

**Files:** Modify `helios/orchestrator/runner.py`, `helios/orchestrator/coe.py` (R step fields), `helios/orchestrator/ledger.py` if the stored fusion row needs the stage times; Test `tests/test_runner_router.py` (new), existing runner tests updated where G-pipe is now ungated under uniform.

- [ ] **Step 1: tests:**
  - noRouter fixture: every pipeline dispatched, G-pipe runs below the old gate, R step `reason = "uniform"`, concurrent timing.
  - Full fixture, agreeing cheap arm with high LCB: L-pipe never dispatched; first publication at the cheap finish.
  - Full fixture, D/G disagreement: L-pipe dispatched; terminal fused from three lists.
  - The same fixture under noConsensus: same arms and reasons as Full (Review Focus 1).
  - noLLM fixture: `llm_off` recorded, no L dispatch.
  - Confirmatory run with provisional router parameters: refused in `_trigger_for` before anything is written (Review Focus 4).
  - `parameter_hashes["router"]` present when routing is ON; a hash mismatch against the frozen file is refused at start.
  - Rerun equality of the R step (without stage times) and the terminal list (Review Focus 6).
- [ ] **Step 2: implement:**
  - Signal type is computed when `mahc_hierarchical` **or** `cbr_routing` is ON (today only under MAHC).
  - `cbr_routing` OFF: G-pipe runs whenever `gpipe` and `l2b_graph` are ON and a graph exists (the gate value is still computed and recorded); L-pipe as today; `finish_times` + `schedule`.
  - `cbr_routing` ON: D-pipe → features → `decide_g` → G-pipe if chosen → `with_gpipe` → `decide_escalation` → L-pipe if escalated → `run_mahc`/`run_vote_only` with `staged`.
  - R step: `features`, `estimates`, `tau_acc`, `g_decision`, `stage1_arm`, `terminal_arm`, `reason`, `gate_value`, `threshold` (reference only), and `stage1_ms`/`terminal_ms`. Reserve `llm_unavailable` for S3.5.
- [ ] **Step 3:** PASS, full suite green. Commit.

### Task 7: Leakage test

**Files:** Modify `tests/evaluation/test_no_ground_truth_leak.py`.

- [ ] **Step 1:** Add the router's public functions to the signature scan, and a runtime trap run of a routed fixture. Commit.

### Task 8: Build tool

**Files:** Create `helios/evaluation/router_calibration.py`, `bin/router_build_run.py`; Test `tests/evaluation/test_router_calibration.py`, `tests/test_router_build_run_cli.py`.

**Interfaces — Produces:**
- `@dataclass(frozen=True) class RouterCase`: `incident_id`, `corpus`, `group` (MAHC's fold groups), `x_cheap`, `x_dg | None`, `votes` (per pipeline), `signal`, `root`, `latency_ms`.
- `arm_outcomes(case, mahc: MAHCParams) -> dict[Arm, int]` — HR@3 hit of each selectable arm's fused list under the frozen MAHC; an arm whose pipelines did not all produce a list is absent.
- `cross_fit(cases, lam, alpha) -> dict[int, dict[Arm, tuple[float, float]]]` — held-out (p̂, LCB) per case and arm, folds from `mahc_calibration.outer_folds`.
- `choose_tau(cases, held_out, tolerance=0.01) -> float | None` — the R-d rule; candidate values are the distinct held-out LCBs, searched in ascending order.
- `fit_all(cases, lam, alpha, tau) -> RouterParams` — the frozen refit on every case.
- CLI: `router_build_run.py run` runs HELIOS-noRouter over both build corpora with the cache-only L-pipe client (as `mahc_build_run.py`), writes `docs/sprints/s3-routing/calibration/router_run1.json`; exits 3 if `choose_tau` returns None. `router_build_run.py freeze` writes `data/frozen/router_params.json` only after the report exists. `router_build_run.py check` re-evaluates the frozen file.
- Report: per corpus, held-out HR@3 of routed, uniform and the S2 Full ledger; escalation share overall and per signal type; G-pipe runs; replayed first-publication median; GPU time and LLM calls saved.

- [ ] **Step 1: tests:** arm outcomes on a hand case; folds never contain the held-out case; `choose_tau` lowest qualifying, ties deterministic, unattainable corpus → None (Review Focus 5); CLI exit 3; `freeze` refuses without a report.
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

### Task 9: Documents and the pre-run entry

- [ ] **Step 1:** `docs/tracking/ablation_architecture.md` §5: routing paragraph (staged cheap-first, uniform semantics, which variants route).
- [x] **Step 2:** Draft the pre-run entry text (design §6) and give it to the owner (appended as deviation entry 69, sig a8fd0261). After review, append it with `bin/log_deviation.py`; run `pytest tests/test_deviation_log.py`; commit the log and anchor.
- [ ] **Step 3:** Full pre-push gate; open PR 1.

---

## PR 2 — build run, freeze, freeze entry

### Task 10: Build run

- [ ] **Step 1:** Check `data/cache/lpipe_cache.sqlite` exists and Ollama has the pinned digest (cache-only: no new model calls are expected; a miss stops the run).
- [ ] **Step 2:** `poetry run python bin/router_build_run.py run`. Exit 3 → stop and bring the report to the owner (R-d).
- [ ] **Step 3:** Owner reviews `router_run1.json` before anything is frozen.

### Task 11: Freeze

- [ ] **Step 1:** `router_build_run.py freeze`; `check` reproduces the report from the frozen file.
- [ ] **Step 2:** Freeze entry (design §6) after owner review; append with the CLI; commit the log, anchor, frozen file and report.
- [ ] **Step 3:** Design §10 Results written from the report.

### Task 12: Close the row

- [ ] **Step 1:** Full pre-push gate; open PR 2.
- [ ] **Step 2:** After merge, row S2-M8-ENG01 DONE (SHA, Ev_Type, Ev_Ref = the report and freeze entry) in its own commit.

## Size

PR 1 about 3 days (Tasks 2–9), PR 2 about 1½ days (the build run replays cached L-pipe calls; G-pipe runs for real on the 19 OTel cases the old gate skipped).
