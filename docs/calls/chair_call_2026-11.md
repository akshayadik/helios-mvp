# HELIOS — chair call reference · November 2026

**For:** dissertation chair · **Status of the work:** Stage A build complete and frozen; confirmatory evidence collection starts next.

How to use this document: sections 1–3 are the overview (where we are, what is done, what the results show so far). Section 4 gives the progress indicators: measurable evidence that the work is moving in the right direction. Section 5 is the remaining work and how many days each part takes. Section 6 proposes how to use the next two months.

All durations are in working days, and they are effort estimates, not calendar commitments.

---

## 1. Where we are, in one page

| Stage | Status |
|---|---|
| Build sprints S0–S5 (planned as about 20 weeks) | **All closed**, about 11 weeks ahead of plan |
| Build freeze (evidence build fixed and public) | **Done** (tag `build-freeze`, then `build-freeze-2` after a pool-format fix) |
| OSF pre-registration | **Three public records:** original pre-registration, addendum 1 (DOI 10.17605/OSF.IO/VG5TE), deposit 2 with the frozen build and rubric (DOI 10.17605/OSF.IO/8PJ5A) |
| Evidence collection (phase E) | **Started:** pool checks done; confirmatory runs (E1) next |
| Analysis and results (phase A) | Not started; most of it can run as soon as E1–E3 finish |
| Full product (Stage B) | Not started; can begin in parallel with evidence collection |

**Scale of the work so far:** over 120 pull requests, each through the full engineering gate (lint, strict typing, about 97% test coverage, ledger and capture verification). 105 signed deviation-log entries record every change to the protocol, and the log is publicly verifiable.

**Integrity position:** no confirmatory result exists yet. The confirmatory pool (240 sealed RCAEval cases) has only been read for format checks (counts only, no labels). The build that will produce the evidence is frozen by code: only the tagged build can open the pool.

---

## 2. Completed work, step by step

### S0 Foundation
- Research-integrity tooling: the HMAC-chained deviation log (later also Ed25519-signed, verifiable with a public key alone), the tracking validator, and the OSF freeze check.
- The Variant Control Layer (VCL): 17 feature flags and the 15 ablation variants (8 confirmatory, 7 exploratory), each with a unique, hashed configuration.

### S1 Data and graph (4 days; planned 15)
- Corpora: the RCAEval RE2 build set (495 cases in three parts) and the **240-case confirmatory pool, converted and sealed** (never run before the freeze). OTel demo build captures (63 cases).
- Unified evidence graph (UEG-C) with k-hop pruning, the verdict contract, the scoring path and the price book for cost per resolution (CpR).
- AIOpsLab spike: conversion works, but it is not suitable for the confirmatory pool; moved to Stage B as an exploratory corpus.

### S2 Reasoning, consensus and narratives (5 days; planned 15)
- Three peer pipelines: **D-pipe** (statistical), **G-pipe** (graph) and **L-pipe** (LLM, `llama3.1:8b`, local).
- MAHC consensus with calibrated confidence, the Chain-of-Evidence ledger, evidence-grounded narratives and the H_fact rating rubric.

### S3 Routing and learning (6 working days; planned 10)
- **Cheap-first router:** the cheaper pipelines answer first, and the LLM is called only when they disagree. Also the action-cost predictor (ACP) and the reward model, plus an LLM fallback.
- The Knowledge Cortex moved to Stage B (entry 82): no index built from evidence data.

### S4 Product shell and evaluation tooling (4 days; planned 10)
- Product shell: REST API, approval console, one-command Docker compose.
- Tier-2 items, all behind flags: PII redaction, shadow modes, lite versions of freshness validation (FGSV) and self-telemetry (IOL).
- Evaluation tooling: five RCAEval baselines (BARO, Multi-source BARO, PDiagnose, Multi-source RCD, TraceRCA), all pre-registered metrics, the run orchestrator with integrity gates, and the analysis suite (Wilcoxon, Holm, McNemar, MCAR/IPW).

### S5 Integration and freeze (6 days; planned 10)
- **System test:** all 13 runnable variants end to end, 7,254 runs, no exclusions.
- **Disjointness certificate:** each flag gates exactly one code path.
- **LLM determinism probe:** 8 of 57 RCAEval prompts answer differently when repeated. No effect on top-1 or the top-3 set.
- **Exploratory pilot** on build data, with compute, larger-model and judge-budget numbers.
- **Clean-environment replication:** HELIOS reproduces exactly on a fresh clone.
- **Component review:** 22 items. Two fixes before the freeze: router reward aligned with top-1 (CR-01) and D-pipe using observed call edges (CR-02). Both were redesigned, re-piloted and replicated before the freeze.
- **Build freeze and OSF deposit 2;** rubric frozen before rater training.

