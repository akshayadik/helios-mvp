# S5.3 Exploratory pilot on build data · report

**Row:** S2-M10-EVAL03 · **Design:** [s5_3_pilot_design.md](s5_3_pilot_design.md) (approved 2026-11-15; Q-a to Q-h owner-approved, Q-a exclusion rule by owner decision) · **Deviation entry:** 91 · **Date:** 2026-11-16 · **Label:** exploratory build data. HELIOS was built and calibrated on these cases, so every HELIOS number here is optimistic, and nothing here is a result.

**Outcome: done, with three defects recorded (§3) and one open item (§3.4).**
- **Baseline phases:** 5,580 runs scheduled in the four S5.1 directories; 4,568 passed, 1,012 excluded with stated reasons. 990 of the exclusions are TraceRCA on RCAEval, which has no traces (`modality_absent`, entry 91).
- **Scoring:** all four directories are scored with the determinism join (Q-d). Every pre-registered test computes except A-H7 (H_fact waits for the raters) and, on RCAEval, B-H2 (TraceRCA has no runs).
- **Compute (L5):** phase E on a cold cache projects to about 5 h for 240 pool cases (HELIOS E1 + E3 about 2.5 h, baselines E2 about 2.5 h). That is within the D11 recheck of 5–6 h, so local hardware is enough.
- **Larger models (L6):** on 20 build worker prompts, `qwen3-coder:30b` answers in 9.6 s median against 6.2 s for the 8B, and its answers pass the worker parser 20 of 20 times. The 14B and 24B models are slower than the 30B.
- **Judge budget (L7):** each narrating variant writes one model narrative per case, about 650–900 prompt tokens and 40–50 completion tokens.

## 1. What ran

- **Code:** branch `s5/pilot`, export `rcaeval-export-v2` and the required-modality rule (d5c6de1, 6d8882c, entry 91); `llama3.1:8b` for HELIOS (entry 58 digest).
- **Baseline phases (Q-b):** `bin/helios_campaign.py run --phase baseline` and `--phase baseline_trigger`, then `compare`, in each directory. The run was paused twice for other work on this machine and resumed. The campaign tool skips finished runs and re-runs the run that was cut off, so no run was lost or counted twice.
- **Machine load:** another project's job ran alongside for most of the RCAEval parts 2 and 3 and for the L6 timing. Rankings are unaffected. Wall times from those parts may be slightly long, which makes the compute projection (§5) conservative.

| Directory | Cases | Binding time | Trigger time | Exclusions |
|---|---|---|---|---|
| `otel_build_v3` | 63 | 315 passed | 302 passed, 13 excluded | 13 Multi-source BARO `baseline_error` (§3.1) |
| `rcaeval_build_1` | 165 | 660 passed, 165 excluded | 660 passed, 165 excluded | 330 TraceRCA `modality_absent` |
| `rcaeval_build_2` | 165 | 657 passed, 168 excluded | 657 passed, 168 excluded | 330 TraceRCA; 6 `baseline_error` on one case (§3.2) |
| `rcaeval_build_3` | 165 | 657 passed, 168 excluded | 660 passed, 165 excluded | 330 TraceRCA; 3 `baseline_error` on one case (§3.3) |

Then, per directory (Q-c, Q-d):
1. `bin/score_runs.py --metrics --determinism <dir>/determinism.json` against the signed build ground truth;
2. `bin/helios_campaign.py cells`;
3. `bin/analyse.py --campaign`;
4. `bin/pilot_compute.py` (Q-e 2) and `bin/pilot_metrics.py` (per-system readings, L7).

The RCAEval parts are scored and analysed separately (Q-c). No test is rerun on pooled data.

## 2. Files

`pilot/` holds one JSON per directory for each reading:
- `analysis_<dir>.json`: the analysis output (tests, cells, sanity floors), labelled exploratory by the analysis guard;
- `metrics_<dir>.json`: per system HR@1, HR@3, CpR, TTT, time to narrative and the determinism covariate, plus L7 narrative counts and tokens;
- `compute_<dir>.json` and `compute_pooled.json`: the cold-cache campaign compute (Q-e 2);
- `l6_model_timing.json`: the L6 timing, per model and per prompt.

## 3. Defects found

### 3.1 Multi-source BARO at trigger time, OTel (13 runs)

All 13 fail inside the container with `IndexError: single positional indexer is out-of-bounds`. The other four baselines pass on the same cases, and Multi-source BARO passes on all 63 at binding time.
- **Cause, from the data:** the trigger falls late in the capture. On the 13 failing cases it is 30–105 s before the window ends; on the 50 passing cases it is mostly 135 s or more (one passes at 15 s). Multi-source BARO splits every modality's series at the anomaly time, and with so little time after it, a log or trace series has no rows there.
- **Effect:** the Multi-source BARO trigger-time cell is 50 of 63 (79%), below the 80% cell rule. Trigger time is a sensitivity reading (entry 88, item 9), so no binding test changes.
- **No code changed.** Any fix (a minimum post-anomaly span, or a longer window) would change a recorded input rule, so it needs its own decision and deviation entry before the freeze. Whether pool captures have late triggers is not read before build-freeze.

