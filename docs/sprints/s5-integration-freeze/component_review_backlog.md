# Component review · backlog and defects

**Raised:** 2026-11-16, from the component review of the S5.1 and S5.3 build campaigns · **Owner:** project owner (revisits once implementation items are done) · **Data:** exploratory build data only (OTel v3, 63 cases; RCAEval build, 495 cases in three parts). HELIOS was tuned on this data, so effects favour it; a weakness that shows here is a strong signal. OTel counts are small.

## How to read this

- **Kind.** `BUG` is a defect: behaviour that contradicts the design or misleads a user. `IMP` is an improvement: the component works as designed, but the design underperforms. `EVAL` is a limit of the evaluation itself. `DOC` is a documentation fix.
- **Priority.** P1 is before `build-freeze`, P2 is before the freeze if time allows, P3 is Stage B or later.
- **Freeze impact.** "Ranking change" means the item changes rankings or frozen parameters. It then needs a design note approved by the owner, a deviation entry approved by the owner before it is appended, a re-freeze of the affected parameter hashes, and a rerun of the HELIOS part of S5.4 on the frozen SHA (about 3 h with the cache). Stage B items stay behind their flags and never touch the frozen evidence build.
- **Status** is one of OPEN, IN_PROGRESS, DONE, WONT_FIX, DEFERRED.

## Summary

| ID | Kind | Pri | Component (flag) | Title | Freeze impact | Status |
|---|---|---|---|---|---|---|
| CR-01 | IMP | P1 | Router (`cbr_routing`) | Skip rule drops the L-pipe on cases it would have solved | Ranking change | OPEN |
| CR-02 | IMP | P1 | Structural features (`ueg_structural`) | Structural weighting slightly hurts OTel and adds latency | Ranking change | OPEN |
| CR-03 | BUG | P1 | MAHC (`mahc_hierarchical`) | CONFIRMED is less reliable than PROVISIONAL on RCAEval | State label only; no ranking change | OPEN |
| CR-04 | BUG | P2 | L-pipe (`l2c_llm`) | Metric-worker prompts give different answers run to run | Ranking change on affected cases | OPEN |
| CR-05 | IMP | P2 | MAHC (`mahc_hierarchical`) | No accuracy gain over plain Borda; confidence compressed on RCAEval | Ranking change if weights change | OPEN |
| CR-06 | IMP | P2 | L-pipe (`l2c_llm`) | Little gain on OTel; prompts may lack topology context | Ranking change | OPEN |
| CR-07 | IMP | P2 | D-pipe / G-pipe | D weak on OTel; fusing D and G does not beat G alone | Ranking change | OPEN |
| CR-08 | EVAL | P2 | All pipelines | Error analysis of the OTel hard core (32 of 63 wrong for Full and noRouter) | None (analysis only) | OPEN |
| CR-09 | EVAL | P1 | G-pipe / A-H6 | G never runs on RCAEval; graph comparisons are empty there | Addendum rule | DONE (entry 93, `eef31c8`) |
| CR-10 | EVAL | P2 | Metrics (CpR, A-H5) | Median log-CpR sits at the censoring ceiling for many systems | Addendum only (contract is OSF-signed) | DONE (entry 94, `eef31c8`) |
| CR-11 | EVAL | P2 | Metrics (HR@3) | HR@3 at ceiling on RCAEval; top-3 tests have low power | Addendum only | DONE (entry 95, `eef31c8`) |
| CR-12 | IMP | P3 | FGSV (`fgsv_ks_gate`) | Gate marks 52% of clean OTel targets STALE | None (no ranking role) | OPEN |
| CR-13 | BUG | P3 | FGSV (`fgsv_ks_gate`) | Replay does not separate HELIOS's wrong answers from right ones | None | OPEN |
| CR-14 | IMP | P3 | ACP (`acp_stateful`) | Code-level faults predicted poorly (10 of 30) | None (recorded, not routed) | DEFERRED (Stage B, E-H8) |
| CR-15 | IMP | P3 | IOL (`iol_self_telemetry`) | Detects only ×5 and ×8 slowdowns, never ×2 or ×3 | None | OPEN |
| CR-16 | IMP | P3 | Reconcile (`reconcile_terminal`) | Inert in rankings; role depends on E-H5 | Depends on E-H5 | DONE (entry 92, E-H5 decided 2026-11-18) |
| CR-17 | IMP | P3 | Cogni (`p4_cognitive`), HIS3 (`his_tier`) | No consumer of their output | None | DEFERRED (Stage B) |
| CR-18 | BUG | — | Baselines (Multi-source BARO) | Late-trigger IndexError; 13 OTel exclusions | Baseline change | WONT_FIX before freeze (owner, R-g) |
| CR-19 | EVAL | P3 | Baselines (TraceRCA) | TraceRCA cannot run on RCAEval (no traces) | None | OPEN (record in report) |
| CR-20 | EVAL | P3 | Seed register | 7,200 slots cap campaign size | None now | OPEN |
| CR-21 | DOC | P1 | S5.4 design | Wrong claim that `raw/checksums_build.json` is tracked | None | OPEN (fix in S5.4 report) |
| CR-22 | DOC | P1 | Provisioning | Part manifests must be regenerated in a fresh clone | None | OPEN (fix in S5.4 report) |
| CR-23 | BUG | P2 | Baselines (Multi-source RCD) | Ranked list varies between runs with identical input, seed and image | Baseline change if fixed | WONT_FIX before freeze (owner accepted 2026-11-18, S5.4 §7); reported per entry 96 (`eef31c8`) |
| CR-00 | BUG | — | Campaign `cells` | Trigger-time runs keyed under the binding-time name | None | DONE (`54becfb`) |

