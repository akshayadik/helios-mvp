# CR-01 Router stop rule · design

**Backlog item:** CR-01 (component review backlog, S5 folder) · **Flag:** `VCLFlag.CBR_ROUTING` · **Status:** draft for the owner, 2026-11-19 · **Data:** build data only (`otel_build_v3` 63, `rcaeval_build` 495); the pool stays locked

## 1. What is wrong

On RCAEval build, HELIOS-Full stops on the D-pipe in about 60% of cases and loses top-1 hits that uniform routing (HELIOS-noRouter) gets. In the held-out replay below, the frozen router gets **416** top-1 hits of 495, against **442** for uniform routing. Top-3 barely moves (478 against 482).

## 2. Cause

The router was fitted and its threshold chosen on **HR@3 only** (deviation entry 69, items 8 and 9; R-d):

- **Reward.** Each arm's LinUCB model predicts the HR@3 hit of that arm's fused list.
- **Threshold rule (R-d).** τ_acc is the lowest lower bound at which routed HR@3 stays within one point of uniform HR@3 in each corpus.

HR@3 sits near its ceiling on RCAEval (CR-11): the D-pipe alone puts the root cause in the top 3 in about 95% of cases. So the router learns, correctly for HR@3, that D alone is "good enough", and stops. Whether D's **first** candidate is right never enters the fit or the rule.

Top-1 is what matters downstream:

- **TTCD and CpR** read the first published verdict whose top-1 is correct (metric contract §4). A run that stops with a wrong top-1 never gets a correct top-1, so its TTCD is censored at 1,800 s and its CpR sits at the ceiling (CR-10).
- **The operator** acts on the first candidate.

The backlog text for CR-01 speaks of "the current threshold of 0.2". That is wrong: the frozen rule is a LinUCB lower bound against τ_acc = 0.812574 (entry 70). The features the backlog proposed (D-pipe top-1 margin, top-1 share, fused confidence) are already in the router's feature set, except fused confidence, which the router must not read (A-H4 pairing, `router_features.py`). So the fix is in what the router is fitted to, not in new features.

## 3. Replay on build data

**Method.** The router's own policy functions (`decide_g`, `decide_escalation`), the frozen MAHC, the S3 fold scheme (one fold per corpus × group), λ = 1, α = 1, and held-out models for every case. The 558 cases were collected by the S3 build path (`collect_cases`: HELIOS-noRouter, cache-only L-pipe, no exclusions, no cache miss). The replay matches `simulate()` exactly on every case at the frozen held-out τ. These are held-out figures; the frozen refit is confirmed separately (entry 70 item 2).

**Selected rows** (top-1 and top-3 hits, routed / uniform; stops = cases that end without the L-pipe):

| Reward | R-d rule | Tol. | RCAEval top-1 | RCAEval top-3 | RCAEval stops | OTel top-1 | OTel stops | L-pipe time saved |
|---|---|---|---|---|---|---|---|---|
| HR@3 (frozen) | HR@3 | 1 pt | 416 / 442 | 478 / 482 | 299 | 31 / 31 | 0 | 2,806 s |
| HR@3 | HR@3 | 2 pt | 387 / 442 | 473 / 482 | 399 | 31 / 31 | 7 | 3,920 s |
| HR@3 | HR@1 and HR@3 | 1 pt | 438 / 442 | 480 / 482 | 170 | 31 / 31 | 0 | 1,591 s |
| **HR@1** | **HR@1 and HR@3** | **1 pt** | **438 / 442** | **480 / 482** | **245** | **31 / 31** | **11** | **2,415 s** |
| HR@1 | HR@1 and HR@3 | 2 pt | 433 / 442 | 479 / 482 | 348 | 31 / 31 | 13 | 3,494 s |
| HR@1 | HR@1 and HR@3 | 3 pt | 428 / 442 | 478 / 482 | 365 | 31 / 31 | 14 | 3,686 s |
| mean of HR@1 and HR@3 | HR@1 and HR@3 | 1 pt | 438 / 442 | 479 / 482 | 306 | 31 / 31 | 12 | 3,075 s |

**TTCD proxy** (first correct top-1 across the stage-1 and terminal publications; never correct = censored):

