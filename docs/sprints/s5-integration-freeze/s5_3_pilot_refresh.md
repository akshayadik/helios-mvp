# S5.3 Exploratory pilot on build data · refresh after CR-01 and CR-02

**Row:** S2-M10-EVAL06 · **Reading refreshed:** [s5_3_pilot.md](s5_3_pilot.md) (S2-M10-EVAL03) · **Changes:** deviation entries 98 (CR-02, D-pipe call edges) and 99 (CR-01, router top-1 reward, re-frozen) · **Design notes:** [cr01_router_reward_design.md](cr01_router_reward_design.md), [cr02_structural_dpipe_design.md](cr02_structural_dpipe_design.md) · **Date:** 2026-11-19 · **Label:** exploratory build data. HELIOS was built and calibrated on these cases, so every HELIOS number here is optimistic, and nothing here is a result.

## 1. Outcome

- **Both changes do what their design notes predicted, on every build directory.** HELIOS-Full's top-1 rises everywhere, its top-3 rises or holds, and no comparator gets worse.
- **No Family A or B reading flips against HELIOS.** Two OTel readings now fall below their Holm thresholds (B-H6 and B-H7). On RCAEval every reading keeps its S5.1 outcome. One OTel reading weakens: A-H1 (Full against noLLM, HR@3) goes from p 0.125 to about one half, because noLLM gains more from CR-02 than Full does (74.6% → 81.0% against 79.4% → 82.5%); neither was below its threshold.
- **A-H8 changes direction on OTel:** Full 82.5% against noStructural 81.0% HR@3, where S5.1 had 79.4% against 81.0%. It is still far from its threshold (p about one half), as the pre-registration expects for an underpowered test.
- **The censoring share falls.** Fewer Full runs end without a correct top-1, so fewer sit at the 1,800 s TTCD cap that prices CpR's opportunity term (§3.2).
- **Runs.** 7,254 HELIOS first runs and 610 determinism reruns, none excluded; no metric exclusion; the same cells below the cell rule as S5.1 in every directory.

## 2. What ran

- **Code:** branch `s5/cr01-cr02`: `5efd348` (CR-02), `072f65e` (CR-01), `496962e` (router re-frozen from build run 4, τ_acc 0.684821).
- **Campaigns:** four new directories `data/campaigns/s5_cr/<dir>`, planned with the S5.1 manifests; every schedule digest equals its S5.1 one.
- **HELIOS:** confirmatory, exploratory and determinism-rerun phases, all 13 run variants, in every directory. Every variant is rerun, not only the changed ones, so each store comes from one build.
- **Baselines carried, not rerun.** Baselines do not read HELIOS code. Their S5.1 log records (all phases) and their rows in both stores were copied into the new directories, with each log record marked `carried_from`. Their S5.1 exclusion-ledger entries stay in the S5.1 ledgers, and nothing was re-signed.
- **Then, per directory, as S5.3:** `helios_campaign.py compare`; `score_runs.py --metrics --determinism` on the main store and `--metrics` on the rerun store; `cells`; `analyse.py --campaign --captures --reruns`; `pilot_metrics.py`.
- **Before figures:** the same analysis code (analysis-v2) on copies of the S5.1 stores, so the comparison isolates entries 98 and 99. S5.3's own `pilot/analysis_<dir>.json` predate analysis-v2 and are not used for the comparison.
- **Model answers:** the response cache grew from 7,706 to 8,163 rows over the day (new escalations and determinism reruns answered live).
- **Machine load:** the full test suite ran alongside part of RCAEval part 2's HELIOS phases. Rankings are unaffected; its wall times are long (§3.3).

Files: `pilot_cr/analysis_<dir>.json`, `pilot_cr/metrics_<dir>.json`, the before analyses in `pilot_cr/before/`, and every before/after table in [pilot_cr/before_after.md](pilot_cr/before_after.md).

## 3. Readings

### 3.1 Accuracy (HELIOS-Full, fused list)

| Directory | Top-1, before → after | Top-3, before → after | noRouter top-1 / top-3, after |
|---|---|---|---|
| `otel_build_v3` (63) | 49.2% → 54.0% | 79.4% → 82.5% | 54.0% / 82.5% |
| `rcaeval_build_1` (165) | 80.0% → 86.7% | 96.4% → 97.0% | 87.3% / 98.2% |
| `rcaeval_build_2` (165) | 83.0% → 88.5% | 97.0% → 97.0% | 91.5% / 98.2% |
| `rcaeval_build_3` (165) | 86.7% → 90.3% | 96.4% → 96.4% | 89.1% / 95.8% |

