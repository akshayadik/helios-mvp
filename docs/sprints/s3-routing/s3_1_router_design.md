# S3.1 — Router with cheap-first gate (IN3) · design

**Task:** S3.1 (tracking S2-M8-ENG01) · **Date:** 2026-11-06 · **Status:** approved by the owner 2026-11-06 (R-a…R-e as recommended) · **Depends on:** frozen detector (entry 52), D-pipe (53), G-pipe (54–56), L-pipe (57–58), MAHC and vote-only (60–63), CoE ledger (64), price book v2 (43) · **Carried in:** S2-BL-01, 03, 04, 06, 07, 08, 13 (S3 plan)

**Flag:** the router is gated by `VCLFlag.CBR_ROUTING` (`cbr_routing`); OFF = uniform routing (HELIOS-noRouter, A-H5 and E-H2).

## 1. Intent

Ch3 Algorithm 1 (ORAR, p.112–114) picks one arm per incident from {D, G, L, D+G, D+L, G+L, Full}. It minimises expected cost subject to an accuracy constraint (τ_acc) and a latency constraint (τ_lat), uses LinUCB per-arm parameters (A_a, b_a) frozen for the confirmatory protocol (static policy, p.114), and falls back to Full with a `constraint-empty` covariate. IN3 (entry 30) makes the cheap part central: statistical and graph evidence first, the LLM only on disagreement or low confidence. D4 option (b) initialises the router from build data instead of the 1,200-incident synthetic corpus.

Today nothing reads `cbr_routing`, so HELIOS-noRouter runs exactly the same pipelines as Full under a different hash (r1 matrix, finding 4). The only routing is the G-pipe disagreement gate from May (`DISAGREEMENT_THRESHOLD` = 0.20), which skips G-pipe on 19 of 63 OTel build cases although ungated G-pipe scored 50/63, above the fused 49 (S2-BL-06).

## 2. What the build data says (Full ledgers, 2026-11-01)

| | OTel build v3 (63) | RCAEval build (495) |
|---|---|---|
| D-pipe latency, median / p90 | 0.05 s / 0.05 s | 0.21 s / 0.65 s |
| G-pipe latency, median / p90 (when run) | 0.86 s / 1.01 s (44 cases) | not run (no traces) |
| L-pipe latency, median / p90 / max | 15.2 s / 19.3 s / 21.5 s | 9.2 s / 13.5 s / 23.0 s |
| First publication, median | 15.2 s | 9.2 s |
| HR@3 D / G / L / MAHC | 0.762 / 0.727 / 0.698 / 0.778 | 0.946 / — / 0.972 / 0.974 |

Two facts follow and shape the whole design.

1. **Every first publication waits for the L-pipe.** MAHC publishes first at the earlier of 30 s and all pipelines done (S2.5 §5.5). L-pipe always finishes inside 30 s, so the first publication comes 10–20 times later than the D+G evidence it could have used.
2. **In CpR the opportunity cost dwarfs everything else.** Under price-book-v2, tokens cost nothing (local inference), an L-pipe run costs well under a cent of GPU time, human review is about $16 (15 minutes at $63.98/h), and opportunity is $5,600 per minute of TTCD, censored at 1,800 s (about $168,000). TTCD is the time to the first published verdict whose top-1 is correct (metric contract §4).

So the CpR gain A-H5 can measure comes from **publishing the cheap evidence early** when it is right, not from the GPU cents saved by skipping the LLM. Skipping the LLM matters to the product (model load, throughput, the LLM as a rate-limited resource, and API cost under any paid model) and is reported as IN3's "cheap-first savings" (analysis A5), but it barely moves CpR. Section 5 is built around this. Raise it with the chair: it is the honest reading of A-H5 under this price book.

## 3. Decisions

All five accepted by the owner on 2026-11-06 as recommended.