| Policy | RCAEval censored | OTel censored | Median TTCD of the rest |
|---|---|---|---|
| Frozen | 69 / 495 | 28 / 63 | 0.2 s RCAEval, 0.9 s OTel |
| HR@1 reward, HR@1 and HR@3 rule, 1 pt | 47 / 495 | 28 / 63 | 0.2 s RCAEval, 0.8 s OTel |

**Reading.**

- Fitting to top-1 and guarding top-1 in the threshold rule recovers **22 of the 26** lost top-1 hits on RCAEval and takes **22 cases off the censoring ceiling**, for **54 fewer stops** (245 against 299).
- On OTel the new fit stops **11** cases with no loss in top-1 or top-3, where the frozen router stops none. A top-1 reward separates the OTel cases where cheap evidence is decisive better than a top-3 reward does.
- Keeping the HR@3 reward and only adding the top-1 guard (row 3) loses more stops (170) for the same accuracy: the reward change is what makes the stop decision sharper, not only the stricter rule.
- With the HR@1 reward, guarding HR@1 or both measures gives the same τ at every tolerance tried; both are kept in the rule so HR@3, which A-H1 to A-H4, A-H6, A-H8 and B-H1 to B-H5 test, stays protected by name.
- The mean reward stops more on RCAEval (306) at one top-3 hit more cost; it is a reasonable alternative but harder to explain.

**Order with CR-02.** These figures use the frozen D-pipe. CR-02 changes the D-pipe on OTel (its design note), and the router reads D-pipe features, so the refit (step 3 below) runs after CR-02 is in, and its OTel figures will differ from the table. RCAEval has no traces, so CR-02 does not change its rows.

## 4. Decisions for the owner

| # | Decision | Proposal | Alternatives |
|---|---|---|---|
| C1-a | Router reward | **HR@1 hit of the arm's fused list** | Keep HR@3; mean of HR@1 and HR@3 |
| C1-b | R-d rule | **Routed HR@1 and HR@3 each within one point of uniform, in each corpus**; at least one stop | HR@3 only (frozen); 2 or 3 points |
| C1-c | Everything else | **Unchanged**: features, λ, α, folds, the refit confirmation (entry 70 item 2), τ_lat, the arm order, the D/G disagreement escalation | — |
| C1-d | Extra "D low confidence" guard | **Not added**: the fitted rule already escalates on D's margin and share | Add a fixed margin floor |
| C1-e | Deviation entries | **Two, as for the S3 router**: a pre-run entry with C1-a to C1-d, disclosing that the choice was made from this held-out replay on build data, appended before the refit; a freeze entry with the new τ_acc, hash and figures | One combined entry at the freeze |

## 5. Steps after approval

1. Pre-run deviation entry (text to the owner first).
2. Code: the reward and the R-d measures become named constants in `helios/evaluation/router_calibration.py` (`REWARD = "hr_at_1"`, `RD_MEASURES = ("hr_at_1", "hr_at_3")`); the report adds routed and uniform HR@1 beside HR@3. Tests for both.
3. `bin/router_build_run.py --run 4` on build data; the owner reviews `router_run4.json`.
4. `--freeze --run 4` writes `data/frozen/router_params.json`; the price-book stamp (entry 97) is kept.
5. Freeze deviation entry (text to the owner first); OSF addendum draft §3 router row updated.
6. **Reruns on build data.** The routed variants (Full, noLLM, noConsensus, noStructural) in the four S5.1 stores ran under the old router, so their rows no longer describe the build to be frozen. They are rerun on build data and the S5.3 pilot reading is refreshed. More cases escalate, so some L-pipe prompts may not be in the response cache and run live (Ollama, about 15 s each).
7. S5.4 replication: its HELIOS part is rerun on the new router (backlog done-when).

## 6. What this changes and what it does not

- **Changes:** which cases Full, noLLM, noConsensus and noStructural stop on; the router parameter hash; the router row of the OSF addendum draft §3.
- **Does not change:** any hypothesis, comparison, metric, test, alpha or Holm rank; noRouter; the feature set; any other frozen parameter.
- **Expected effect on the tests** (build figures, exploratory): Full's HR@3 and top-1 move closer to noRouter's; A-H5 (log-CpR, noRouter against Full) loses some of the saved L-pipe time but fewer Full runs sit at the censoring ceiling, which works in Full's favour; the net direction is not known until the reruns.
