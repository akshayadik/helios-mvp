# OTel fix: error origin and memory trend (design)

Rows S2-M8-ENG06 (fixes, held-out corpus, validation) and S2-M8-ENG07 (refit chain) · 2026-11-07 · Diagnosis: `otel_diagnosis/README.md` · Owner scope decision 2026-11-07: A and B now, C in Stage B; S3.2 and S3.4 exploratory · Approved 2026-11-07, pre-run entry 76

## 1. Problem

On OTel build v3, HELIOS-noRouter's fused HR@3 is 50/63. None of the 13 misses comes from a fault invisible in the data. Two causes are addressed here:

- **A, error attribution (4 misses):** paymentFailure ×2, productCatalogFailure, adFailure.
  - G-pipe's `error_share_shift` (the ranker's largest weight) and D-pipe's error channel (`span_error_calls_total`) count every span along the failing path. Callers inherit the errors.
  - Where the error *starts* (an `ERROR` span with no `ERROR` child) ranks the root first in 34 of 63 cases, including every case of the error faults.
- **B, memory leaks (3 misses):** emailMemoryLeak.
  - Memory ranks email first in all 7 leak cases when measured from the injection.
  - D-pipe measures from the trigger, a fallback anchor in all 7 cases. In that view email's resource shift is small (0.7–2.8), while CPU and memory noise on other services reaches 2–16. D-pipe's resource channel takes the larger of the CPU and memory shifts, with frozen weight 0.1.
  - Raising the weight would amplify that noise. A leak is a sustained rise, which a trend measure can separate from spikes.

## 2. Decisions

**O-a. Scope.**
- A and B only.
- C (errors confined to one caller's calls, recommendationCacheFailure) goes to Stage B, into the backlog.
- No new VCL flag: each change is a parameter of an existing pipeline, recorded in its frozen file and hash. A new flag would change every variant hash in deposit 1.

**O-b. Fix A: error origin in G-pipe only.**
- **The feature:** G-pipe gains `error_origin_shift`, the change in each service's share of error-origin spans from before the trigger to after it.
  - An error-origin span is an `ERROR` span none of whose child spans is `ERROR`.
  - A client span that errors while its server child does not (a timeout) counts for the caller.
  - It is added beside `error_share_shift`, not in place of it.
- **The ranker:** reselected under the frozen S2.2 rule (entries 54–55): leave one root service out, with learned vs feature-weighted PPR vs plain PPR.
- **As built (2026-11-07):**
  - The unit is a service's entry span (one request's work), as for `error_share_shift`. An entry is an error origin when a span of its own work (the entry or a same-service span below it) is `ERROR` and none of that span's children is (`helios/graph/span_features.py`, column `error_origin`). The feature is its share after the trigger minus before.
  - The S2.2 model stays loadable and unchanged. A parameter file that names no `features` is read over the ten S2.2 columns (`S22_COLUMNS`), so today's frozen file keeps its hash and scores; a refit model names its columns in `features`. This keeps *old* runnable beside *new* for O-f.
  - `bin/gpipe_select.py --columns all --report <new path>` runs the reselection; the defaults reproduce the S2.2 run, and an existing report other than S2.2's is never overwritten.
- **D-pipe stays metrics-only.** Its span-metric error series carry only `service_name`, so they cannot tell where an error starts. Reading traces in D-pipe would also blur what HELIOS-D (A-H3) ablates.

