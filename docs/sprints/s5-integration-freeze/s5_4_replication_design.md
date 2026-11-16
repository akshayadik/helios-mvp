# S5.4 Clean-environment replication · design

**Row:** S2-M10-EVAL04 · **Status:** approved by the owner 2026-11-16 (R-a to R-f as written; R-e fix without a deviation entry; R-g: no, §3.1 stays as recorded) · **Plan:** [plan.md](plan.md) step 5 · **Carries in:** S5.3 report §3.4 (the open `c80ff7d1` item)

## 1. What the replication has to show

The breakdown's done-when is "snapshot hashes and fused rankings reproduce on a fresh checkout". The plan adds that it runs on a fresh clone of the commit to be frozen, so that anything the working tree has but the repository lacks shows up before the freeze. That covers untracked data, local edits, a stale virtualenv or a cache the clone has not been given.

It is a check of the build, not a measurement. No hypothesis is read.

## 2. Starting point

- **Reference runs.** The four S5.1 directories in `data/campaigns/s5_1/` hold every first run on build data:

| Directory | Cases | HELIOS specs | Baseline specs (binding + trigger) |
|---|---|---|---|
| `otel_build_v3` | 63 | 819 | 630 |
| `rcaeval_build_1` | 165 | 2,145 | 1,650 |
| `rcaeval_build_2` | 165 | 2,145 | 1,650 |
| `rcaeval_build_3` | 165 | 2,145 | 1,650 |

- **Code since those runs.** HELIOS pipeline code has not changed since the S5.1 first runs. The later commits touch the baselines (`d5c6de1`, `6d8882c`, entry 91) and scoring (`6e8fd4e`), and the baseline phases were run after them. So the existing stores are a valid reference: a difference in the clone is a reproducibility problem, not a code change.
- **What a fresh clone has.** OTel build captures (`data/otel/build_v3`), the 20 exploratory captures, the RCAEval manifests and signed ground truth are tracked.
- **What a fresh clone lacks.**
  - the RCAEval build windows: `data/rcaeval/build/`, 495 sealed cases, about 490 MB, git-ignored;
  - their downloads: `data/rcaeval/raw/`, hash-checked against the tracked `raw/checksums_build.json`;
  - the response cache `data/cache/lpipe_cache.sqlite`;
  - `.env`;
  - the virtualenv.
- **Where hashes live.** `result_row.snapshot_hash` and `decision_hash` for HELIOS, `fusion_row.ranked_json` for the fused list, and `baseline_row.snapshot_hash` and `ranked_json` for the baselines.

## 3. Defect found while preparing this (S5.3 §3.4 resolved)

The 18 `metric_missing` exclusions on `c80ff7d1` are a bookkeeping defect in `helios_campaign.py cells`. They are not missing scores: the three trigger-time runs (Multi-source BARO, BARO, Multi-source RCD) each have an `eval_score` and an `eval_run` row.

- **Cause.** `cells` keys passed runs by `system_name(...)`, which drops the trigger-time suffix. The binding-time and trigger-time runs of one baseline on one case therefore share a key, and the trigger run wins.
  - On `c80ff7d1` the binding-time runs of those three baselines were excluded (`baseline_error`, S5.3 §3.3). So `cells` looked up the binding-time cell, found no metric, and wrote `metric_missing` against the trigger run's id.
  - `scheduled_by_system` in `schedule.py` adds the suffix correctly, so the cell table itself is right.
- **Effect on the S5.3 reading:** none. `bin/analyse.py` reads scores and cells, not the exclusion ledger, and the cells on that case were already counted correctly.
- **Effect in phase E.**
  1. Wrong ledger entries whenever a binding-time baseline run fails and its trigger-time run passes.
  2. A blind spot: a trigger-time run that passes but is not scored is never detected, because trigger runs never appear under their own name.
- **Fix (R-e).** Build `passed` with the same naming as `scheduled_by_system`, plus a regression test with the `c80ff7d1` shape.
- **The 18 build entries.** They stay in the build campaign's ledger, which is append-only. The S5.4 report records them as mis-attributed.

## 4. Decisions (R-a to R-g)

**R-a When, and on which commit.** Run now on a candidate: `main` plus the R-e fix, plus the §3.1 fix if you approve it (R-g). Record its SHA in the report.
- If any code that changes rankings is merged before `build-freeze`, rerun the HELIOS part (about 3 h with the cache) on the frozen SHA as part of S5.6.
- A change to documents or price books only does not need a rerun; price books affect CpR, not rankings.
- No candidate tag: tags are never moved, and a SHA in the report is enough.

*Alternative:* wait until every freeze input is in (rater 2, E-H5, price books, the chair call), then run once. That leaves the costly check to the last days before the freeze, with no time to fix what it finds. I don't recommend it.

**R-b Where.** Make a fresh `git clone` of the GitHub repository at the candidate SHA into a folder beside the working tree, not inside it: `../helios-s54-replica`. Then run `poetry install` from the lock into a new virtualenv. The clone gets only the following:

| Item | How | Why |
|---|---|---|
| `.env` | copied (mode 600) | needed to verify seals and score; never committed |
| `data/rcaeval/raw/` (build files only) | copied, then checked against the tracked checksums | avoids a 3 GB download; the checksum check makes the copy as good as a download |
| response cache | copied (R-c) | |