### Phase E, first steps (2 days)
- **Day-one pool checks** found one defect that build data could not show. The pool's traces carry gRPC status codes, which the build data never had, so span errors were under-counted (9 of 50 windows seen).
- It was fixed **before any confirmatory run**, with one shared rule for HELIOS and the baselines. The fix was recorded (entries 104–105) and re-frozen as `build-freeze-2`.
- The rerun passed: all 240 windows intact, and HELIOS and the baselines agree on errors in every window.

---

## 3. Results so far (build data, exploratory)

**Read this first.** Every number below is from the build data that HELIOS was built and calibrated on, so HELIOS numbers are optimistic. These are design checks, not results. Confirmatory results come only from the sealed pool.

### 3.1 Accuracy of HELIOS-Full (after CR-01 and CR-02)

| Build corpus | Cases | Top-1 | Top-3 |
|---|---|---|---|
| OTel demo v3 | 63 | 54.0% | 82.5% |
| RCAEval part 1 | 165 | 86.7% | 97.0% |
| RCAEval part 2 | 165 | 88.5% | 97.0% |
| RCAEval part 3 | 165 | 90.3% | 96.4% |

### 3.2 Against the baselines (Family B, top-3)

On OTel, HELIOS-Full is ahead of every baseline by a wide margin: 79% against 16–54% at the pilot. On RCAEval it is ahead against all four baselines that can run there, and most comparisons fall below their Holm thresholds. TraceRCA cannot run on RCAEval because there are no traces (recorded in advance, entry 91).

### 3.3 Cost and speed (the cheap-first router)

| | OTel | RCAEval part 1 |
|---|---|---|
| Median time to first answer, HELIOS-Full | 1.4 s | 0.23 s |
| Same, without the router (LLM on every case) | 15.6 s | 9.2 s |
| A-H5 (router lowers CpR) | below threshold in every corpus | below threshold in every corpus |

The router cuts time to first answer about tenfold on OTel and about fortyfold on RCAEval. Accuracy is unchanged on OTel and within about three points of uniform routing on RCAEval.

### 3.4 Reproducibility
- A fresh clone gives identical rankings, snapshot hashes and analyses for all 7,254 HELIOS runs, before and after CR-01/CR-02.
- The only differences are timing-derived figures and one baseline (Multi-source RCD) that reorders 3 of 495 cases. That difference is accepted, with a reporting rule (entry 96).

### 3.5 What the build data warns us about
- **Power of the Family A top-3 tests on RCAEval is low.** Top-3 is near its ceiling (96–98%), so paired tests have only 0–6 informative pairs per corpus. If the pool behaves like the build data, several A-family top-3 hypotheses may be inconclusive, which is not the same as negative.
- **Some ablations add little on build data.** These are A-H1 (LLM), A-H4 (consensus), A-H6 (graph) and A-H8 (structural graph). The LLM adds little on OTel, and consensus shows no accuracy gain over plain Borda (component review CR-05 to CR-07). This is a finding for Chapter 5 either way.
- **Timing noise:** CpR and TTCD move with machine load, so confirmatory runs need the machine to themselves.
- **CR-03:** MAHC's "CONFIRMED" label is less reliable than "PROVISIONAL" on RCAEval (90% against 98% top-3). CpR reads this state, so it is being fixed **before** the confirmatory runs (section 5).

---

## 4. Progress indicators

Progress at this stage cannot be measured by confirmatory results: collecting results before the method is frozen would undermine them. It is measured instead by **delivery against plan**, **quality**, **integrity**, **reproducibility** and **readiness**, with the build-data readings as an early signal of direction. Every figure below can be checked in the repository.

### 4.1 Summary

