# S5.5 LLM determinism probe · report

**Row:** S2-M10-EVAL05 · **Design:** [s5_5_determinism_design.md](s5_5_determinism_design.md) (approved 2026-11-15) · **Date:** 2026-11-15 · **Label:** exploratory build data. No hypothesis is tested; nothing here is a result.

**Outcome: measured.**
- **Model calls:** greedy decoding is not fully deterministic on this model server. On RCAEval build, 8 of 57 distinct metric-worker prompts got a different answer when asked again; on OTel v3, none of 17 did.
- **Fused rankings:** one RCAEval case changed for 9 variants. In every changed pair the top-1 and the top-3 set stayed the same.
- **Prompts:** no prompt differed between a run and its rerun.
- **Baselines (separate finding):** every RCAEval baseline rerun failed on a defect in the baseline export. It needs a decision before S5.3 (§5).

## 1. What ran

- **Rerun phase:** `bin/helios_campaign.py run --phase rerun`, then `compare`, in the four S5.1 directories. These are the rerun specs already in the S5.1 schedules: every 10th case, with the response cache bypassed and a separate rerun store.
- **Code and model:** branch `s5/determinism` (2a04c84); `llama3.1:8b`, the entry 58 digest; Protocol A: temperature at zero, top-k 1, seed 42, one request at a time.
- **Per-call counts:** `bin/determinism_report.py` (P-d). Two prompts are the same when the persona template hash, the candidate list and the worker's digest are all equal, because those three make up the rendered prompt (`personas.render_prompt`). The template hash alone is the same for every case, so it is not enough.

| Directory | Rerun cases | HELIOS reruns | Baseline reruns | Wall time |
|---|---|---|---|---|
| `otel_build_v3` | 6 | 60 passed | 30 passed | 1,210 s |
| `rcaeval_build_1` | 15 | 150 passed | 75 excluded (§5) | 1,372 s |
| `rcaeval_build_2` | 16 | 160 passed | 80 excluded (§5) | 879 s |
| `rcaeval_build_3` | 15 | 150 passed | 75 excluded (§5) | 865 s |

## 2. Token equality (the done-when)

Only calls that produced output on both sides, under the same rendered prompt, are compared.

| Corpus | Distinct prompts compared | Prompts with a different answer | Calls compared | Calls identical | Token-equality rate (calls) |
|---|---|---|---|---|---|
| OTel v3 | 17 | 0 | 170 | 170 | all |
| RCAEval build | 57 | 8 | 234 | 181 | 77.4% |
| **Both** | 74 | 8 | 404 | 351 | 86.9% |

**Readings:**
- **Different prompts:** none, in either corpus. Wherever outputs differ, the prompt was the same, so the pipeline upstream of the model is deterministic.
- **Where differences occur:** only in the metric worker. Log and trace calls were identical wherever they ran.
- **Same session, two answers.** In 3 of the 8 prompts, the reruns themselves disagree: for example, 9 variants got one answer and 1 got another, all in the same session. So the variation is run to run, not just between the session that filled the cache and today's.
  - Requests are sent one at a time, and decoding is greedy with a fixed seed. The likely source is numerical: the GPU kernels, or the server reusing a cached prompt prefix. This is not established.
- **Why the call rate is lower than the prompt rate.** One prompt is asked by up to 10 variants, so a prompt with a different answer counts up to 10 times among calls. The prompt-level figure is 66 of 74 prompts identical.

## 3. Run level (`determinism.json`, the S5.3 covariate)

| Corpus | Pairs | Not equal | Fused list differs | L-pipe evidence differs | Narrative differs | Narrative not comparable |
|---|---|---|---|---|---|---|
| OTel v3 | 60 | 0 | 0 | 0 | 0 | 0 |
| RCAEval 1 | 150 | 21 | 0 | 21 | 0 | 0 |
| RCAEval 2 | 160 | 12 | 0 | 11 | 1 | 0 |
| RCAEval 3 | 150 | 21 | 9 | 21 | 1 | 0 |
| **Total** | 520 | 54 | 9 | 53 | 2 | 0 |

**Readings:**
- **No narrative was "not comparable".** With live first runs, every slot had a model answer, which fixes the S4.10 trial's 17 such pairs.
- **The 9 fused differences are one case** in `rcaeval_build_3`: Full, LLM-only, noConsensus, noStructural, noACP, noReconcile, noFGSV, noIOL and noExpl. The rerun's metric answer was much shorter (960 characters against 1,700).
  - In all 9 pairs, top-1 and the top-3 set are unchanged. In LLM-only, the order within the top 3 changes; in the others, only lower ranks or scores move.
  - noRouter's rerun on that case got the original answer, so its pair is equal.
- **Other non-equal pairs:** in the remaining 45, the L-pipe evidence or the narrative changed without changing the fused list.

## 4. What this means for phase E (P-e)

**Within one campaign, variants are not affected.**
- In a phase E case, the first variant (noRouter) fills the response cache, and every later variant replays the same answers (S4.10).
- So two variants are never compared on different model answers for the same prompt. The paired confirmatory tests compare variants on the same answers.

**What is affected is reproducibility.**
- A fresh run of the same spec without the cache can give a different L-pipe answer: here for 8 of 74 prompts.
- Rarely, that changes the fused list (1 case of 52), but not, in this sample, top-1 or the top-3 set.
- D11 §4 already plans for this: any non-equal rerun is recorded as a covariate. S5.3 joins `determinism.json` into `eval_run` as designed. No protocol change follows from this measurement.

**For you, before S5.3.** P-e asks me to bring the fused differences to you.
- **What I recommend:** keep the D11 covariate as planned. Record in the S5.3 pilot that the cache, not the model, is what makes the phase E runs repeatable: the frozen cache is the reproducibility record, and the OSF deposit should carry it. This needs no deviation entry.
- **Optional, for Stage B or before the freeze if you want it:** test whether turning off the server's prompt-prefix reuse makes the 8 prompts repeatable. That would change the server configuration, which is part of the freeze record (S5.6).

## 5. Separate finding: baselines fail on RCAEval-format captures

All 230 RCAEval baseline reruns, five baselines on 46 cases, were excluded with `baseline_error: EmptyDataError: No columns to parse from file`. The OTel baseline reruns passed.

**Cause:**
- `helios/baselines/export.py` writes `traces.csv` and `logs.csv` with no columns at all when a capture has no traces or logs. RCAEval build captures have none.
- The baseline containers then fail to parse the empty file.
- The S4.8 check on RCAEval ran BARO on RCAEval's own files, not on this export, so the campaign path was never run on RCAEval captures.

**Why it matters:** this is not a determinism result, but it blocks S5.3's baseline phase on RCAEval, and phase E's baselines on any capture without traces or logs.

**What I propose for S5.3's design, not done here:**
- the export writes header-only files;
- a baseline that needs a modality the capture lacks (TraceRCA without traces) is excluded with a stated reason, not an error;
- the RCAEval baseline phase runs only after that fix, with its own test.

The 230 excluded rerun specs stay in the ledgers of these directories as a record. The S5.3 design says how the baseline reruns are redone (S5.1 S-e: a new directory, or a resumed phase after the fix).

## 6. Files

- **Per-corpus reports:** `determinism/{otel_build_v3,rcaeval_build_1,rcaeval_build_2,rcaeval_build_3}.json`. Each has per-call counts per variant, run-level counts per system, and every pair whose calls were not all equal.
- **In the campaign directories (gitignored):** `determinism.json`, `rerun.duckdb`, and `coe/rerun.*`.
- **Code:** `bin/determinism_report.py` and `tests/test_determinism_report.py`.