## Items

### CR-01 · Router skip rule drops the L-pipe on cases it would have solved

- **Kind / priority:** IMP, P1. **Flag:** `cbr_routing`.
- **Evidence.**
  - On RCAEval, Full skips the L-pipe in about 75% of cases.
  - Of Full's wrong top-1 answers where it skipped, noRouter (uniform routing) is right in 36 and also wrong in 19. Skipping helped in 6. Net about −30 top-1 hits of 495.
  - Top-1: Full 80–87% against noRouter 87–92%. Top-3: 96–97% against 98%.
  - What the router buys: median TTT about 0.2 s against about 9 s; median log-CpR about 3.6 against 6.8.
  - On OTel the router asks the L-pipe in 57 of 63 cases, so Full and noRouter barely differ.
  - The router was frozen before ACP existed (S3 report).
- **Problem.** The stop signal does not separate easy cases from hard ones.
- **Proposed approach.**
  1. On build data, fit the escalation rule with features such as the D-pipe top-1 margin, the fused confidence and the anomaly breadth; compare against the current threshold of 0.2.
  2. Report the accuracy and cost frontier, and choose an operating point with the owner.
  3. Optionally add "escalate when D's confidence is low" as a guard.
- **Done when.** A design note approved by the owner; a new rule that recovers most of the 36 cases at a stated cost; frozen parameters re-hashed; deviation entry appended after owner approval; S5.4 HELIOS part rerun.

### CR-02 · Structural weighting slightly hurts OTel and adds latency

- **Kind / priority:** IMP, P1. **Flag:** `ueg_structural`.
- **Evidence (OTel only; RCAEval has no topology).**
  - noStructural against Full, per case: top-1 4 better and 1 worse; top-3 2 better and 1 worse.
  - Median TTT about half a second against 1.4 s; structural features add about 0.9 s.
  - The direction is the opposite of what the structural ablation predicts.
- **Proposed approach.** Review how structural features are weighted in the G-pipe ranking; look at the 5 cases that differ; test a lighter weighting or a gated use (only when the graph is dense enough); profile the 0.9 s.
- **Done when.** Structural features do not lose to noStructural on build data, or the reason is documented and accepted; same freeze steps as CR-01.

### CR-03 · CONFIRMED is less reliable than PROVISIONAL on RCAEval

- **Kind / priority:** BUG, P1. **Flag:** `mahc_hierarchical`.
- **Evidence.** RCAEval: CONFIRMED hits the top 3 in 74 of 82 cases (90%); PROVISIONAL in 404 of 413 (98%). Part of this is selection, because confirmed cases are the ones where the L-pipe ran, and those are the harder cases.
- **Problem.** A production user reads CONFIRMED as more trustworthy, and here it is not.
- **Proposed approach.** Redefine the state rule so CONFIRMED needs both agreement and calibrated confidence above a threshold; or rename the states to describe what happened ("LLM-corroborated") rather than imply reliability. Check the rule against the confidence bins on build data.
- **Done when.** On build data, CONFIRMED is at least as reliable as PROVISIONAL, or the label no longer implies reliability. State label only; check whether any pre-registered measure reads the state before deciding if a deviation entry is needed.

