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
- **D-pipe stays metrics-only.** Its span-metric error series carry only `service_name`, so they cannot tell where an error starts. Reading traces in D-pipe would also blur what HELIOS-D (A-H3) ablates.

**O-c. Fix B: a memory-trend channel in D-pipe, built only if it passes a build-data gate.**
- **The channel:** memory is scored apart from CPU, as a sustained rise. The candidate statistic is the post-trigger memory slope, scaled by the variability of pre-trigger slopes, upward only (as D-h).
- **The weight:** it gets its own weight, w_memory, in D-pipe's grid. The objective is unchanged from S2.1: the mean of per-corpus HR@3 on OTel and RCAEval build, with the frozen trigger. The grid is fixed in the build-run entry before the run.
- **Gate, fixed now:** the channel enters the refit only if, on build data with the frozen trigger, it beats the current resource channel at ranking email among in-scope services in at least 5 of the 7 leak cases. It must also not lower D-pipe's build HR@3 on RCAEval or on the other 8 OTel fault types.
- **If B fails the gate,** it is dropped and recorded; A goes ahead alone.
- **RCAEval has memory faults,** so B is the change that can touch the confirmatory corpus. That is why it is gated.

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