- **OTel (CR-02 and CR-01).** Every variant with the typed graph and D-pipe propagation gains two or three top-1 hits and two top-3 hits. noRouter gains the same, so on OTel Full still equals uniform routing, now with 13 of 63 cases stopping before the L-pipe. noLLM gains most (top-1 49.2% → 61.9%, top-3 74.6% → 81.0%): without the L-pipe, the D-pipe and the G-pipe it seeds carry the whole ranking.
- **RCAEval (CR-01 only; no traces, no graph).** The routed variants gain 4 to 7 points of top-1. Variants the router does not touch (noRouter, LLM-only, D, G, noLLM) are unchanged to the hit. Against uniform routing, Full's top-1 is now 0.6 points behind on part 1, 3.0 behind on part 2 and 1.2 ahead on part 3, where it was 7.3, 8.5 and 2.4 points behind.

### 3.2 Cost and censoring

Share of runs with no correct top-1 before the 1,800 s cap (A-H5 timing block, entry 94):

| Directory | Full, before → after | noRouter, before → after |
|---|---|---|
| `otel_build_v3` | 44.4% → 28.6% | 50.8% → 46.0% |
| `rcaeval_build_1` | 17.3% → 9.8% | 11.7% → 11.7% |
| `rcaeval_build_2` | 14.7% → 8.6% | 8.0% → 8.0% |
| `rcaeval_build_3` | 12.8% → 8.5% | 10.4% → 10.4% |

- **A-H5 (noRouter against Full, log-CpR).** The mean log-CpR of Full falls in every directory: OTel 8.15 → 6.97, RCAEval 5.35 → 4.84, 5.11 → 4.88 and 4.99 → 4.72. The router now stops on fewer cases, so it saves less L-pipe time, but CpR is dominated by the opportunity cost of TTCD, and fewer Full runs reach the cap. The A-H5 difference grows in every directory.
- **B-H6 and B-H7 on OTel** (best baseline against Full, log TTCD and log-CpR) now fall below their thresholds: p about 0.055 → 4e-6 and 0.038 → 1e-6. In S5.3 and S5.4, B-H7 on OTel was the reading that moved across its threshold with timing noise alone; it is now far from it.

### 3.3 Timing

- **Timing noise (entry 94).** Variants untouched by both changes show the size of run-to-run timing noise. On parts 1 and 3 their median TTT moved by up to about 15%. On RCAEval part 2, partly run alongside the test suite, the median TTT of every variant that stops on the cheap stage rose by 25 to 55%, HELIOS-D's included (218 → 321 ms), and so did the median log-CpR of every cheap-stage variant (about 3.6 → 3.9). These are machine-load effects, not changes from entries 98 and 99. Part 2's timing-derived figures are therefore conservative for HELIOS and are not used to size any effect.
- **OTel TTT.** Full's median TTT is 1,225 ms against 1,434 ms before. The G-pipe's trace features, about 0.9 s, are still in Full's path (CR-02 design §4).

### 3.4 Determinism reruns

| Directory | Pairs | Not equal, S5.1 → refresh |
|---|---|---|
| `otel_build_v3` | 90 (60 HELIOS, 30 baseline) | 0 → 0 |
| `rcaeval_build_1` | 150 (HELIOS only) | 21 → 29 |
| `rcaeval_build_2` | 160 (HELIOS only) | 12 → 18 |
| `rcaeval_build_3` | 150 (HELIOS only) | 21 → 21 |

Every non-equal pair is an L-pipe answer that differs between runs (CR-04). The counts rise where the new router sends more rerun cases to the L-pipe: on part 1 each routed variant gains one non-equal pair, and noRouter and LLM-only, which the router does not touch, keep theirs.

## 4. What this changes for the freeze

- The frozen router and the D-pipe input path described in entries 98 and 99 are what S5.6 freezes; the OSF addendum draft (§2.6, §2.16, §3) records both.
- The S5.4 replication's HELIOS part is rerun on a fresh clone of this branch (S5.4 report §7, R-a); its report follows separately.
- S5.3's decisions L5 to L7 (compute, larger model, judge budget) are not affected: the compute projection rests on HELIOS time per run, which entries 98 and 99 lower on OTel and leave about the same on RCAEval.