**O-c. Fix B: a memory-trend channel in D-pipe, built only if it passes a build-data gate.**
- **The channel:** memory is scored apart from CPU, as a sustained rise. The candidate statistic is the post-trigger memory slope, scaled by the variability of pre-trigger slopes, upward only (as D-h).
- **The weight:** it gets its own weight, w_memory, in D-pipe's grid. The objective is unchanged from S2.1: the mean of per-corpus HR@3 on OTel and RCAEval build, with the frozen trigger. The grid is fixed in the build-run entry before the run.
- **Gate, fixed now:** the channel enters the refit only if, on build data with the frozen trigger, it beats the current resource channel at ranking email among in-scope services in at least 5 of the 7 leak cases. It must also not lower D-pipe's build HR@3 on RCAEval or on the other 8 OTel fault types.
- **If B fails the gate,** it is dropped and recorded; A goes ahead alone.
- **RCAEval has memory faults,** so B is the change that can touch the confirmatory corpus. That is why it is gated.
- **Statistic and gate procedure, fixed 2026-11-08 before any code read the leak cases:**
  - *Series:* per service, each memory metric (`mem` in RCAEval, `container_memory_usage_total_bytes` in OTel), split at the frozen trigger as D-pipe's other channels are. Memory leaves the resource channel; the resource channel keeps the other resource metrics.
  - *Trend:* the Theil–Sen slope (median of pairwise slopes, per step) of all finite values after the trigger, *s*. Reference: with *L* = min(points after, ⌊points before / 2⌋), the Theil–Sen slopes of every run of *L* consecutive finite values before the trigger. If *L* < 3 the channel is zero.
  - *Score:* (*s* − median of the reference slopes) / scale, upward only (as D-h). The scale is the reference slopes' robust spread (`robust_scale`, gauge rule), floored at `REL_FLOOR` × |median level before| / *L*, a 5% level change over a run. A service with several memory metrics takes the largest.
  - *Old chain:* a parameter file without `w_memory` keeps memory inside the resource channel and scores exactly as before, with the same hash.
  - *Gate (run once, `bin/dpipe_memory_gate.py`):* the 7 `emailMemoryLeak` cases of OTel build v3, the frozen trigger. For each case, email's rank among the in-scope services by (a) the current resource channel and (b) the memory trend: 1 + the number of services with a strictly larger value, and last when email's value is zero. The channel passes if (b) is strictly better than (a) in at least 5 of the 7. The no-loss half of the gate (RCAEval build and the other 8 OTel fault types) is checked on the refit grid's selected setting in ENG07.
  - *Result (2026-11-08, run once, `calibration/memory_gate.json`, code 1efd6da):* **passes, 5 of 7**, at the threshold. All 7 cases used the fallback trigger. Email's rank (resource → memory trend, of 20): 3→1, 8→1, 4→2, 7→1, 9→2 better; 1→2 and 1→20 worse. In the last case the trend is zero: email's memory did not rise faster after the fallback split than before it. B enters the ENG07 refit; its no-loss half is still open.
  - *Refit grid (entry 77, `calibration/dpipe_refit.json`, code 3a25665; 3100 settings, run once to completion 2026-11-08):* **fix B is dropped.** The selected setting is the current frozen one (w_error 0.7, w_resource 0.1, rho 0.2, boost 1; mean HR@3 85.37%, RCAEval 94.55%, OTel 76.19%), reproducing S2.1 exactly; it ties with 49 other settings without w_memory. The best setting with w_memory reaches 84.88% (RCAEval 95.15%, OTel 74.60%). At the frozen weights, w_memory 0.1 keeps OTel at 76.19% and lowers RCAEval to 93.13%. `data/frozen/dpipe_params.json` and its hash are unchanged; the refit continues with fix A alone. A first start of this run (9347145) was stopped after 2.5 h with no output or report: it recomputed the trend for every setting; 14c8f0c and 3a25665 removed that cost without changing any value.
  - *Production cost, for any later version:* on a 4200-step window the trend costs about 2.5 s per memory series (about 30 s for 12 series). A later memory channel should bound its horizon.

**O-d. Held-out corpus: OTel v4.**
- **Protocol:** the v3 protocol unchanged:
  - pinned demo;
  - 25 users;
  - normal period varied 8–15 min;
  - 5 min fault;
  - span metrics and attributed logs.
- **Size and naming:** 9 fault types × 4 repetitions = 36 cases, under its own corpus name (`otel_heldout_v4`) and IDs.
- **Sealing:** sealed and signed at capture. The manifest digest is recorded in the tracking row on the day of capture.
- **Unread until step 5:**
  - no build tool lists it (`BUILD_CORPORA` unchanged);
  - only the validation tool reads it, once.
- **Capture first.** v4 is captured before fixes A and B are built, so nothing built here was shaped by it.

**O-e. Refit chain, once, on build data** (OTel v3 and RCAEval build). Each stage reruns its existing build tool and selection rule and gets its own freeze entry, as in S2 and S3.1:
1. D-pipe grid, only if B passes its gate;
2. G-pipe ranker selection;
3. MAHC (priors, calibrator, floor);
4. router (τ_acc by R-d, refit confirmation).