### CR-04 · L-pipe metric-worker nondeterminism

- **Kind / priority:** BUG, P2. **Flag:** `l2c_llm`.
- **Evidence (S5.5).** 8 of 57 RCAEval metric-worker prompts give different answers run to run; 54 of 460 RCAEval HELIOS rerun pairs differ. OTel pairs are all equal.
- **Proposed approach.** Find what makes those 8 prompts unstable (ties in the candidate list, prompt length, sampling settings, parse fallbacks); fix decoding settings or the candidate ordering; add a determinism test on those prompts.
- **Done when.** Rerunning the S5.5 pairs gives fewer differing pairs, with the cause written up.

### CR-05 · MAHC adds no accuracy over Borda; confidence compressed

- **Kind / priority:** IMP, P2. **Flag:** `mahc_hierarchical`.
- **Evidence.**
  - noConsensus (uniform Borda) matches Full: the top-1 differs on 3 OTel and 3 RCAEval cases, split both ways. On OTel, noConsensus is cheaper (median log-CpR 5.02 against 7.09).
  - The confidence targets P(root cause in top 3) and is roughly calibrated. AUROC is 0.665 on OTel and 0.735 on RCAEval. OTel is overconfident in the 0.8–0.9 bin (stated 0.97 at the top, observed 0.87). On RCAEval, 455 of 495 cases fall in the 0.9 bin.
- **Proposed approach.** Decide what MAHC is for: accuracy (then the pipeline weights must earn it) or calibrated confidence (then improve how well it ranks cases, for example with per-corpus calibration or more features). Look at the cost difference on OTel.
- **Done when.** Either measurable gain over Borda on build data, or MAHC's claimed value is restated as confidence only, with calibration that ranks cases better.

### CR-06 · L-pipe gives little gain on OTel

- **Kind / priority:** IMP, P2. **Flag:** `l2c_llm`.
- **Evidence.** RCAEval: LLM-only top-1 84–88%, above Full. OTel: Full against noLLM is 4–4 on top-1, and Full is 3 cases worse on top-3.
- **Proposed approach.** Compare the OTel prompt contents with RCAEval's; try adding topology or trace context; check whether the L-pipe is being outvoted in fusion on OTel.
- **Done when.** A clear reason for the gap, and either a prompt change that helps OTel on build data or a documented limit.

### CR-07 · D-pipe weak on OTel; D plus G does not beat G

- **Kind / priority:** IMP, P2. **Flags:** `dpipe`, `gpipe`.
- **Evidence.** OTel: D top-1 0.30; noLLM (D and G fused) 0.49; G alone 0.51. Per case, G against Full on top-1 is 5 better and 4 worse.
- **Proposed approach.** Look at which fault types D misses; check whether fusion should weight D down on corpora with traces.
- **Done when.** Fusing D and G is at least as good as the better of the two on build data, or the weighting is justified.

### CR-08 · Error analysis of the OTel hard core

- **Kind / priority:** EVAL, P2.
- **Evidence.** 32 of 63 OTel cases are wrong at top-1 for both Full and noRouter.
- **Proposed approach.** Break the 32 down by fault type, service and signal availability, on build data only. This sets the ceiling for CR-01, CR-02, CR-06 and CR-07.
- **Done when.** A short analysis note in this folder, linked from here.

### CR-09 · G-pipe never runs on RCAEval

- **Kind / priority:** EVAL, P1.
- **Evidence.** RCAEval has no traces, so G is skipped every time. HELIOS-G, HELIOS-D and noLLM give identical rankings there, so the graph-only comparisons (A-H6 and others that use G) have nothing to compare on RCAEval.
- **Proposed approach.** Check which pre-registered tests read G on RCAEval; draft an addendum note (never an edit to `metric_contract.md`) saying those tests are informative on OTel only.
- **Done when.** The affected tests are listed and the addendum text is approved by the owner.
- **Done (2026-11-18).** Entry 93: A-H6, A-H8 and E-H10 are untestable on a system none of whose sealed captures carries traces. Computed by the analysis (`helios/analysis/reporting.py`, `eef31c8`); addendum §2.15. On RCAEval build part 1 both A-H6 and A-H8 move from p = 1 (tied by construction) to untestable; every other result is unchanged.

