# S2.5 — MAHC with calibrated confidence (IN2), and S2.6 vote-only · design

**Tasks:** S2.5 (tracking S2-M7-ENG05) and S2.6 (S2-M7-ENG06) · **Date:** 2026-10-30 · **Status:** approved by the owner 2026-10-30; frozen 2026-10-31 (entries 60-63) · **Depends on:** frozen detector (entry 52), D-pipe (53), G-pipe (54–56), L-pipe (57–58), H_struct (59) · **Owner decisions:** marked *owner* (2026-10-30)

**Flag:** MAHC is gated by `VCLFlag.MAHC_HIERARCHICAL` (`mahc_hierarchical`); OFF = vote-only fusion (HELIOS-noConsensus).

## 1. Intent

The three pipelines each return a ranked list with (μ, σ). HELIOS's answer to an incident is the **fused** list: HR@k, TTT and the A-H4 comparison are all measured on it. MAHC (Ch3 Algorithm 3, p.115; C4) fuses the pipelines with weights that reflect how reliable each pipeline is in this kind of incident (hierarchical priors) and how sure it is this time (σ), and says how far its answer can be trusted (IN2: a calibrated confidence). Below a pre-registered confidence it publishes PROVISIONAL and asks a human, rather than CONFIRMED.

Today the runner stores the three pipeline verdicts and **never fuses them**; a uniform-Borda module and a `ConsensusVerdict` schema exist but nothing calls them. S2.5 builds MAHC and wires it in; S2.6 builds the vote-only fusion HELIOS-noConsensus uses.

## 2. Decisions already made