Everything else comes from the repository. Docker images and the Ollama model are the machine's own, pinned by digest. The digests are checked the way a campaign checks them.

- **Limitation, stated in the report:** same machine, same OS, same model server. This rules out working-tree leakage, not hardware or OS differences.

**R-c Response cache.** Copy `lpipe_cache.sqlite` into the clone, so the L-pipe answers are the ones the S5.1 runs used.
- This separates "the code and data reproduce" (S5.4) from "the model reproduces" (S5.5 already measured that: 54 of 460 RCAEval HELIOS pairs not equal, OTel all equal).
- Any cache miss goes live and is counted. A ranking difference on a run with a miss is classified as model nondeterminism, not a build defect.

*Alternative:* an empty cache. That repeats S5.5's measurement and mixes the two questions, so a difference could not be attributed. I don't recommend it.

**R-d What runs.** Every first-run phase in the four directories:
- confirmatory, exploratory, baseline and baseline_trigger;
- not rerun, which is S5.5's;
- with the same schedules, whose digests must match.

The S5.1 and S5.3 phase durations give about 3 h for HELIOS and about 6½ h for baselines, so about 9–10 h in all, best overnight. It is the same heavy machine load as the pilot, so I start it only when you say Tessera is not running.

*Alternative:* HELIOS plus binding-time baselines only, about 5½ h. Trigger-time baselines would not be checked, and the analysis JSON could not be compared whole.

**R-e Comparisons.** One new read-only tool, `bin/replication_compare.py` (flag `HELIOS_ENABLE_REPLICATION_COMPARE`, with tests). It compares a clone directory with its S5.1 reference, spec by spec, and writes `docs/sprints/s5-integration-freeze/replication/compare_<dir>.json`. It checks, in order:

1. **Clone health:** the full pre-push gate in the clone, including `verify_captures`, `verify_osf_freeze --verify` and the ledger checks.
2. **Data:** `import_rcaeval.py convert --corpus build` in the clone, then `verify`. The re-converted `build_manifest.json` digest must equal the tracked one, and every `content_seal.json` must be byte-identical to the working tree's.
3. **Schedules:** the digest of each `schedule.json` must equal the reference's.
4. **Runs, per spec:**
   - outcome (passed or excluded, and the gate check);
   - `snapshot_hash`;
   - fused ranked list;
   - `decision_hash`;
   - baseline ranked list.

   Wall times and timestamps are expected to differ and are not compared.
5. **End to end:** `score_runs --metrics`, `cells` and `analyse` in the clone. The analysis JSON must equal the S5.3 `pilot/analysis_<dir>.json`, apart from timing-derived fields (TTT, time to narrative, CpR's compute part), which are listed and compared within a stated tolerance, not for equality.

**Pass:**
- every snapshot hash and every cache-hit fused ranking is identical;
- every outcome is identical;
- every analysis field outside the timing list is identical.

Any difference is diagnosed and either fixed before the freeze or recorded as an accepted environment difference, with a reason.

- **The R-e code fix** (§3) lands first, in its own commit with its test, so the clone runs the fixed `cells`. The reference directories' `cells` is then rerun in the working tree, to show the fix removes the 18 entries' cause. It writes no new entries.
  - It needs no deviation entry, in my reading: phase E has not started, the analysis does not read the ledger, and no pre-registered test changes. If you read it differently, I'll draft one.

**R-f Outputs.**
- `s5_4_replication.md` (report);
- `replication/compare_*.json`;
- the tracker row EVAL04 DONE with SHA and evidence;
- PR.

**R-g Multi-source BARO late-trigger fix (S5.3 §3.1).** This is still your decision from the pilot PR. It changes baseline code, so if you want it before the freeze it should go into the candidate before R-d runs, not after.
- If yes: I draft the fix and the deviation entry text for your approval first.
- If no: the 13 OTel exclusions stay as the pilot recorded them. Phase E will show the same pattern on cases where the trigger falls late in the capture.

## 5. Risks

| Risk | Mitigation |
|---|---|
| The clone needs something the repository lacks | That is what S5.4 looks for: the item is added to the repository, or to a documented provisioning step, before the freeze |
| Copying `raw/` hides a broken download path | The checksum check covers the bytes; `fetch` itself was exercised in S1.1. The report says the download was not repeated |
| Machine load from Tessera skews nothing here (no timing is compared for equality) but doubles the wall time | Run only when you say the machine is free |
| A ranking-relevant change lands after S5.4 | R-a: rerun the HELIOS part on the frozen SHA in S5.6 |

## 6. Record

- **2026-11-16, owner decisions.** R-a to R-f approved as written. The R-e `cells` fix goes in without a deviation entry. R-g: the Multi-source BARO late-trigger failures (S5.3 §3.1) are not fixed; the 13 OTel exclusions stay as recorded.
- **R-e fix.** `spec_system_name` in `schedule.py` is now the one naming rule for schedule specs; `cells` uses it through `passed_runs`. Regression tests: `tests/test_campaign_cells.py`.
  - A read-only run of the fixed check on the four S5.1 directories finds no passed run without its metrics (1,436, 3,465, 3,459 and 3,462 passed first runs). So the old blind spot hid nothing, and the 18 `c80ff7d1` entries were its only symptom. `cells` was not rerun on the reference directories, so their ledgers are unchanged.
