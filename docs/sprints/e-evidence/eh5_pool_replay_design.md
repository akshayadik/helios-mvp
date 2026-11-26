# E-H5 pool replay · design

**Hypothesis:** E-H5, HELIOS-noReconcile against HELIOS-Full, reward reconciliation error (RRE) on the delayed-label subset. Exploratory, BCa only, outside Holm (Ch3 Table 18) · **Registered:** S3.3 design W-b; entry 87 (the subset is every 4th case of each benchmark system in the pool `case_order`, and the schedule has an E-H5 replay phase); entry 92 (same-case form first, worded form beside it); entries 74 and 75 (clock, rewards, update rule) · **Owner:** option (a) chosen 2026-11-26 · **Freeze:** `build-freeze-5`, before E1

## 1. Gap

- **The tool refuses the pool.** `bin/reward_replay.py --corpus pool` exits with "the pool is locked" even under the frozen build: only the build replay exists.
- **Nothing runs on the subset.** The campaign schedule lists the 60-case subset (`eh5_cases`), but no phase acts on it.
- **The statistics are never fed.** `helios/analysis/run.py` `e_h5_forms` computes both forms, but nothing gives it per-case RRE.

## 2. Design

| | Decision | Why |
|---|---|---|
| **P-a** | **Pool cases come from E1's own runs.** The replay reads HELIOS-noRouter's chain-of-evidence entries from the E1 campaign (`coe/results.HELIOS-noRouter.coe.jsonl`) for the registered subset only. It does not run the pipelines again. Cases are built with the build replay's `case_from_entry`. | The cases are exactly the confirmatory outputs: same pipelines, same cache, same seeds. No compute, and nothing can differ from E1. |
| **P-b** | **Labels only after scoring.** The pool ground truth is read through the existing pool gate (`build_frozen()`, signed ground truth). The tool also refuses unless the E1 store is scored (`eval_score` present). | W-b: "reads ground truth only after scoring and never feeds a confirmatory number". |
| **P-c** | **Starting state = the frozen router's own fit.** The router is pre-warmed with the full-information rows of all build cases, the same rows the frozen router was fitted on. The pool subset is then streamed whole: there are no halves, because pool and build do not overlap. | This is entry 74's "starting state as in the build replay" without the cross-fitting. The build replay needed halves only because it streamed the data it was warmed on. A test checks that the pre-warmed state equals the frozen router. |
| **P-d** | **Same clock, rewards and draws as the build replay.** Same variants (Full, noReconcile), the 8 streams, the three mean gaps (3,600 s primary; 900 s and 14,400 s sensitivity), entry 74's delay distributions and entry 75's superseded rule. Each stream's order and delays come from the registered seed slot `orar_prewarm_order` with that stream's index: one sub-stream over the pool subset. | No new seed and no new parameter. |
| **P-f** | **The terminal reward r² is HR@1** (owner, 2026-11-26). S3.3 W-c defines r² as "the same reward the frozen router was fitted on". That was HR@3 when the replay was written; CR-01 (entry 99) refitted the router on HR@1, and the replay was not updated. The pool replay uses `router_calibration.REWARD`. The build replay keeps HR@3, so its reports reproduce. | It keeps W-c's rule and makes P-c hold. Disclosed: r¹ (MAHC confidence) estimates P(root cause in top 3) while r² is a top-1 hit. Both variants share this mismatch, so the E-H5 difference (noReconcile minus Full) still isolates reconciliation. |
| **P-e** | **The reading (entry 92).** Per gap, `e_h5_forms` gets RRE per (case, stream) for each variant. The same-case form uses the pairs where both variants have a provisional reward on the same stream; the worded form uses each variant's own cases, with the counts and the overlap. Also reported: HR@3, escalation share and RRE by stream, as in the build report. The output holds aggregates only, never a case ID, and goes to the campaign folder. | Entry 92 as decided, fed for the first time. |

## 3. Code (frozen paths, so entry and new freeze)

- **`bin/reward_replay.py`:** a `--corpus pool --campaign DIR` path for P-a to P-e. The build path is unchanged, so the build report reproduces.
- **`helios/evaluation/reward_replay.py`:**
  - a single-sub-stream draw over a given case list (P-d);
  - per-(case, stream) RRE for `e_h5_forms`.
  The existing functions are unchanged.
- **Tests:**
  - the pool path refuses without the freeze, without scoring, and outside the subset;
  - the pre-warmed state equals the frozen router (P-c);
  - the draws are deterministic per stream;
  - pairing for the same-case form;
  - the build replay output is unchanged.
- **After merge:** the tag constant becomes `build-freeze-5`, then the record, the tag (owner OK), an entry recording the tag, `../helios-e` moved, and E1 planned again.

## 4. P-c checked on build data (2026-11-26)

`collect_cases` (HELIOS-noRouter over the 558 build cases, cache only, no exclusions, no unfeatured case) took 1,057 s.

| Pre-warm reward | Largest difference from the frozen router (θ and A⁻¹, all arms) |
|---|---|
| HR@1 (P-f) | 4.95e-07: the 6-decimal rounding of the frozen file, inside the tolerance of 1e-06 |
| HR@3 (before CR-01) | 1.03 |

Rows per arm equal the frozen router's counts: D 558, D+G 63, D+L 557, Full 63. The tool refuses to replay if the difference exceeds 1e-06.

## 5. When it runs

After E1 is scored (it needs E1's chain-of-evidence entries and scores), alongside E6. The build-case pre-warm reruns HELIOS-noRouter over the build captures with the cache only, as the build replay does: about 18 minutes of CPU and no model calls. The pool stream itself takes seconds.

## 6. What this is not

- No confirmatory hypothesis, metric, test, Holm rank, variant hash or frozen parameter changes.
- E-H5 stays exploratory.
- The subset rule (entry 87) and the reading (entry 92) are unchanged. This makes them runnable.

## 7. For the owner

**Approved 2026-11-26:** P-a to P-e, and P-f (HR@1) chosen when the reward mismatch was found during implementation. The points that deserved a look:
- **P-c:** the starting state is the frozen router, not a half of the build data.
- **P-d:** the seed slot is reused with the same stream indices.
