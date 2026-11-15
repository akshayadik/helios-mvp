# S5.3 Exploratory pilot on build data · design

**Row:** S2-M10-EVAL03 · **Status:** approved by the owner 2026-11-15 (Q-a to Q-h; Q-f changed, see below) · **Plan:** [plan.md](plan.md) step 4 · **Inputs:** S5.1 campaigns ([report](s5_1_system_test.md)), S5.5 determinism ([report](s5_5_determinism.md))

## 1. What the pilot has to show

Done-when (breakdown): "pilot report labelled exploratory; metrics, cost and timing all populated". The pilot runs the whole phase E path on build data, from campaign to analysis, so that:
- every metric, cost and timing column the confirmatory analysis reads is filled on real runs;
- the numbers for your decisions L5 (compute), L6 (70B subset) and L7 (judge models) exist;
- the S5.5 determinism rows are joined into `eval_run` as the D11 covariate.

The pilot is exploratory build data. Its hypothesis tests are a build reading of the pipeline, never a result, and the pool stays locked.

## 2. Starting point

- **Four S5.1 campaign directories** (`data/campaigns/s5_1/`): OTel v3 (63 cases) and RCAEval build in three parts of 165. They hold:
  - every HELIOS confirmatory and exploratory run (7,254, no exclusions);
  - the HELIOS determinism reruns and `determinism.json` (S5.5);
  - no baseline runs yet.
- **Tools that exist:**
  - `bin/score_runs.py --metrics` (eval_score, then eval_run: TTT, TTCD, CpR, H_struct, the ambiguous stratum);
  - `bin/helios_campaign.py cells` (the cell rule, MCAR and IPW);
  - `bin/analyse.py --campaign` (the pre-registered tests, Holm);
  - the cost model and price book (`helios/evaluation/cost.py`).
- **Two open items from S5.5:**
  - the baseline export defect on captures without traces or logs;
  - your decision on the determinism reading.

## 3. Decisions (Q-a to Q-h)

**Q-a Fix the baseline export first (defect, S5.1 S-e).** `helios/baselines/export.py` writes `traces.csv` and `logs.csv` with no columns when a capture has none, and every baseline container fails to parse them (S5.5 §5).
- The fix writes the RCAEval column headers with no rows.
- A new test runs the export on a trace-less RCAEval build window and checks every file.
- A container check runs each of the five baselines on one RCAEval build case.

If a baseline still cannot run without a modality, for example TraceRCA without traces:
- it is not left to fail;
- a declared table (baseline → modalities it needs) excludes it before the container starts, with the reason `modality_absent:<modality>`.

The header fix alone is a bug fix and needs no entry. The table, if it is needed, changes how B-family runs are excluded on the pool, so it gets a deviation entry first, with your approval of the text.

**Q-b Baseline runs.** Run `--phase baseline` and `--phase baseline_trigger` in the four directories: 5,580 runs (630 OTel, 4,950 RCAEval). At about 3 s per run (the S5.5 OTel reruns: 1.9–3.0 s), this is about 4–5 h.
- The 230 RCAEval baseline rerun specs that S5.5 excluded stay excluded as the record.
- Baseline determinism is then read from the 30 OTel baseline pairs, after `compare` reruns once the baseline phase exists.

*Alternative:* rerun all of RCAEval in new directories so the baseline reruns can be redone. That is about 3 h more for 230 runs of methods that S4.8 found deterministic or seeded. I don't recommend it.

**Q-c Scoring and analysis.** Per directory:
1. `score_runs --metrics` against the signed build ground truth (`build` or `otel_build_v3`);
2. `cells`;
3. `analyse --campaign`.

The RCAEval parts are scored separately, and the report pools them by summing counts. No test is rerun on pooled data, because three directories are not one campaign. The analysis output is a build reading: which tests compute, which cells pass the cell rule, and where a test cannot be computed and why.

**Q-d Determinism join (S4.10 left this to the pilot).**
- `eval_run` gains one nullable column, `nondeterministic`: true or false for a run that has a rerun pair, NULL for the rest.
- `score_runs --metrics --determinism <dir>/determinism.json` fills it, and a test covers it.
- No metric definition changes, so the metric contract is untouched.