### 3.2 A 62-second RCAEval capture (`rcaeval_build_2`, case `9a8e3cfb`)

The capture window is 62 s long. Multi-source BARO, BARO and Multi-source RCD fail with the same `IndexError` at both binding and trigger time; PDiagnose passes. This affects one case in 495, so no cell is near the rule.

### 3.3 An injection time at one hundredth of its value (`rcaeval_build_3`, case `c80ff7d1`)

The binding-time anomaly time passed to the baselines is 16,933,142 s. The trigger time for the same case is 1,693,314,223 s (2023-08-29 12:57 UTC), so the injection time has lost its last two digits. At binding time, Multi-source BARO, BARO and Multi-source RCD fail with the same `IndexError`; PDiagnose ranks anyway.
- **Effect:** three exclusions; no cell is near the rule.
- **Source:** the recorded injection time of this build case. It is build data, so the label stays as signed (OSF deposit 1).

### 3.4 Open: three passed trigger-time runs with no metrics (case `c80ff7d1`)

On the same case, BARO, Multi-source BARO and Multi-source RCD pass at trigger time and store rankings, but scoring writes no HR@3 or other metric for them. That gives 18 `metric_missing` exclusions, one per metric, written by `cells`. PDiagnose's trigger-time run on the case is scored. The likely link is the injection time in §3.3, which the scorer also uses, but the cause is not confirmed. It is listed for S5.4, before the freeze.

## 4. Cells and tests (build reading)

### 4.1 Cells below the 80% rule

- **H_fact, every system and app:** not scored until the two raters have rated (S4 rater protocol). A-H7 is therefore untestable everywhere.
- **TraceRCA, every metric on RCAEval:** no runs (entry 91). B-H2 is therefore untestable on RCAEval, as entry 91 anticipated. On OTel, TraceRCA runs and B-H2 computes.
- **Multi-source BARO at trigger time on OTel:** 50 of 63 (§3.1).

No other cell fails. MCAR and IPW report complete data for every computed test, except in RCAEval parts 2 and 3. There, the one §3 case leaves one pair missing from the B tests, and the missing-data check reports that descriptively (fewer than 10 missing pairs).

### 4.2 Pre-registered tests

The table gives p-values by directory, and in brackets the means of the two compared systems (HR@3, Avg@5 or log-CpR). ✓ means below its Holm threshold in that directory. The guard labels every directory exploratory: build corpus, no `build-freeze` tag, and exploratory variants in the same store.

| Test | Comparison | OTel v3 (63) | RCAEval 1 (165) | RCAEval 2 (165) | RCAEval 3 (165) |
|---|---|---|---|---|---|
| A-H1 | Full vs noLLM, HR@3 | .125 (.79/.75) | .031 (.96/.93) | .5 (.97/.96) | .063 (.96/.94) |
| A-H2 | Full vs LLM-only, HR@3 | .105 (.79/.70) | .98 (.96/.99) | 1 (.97/.98) | .109 (.96/.94) |
| A-H3 | Full vs D, HR@3 | .31 (.79/.76) | .031 (.96/.93) | .5 (.97/.96) | .063 (.96/.94) |
| A-H4 | Full vs noConsensus, HR@3 (disagreement stratum) | .75, n 39 | 1, n 22 | 1, n 19 | 1, n 28 |
| A-H5 | noRouter vs Full, log-CpR | ✓ 1.3e-5 (9.6/8.2) | ✓ 7e-14 (7.4/5.3) | ✓ 2e-13 (7.2/5.1) | ✓ 8e-20 (7.3/5.0) |
| A-H6 | Full vs G, HR@3 (stratum) | .31, n 43 | 1, n 25 | 1, n 19 | 1, n 16 |
| A-H7 | Full vs noLLM, H_fact and H_struct | untestable | untestable | untestable | untestable |
| A-H8 | Full vs noStructural, HR@3 | .88 (.79/.81) | 1 (.96/.96) | 1 (.97/.97) | 1 (.96/.96) |
| B-H1 | Full vs Multi-source BARO, HR@3 | ✓ 2.4e-4 (.79/.54) | ✓ .0038 (.96/.90) | .055 (.98/.95) | ✓ .011 (.96/.92) |
| B-H2 | Full vs TraceRCA, HR@3 | ✓ 1.5e-11 (.79/.24) | untestable | untestable | untestable |
| B-H3 | Full vs BARO, HR@3 | ✓ 9.7e-9 (.79/.30) | ✓ .011 (.96/.91) | .019 (.98/.93) | ✓ .019 (.96/.92) |
| B-H4 | Full vs PDiagnose, HR@3 | ✓ 7e-7 (.79/.38) | ✓ .0036 (.96/.89) | ✓ 7e-9 (.97/.81) | ✓ 1.6e-4 (.96/.86) |
| B-H5 | Full vs Multi-source RCD, HR@3 | ✓ 5e-12 (.79/.16) | ✓ 1e-27 (.96/.40) | ✓ 2e-24 (.98/.48) | ✓ 9e-27 (.96/.37) |
| B-H6 | best baseline vs Full, log TTCD | .055 | ✓ 7e-17 | ✓ 4e-22 | ✓ 3e-17 |
| B-H7 | best baseline vs Full, log-CpR | .038 (9.0/8.2) | ✓ 2e-16 (8.2/5.5) | ✓ 4e-21 (8.0/5.1) | ✓ 4e-16 (7.7/4.9) |
| B-H8 | Full vs best baseline, Avg@5 | ✓ .0019 (.71/.57) | ✓ 3e-8 (.93/.84) | ✓ 2e-9 (.95/.85) | ✓ 2e-8 (.95/.86) |