### CR-10 · CpR median at the censoring ceiling

- **Kind / priority:** EVAL, P2.
- **Evidence.** The median log-CpR sits at 12.03 for many systems, which is the censoring cap. A-H5 is below its threshold in every campaign.
- **Proposed approach.** Report the censoring share and a censoring-aware summary (for example restricted mean or Kaplan–Meier style) as exploratory. Any change to the binding metric goes to the addendum draft; the signed contract stays untouched.
- **Done when.** Addendum text drafted and approved, or explicitly declined.
- **Done (2026-11-18).** Entry 94: censored share, timing-noise statement, p-value with rerun values substituted and a sensitivity reading beside every timing-derived result (`eef31c8`; addendum §2.15). A restricted-mean or Kaplan–Meier summary was not adopted. On OTel build v3 the reading flags B-H7 (p about 0.038 against threshold 0.025; about 0.022 with its 6 reruns substituted).

### CR-11 · HR@3 at ceiling on RCAEval

- **Kind / priority:** EVAL, P2.
- **Evidence.** Full HR@3 is 96–98% on RCAEval, so the A-family top-3 tests have few differing cases.
- **Proposed approach.** Report HR@1 and MRR alongside as exploratory; note the power limit in the addendum.
- **Done when.** Addendum note approved, or declined.
- **Done (2026-11-18).** Entry 95: HR@1 and MRR exploratory columns (paired BCa, no p-value) and the HR@3 discordant pairs beside each HR@3 test (`eef31c8`; addendum §2.15).

### CR-12 · FGSV gate marks half of clean OTel targets STALE

- **Kind / priority:** IMP, P3. **Flag:** `fgsv_ks_gate`.
- **Evidence.** STALE on 52% of clean OTel targets; every RCAEval case STALE `no_structure`. FGSV changes no ranking by design.
- **Proposed approach.** Recalibrate the KS gate threshold on clean windows; add a "not applicable" outcome distinct from STALE where there is no structure.
- **Done when.** STALE rate on clean targets at an agreed level; Stage B behind the flag.

### CR-13 · FGSV replay does not separate wrong answers from right ones

