# CR-03 MAHC state label · design

**Backlog item:** CR-03 (component review backlog, S5 folder) · **Flag:** `VCLFlag.MAHC_HIERARCHICAL` · **Status:** draft for the owner, 2026-11-26 · **Data:** build data only (`data/campaigns/s5_cr`: `otel_build_v3` 63 cases, `rcaeval_build_1..3` 495 cases); the pool stays locked · **Chair:** "CR-03, then E1–E3" approved on the 26 Nov call

## 1. What is wrong

On RCAEval build data, HELIOS-Full's CONFIRMED verdicts are less reliable than its PROVISIONAL ones. A user reads CONFIRMED as the more trustworthy label.

| Run | CONFIRMED top-1 | CONFIRMED top-3 | PROVISIONAL top-1 | PROVISIONAL top-3 |
|---|---|---|---|---|
| `s5_1` (before CR-01, the backlog figures) | 63/82 (77%) | 74/82 (90%) | 349/413 (85%) | 404/413 (98%) |
| `s5_cr` (CR-01/CR-02 build, now frozen) | 150/180 (83%) | 172/180 (96%) | 288/315 (91%) | 307/315 (97%) |

The CR-01 router fix halved the gap but did not close it.

## 2. Cause: a mix effect from the router, not a broken floor

The state rule (`helios/consensus/mahc.py` `_publish`, `calibration.py` `state`):

- NON_CONVERGED if the schedule did not converge;
- PROVISIONAL if only **one** pipeline contributed (R-e, S3.1: the agreement feature is trivially true for one pipeline);
- otherwise CONFIRMED if calibrated confidence is at least the frozen floor (0.914286, owner target M-c: top-3 of at least 80% above the floor), else PROVISIONAL.

The PROVISIONAL bucket mixes two very different groups. The large one is the cases where **the router stopped after the D-pipe**. The router stops because D is clearly right, so these are the easiest cases, and R-e still labels them PROVISIONAL.

**HELIOS-Full, PROVISIONAL split by reason (`s5_cr`):**

| Corpus | Group | n | top-1 | top-3 |
|---|---|---|---|---|
| RCAEval | CONFIRMED (two or more pipelines, confidence at or above the floor) | 180 | 150 (83%) | 172 (96%) |
| RCAEval | PROVISIONAL: one pipeline (router stopped) | 266 | 247 (93%) | 261 (98%) |
| RCAEval | PROVISIONAL: two or more pipelines, below the floor | 49 | 41 (84%) | 46 (94%) |
| OTel | CONFIRMED | 16 | 11 (69%) | 12 (75%) |
| OTel | PROVISIONAL: one pipeline | 13 | 13 | 13 |
| OTel | PROVISIONAL: below the floor | 34 | 10 (29%) | 27 (79%) |

**Without the router (HELIOS-noRouter), the label already works:**

| Corpus | CONFIRMED top-1 | CONFIRMED top-3 | PROVISIONAL top-1 | PROVISIONAL top-3 |
|---|---|---|---|---|
| RCAEval | 401/445 (90%) | 436/445 (98%) | 41/50 (82%) | 46/50 (92%) |
| OTel | 24/29 (83%) | 25/29 (86%) | 10/34 (29%) | 27/34 (79%) |

So:

1. Among comparable cases (two or more pipelines), CONFIRMED is as reliable as or more reliable than PROVISIONAL. On OTel the floor separates top-1 sharply (69% against 29%). On RCAEval the separation is small (96% against 94% top-3), because confidence is compressed there (CR-05).
2. The inversion comes from R-e putting the router's easiest cases into PROVISIONAL.
3. The label says "not confirmed" when it should say *why*: one pipeline ran, or the confidence was below the floor.

## 3. Constraint: the state is measured

The state is not only a label:

- **CpR** charges human review time to every PROVISIONAL or NON_CONVERGED verdict (`helios/evaluation/run_metrics.py` `requests_human`, metric contract "Human time"). CpR feeds **A-H5** (noRouter against Full, log-CpR) and **B-H7** (best baseline against Full, log-CpR). The HITL escalation rate (exploratory) reads it too.
- **Narratives** print it: the code-filled first line (`helios/narrative/render.py`) shows "confidence 0.95, confirmed", and the narrator's LLM input includes the state (`helios/narrative/llm.py`). Raters and the user study will read these narratives.

Any change to *which* cases are CONFIRMED changes what A-H5 and B-H7 measure. Under the integrity rule it needs a deviation entry and a new freeze before E1. A change to the *wording* alone leaves CpR untouched but changes the narrative text.

## 4. Options

Human requests are the number of PROVISIONAL verdicts that CpR charges for review.