| # | Decision | Who |
|---|---|---|
| M-a | **Priors are keyed on context observable at run time**, never the fault label: level 1 the trigger's **signal type** (resource, latency, error); level 2 **global**. System name is not used (the pool's systems are unseen). The modality level (traces or not) is dropped: on build data it equals the dataset (OTel vs RCAEval), so every pool prior would have come from 63 OTel cases and none from the 495 RCAEval cases of the pool's own systems | owner, 2026-10-30 (modality dropped after the builder check) |
| M-b | **State rule = a calibrated-confidence floor** (replaces Ch3's entropy floor): a calibration model maps observable features of the fused result to P(root cause in the fused top 3); CONFIRMED at or above the floor, PROVISIONAL + human request below. λ is this floor | owner, 2026-10-30 |
| M-c | **The floor is the lowest value at which the build cases MAHC would confirm have held-out HR@3 ≥ 80%** | owner, 2026-10-30 |
| M-e | **The 80% must hold in each corpus separately** (OTel, RCAEval); the floor is the stricter of the two. **If a corpus has no confidence value reaching 80%, the build run stops and is brought to the owner** — no automatic fallback; any change is a new entry | owner, 2026-10-30 |
| M-d | σ enters the **weights and the fused σ**, not the ranking alone: when all pipelines agree, σ 0.1 and σ 0.8 give the same ranking (Ch3 p.157: "identical scalar votes, distinguishable (μ, σ)") but a different fused σ, confidence and state | agreed 2026-10-30 |

## 3. Goals, non-goals, anti-goals

**Goals.** Signal type of the trigger; hierarchical priors with back-off; σ-weighted Borda; fused σ; calibrated confidence and the PROVISIONAL / CONFIRMED / non-convergence states with replayed timing; the consensus verdict stored per run and HR@k scored on it; vote-only fusion for noConsensus; the Ch3 counterexample and a disagreement counterexample as tests; a calibration curve on build data.

**Non-goals.** The narrator and contradiction explanations (S2.8; MAHC records which pipelines disagreed, nothing more); the router (S3.1); learning weights by gradient descent; changing any frozen pipeline.

**Anti-goals** — it fails even if it runs:

- Any fusion input carries the label, fault type, injection time or system name.
- Priors or calibration are fitted and evaluated on the same cases (the pipelines were frozen on this build data: fits are held-out only).
- noConsensus fuses different lists than Full (A-H4's stratum and pairing would break).
- The state depends on wall-clock noise (a rerun of the same incident must give the same state).

## 4. Constraints

- Build data only: `otel_build_v3` (63, traces) and `rcaeval_build` (495, no traces). On build data "traces present" is OTel only; the pool is RCAEval **with** traces — a shift stated in the entry (validity T21).
- σ from every pipeline is in [0, 1] or None; consensus treats None as unknown, never certain (verdict contract): None → 1. A SKIPPED, FAILED or ABSTAINED pipeline contributes nothing.
- G-pipe runs only when the routing gate opens (44 of 63 OTel build cases); the fusion must handle any subset.
- Never edit `metric_contract.md`, `variants.py`, `research/osf/*`, the seed register, frozen pipeline parameters.

## 5. Design

### 5.1 Signal type (label-free, from the frozen trigger)

The detector pools each service's series into one score and does not say which series crossed. A new read-only step takes the trigger's top suspect and trigger bucket, finds that service's series with the largest causal z at the trigger bucket (the detector's own `causal_z`), and sorts its name into one type:

- **resource** — cpu, memory/mem, gc, thread, fd, disk, socket;
- **latency** — latency, duration, response time;
- **error** — error counts, error spans, error-level log lines, HTTP 5xx;
- **unclassified** — anything else, or a fallback trigger with no crossing.

The keyword lists are fixed in the pre-run entry. The detector and its parameters are unchanged.

### 5.2 Hierarchical priors

π_p(context) = pipeline p's HR@3 on build cases in that context, smoothed toward the global level (Beta prior with strength 10 cases), estimated **held-out**. Back-off: signal type → global when a signal type has fewer than **30** build cases for that pipeline (M-a). The frozen prior table is refitted on all build cases after the run, as G-pipe's ranker was.

**Cross-fitting (my call):** priors and calibration are fitted together, nested, on the same outer folds: for each outer fold, the training cases' priors come from inner folds of the training set, the calibration model is fitted on those training cases, and the held-out fold is scored with priors and calibration that never saw it.

### 5.3 Fusion

- w_p = π_p / (σ_p² + ε), ε = 10⁻⁴, over pipelines that returned a list; normalised.
- Weighted Borda over the union of the lists: a pipeline's rank r of n scores (n − r + 1)/n, unlisted 0; fused score = Σ w_p · score_p. Ties by name.
- Fused σ = √(Σ w_p σ_p²).
- Out-of-scope services are dropped first (D-f), as the scorer does.

### 5.4 Calibrated confidence and state

- Features of the fused result: top-1 share of the fused scores, normalised entropy of the fused scores, fused σ, number of contributing pipelines, whether their top-1s agree.
- Model: logistic score of the features, then **isotonic regression** to P(root in fused top 3), fitted by cross-fitting (each case scored by a model that never saw it).
- Floor (M-c, M-e): per corpus, the lowest confidence c such that held-out cases of that corpus with confidence ≥ c have HR@3 ≥ 0.80; the floor is the larger of the two. No qualifying c in a corpus → stop and report. CONFIRMED at or above; PROVISIONAL + HITL below.
- Output: the ranked list, the confidence, the fused σ, the state, the disagreeing pipelines.

### 5.5 Timing (replayed concurrency)

Recorded runs execute the pipelines one after another but record each pipeline's latency (cached L-pipe calls replay theirs). MAHC replays them as if concurrent:

- **First publication** at the earlier of 30 s or all pipelines finished, fused from the pipelines finished by then; its state is CONFIRMED only if all pipelines are in and the confidence is at or above the floor, else PROVISIONAL.
- **Terminal publication** when all pipelines have finished, if within 90 s; a pipeline unfinished at 90 s → **non-convergence**: elevated-uncertainty PROVISIONAL + HITL from what is in, counted per case.
- **The fused list that is scored** (HR@k, the calibration target, A-H4) is the **terminal** one *(my call)*; the first publication's list is stored too.
- **TTT = the first publication of any state** *(my call)*: the metric contract says "first PROVISIONAL", but variants with no gate (vote-only and the single-pipeline variants) never publish one; the entry records the reading. Vote-only applies the same 90 s cutoff.
- **Timing noise stays in the timing fields** *(my call)*: rerun equality covers the terminal list, confidence and state; TTT and non-convergence are reported as measured on the stated hardware (Apple M5 Pro).

### 5.6 Vote-only (S2.6, HELIOS-noConsensus)

`mahc_hierarchical` OFF → the same per-pipeline lists fused by plain Borda with equal weights, no priors, no σ, no confidence, always CONFIRMED (no gate). Same input lists as Full by construction.

### 5.7 Records and wiring

The runner calls MAHC (or vote-only) after the three pipelines and stores a consensus verdict per run (extending `consensus_verdict`), plus the fusion evidence (weights, priors used and their level, fused scores, features). The scorer computes HR@k on the fused list. Rows only for runs whose verdicts are stored (as H_struct).

## 6. Protocol records

- **Pre-run entry** (owner signs before any fit): M-a…M-e, the signal-type keyword lists, prior smoothing and back-off threshold, ε, the feature list, the calibration method, the 80% floor rule, the fold scheme, the timing rule, vote-only.
- **Freeze entry** (after the build run, owner reviews first): the prior table, the calibration map, the floor value, the calibration curve, the build HR@3 of MAHC vs vote-only vs each pipeline.

## 6a. Size and tracking

S2.5 is 2½ days in the plan; with the runner wiring and the signal type, my estimate is **3½**; S2.6 ½ day. Rows S2-M7-ENG05 and S2-M7-ENG06. Two PRs as before: PR 1 = code + pre-run entry; PR 2 = build run, freeze, entry. Local merges while the Actions quota is low.

## 7. Done when

- Ch3 p.157 counterexample: same ranking, different fused σ and state (test).
- Disagreement counterexample: MAHC and vote-only rank differently (test).
- Calibration curve (held-out) reported; the floor and the share of build cases confirmed reported.
- noConsensus differs from Full on a fixture (S2.6 done-when).
- Leakage test extended to the fusion inputs; rerun equality of the consensus verdict.

## 8. Calls I made (owner to check)

1. **Signal type from the top suspect's strongest series at the trigger bucket**, keyword-sorted.
2. **π = held-out HR@3 per pipeline and context**, Beta smoothing (strength 10), back-off below 30 cases.
3. **w = π / (σ² + ε)**, Borda (n − r + 1)/n, fused σ = √Σwσ².
4. **Calibration = logistic score then isotonic**, cross-fitted, target = HR@3 of the fused list.
5. **Replayed concurrency** for PROVISIONAL / CONFIRMED / non-convergence and TTT.
6. **S2.6 designed here**, vote-only always CONFIRMED.
7. **Fold scheme:** OTel by root service (as G-pipe); RCAEval by system (Online Boutique, Sock Shop, Train-Ticket), so no fold is fitted on its own system.
8. **Nested cross-fitting** of priors and calibration on the same outer folds (§5.2).
9. **Scored list = terminal publication; TTT = first publication of any state; timing fields outside rerun equality** (§5.5).

## 9. Left to the builder

The exact keyword lists' spelling (fixed before the run); how the consensus verdict extends the existing table (and whether its `consensus_rank` field, which may hold a label-derived rank, belongs in the scorer instead); fold count within each scheme; feature scaling.

## 10. Results

Build runs of `bin/mahc_build_run.py` (HELIOS-Full over `otel_build_v3` and `rcaeval_build`, frozen pipelines, cached L-pipe answers, nested cross-fitting). Reports in `calibration/mahc_run{1,2,3}.json`. The fused lists, and so HR@3 of MAHC and vote-only, are identical in all three runs; only the calibrator differs.

| Run | Rules | Calibrator | Floor | OTel confirmed (HR@3) | RCAEval confirmed (HR@3) | Outcome |
|---|---|---|---|---|---|---|
| 1 | entry 60 | 5 features | 0.895833 | 22 / 63 (0.818) | 495 / 495 (0.974) | withdrawn (entry 61): the largest weight was on the pipeline count, a dataset proxy (3 pipelines only on OTel) |
| 2 | + entry 61 | 4 features | 0.893333 | 29 / 63 (0.828) | 310 / 495 (0.977) | withdrawn (entry 62): L2 on the mean loss shrank every weight to ~0; isotonic fitted 229 noise steps; 44 held-out cases at confidence 0 were 88.6% right |
| 3 | + entry 62 | L2 on the summed loss, isotonic steps of ≥ 20 | **0.914286** | **27 / 63 (0.852)**; the other 36 at 0.72 | **308 / 495 (0.990)**; the other 187 at 0.95 | **frozen (entry 63)**, reproduced byte for byte |

**HR@3 (all runs):**

| | OTel v3 (63) | RCAEval build (495) |
|---|---|---|
| MAHC | 0.7778 | 0.9737 |
| Vote-only (S2.6) | 0.7619 | 0.9737 |
| D-pipe alone | 0.7619 | 0.9455 |
| G-pipe alone | 0.7273 (44 routed cases) | — (no traces) |
| L-pipe alone | 0.6984 | 0.9717 |
| Ambiguous stratum (top-1s differ): MAHC / vote-only | 39 cases: 0.718 / 0.692 | 141 cases: 0.936 / 0.943 |

**Frozen calibrator (run 3):** weights on standardised features — fused sigma −1.342, entropy −0.847, agree +0.421, top-1 share −0.369; 16 isotonic steps. Priors: global D 0.92, G 0.73, L 0.94; by signal type for D and L (latency, resource, unclassified); G and the error type on the global prior (fewer than 30 cases). Signal type is unclassified on 34 of 63 OTel cases and 31 of 495 RCAEval cases.

**Findings:**

- MAHC adds one case over vote-only and D-pipe on OTel and none on RCAEval, where D-pipe and L-pipe usually agree. **A-H4 is near null on build data** (ambiguous stratum +1 on OTel, −1 on RCAEval): for the chair call with A-H4's power.
- **The confidence discriminates modestly:** OTel 0.85 confirmed vs 0.72 provisional; RCAEval 0.99 vs 0.95 — 38% of RCAEval build cases would go to a human although 95% are right. Held-out confidence runs below the observed rate (conservative), reflecting folds that hold out whole systems.
- **The routing gate costs G-pipe cases on OTel:** G-pipe runs on 44 of 63 cases; ungated it scored 50 of 63 in the S2.2 selection run, above the fused 49. For S3.1 (router).
- Process: two changes were made after inspecting build runs; both removed demonstrable defects (a dataset proxy; numerical over-regularisation), each under a signed entry before the next run, and each withdrawn run is kept as evidence.

### Frozen parameters on the build cases (PR 2 review; `calibration/mahc_frozen_check.json`)

The floor was chosen on cross-fitted confidences and is applied with the refit calibrator. Applied in-sample (an upper bound, not a held-out estimate):

| | Confirmed (HR@3) | Provisional (HR@3) | Cross-fitted confirmed |
|---|---|---|---|
| OTel v3 (63) | 33 (0.879) | 30 (0.667) | 27 |
| RCAEval build (495) | 445 (0.980) | 50 (0.920) | 308 |

**A third pipeline lowers confidence.** On the 44 OTel cases where G-pipe voted, the frozen MAHC confirms 16 with G-pipe's vote and 30 without it (14 cases flip to PROVISIONAL, none the other way); mean confidence 0.84 vs 0.90; HR@3 0.705 with G-pipe vs 0.682 without. The channel is agreement and fused sigma (a third list disagrees more often and G-pipe's sigma is often high), not the removed pipeline count. Reading:

- It is not a dataset proxy on the pool. G-pipe runs only when the routing gate opens (D-pipe's scores disagree, `should_run_gpipe`), on build and pool alike: three contributing pipelines mark the cases D-pipe itself found ambiguous. Those cases are harder (HR@3 about 0.70), and without G-pipe's vote the calibrator would confirm them at 0.90 while 68% are right; with it, the confidence is the more honest of the two.
- It is a thin regime. All three-pipeline build cases are OTel (44), because the RCAEval build cases have no traces; the pool's RCAEval cases with traces will reach this regime for the first time. **The pool analysis must report the confirmed share and HR@3 separately for cases with and without G-pipe** (and the state flips with and without G-pipe's vote), as here.

### Notes on the frozen calibrator

- The 16 isotonic knots carry 6 distinct confidence levels (adjacent blocks with equal rates are not merged; 11 knots are 1.0). Resolution is 6 levels, not 16.
- The top-1 share weight is negative (−0.369) although a higher share should raise confidence; it is collinear with entropy (−0.847), and the pair should be read together.
- Entry 61's consequence says run 2 "is fitted and frozen"; run 2 was withdrawn and entry 62 records it.