Best baseline: Multi-source BARO on OTel and RCAEval 2; BARO on RCAEval 1 and 3.

What the build reading shows about the design, not about HELIOS:
- **HR@3 is near its ceiling on RCAEval build.** Full reaches .96–.98, D and noLLM .93–.96, and the prior-only floor is .60. Paired HR@3 tests have 0–6 informative pairs per directory, so the A-family HR@3 tests can barely separate variants on this corpus. The pool is not read before the freeze. If its cases behave like these, the A-family HR@3 tests will have little power there too. This is a question for the chair call, not a change.
- **Strata are small:** A-H4 has 19–39 pairs and A-H6 has 16–43 per directory.
- **OTel CpR is bimodal.** A run that never ranks the culprit first is censored at the 1,800 s TTCD cap, and its opportunity cost then dominates CpR. Most OTel runs are censored (895 of 1,436), so median CpR sits either at the cap (about 168,000) or far below it (Full 1,201). log-CpR and the Wilcoxon tests handle this; medians in tables should be read with it in mind.

## 5. Cost and timing

### 5.1 Per run (Q-e 1; replayed call times, as phase E will)

Median per run, from `metrics_<dir>.json`:

| System | OTel CpR | OTel TTT | RCAEval 1 CpR | RCAEval 1 TTT | Time to narrative (OTel, RCAEval 1) |
|---|---|---|---|---|---|
| HELIOS-Full | 1,201 | 1.43 s | 39.9 | 0.23 s | 1.45 s, 1.10 s |
| HELIOS-noRouter | 168,000 | 15.6 s | 913 | 9.2 s | 1.45 s, 1.13 s |
| HELIOS-LLM-only | 168,000 | 15.3 s | 923 | 9.2 s | 0.79 s, 0.40 s |
| HELIOS-noLLM | 168,000 | 1.35 s | 40.5 | 0.24 s | template |
| Multi-source BARO | 168,016 | 1.11 s | 115 | 1.01 s | none |
| PDiagnose | 168,016 | 0.35 s | 26.3 | 0.10 s | none |
| Multi-source RCD | 168,016 | 1.39 s | 168,016 | 6.1 s | none |

The router's effect shows directly: Full's TTT is about a tenth of noRouter's on OTel and about a fortieth on RCAEval, because cheap-first routing skips the model calls when the cheaper pipes agree.

### 5.2 Campaign compute on a cold cache (Q-e 2, L5)

`bin/pilot_compute.py` takes each rerun case: the noRouter rerun's wall time (every worker call live), plus each other variant's rerun minus its live worker time (cache hits in phase E), plus the first-run time of D, G and noLLM, plus both baseline phases.

| Reading | Cases | HELIOS s/case (median, mean, p90) | Baselines s/case (median, mean, p90) |
|---|---|---|---|
| OTel v3 | 6 | 58.5, 57.7, 60.3 | 29.4, 29.1, 30.8 |
| RCAEval 1 | 15 | 46.6, 46.9, 73.6 | 57.6, 52.6, 78.9 |
| RCAEval 2 | 16 | 31.9, 33.0, 49.1 | 33.8, 36.5, 68.1 |
| RCAEval 3 | 15 | 21.1, 26.5, 47.4 | 18.0, 27.6, 54.2 |
| **Pooled** | **52** | **33.0, 38.0, 58.6** | **30.5, 37.7, 68.1** |

