# S5.4 Clean-environment replication · report

**Row:** S2-M10-EVAL04 · **Design:** [s5_4_replication_design.md](s5_4_replication_design.md) (approved 2026-11-16) · **Candidate:** `54becfb` (`main` at `2961673` plus the R-e `cells` fix) · **Run:** 2026-11-17 19:05 to 2026-11-18 02:30, about 7½ h · **Label:** build data; a check of the build, not a measurement. No hypothesis is read.

## 1. Result

**HELIOS reproduces exactly on a fresh clone.** Every snapshot hash, every per-pipeline ranking and decision hash, and every fused ranking of all 7,254 HELIOS runs is identical to the S5.1 reference. Every run outcome is identical. Every analysis field outside the timing-derived list is identical. So the design's pass condition (R-e) is met.

One difference remains, in a baseline: **Multi-source RCD (`BASELINE-5`) reorders its list on 3 of 495 RCAEval cases** (6 of 5,580 baseline runs), with identical input, seed, image and config. It changes no HR@1 or HR@3 value, and no field of the analysis. §4 diagnoses it; it is proposed as an accepted difference, for the owner to confirm (§7).

| Directory | Runs compared | Identical | Differ | Schedule digest | Analysis (outside timing) |
|---|---|---|---|---|---|
| `otel_build_v3` | 1,449 | 1,449 | 0 | equal | identical (74 timing-derived fields differ) |
| `rcaeval_build_1` | 3,795 | 3,793 | 2 (RCD, one case) | equal | identical (70) |
| `rcaeval_build_2` | 3,795 | 3,795 | 0 | equal | identical (73) |
| `rcaeval_build_3` | 3,795 | 3,791 | 4 (RCD, two cases) | equal | identical (65) |
| **Total** | **12,834** | **12,828** | **6** | | |

Per-spec detail: `replication/compare_<dir>.json`; analysis diffs: `replication/analysis_compare_<dir>.json`.

## 2. Clone and data (R-b, R-e steps 1 and 2)

- **Clone.** `git clone` of the GitHub repository at `54becfb` into `../helios-s54-replica`; new virtualenv from `poetry.lock` on the machine's Python 3.11 interpreter; `.env` copied (mode 600).
- **Clone health.** Full pre-push gate green in the clone: coverage 96.79%, deviation log verified with the public key (91 entries), `verify_captures` OK, `verify_osf_freeze --verify` intact, tracking valid.
- **RCAEval build data.**
  - The build files of `data/rcaeval/raw/` were copied, not downloaded again.
  - Correction to design §2: there is no tracked `raw/checksums_build.json`. The raw hashes are recorded in the tracked, signed `ground_truth_build.json`, and the copy was checked against those.
  - `import_rcaeval.py convert --corpus build`, then `verify --corpus build`: 495 of 495 OK, manifest digest `158e1088…`. `git diff` on `build_manifest.json` and `ground_truth_build.json` is empty, and all 1,605 window files are byte-identical to the working tree's.
- **Provisioning step found.** The three RCAEval part manifests (`data/campaigns/s5_1/rcaeval_build_{1,2,3}_manifest.json`) are not tracked; they are regenerated from the tracked build manifest and come out byte-identical. This step is now part of provisioning a clone (§6).
- **Response cache (R-c).** `lpipe_cache.sqlite` copied with SQLite's backup command. The file bytes differ (page layout), the row-level digest is identical (7,706 rows).
- **Not compared, as designed.** Docker images and the Ollama model are the machine's own, pinned by digest and checked the way a campaign checks them.

## 3. Runs (R-d, R-e steps 3 and 4)

- **Schedules.** All four `schedule.json` digests equal the reference's.
- **Phases.** Confirmatory, exploratory, baseline and baseline_trigger in each directory; rerun is S5.5's and was not repeated.

| Directory | Confirmatory | Exploratory | Baseline | Baseline (trigger) |
|---|---|---|---|---|
| `otel_build_v3` | 504 passed · 14 min | 315 passed · 13 min | 315 passed · 12 min | 302 passed, 13 excluded · 14 min |
| `rcaeval_build_1` | 1,320 · 26 min | 825 · 15 min | 660 passed, 165 excluded · 47 min | 660, 165 · 52 min |
| `rcaeval_build_2` | 1,320 · 26 min | 825 · 16 min | 657, 168 · 41 min | 657, 168 · 47 min |
| `rcaeval_build_3` | 1,320 · 22 min | 825 · 13 min | 657, 168 · 37 min | 660, 165 · 45 min |

- **Outcomes.** Every outcome and gate check equals the reference's, exclusions included: the 13 Multi-source BARO late-trigger failures on OTel (S5.3 §3.1, left as recorded by owner decision R-g) and TraceRCA `modality_absent` on every RCAEval case (entry 91).
- **HELIOS.** All 819 OTel and 6,435 RCAEval HELIOS runs identical: snapshot hash, per-pipeline ranked list and decision hash, fused list (first and terminal) and fusion state.
- **Model answers.** No L-pipe worker made a live model call in the clone: every answer came from the copied cache. So every HELIOS comparison is a code-and-data comparison, as R-c intended; model reproducibility stays S5.5's measurement (54 of 460 RCAEval pairs not equal).
- **`cells`.** The fixed `cells` (R-e) wrote 0 metric exclusions in all four directories. The reference build ledger holds 18 entries on case `c80ff7d1` that are mis-attributed (design §3); they stay in the append-only ledger.