| Area | Indicator | Value | Reading |
|---|---|---|---|
| Schedule | Working days, S1–S5: planned vs actual | 60 planned, 25 actual | Schedule performance index about 2.4 (above 1 means ahead of plan) |
| Schedule | Tracker tasks DONE | 176 of 190 | The other 14: 7 planned for later phases, 5 deferred (each with a signed deviation entry), 2 in progress |
| Scope | Planned scope delivered | All Tier 1 and all Tier 2 | Speed did not come from cutting; one item (Knowledge Cortex) moved to Stage B for integrity reasons (entry 82) |
| Quality | Merged pull requests through CI | 121 | Every change passed lint, strict typing, tests, ledger and capture checks |
| Quality | Automated tests / coverage | 1,835 tests / 96.8% | Above the 90% gate, and rising (96.6% at S4) |
| Integrity | Signed deviation entries | 105 | Every protocol change recorded and public before any confirmatory data |
| Integrity | Confirmatory pool data used | None | Only counts-only format checks; no label opened |
| Integrity | Public OSF records | 3 | Pre-registration, addendum 1, deposit 2 (frozen build and rubric) |
| Integrity | Defects caught before confirmatory runs | 4 | Baseline export, router reward (CR-01), D-pipe call edges (CR-02), pool status codes |
| Reproducibility | Fresh-clone replication | 7,254 of 7,254 runs identical | Before and after the CR fixes |
| Reproducibility | LLM nondeterminism | 8 of 57 prompts | Measured and reported; top-1 and top-3 set never change |
| Direction | HELIOS-Full vs baselines (build data) | Ahead of every baseline | OTel top-3 79% against 16–54% |
| Direction | Router cost effect (A-H5) | About 10× (OTel) and 40× (RCAEval) faster | Below threshold in every corpus |
| Direction | Improvement loop (CR-01, CR-02) | Top-1 up 4–7 points on RCAEval | No comparator got worse |
| Readiness | Pre-registered tests that compute | All except two, both expected | A-H7 waits for raters; TraceRCA on RCAEval has no traces (recorded in advance) |
| Readiness | Compute for phase E | About 5 h measured | Matches the earlier 5–6 h estimate; no rented compute needed |

### 4.2 Schedule by sprint

| Sprint | Planned working days | Actual days |
|---|---|---|
| S1 Data and graph | 15 | 4 |
| S2 Reasoning, consensus, narratives | 15 | 5 |
| S3 Routing and learning | 10 | 6 |
| S4 Product shell and evaluation tooling | 10 | 4 |
| S5 Integration and freeze | 10 | 6 |
| **Total** | **60** | **25** |

### 4.3 Why fast does not mean rushed

- **Quality went up, not down:** coverage rose between sprints, and no change bypassed CI.
- **Problems were found early and fixed openly:** four defects were caught and recorded before any confirmatory run, each with a deviation entry where the protocol was affected. Finding them before the evidence, not after, is the process working as designed.
- **The freeze is enforced by code:** only the tagged, frozen build can open the confirmatory pool, so speed in Stage B can never leak into the evidence.

### 4.4 In one sentence

> Progress is measured by delivery (about 2.4× faster than planned, nothing cut), integrity (every change signed and public before data, confirmatory pool untouched) and readiness (every test runs, replication is exact, compute confirmed). The build-data readings show the artefact is heading the right way; the confirmatory runs, starting next, are where it is tested.

---

## 5. Remaining work and days to finish

### 5.1 Stage A: evidence and results (the dissertation results)

| # | Work | Depends on | Days |
|---|---|---|---|
| 1 | **CR-03 fix:** design note, deviation entry, fix, new freeze record and tag `build-freeze-3` | Owner approval | 2–3 |
| 2 | **E1–E3 confirmatory, baseline and exploratory runs** on the 240-case pool: 1,920 Family A runs, 1,200 baseline runs and the exploratory variants (about 5 h compute, at most about 8.5 h), then scoring | Step 1; machine free | 2–3 |
| 3 | **E6 sensitivity:** cache-bypassed 10% rerun and delayed-label subset | Step 2 | 1–2 |
| 3b | Larger-model subset, only if L6 says so | L6 decision | 2–3 |
| 4 | **Family A and B analysis** (all hypotheses except A-H7), exactly as deposited | Step 2 | 5 |
| 5 | **Raters:** recruit two raters and an adjudicator, train to κ ≥ 0.7 on build data | Recruitment | 15–20 |
| 6 | **E5 rating (A-H7):** blind rating of 480 narratives (Full and noLLM) | Step 5 | 15–25 of rater time |
| 7 | **E4 user study (RQ4):** 24 participants, Full vs noExpl | IRB approval | 15–20 |
| 8 | **Phase A results package:** sensitivity analyses, exploratory estimates, figures, replication bundle | Steps 4, 6, 7 | 10 |

