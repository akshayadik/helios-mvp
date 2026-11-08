# OTel build misses: are the faults visible? (diagnosis, exploratory)

2026-11-07 · build data only (63 `otel_build_v3` cases) · no code, parameter or ledger change · no deviation entry needed

## Question

HELIOS-noRouter's fused HR@3 on OTel build is 50/63 (79.4%), against 97.4% on RCAEval build. For each of the 13 misses: is the fault invisible in the recorded data (a testbed problem), or visible but ranked wrong (an implementation problem)?

## Method

1. **Re-run HELIOS-noRouter** over the 63 cases (`otel_run.py`). Settings: frozen detector, D-, G- and L-pipe and MAHC; L-pipe from the response cache. Then read each pipeline's and the fusion's rank of the labelled root from the CoE entries. This reproduces 50/63.
2. **Measure visibility per channel** (`otel_diag.py`). For each in-scope service, compare the fault period (injection to window end) with the pre-injection baseline in 60 s buckets.
   - Count channels use a Poisson-scaled shift: (after − before) / √(before + 1). They are:
     - spans;
     - error spans;
     - error-origin spans: an `ERROR` span none of whose child spans is `ERROR`, i.e. where an error starts in the trace;
     - error/warn logs;
     - the `span_error_calls_total` metric.
   - Level channels use a robust shift: median change / (1.4826·MAD + 1% of the baseline level). They are span p90 latency, span-mean-latency metric, CPU and memory.
   - For each channel the script records the root's shift and its rank among in-scope services.
3. **Find where errors start and what the fusion ranked instead** (`otel_origin.py`), and **count, per fault type, how often each channel ranks the root first** (`otel_signal_check.py`).

**Caveats:**
- The measures use the true injection time and the label, which the system never sees. They answer whether the information is in the data, not what HELIOS could compute.
- The channels were chosen after looking at the misses, on the same 63 cases the frozen parameters were fitted on. Any change built on them must be decided before measuring and checked on new cases (see the end).

## Results

Full table: `visibility_table.txt` (format: shift#rank).

| Fault (misses) | Fused picked instead | What shows the root in the data |
|---|---|---|
| recommendationCacheFailure (6 of 7) | frontend, product-catalog, frontend-proxy | Error spans rise sharply (+6 to +15) but rank 3rd. In the traces, errors *start* in product-catalog (`GetProduct`), and every one of those is a call made by recommendation. Span p90 latency ranks recommendation 1st in 3 of the 6 misses. |
| emailMemoryLeak (3 of 7) | quote, checkout, recommendation, ad | Memory ranks email 1st in **all 7** cases (+2.8 to +4.7). No errors at all. |
| paymentFailure (2 of 7) | frontend, checkout, shipping | Error origin ranks payment 1st in **all 7** (`PaymentService/Charge`). Error spans and the error metric rank it only 4th, behind callers that inherit the errors. |
| productCatalogFailure (1 of 7) | frontend, kafka, payment | Error origin ranks product-catalog 1st (+11, `GetProduct`). |
| adFailure (1 of 7) | recommendation, product-reviews, accounting | Error origin and error logs rank ad 1st, but sparse: about one error a minute (+0.8). |

**How often each channel ranks the root first, all 63 cases:** error origin 34, error/warn logs 27, span p90 23, memory 22, CPU 21. Per-service error totals (spans or metric) only 7, all of them cartFailure. Error origin is first in every case of adFailure (6), cartFailure, paymentFailure, paymentUnreachable and productCatalogFailure, and never in the three fault types without errors at the root.

## Conclusions

1. **None of the 13 misses is invisible.** Each fault leaves a signal that ranks the root first or close to it. This corrects the earlier reading that emailMemoryLeak and recommendationCacheFailure are near-silent: they are silent to the *detector's threshold* (all 14 cases use the fallback trigger), not in the data.
2. **The misses are mostly implementation, three mechanisms:**
   - **Error attribution.** D-pipe's error channel is `span_error_calls_total` per service (frozen weight 0.7), and G-pipe's error feature is the share of a service's spans that fail. When a downstream call fails, the callers' own spans fail too. The capture's error metric counts server and consumer spans only, but a caller's server span fails with its downstream call. So errors spread up the call chain, and frontend and checkout outrank the service where the error starts. (Corrected 2026-11-07: an earlier version said the metric counts callers' client spans.) That causes 4 misses: paymentFailure ×2, productCatalogFailure, adFailure.
   - **Resource weight.** Memory names email first in all 7 leak cases, but D-pipe's resource channel (CPU and memory together) has frozen weight 0.1. That causes 3 misses (emailMemoryLeak).
   - **Errors that start downstream.** recommendationCacheFailure makes product-catalog return errors, but only on calls from recommendation. A rule that "errors confined to one caller's calls point at the caller" would name recommendation; error origin alone names product-catalog, which is wrong. That covers 6 misses. This is the hardest case, and partly a labelling question (threat T14).
3. **A testbed fix is not needed for these misses.** It would change the measurement, not the system.

## What a fix would take

These are candidate changes, not decisions. Each needs a design note, a deviation entry before any refit, and a refit of everything downstream. The detector is unaffected; D-pipe, G-pipe, MAHC and the router would all refit.

- **Error origin** as the error signal: errors counted where they start in the trace, not on every span on the path. It goes either into D-pipe's error channel or as a G-pipe feature.
- **The resource weight.** w_resource was frozen at 0.1 from the S2.1 grid. A memory-trend channel or a regridded weight is the change; it would also need checking on RCAEval, where memory faults exist too.
- **Caller-confined errors** as a G-pipe feature, for faults whose errors appear in a dependency.

**Validation before any of it is adopted:**
- New OTel repetitions captured on the testbed (held out, never tuned on).
- RCAEval build HR@3 not lowered, since the same pipelines run the confirmatory pool.
- The rule decided before measuring.

## Reproduce

From the repository root, with `.env` loaded:

```
poetry run python docs/sprints/s3-routing/otel_diagnosis/otel_run.py OUT
poetry run python docs/sprints/s3-routing/otel_diagnosis/otel_diag.py OUT/otel.coe.jsonl OUT/diag.json
poetry run python docs/sprints/s3-routing/otel_diagnosis/otel_table.py OUT/diag.json
poetry run python docs/sprints/s3-routing/otel_diagnosis/otel_origin.py OUT/diag.json
poetry run python docs/sprints/s3-routing/otel_diagnosis/otel_signal_check.py OUT/diag.json
```

`OUT` must not exist. The scripts read build data only.
