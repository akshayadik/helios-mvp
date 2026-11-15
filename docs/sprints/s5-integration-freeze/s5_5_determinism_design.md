# S5.5 LLM determinism probe · design

**Row:** S2-M10-EVAL05 · **Status:** approved by the owner 2026-11-15 (P-a to P-e as written) · **Plan:** [plan.md](plan.md) step 3 · **Feeds:** S5.3 pilot (the `determinism.json` join)

## 1. What the probe has to show

Done-when (breakdown): "token-equality rate measured on repeated prompts". D11 §4 says the L-pipe uses greedy decoding, so it should be deterministic in principle. A 10% rerun measures whether token sequences are actually equal, and any non-equal rerun is recorded as a covariate. S5.5 measures that rate on build data before the freeze, with the phase E machinery, so that the number and the covariate are both known before the pool runs.

It is a measurement, not a test. No threshold is pre-registered, and no hypothesis is read.

## 2. Starting point

- **Rerun phase (S4.10, design O-g).** The schedule already holds rerun specs: every 10th case of each system, for every HELIOS variant that calls the model, and for the baselines. A rerun bypasses the response cache and writes to its own store (`rerun.duckdb`, `coe/rerun.*`), so the analysis never sees two runs of one spec.
  - `bin/helios_campaign.py compare` writes `determinism.json`: one row per pair, with `nondeterministic` and which parts differ (fused list, L-pipe evidence, narrative).
- **S4.10 trial (2026-11-13).** 48 pairs on OTel v3 were all equal where comparable. 17 narratives were not comparable, because the cache-only first run had no model answer for some slots.
- **S5.1 campaigns.** The four directories in `data/campaigns/s5_1/` hold the first runs: live model, cache in front, no exclusions. Their schedules already list the rerun specs:

| Directory | Rerun cases | HELIOS rerun specs | Baseline rerun specs |
|---|---|---|---|
| `otel_build_v3` | 6 | 60 | 30 |
| `rcaeval_build_1` | 15 | 150 | 75 |
| `rcaeval_build_2` | 16 | 160 | 80 |
| `rcaeval_build_3` | 15 | 150 | 75 |
| **Total** | 52 | 520 | 260 |

- **What a run records.** Each L-pipe worker (log, metric, trace) stores its prompt hash (`prompt_shas`) and its raw model output (`raw`). The narrative stores its rendered text and, per slot, whether a model answer was used. So a per-call comparison needs no new instrumentation.

## 3. Decisions (P-a to P-e)

**P-a Where.** Run the existing rerun phase in the four S5.1 directories: `run --phase rerun`, then `compare`. There is no new campaign and no new seeds, and the first runs are already there. The pool stays locked.

*Alternative:* a standalone loop that sends the same prompts N times in a row. It isolates the model server, but it is not the phase E path and it would not produce the `determinism.json` that S5.3 joins. I don't recommend it as the main measure. P-c gets the server-level number from the same runs.

**P-b What runs.** All 780 rerun specs, HELIOS and baselines, with no code change to the campaign tool.
- The 520 HELIOS reruns are compared now.
- The 260 baseline reruns have no first run yet, because S5.3 adds the baseline phase. `compare` already skips any pair without two passed runs, so S5.3 reruns `compare` after its baseline phase and the baseline rows join then. The S4.10 trial found every baseline ranking identical, so RCD's stochastic part is the one to watch.

*Alternative:* add a `--systems` filter so S5.5 runs only HELIOS reruns, and S5.3 runs the baseline reruns. That is a small code change for no gain in the measure. I don't recommend it.

**P-c Measures.** Two levels, both reported per corpus and per variant:

1. **Token-equality rate (the done-when).** For each L-pipe worker call in a pair, where both sides produced output under the same prompt hash: is the raw output byte-identical? The rate is identical calls over compared calls.
   - Calls whose prompt hashes differ are counted separately. A different prompt means the nondeterminism is upstream of the model (pipeline or data), which is a defect to investigate, not model noise.
   - A cache hit on the first side still counts: the cached answer came from the same model digest and the same prompt, so the comparison is across sessions. That is the stronger test.
2. **Run-level equality (`determinism.json`, unchanged).** Fused list, L-pipe evidence and narrative, as `compare` defines them. This is the covariate S5.3 joins into `eval_run`.

Narratives are compared on their rendered text only, because the slots do not store raw model text. A slot that fell back to the template on one side because no model answer was available stays "not comparable", as in S4.10. With live first runs this should be rare, and the report counts it.

**P-d Code.** One small reader, `bin/determinism_report.py --dir <campaign>`, which reads `determinism.json` and the two stores and writes the per-call counts (P-c 1) next to it. It reads no ground truth and changes no run. Its test plants an unequal raw output, a differing prompt hash and a fallback slot. `compare` and `compare_rerun` stay as they are.

**P-e Reading the result.** No threshold is pre-registered, so the probe reports and does not decide. What would need you:
- **Fused lists differ in any pair.** The confirmatory metrics would then move between runs of the same spec. I would bring the pairs and the cause to you before S5.3, and a covariate or protocol change would get a deviation entry with your approval of the text.
- **Prompt hashes differ.** This is treated as a defect under S5.1 S-e: fixed in its own commit, with the affected corpus rerun.
- **Raw outputs differ but fused lists do not.** This is reported, and the covariate carries it. It needs no decision now.

## 4. Compute and order

| Step | Runs | Estimate |
|---|---|---|
| HELIOS reruns, live, no cache | 520 | About 20 s each in the S4.10 trial, so about 3 h |
| Baseline reruns | 260 | Short; no model calls |
| `compare` and the report | — | Minutes |

Order: OTel v3 first, then the three RCAEval parts, with `compare` and the report after each. The run goes in the background, and the pre-push gate runs only after it finishes, so its timings are not disturbed.

## 5. Done-when, files, deviation entry

- **Done when:** the rerun phase is complete in all four directories; `determinism.json` and the per-call report exist for each; the S5.5 report gives the token-equality rate per corpus and variant; the full gate is green.
- **Files:**
  - new: `bin/determinism_report.py`, `tests/test_determinism_report.py`, `docs/sprints/s5-integration-freeze/s5_5_determinism.md` with one JSON per corpus in `determinism/`;
  - updated: tracker row S2-M10-EVAL05.
- **Deviation entry:** none expected. One only if P-e finds a change to a covariate or the protocol, with your approval of the text first.
- **Effort:** half a day plus about 3 h of compute, within the plan's ½.

## 6. Changes in execution (2026-11-15)

- **Prompt identity (P-c 1).** `prompt_shas` hashes only the persona template, which is the same for every case. The reader therefore treats two calls as having the same prompt when the template hash, the candidate list and the worker's digest are all equal, because those three make up the rendered prompt (`personas.render_prompt`), and the response cache keys on them too. The first version of the reader compared the template hash alone. It was fixed before any number was reported, and a test covers it.
- **Baseline reruns on RCAEval** all failed on a baseline-export defect (report §5). They are a record in the ledgers, and the fix belongs to S5.3's design.