**How long to results.** There are two paths, and they run in parallel:
- **Compute path (steps 1–4):** about **10–15 working days** of my and Claude's time. This gives results for every hypothesis except A-H7 and RQ4.
- **People path (steps 5–7):** about **6–9 weeks**, set by the raters and the IRB, not by compute. If either is late, A-H7 or RQ4 is reported as incomplete, never dropped (entry 102).
- **Then the results package (step 8):** about **10 working days**.

Overall, the complete Stage A results need about **8–11 weeks of elapsed time**, most of it waiting on raters and the user study. That stays well within the committed deadline for results (31 March 2027).

### 5.2 Stage B: completing the full product (exploratory evaluation)

| Module | Contents | Working weeks |
|---|---|---|
| B1 Ingest and deployment | Live OTLP ingest, cognitive and business telemetry, Helm deployment, multi-tenant admin, router shadow go-live | 6 |
| B2 Privacy and robustness | Full Privacy Gateway (per-tenant differential privacy), adversarial robustness monitor, eBPF sampling | 4 |
| B3 Safe action | Digital twin with traffic mirroring, ASRE, remediation templates, live MTTR | 4 |
| B4 Self-healing and learning | Cognitive Sentinels, full IOL, HIS tiers, production learning loops with an accuracy guard, Knowledge Cortex | 4 |
| B5 Stage B evaluation | Tier-4 cognitive faults, E-H1/E-H4/E-H6/E-H9, scaling study, 70B contrast, AIOpsLab | 4 |

**How long to the full product:** about **22 working weeks** for Stage B, which can start alongside the Stage A evidence work. If the build pace so far continues (sprints finished in a third to half of their planned time), it may be shorter.

**Whole project:** Stage A results in about 8–11 weeks; the full product in about 22 weeks of Stage B work, overlapping with Stage A. Chapters 4–5 are written once the results are in, alongside Stage B.

---

## 6. Proposal: how to use the next two months

Being 11 weeks ahead means the next two months can turn into better evidence and a stronger dissertation.

| # | Proposal | Why it improves the work |
|---|---|---|
| 1 | **Fix CR-03, then run E1–E3 straight away** | Confirmatory evidence months ahead of plan; time to handle any surprise with a proper deviation entry |
| 2 | **Recruit and train raters now** | A-H7 (narrative factuality) is the one hypothesis that can slip; starting now protects it |
| 3 | **Submit the IRB application now** | RQ4 (user study) is the other people-dependent item; an early approval keeps it on schedule |
| 4 | **Decide the larger-model subset (L6) early.** `qwen3-coder:30b` runs locally at about 1.5× the 8B's worker time; the 70B in Ch3 would need rented compute | A model-size sensitivity result strengthens the generalisability argument |
| 5 | **Address the low power of the A-family top-3 tests by reporting, not by changing tests.** Pre-registered exploratory readings (top-1, Avg@5, effect sizes with BCa intervals) carry the story where top-3 is at its ceiling | Keeps the confirmatory protocol untouched while giving the chapters informative results |
| 6 | **Start Stage B module B1 in parallel** (live ingest, router shadow mode) on `main`, which is locked out of the pool by code | Brings the full-product finish forward and adds a production-readiness story |
| 7 | **Turn the open component-review items (CR-04 to CR-08) into Stage B variants** with their own pre-registration, evaluated on non-pool data | Converts build-data weaknesses (LLM gain on OTel, consensus vs Borda) into design-science iterations for Chapter 4 |
| 8 | **Draft the Chapter 4 method and artefact sections** from the sprint exit reports while raters work | The build–evaluate episodes and freeze-by-code are already documented; writing early reduces the load later |


---

**Sources in the repository:** sprint exit reports (`docs/sprints/s0-foundation/` to `s5-integration-freeze/exit_report.md`); pilot and refresh (`docs/sprints/s5-integration-freeze/s5_3_pilot.md`, `s5_3_pilot_refresh.md`); replication (`s5_4_replication.md`, `s5_4_replication_rerun.md`); the component review backlog in the same folder; phase E plan and day-one checks (`docs/sprints/e-evidence/`); end-to-end plan (`docs/tracking/helios_e2e_product_plan_2026-10.md`).