- **Kind / priority:** BUG, P3. **Flag:** `fgsv_ks_gate`.
- **Evidence.** Replay accepts 12 of 17 of HELIOS's wrong answers and 12 of 17 of its right ones.
- **Problem.** As a verifier it currently carries no signal about correctness.
- **Proposed approach.** Review what replay checks; test a stronger counterfactual (remove the candidate's signal and measure the change).
- **Done when.** Acceptance rate differs clearly between right and wrong answers on build data.

### CR-14 · ACP code-level faults

- **Kind / priority:** IMP, P3. **Flag:** `acp_stateful`.
- **Evidence.** 78.85% accuracy against a 52.15% majority class; code-level faults 10 of 30. Recorded, not routed.
- **Proposed approach.** Needs real remediation data; moves with E-H8 to Stage B.
- **Done when.** Stage B evaluation.

### CR-15 · IOL sensitivity

- **Kind / priority:** IMP, P3. **Flag:** `iol_self_telemetry`.
- **Evidence.** Detects ×5 and ×8 self-slowdowns, never ×2 or ×3.
- **Proposed approach.** Tune the detector baseline window and threshold; acceptable as-is for the lite version.
- **Done when.** ×3 detected on build data, or the lite limit is documented.

### CR-16 · Reconcile inert in rankings

- **Kind / priority:** IMP, P3. **Flag:** `reconcile_terminal`.
- **Evidence.** Never changes a ranking; works as designed.
- **Open decision.** E-H5 (owner).
- **Done when.** E-H5 decided and Reconcile's role set accordingly.
- **Done (2026-11-18).** Entry 92: E-H5 is read in the same-case form. Reconcile is assessed through E-H5 and the learning curves, and stays inert in the confirmatory rankings under the static frozen router.

### CR-17 · Cogni and HIS3 have no consumer

- **Kind / priority:** IMP, P3. **Flags:** `p4_cognitive`, `his_tier`.
- **Evidence.** Nothing reads their output; refused for Stage A.
- **Done when.** Stage B gives them a consumer and an exploratory evaluation.

### CR-18 · Multi-source BARO late-trigger IndexError

- **Kind / priority:** BUG. **Status:** WONT_FIX before the freeze (owner decision R-g, 2026-11-16).
- **Evidence.** 13 OTel exclusions when the trigger falls late in the capture (S5.3 §3.1). Phase E will show the same pattern.
- **Revisit:** after the freeze, as a baseline fix for exploratory reruns only.

### CR-19 · TraceRCA absent on RCAEval

- **Kind / priority:** EVAL, P3.
- **Evidence.** No traces in RCAEval, so TraceRCA cannot run there. Also the 62 s window case on OTel.
- **Done when.** Stated in the phase E report as a corpus limit.

### CR-20 · Seed register size

- **Kind / priority:** EVAL, P3.
- **Evidence.** 7,200 slots limit how large a campaign can be.
- **Done when.** Sized against the phase E and Stage B campaign plans; extended (with a deviation entry) only if needed.

### CR-21 · S5.4 design: checksum file wording

- **Kind / priority:** DOC, P1.
- **Evidence.** `s5_4_replication_design.md` §2 says `raw/checksums_build.json` is tracked. It is not; the tracked, signed `ground_truth_build.json` records the raw hashes.
- **Done when.** Corrected in `s5_4_replication.md`.

### CR-22 · Part manifests in a fresh clone

- **Kind / priority:** DOC, P1.
- **Evidence.** The RCAEval part manifests (`rcaeval_build_{1,2,3}_manifest.json`) are regenerated, byte-identical, from the tracked manifest; a fresh clone needs this step.
- **Done when.** Documented as a provisioning step in the S5.4 report.

### CR-23 · Multi-source RCD is nondeterministic beyond its seed

- **Kind / priority:** BUG, P2. **Raised:** 2026-11-18, S5.4 replication.
- **Evidence.** On 3 of 495 RCAEval build cases, 6 of 5,580 baseline runs, Multi-source RCD returned a different ranked list (order and length) in the clean clone. Snapshot hash, run seed, image digest and config hash were identical. HR@1 and HR@3 are unchanged in all six runs; Avg@5 and MRR change on two cases; no analysis field changes. The S5.5 rerun subset covers HELIOS only, so this was not seen before.
- **Proposed approach.** Either accept it and say in phase E that RCD's lower ranks can move between reruns, or pin the RCD container to one thread or a fixed search order. A fix is a baseline change: deviation entry and RCD rerun before the freeze.
- **Decision (owner, 2026-11-18).** Accepted as a baseline environment difference; not fixed before the freeze. Phase E states the limit.
- **Reporting (2026-11-18).** Entry 96: the analysis reports each system's determinism reruns, and Multi-source RCD's beside B-H5 and, when it is the best baseline, B-H8 (`eef31c8`). The RCAEval build part 1 campaign has no baseline reruns (its S5.1 baseline reruns ran under export v1, entry 91), so those figures show no pairs there; OTel v3 shows 6 RCD pairs, all identical.
- **Revisit:** after the freeze, as a baseline fix for exploratory reruns only; done when a rerun of the six runs matches itself.

### CR-00 · `cells` keyed trigger-time runs under the binding-time name (closed)

- **Kind:** BUG. **Status:** DONE in `54becfb` (`spec_system_name`, `tests/test_campaign_cells.py`). The 18 `c80ff7d1` ledger entries stay as recorded and are reported as mis-attributed in the S5.4 report.

## Suggested order

1. CR-21 and CR-22 go into the S5.4 report.
2. CR-01, then CR-02: each needs a design note first. Settle them before running S5.4, or rerun its HELIOS part afterwards.
3. CR-03 and CR-09, before the freeze.
4. CR-04 through CR-08, CR-10 and CR-11 if time allows; otherwise the addendum notes only.
5. CR-12 to CR-20 go to Stage B or after the freeze.