| | Option | What changes | Reliability after (RCAEval, HELIOS-Full, top-3) | Human requests, Full RCAEval / OTel | A-H5 / B-H7 | Freeze, entry | Effort |
|---|---|---|---|---|---|---|---|
| **A** | **Reason codes (recommended)** | Rule unchanged. The verdict gets a `state_reason` (corroborated, single pipeline, below floor, not converged) in its evidence; the narrative's first line prints it, e.g. "provisional: one pipeline ran" | Unchanged numbers; the label now says what happened, and §2's split becomes visible to the user | 315 / 47 (unchanged) | Unchanged | New freeze (narrative text changes), one entry | 2–3 days with the freeze |
| B | Raise the floor to 0.99 | Fewer CONFIRMED | CONFIRMED 69/70 (99%) against PROVISIONAL 410/425 (96%); OTel 5/5 | 425 / 58 (up) | Changed: CpR rises for every MAHC variant; noRouter's requests go from 50 to 177 | New freeze, entry, pilot rerun | 3 days |
| C | Let a router stop at or above the floor be CONFIRMED (relax R-e for routed stops) | Many more CONFIRMED | CONFIRMED 433/445 (97%) against PROVISIONAL 46/50 (92%) | 50 / 34 (down sharply) | Changed **in the predicted direction**: Full's human cost falls to noRouter's level | New freeze, entry, pilot rerun | 3–4 days |
| D | Report only | Nothing in the build; §2 goes into the phase A report as a limitation; A goes to Stage B | Unchanged | Unchanged | Unchanged | None | 0 days; E1 can start now |

All figures are in-sample on build data. The floor in B was read off the same data, so it would be optimistic on the pool.

## 5. Recommendation: option A

- **It fixes the real defect.** The rule works where cases are comparable. What misleads the user is a single word for two different reasons. With reason codes, a PROVISIONAL from a confident router stop no longer reads like a weak consensus.
- **Pre-registered measures stay the same.** CpR, A-H5 and B-H7 read the state, and the state does not change, so no confirmatory test changes. The entry records only the narrative wording.
- **B and C stay off the evidence build.** B makes CONFIRMED rare and expensive on build-fitted numbers. C moves A-H5 towards its prediction after we have seen build data, and an examiner would rightly question that. Both are good Stage B variants (an extra exploratory item next to CR-04..08), evaluated after March.
- **Why not D:** the chair approved fixing CR-03 before E1. The narratives that raters and study participants read come from the confirmatory runs. If the wording is ever going to change, it has to change before E1, not after.

## 6. Plan for option A

1. On branch `e/cr03-state-reason` from `main`, done as built:
   - `helios/narrative/render.py` gets `state_text`. It derives the reason from the F step alone (state, confidence, `detail.contributing`), and the header prints it after the confidence.
   - This is simpler than the first draft, which put a `state_reason` field into `FusedVerdict.evidence`. Nothing in `helios/consensus/`, the stored fusion rows, their CoE `row_ref` digests, `requests_human` or CpR changes.
   - The narrator's LLM input is unchanged: `PINNED_PROMPT_INPUTS` still matches, and a new test checks the prompt carries the raw state.
2. Tests (done; the full suite passes):
   - One reason per path, plus the case of an entry without `detail`.
   - The exact header text, with and without confidence.
   - The state is never altered.
   - Replay on the `s5_cr` stores: all 7,254 fusion rows give a reason that matches the stored state. HELIOS-Full RCAEval: 180 "two or more pipelines, confidence above floor", 266 "one pipeline ran", 49 "confidence below floor".
3. Deviation entry (draft first; you say "approve N"). Clause: narrative first-line wording, CR-03. Analytic consequence: none on any hypothesis test. The narrative text that raters see changes before any confirmatory narrative exists.
4. New freeze record, tag `build-freeze-3` (your OK), bump `BUILD_FREEZE_TAG`, entry recording the tag.
5. Move `../helios-e` to `build-freeze-3`, run `--check`, then E1 on a free machine.

## 7. Owner decisions (2026-11-26)

1. **Option A.**
2. **Wording.** The first proposal said "confirmed: pipelines agree". On build data that is false for 66 of 196 HELIOS-Full CONFIRMED verdicts and for 149 of 279 noConsensus ones: at least one pipeline's top-1 differs, and the narrative lists that difference under "Where the pipelines disagree". CONFIRMED means two or more pipelines contributed and confidence reached the floor. The owner chose the accurate wording:
   - "confirmed: two or more pipelines, confidence above floor"
   - "confirmed: two or more pipelines voted" (noConsensus, which has no floor)
   - "provisional: one pipeline ran"
   - "provisional: confidence below floor"
   - "not converged"
3. **B and C** go to the backlog as CR-03b and CR-03c (Stage B, exploratory).

**Note on the data.** `s5_cr` ran on the CR-01/CR-02 candidate (`ee64627`), which became `build-freeze`. `build-freeze-2` changed only OTel span-status parsing (entry 104), so OTel counts may differ slightly on the current freeze. RCAEval counts are unaffected. Scripts: the scratchpad scripts `cr03.py` and `cr03_floor.py`; they read the build campaign stores only.