**Q-e Cost and timing.** Two readings, kept apart:
1. **Per run (the metrics):** CpR and its five parts, TTT, TTCD and time to narrative from `eval_run`, by variant and corpus. These replay the cached call times, as phase E will.
2. **Campaign compute (for L5):** what phase E costs on a cold cache. The S5.1 first runs were mostly cache hits, so their wall times understate it. The S5.5 reruns are live, and each run records per-call wall times. So, per case:
   - **worker calls once:** the noRouter rerun's worker times, since the cache shares them across variants;
   - **plus narrator calls per variant:** from the reruns' narrative wall times;
   - **plus the non-model work.**
   
   Scaled to 240 pool cases, this gives E1 + E3 hours, set against the D11 recheck (5–6 h central). Baselines are added from Q-b's measured times.

**Q-f L6 and L7.**
- **L6 (70B subset).** No 70B model is on this machine. If you want a local option measured, pull `llama3.1:70b` (4-bit, about 40 GB). I would then time it on 20 worker prompts taken from the build cache: speed only, never scored or used in any analysis. Otherwise the report gives the subset's token counts, so a rented-GPU price can be put on them.
- **L6 as approved (owner, 2026-11-15).** No 70B pull. The pilot times the larger models already on this machine against the 8B: `qwen2.5-coder:14b`, `devstral:24b` and `qwen3-coder:30b`, on the same 20 worker prompts. It reports speed, and whether each model returns output the worker parser accepts. Nothing is scored or analysed. Ch3 and D11 name a 70B subset (RB2, E6), so choosing a smaller model for that subset is a protocol change: it gets its own decision and a deviation entry before phase E, not here.
- **L7 (judge models).** The report gives narrative counts and tokens per narrative, from the pilot's Full and noLLM runs, so a judge budget can be set. It does not call any judge.

**Q-g Determinism reading (the S5.5 decision).** Recommended:
- keep the D11 covariate as planned (Q-d);
- record that the frozen response cache, not the model, makes phase E runs repeatable, so the cache goes into the OSF deposit with the freeze record (S5.6).

No deviation entry. *Alternative:* test a server setting such as prefix reuse before the freeze. That would change the server configuration recorded at the freeze.

**Q-h Seed register (S5.1 finding).** The register's 7,200 slots cover phase E (240 cases), and only build pilots larger than the pool hit the limit. Recommended: record it in the pilot report and change nothing. *Alternative:* widen the register before the freeze, with a deviation entry.

## 4. Report

`docs/sprints/s5-integration-freeze/s5_3_pilot.md`, with a JSON per directory, labelled exploratory build data. It contains:
- **Metrics:** HR@3, AC@1 and the S4.9 suite per variant, baseline and corpus.
- **Cells:** the cell rule, MCAR and IPW result.
- **Tests:** the build reading of every pre-registered test.
- **Cost and timing:** per-run (Q-e 1) and campaign compute with the phase E projection (Q-e 2).
- **Covariate:** the determinism covariate counts.
- **L5–L7:** the numbers for each decision.
- **Records:** the seed-register note and the baseline fix.

## 5. Order and compute

| Step | Runs | Estimate |
|---|---|---|
| Q-a export fix, tests, container check | — | Half a day |
| Q-b baseline phases, four directories | 5,580 | 4–5 h, background |
| `compare` again (baseline pairs, OTel) | — | Minutes |
| Q-c and Q-d scoring, cells, analysis | — | Under an hour |
| Q-e and Q-f readings, report | — | Half a day |

The pre-push gate runs after the baseline phases, so it does not disturb their timings.

## 6. Done-when, files, deviation entry

- **Done when:** the baseline phases are complete (or excluded with stated reasons) in all four directories; every directory is scored with the determinism join; the report has metrics, cost and timing populated; the full gate is green.
- **Files:**
  - updated: `helios/baselines/export.py`, `helios/store/schema.sql` (one nullable column), `bin/score_runs.py`, and their tests;
  - new: the report and its JSON;
  - only if Q-a needs it: the modality table in `helios/baselines/`.
- **Deviation entry:** none for the header fix, the join or the report. One only if Q-a needs the modality table, with your approval of the text first.
- **Effort:** 2 days plus about 5 h of compute, as planned.