| # | Decision | Accepted | Alternative not taken |
|---|---|---|---|
| R-a | **Staged routing.** Ch3 picks one arm before anything runs; IN3 consults cheap evidence first | **Two stages:** stage 1 runs the cheap arm and publishes; the router then decides whether to escalate to the L-pipe. The arm a run ends on is still one of Ch3's arms and is recorded | Single-shot arm choice as in Algorithm 1, before any pipeline runs (no early publication, so most of the A-H5 effect disappears) |
| R-b | **Meaning of `cbr_routing` OFF (noRouter, "uniform")** — Ch3 never defines it beyond Table 17 | **Every incident gets the same treatment: all pipelines run, G-pipe ungated, publication by today's concurrent replay (S2.5 §5.5).** The G gate is a routing decision, so "no routing" has none | noRouter = the S2 system as frozen (G gate kept). Closer to what was measured in S2, but keeps the BL-06 loss in the comparison arm |
| R-c | **Arm set.** D-pipe runs first in every routed run (its output is the router's input; 0.05–0.7 s) | **Reachable arms: D, D+G, D+L, Full.** G, L and G+L stay in the recorded action set but are never selected (they drop evidence already computed); stated in the entry | Keep all seven selectable (an arm that drops D's computed votes has no product meaning) |
| R-d | **Tolerance for routed accuracy** (τ_acc rule, §5.4) | Routed held-out HR@3 at least the uniform held-out HR@3 **minus one percentage point, in each corpus separately**; the threshold is the lowest τ_acc that holds in both. If no τ_acc holds, the build run stops and is brought to the owner (as MAHC's M-e) | Zero tolerance (likely escalates nearly every RCAEval case, where L 0.972 beats D 0.946) |
| R-e | **Single-pipeline stop.** MAHC's agreement feature is trivially true with one pipeline (`top1s_agree` = set size ≤ 1), so its confidence for a D-only result looks like full consensus, and it was never calibrated on one pipeline | **A run that stops on D alone always publishes PROVISIONAL with a human request.** CONFIRMED needs at least two contributing pipelines | Forbid stopping on D alone (then the router never stops on RCAEval build cases, which have no traces, and learns nothing there) |

## 4. Goals, non-goals, anti-goals

**Goals.** The two-stage cheap-first policy; frozen LinUCB parameters initialised on build data with full-information counterfactuals; the τ_acc and τ_lat constraints with a `constraint-empty` fallback to Full; staged publication timing; uniform routing for noRouter; the routed arm, features, estimates and decision recorded per run in the CoE ledger; VCL verifies the router's parameter hash at run start; a hook for S3.5 (LLM unavailable → stay on the cheap arm, covariate recorded).

**Non-goals.** Online learning (static policy in every confirmatory variant; S3.3 builds the delayed-reward machinery for exploratory subsets only); ACP features (S3.2 is Tier 2: the router takes ACP output as optional features, absent = not used); refitting MAHC, the detector or any pipeline; the S4 CpR scoring path (this design only states what S4 must read).

**Anti-goals** — it fails even if it runs:

- Any router input carries the label, fault type, injection time, system name or a pool case.
- Router parameters are fitted and evaluated on the same cases (held-out only, as MAHC).
- Full's HR@3 falls by more than the R-d tolerance against uniform routing on held-out build data. Full's HR@3 is what A-H1–A-H4, A-H6 and B-H1–B-H5 test; the router must not buy cost with it.
- The routing decision depends on run order or wall-clock noise (static policy: a deterministic function of the incident's features and frozen parameters).
- noRouter and Full see different inputs at stage 1.
- **The router reads any fusion output** (MAHC confidence, fused list or state). noConsensus has routing ON with vote-only fusion; if routing read the fusion, Full and noConsensus could route a case differently and A-H4's pairing would break. Router inputs are the D-pipe and G-pipe verdicts only.

## 5. Design

### 5.1 Flow of one routed run (`cbr_routing` ON)

1. Trigger, graph and D-pipe as today.
2. **G decision.** If a graph exists, the router estimates p̂_acc for D and D+G. G-pipe runs if D+G is the cheaper feasible arm *or* D alone is infeasible. The PPR disagreement value becomes a router feature; the fixed 0.20 gate no longer decides on its own in Full (the frozen value stays in `gpipe_config.py` and the OSF `thresholds.json`, unchanged).
3. **Stage-1 publication.** MAHC (frozen) fuses the cheap arm's lists and publishes: its state, except a single-pipeline result is PROVISIONAL (R-e).
4. **Escalation decision.** Escalate to the L-pipe if (a) D and G both ran and their top-1s disagree, or (b) the lower confidence bound of p̂_acc for the cheap arm is below τ_acc. Otherwise stop: the stage-1 publication is terminal.
5. **Stage 2** (if escalated). L-pipe runs; MAHC fuses all lists that ran; terminal publication.
6. If no arm is feasible (every LCB below τ_acc, or the latency bound excludes all), run Full and record `constraint_empty`.

**Which variants route.** Routing is ON in Full, noLLM, noConsensus, noStructural and the exploratory variants; OFF (uniform) in noRouter, LLM-only, D and G. Uniform therefore also means **HELIOS-G runs G-pipe ungated** (under the May gate it ran G-pipe only on gated cases). With the L-pipe off (noLLM), an escalation decision is still computed and recorded, with reason `llm_off`, and the run stays on its cheap arm.

Rule (a) is in the rule itself, not just a feature, because IN3 promises it in words ("the LLM only on disagreement") and it keeps every stop explainable.

### 5.2 Features (label-free, observable after D-pipe and, when run, G-pipe)

D-pipe σ and μ; D-pipe top-1 score share and top-1/top-2 margin; PPR disagreement (the old gate value); signal type (four indicators, the frozen S2.5 classifier); traces present; and, for the D+G arm, G-pipe σ, top-1 margin, D/G top-1 agreement and top-3 overlap. About 12–14 dimensions, matching Ch3's "approximately 12" (p.110). ACP output (S3.2) is appended only if S3.2 is built and frozen before the router's freeze. The leakage test is extended to the router inputs.

### 5.3 Model and initialisation (D4 option b)

- **Per-arm LinUCB, frozen.** For each reachable arm a: A_a = λI + Σ x xᵀ, b_a = Σ r x, θ_a = A_a⁻¹ b_a, where r is the HR@3 hit of arm a's fused list (MAHC on that arm's lists). p̂_acc(a) = θ_aᵀx; its lower bound LCB(a) = θ_aᵀx − α √(xᵀ A_a⁻¹ x).
- **Full information instead of a simulated bandit.** On build data every pipeline's output can be computed for every case, so each case gives a reward for every arm, rather than one sampled arm as in Algorithm B.1. This uses the 558 build cases fully and makes the fit deterministic. It needs one extra pass: **ungated G-pipe on the 19 OTel build cases the gate skipped** (the S2.2 selection run did this once). On RCAEval build there are no traces, so the G arms learn from OTel only (S2-BL-01).
- **The exploration bonus becomes a pessimism margin.** A frozen policy cannot explore, so Ch3's upper-confidence bonus has no use. Subtracting it instead makes the router escalate where its own estimate is uncertain, which is the safe direction for an operations tool. α is fixed in the pre-run entry; λ (ridge) likewise.
- **Cross-fitting** on MAHC's folds (OTel by root service; RCAEval by system), so every held-out estimate comes from parameters that never saw the case. The frozen parameters are refitted on all build cases after the run, as for G-pipe and MAHC.

### 5.4 Constraints and thresholds

- **τ_acc** by the R-d rule: the lowest value for which the routed policy's held-out HR@3 is within the tolerance of uniform routing in each corpus. Report the share of runs escalated per corpus and per signal type.
- **τ_lat:** an arm is infeasible if its expected finish (build median of each pipeline in the arm, staged) exceeds the 90 s convergence bound. On build data this never binds (L max 23 s); it is kept for Ch3 fidelity and for the slower pool.
- **Cost order of the reachable arms** is fixed: D < D+G < D+L < Full, by build-median latency and GPU time under price-book-v2's AWS primary profile. The cost term is fixed by this order, so a price-book change cannot reorder arms silently. The profile's digest goes into the router's parameter hash; GCP and Azure profiles never feed routing.

### 5.5 Publication and timing

| | Full (`cbr_routing` ON) | noRouter (OFF, uniform) |
|---|---|---|
| Dispatch | Staged: D, then G if routed, then L if escalated | All pipelines at the trigger (replayed concurrently, as today), G ungated (R-b) |
| First publication | When the cheap arm finishes | At the earlier of 30 s and all done (S2.5 §5.5, unchanged) |
| Terminal publication | Stage-1 publication if stopped; after L if escalated (cheap stage + L latency, replayed sequentially) | When all done, within 90 s |
| Non-convergence | Escalated L unfinished at 90 s | Unchanged |
| Scored list (HR@k) | Terminal | Terminal |

What S4's scoring path must read (recorded now, so S4 has it): **TTCD** from the publication records (first correct top-1 across first and terminal publications); **`requests_human`** from the terminal state; the arm and stage times from the routing record. TTT is the first publication of any state, as entry 46 and S2.5 §5.5 read it.

Escalation adds the cheap stage (at most about 1 s on build data) to the L-pipe's finish time. Starting the L-pipe speculatively and cancelling it on a stop would save that second at the cost of GPU time for every run; it is left to Stage B.

### 5.6 Records and wiring

- The CoE `R` step grows from the G gate record to the full routing record: features, per-arm p̂_acc and LCB, τ_acc, the chosen arm, stage 1 and terminal arms, escalation reason (`disagreement`, `low_confidence`, `none`), `constraint_empty`, and later S3.5's `llm_unavailable`. The F step records both publications.
- Router parameters live in `data/frozen/router_params.json` with a hash in `parameter_hashes`; the runner refuses to start a routed run whose hash does not match (VCL done-when).
- The router module sits under `helios/consensus/` (next to MAHC), with `@gated_by(VCLFlag.CBR_ROUTING)` on its entry point.

## 6. Protocol records

- **Pre-run entry** (owner signs before any fit): R-a…R-e; the feature list; λ and α; the reward (HR@3 hit of the arm's fused list); the fold scheme; the τ_acc rule and tolerance; τ_lat; the arm cost order and price-book digest; staged timing; the meaning of uniform routing; the G gate's change of role (from a decision to a feature in Full, ungated in noRouter); the PROVISIONAL rule for single-pipeline stops.
- **Freeze entry** (after the build run; owner reviews first): the frozen parameters and hash; τ_acc; held-out HR@3 of routed vs uniform vs S2 Full per corpus; escalation shares; the replayed first-publication times; the GPU time and LLM calls saved.
- **OSF addendum** (before `build-freeze`): both entries, and the pre-registered split of A-H5 by routed arm and by G-pipe participation (S2-BL-01).

## 6a. Size and tracking

The plan gives 3 days. With the ungated G pass, the full-information arm evaluation, staged timing and the runner changes, my estimate is **4½**. Row S2-M8-ENG01, opened at sprint start. Two PRs as in S2: PR 1 = router, staged runner, records, tests, pre-run entry; PR 2 = build run, freeze, freeze entry.

## 7. Done when

- The routed arm, escalation reason and stage times are recorded per run (task done-when); a run with a mismatched router hash refuses to start (VCL done-when).
- noRouter differs from Full on a fixture (different dispatch and first publication from the same inputs).
- A disagreement fixture escalates; a high-confidence agreeing fixture stops; a constraint-empty fixture runs Full with the covariate.
- A D-only stop publishes PROVISIONAL (R-e).
- Rerun equality of the routing decision and the terminal list; leakage test covers router inputs.
- Held-out routed HR@3 within the R-d tolerance in both corpora; escalation shares and saved GPU time reported.

## 8. Calls I made (owner to check)

1. **The A-H5 effect is driven by early publication**, not by skipping the LLM (§2); the design keeps both and reports them separately.
2. **Full-information initialisation** instead of a simulated bandit pass (§5.3).
3. **LCB, not UCB**, in a frozen policy (§5.3).
4. **Disagreement escalates by rule**, low confidence by the model (§5.1).
5. **MAHC stays frozen.** The router never refits priors or the calibrator; it only chooses which lists MAHC fuses.
6. **Fixed arm cost order** rather than a learned cost (§5.4): costs are known from the price book; only accuracy needs learning.
7. **L-pipe starts after the decision** (no speculative start) (§5.5).

## 9. Left to the builder

λ and α values (fixed before the run); feature scaling; how the R step's record extends the CoE schema without breaking S2 ledgers (new fields only); whether the G decision and the escalation decision share one model per arm or the G decision uses a simpler rule if its model is too thin on 63 OTel cases.

## 10. Questions for the chair call

- A-H5 under this price book measures early publication (§2). Is that the claim the dissertation wants, with the LLM savings reported as IN3 evidence beside it?
- The reading of uniform routing (R-b) and the G gate's change of role.
- **A-H1 narrows.** noLLM also routes, so Full and noLLM differ only on the cases the router escalates; A-H1 measures the LLM's value on escalated cases. A-H2 (Full vs LLM-only) is affected less, since LLM-only does not route. Report the escalated share beside both, and pre-register A-H1 split by escalation in the addendum.