The detector is unchanged.

**O-f. Adoption rule, fixed now and applied once.** Compare the current frozen chain (*old*) with the refit chain (*new*):

| Corpus | Measure | Rule |
|---|---|---|
| OTel v4 (held out) | HELIOS-Full fused HR@3 | new ≥ old + 2 cases (of 36) |
| RCAEval build | HELIOS-Full fused HR@3 | new ≥ old |

- **If both hold,** *new* is frozen.
- **If either fails,** *old* stays frozen, and the fixes and their results are reported as exploratory.
- **No tuning between scoring and decision.** The rule is applied once. There is no second attempt on v4.
- **Also reported,** per fault type, with no effect on the decision:
  - HELIOS-noRouter on v4;
  - v3 in sample, beside v4 held out.

**O-g. After the decision:**
- **If *new* is adopted:** the S3.3 replay is rerun on it (run 3).
- **The S2.9 rater-training ledgers stay as generated.** They are training material, not evidence.
- **OSF addendum:** the pipeline changes and the v4 corpus are added to the draft.

## 3. Work and effort

| Step | Work | Effort |
|---|---|---|
| 1 | Pre-run entry (this design) | — |
| 2 | v4 corpus in the campaign tool; capture (unattended, about 12 h); seal; verify | ½ day plus the capture |
| 3 | Fix A: span error-origin analysis, the G-pipe feature, tests | 1½ days |
| 4 | Fix B: the memory-trend channel, the build-data gate, tests | 1 day |
| 5 | Refit chain, with freeze entries | 2 days, mostly automated |
| 6 | Validation tool, a single scoring on v4 and RCAEval build, decision | 1 day |

## 4. Risks

- **A shifts G-pipe's ranker weights.** paymentUnreachable's labelled root is the caller (checkout), and error origin points at payment. Ranker reselection is by leave-one-root-out HR@3, so a loss there shows before the freeze.
- **Fallback triggers (about half of OTel) misplace the before/after split for both fixes.** Error origin is robust to this: errors are absent before the fault, wherever the split falls. The memory trend is less robust, which is one more reason for B's gate.
- **36 held-out cases** detect only a large change. The +2 margin guards against noise, not against a small real loss; the per-fault report shows where any change comes from.

## 5. Result and decision (entry 81, 2026-11-08)

Validation run once (`bin/otel_fix_validate.py` at 957ef9a; report `calibration/otel_fix_validation.json`, 0def33e): 2,124 incident runs, none excluded; v4 L-pipe answers from the pinned model (digest checked), RCAEval build from the cache.

| | OTel v4 held out (36) | RCAEval build (495) |
|---|---|---|
| *old*, HELIOS-Full | 30/36 (83.33%) | 478/495 (96.57%) |
| *new*, HELIOS-Full | 30/36 (83.33%) | 478/495 (96.57%) |
| *old* and *new*, HELIOS-noRouter (reported) | 30/36 | 482/495 (97.37%) |

v4 per fault type, identical for both chains: 4/4 for adFailure, adHighCpu, adManualGc, cartFailure, paymentFailure, paymentUnreachable; productCatalogFailure 3/4; emailMemoryLeak 2/4; recommendationCacheFailure 1/4.

**Decision (O-f):** the v4 condition fails (30 against 30 + 2), the RCAEval condition holds, so ***old* stays frozen**. `data/frozen/` and every frozen hash are unchanged. Per O-g, no S3.3 replay run 3.

**What it shows (exploratory, Chapter 4):**
- Fix A improved G-pipe's own list (51/63 on build, cross-fitted) but changed no published answer: on the error faults the fused verdict follows D-pipe's error channel and the L-pipe, which both credit the callers. A further OTel change would start there (fix C, Stage B backlog).
- Fix B passed its gate (5/7) but lost in the D-pipe refit grid (entry 77) and was dropped.
- The frozen chain scores higher on held-out v4 (83.33%) than on the v3 build cases it was fitted on (79.37%).
- The code of both fixes stays behind parameters the frozen files do not set; `data/candidate/otel_fix/` and the build reports (entries 77–80) are the record.