**Projection to 240 pool cases** (mean × cases is the expected total; p90 bounds a slow pool):
- HELIOS E1 + E3: **2.5 h** (p90 3.9 h);
- baselines E2: **2.5 h** (p90 4.5 h);
- together: **about 5 h, at most about 8.5 h**, against the D11 recheck of 5–6 h central.

**L5 reading:** phase E fits on this machine in one working day, and the 8B campaign does not need rented compute. Part of the spread between the RCAEval parts may come from the shared machine (§1).

### 5.3 Larger models (L6)

`bin/pilot_model_timing.py`: 20 worker prompts (10 OTel, 10 RCAEval part 1; metric, log and trace workers), each rebuilt from stored evidence. All 20 match their S5.1 cache keys byte for byte, so they are exactly the prompts the 8B answered. One warm-up call per model is excluded. Protocol A decoding throughout. Parser acceptance follows `workers.run_worker`: the answer parses, keeps its allowed values and ranks at least one candidate with a valid citation.

| Model | Load + first call | Wall per call (median, p90) | Completion tok/s (compute) | Accepted |
|---|---|---|---|---|
| `llama3.1:8b` (confirmatory) | 8.4 s | 6.2 s, 8.9 s | 48 | 20 of 20 |
| `qwen2.5-coder:14b` | 20.7 s | 17.0 s, 21.4 s | 26 | 19 of 20 |
| `devstral:24b` | 29.3 s | 17.8 s, 31.3 s | 14 | 20 of 20 |
| `qwen3-coder:30b` | 13.9 s | 9.6 s, 12.9 s | 77 | 20 of 20 |

**L6 reading:** `qwen3-coder:30b` is a mixture-of-experts model, so it generates faster than the 8B even though its answers are longer. A 30B subset would cost about 1.5× the 8B's worker time. Nothing here is scored. Choosing a model other than the 70B named in Ch3 and D11 (RB2, E6) is a protocol change: it needs its own decision and a deviation entry before phase E (design Q-f).

### 5.4 Judge budget (L7)

Per narrating variant, from `metrics_<dir>.json`: one model narrative per case. D, G and noLLM fill the template instead, and noExpl writes none.

| Corpus | Narratives per variant | Prompt tokens (median) | Completion tokens (median) | Tokens per narrative (p90) |
|---|---|---|---|---|
| OTel v3 | 63 | 876 | 48 | 1,077 |
| RCAEval 1 | 165 | 625 | 40 | 877 |
| LLM-only, both | 63 / 165 | 237–268 | 16–20 | 557–609 |

**L7 reading:** a judge reads one narrative of about a thousand tokens or fewer, plus its evidence. On the pool, that is 240 narratives per narrating variant to judge, per judge model.

## 6. Determinism covariate (Q-d)

`score_runs --determinism` marked every run that has a rerun pair. In every directory, each nondeterministic pair is a HELIOS pair.

| Directory | Pairs marked | Nondeterministic |
|---|---|---|
| OTel v3 | 90 (60 HELIOS, 30 baseline) | none |
| RCAEval 1 | 150 | 21 |
| RCAEval 2 | 160 | 12 |
| RCAEval 3 | 150 | 21 |

- **Baseline determinism (OTel):** all 30 baseline pairs are identical. That agrees with S4.8 (deterministic or seeded methods).
- **RCAEval baseline reruns:** the 230 that S5.5 excluded under export v1 stay excluded as the record (design Q-b).

## 7. Records

- **Q-g (S5.5 determinism reading), as recommended in the design:** keep the D11 covariate (§6). The frozen response cache, not the model, makes phase E runs repeatable, so the cache goes into the OSF deposit with the freeze record (S5.6). No deviation entry. The owner confirms this position in the PR review.
- **Q-h (seed register):** the register's 7,200 slots cover the 240-case phase E schedule. Only build pilots larger than the pool hit the limit, which is why RCAEval build ran as three parts of 165 (S5.1). Nothing changes.
- **Baseline fix:** export v2 and the required-modality rule (entry 91) worked as recorded. The four baselines that can run without traces return rankings on RCAEval, and TraceRCA is excluded before its container starts.

## 8. For the owner

- **L5:** local compute is enough for phase E (§5.2).
- **L6:** if a larger-model subset is wanted, `qwen3-coder:30b` is the practical local option (§5.3). Choosing it needs a decision and a deviation entry.
- **L7:** the judge budget is in §5.4.
- **§3.1:** the late trigger behind the Multi-source BARO failures is a pool risk for the trigger-time sensitivity reading only. Decide whether to fix it before the freeze; a fix needs a deviation entry.
- **§4.2:** HR@3 is near its ceiling on RCAEval build, which limits the A-family HR@3 tests' power. Worth raising on the chair call.