## 4. Multi-source RCD difference

- **Where.** `BASELINE-5`, Multi-source RCD, on three RCAEval cases: `1ae703fe` (part 1), and `a7503bb9` and `de61bceb` (part 3), at both binding and trigger time.
- **What is the same.** Snapshot hash, run seed, container image digest and config hash are identical to the reference's in all six runs.
- **What differs.** The order and the length of the ranked list. Examples:
  - `1ae703fe`: the top 3 are identical; ranks 4 and below are reordered. The clone's binding-time list is exactly the reference's trigger-time list, so the method moves between a few outcomes on the same input.
  - `a7503bb9` and `de61bceb`: the top of the list changes as well.
- **Effect on scores.** HR@1 and HR@3 are unchanged in all six runs (misses in reference and clone alike). Avg@5 and MRR change on `1ae703fe` and `de61bceb`. No analysis field changes: the B-H5 test (Full against Multi-source RCD) reads HR@3.
- **Diagnosis.** The method is nondeterministic beyond its seed, inside the baseline container. The likely source is its causal-discovery search running across the container's 8 CPUs, but this was not isolated. HELIOS code and data are not involved, and the copied cache plays no part, since baselines call no model.
- **S5.5 did not see it.** The S5.5 rerun subset covers HELIOS variants only, so this is new information.
- **Proposed treatment.** Accept as an environment difference in a baseline, with this reason, and carry it as backlog item CR-23 (component review backlog in this folder). In phase E, B-H5's HR@3 reading is unaffected on build data, but Multi-source RCD's lower ranks, and so its Avg@5 and MRR, can move between reruns. The alternative, pinning RCD to one thread or fixing its search order, is a baseline code change. It would need a deviation entry and a rerun of the RCD phases before the freeze, like the R-g question.

## 5. Analysis end to end (R-e step 5)

- `score_runs --metrics` with the S5.5 `determinism.json` join, `cells` and `analyse` ran in the clone with the commands that produced `pilot/analysis_<dir>.json`.
- **Outside the timing list,** all four analysis JSONs are identical to the S5.3 ones.
- **Timing-derived fields** differ, as expected, since wall-clock time depends on machine load. They are the fields of A-H5 (log-CpR at matched HR@3), B-H7 (log-CpR) and B-H6 (log time to correct diagnosis), including their entries in the Holm and Benjamini–Hochberg tables and their sensitivity readings.
  - One descriptive reading flips: on OTel, B-H7 in the Benjamini–Hochberg table goes from below its threshold (p about 0.038) to not below (p about 0.099).
  - No timing-derived reading flips on RCAEval.
  - Build data has no binding verdicts. But for phase E this is a reminder that CpR and TTCD readings carry run-to-run timing noise (backlog CR-10).

## 6. Corrections, tooling and provisioning

- **Design §2 wording.** The raw hashes live in the signed `ground_truth_build.json`, not a tracked `raw/checksums_build.json` (backlog CR-21; corrected here, the approved design is left as written).
- **Provisioning a clone,** in addition to the root `CLAUDE.md` setup (backlog CR-22):
  1. Copy `.env`.
  2. Copy or fetch the RCAEval build files into `data/rcaeval/raw/`, then run `import_rcaeval.py convert --corpus build` and `verify --corpus build`.
  3. Regenerate the three part manifests from the tracked build manifest.
  4. Copy the response cache.
- **`bin/replication_compare.py`, two corrections found while reading the results** (comparisons regenerated after both; tests added):
  1. Correction-table and sensitivity entries name a hypothesis only by its id. They are now classed by that hypothesis' metric, taken from the reference itself. Before, their timing differences were reported as non-timing.
  2. A worker that was dropped before calling the model (for example `no_digest`) was counted as a live call; it no longer is. The corrected count is zero in all four directories.
- **Limitations.**
  - Same machine, operating system and model server. This rules out working-tree leakage, not hardware or OS differences.
  - The raw download was not repeated; the bytes were checked against the signed hashes, and `fetch` itself was exercised in S1.1.
  - Wall times, timestamps and timing-derived metrics are not compared for equality.

## 7. Owner decision

**Multi-source RCD difference (§4).** Accept it as a baseline environment difference with the reason above, and carry it as CR-23 (recommended); or fix it before the freeze, which needs a baseline change, a deviation entry and a rerun of the RCD phases.

**Rerun on the frozen SHA (R-a).** If any change to rankings lands before `build-freeze`, for example CR-01 or CR-02 from the component review, the HELIOS part of S5.4 is rerun on the frozen SHA in S5.6. That takes about 2 h with the cache: HELIOS phases took 14 to 41 min per directory here.
