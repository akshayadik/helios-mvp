# S3.5 — LLM-unavailable fallback

Tracking row S2-M8-ENG05 · Tier 2 · depends on S3.1 · 2026-11-07

## 1. Goal

When the local model cannot be asked, an incident run still completes on D and G, the outage is recorded as a covariate, and nothing is written to the L-pipe cache (S2-BL-17).

## 2. What happened before S3.5

- **Endpoint unreachable at the start of an incident.** `run_lpipe` returned a FAILED verdict (`l-pipe-connectivity-error`). This happened even when every prompt was already in the cache, because the cache key needs the model digest and the digest came only from the endpoint. Cache-only reruns therefore needed a running Ollama.
- **Endpoint up but every call failing.** Each worker was dropped (timeout, connection or HTTP), and the verdict was ABSTAINED.
- **Fusion.** MAHC and the vote-only aggregator already use RANKED verdicts only. In both cases above, the fused verdict was already D and G alone. Nothing recorded *why* the L-pipe contributed nothing.
- **Routing.** A routed run that escalated still recorded `terminal_arm` = Full or D+L, which was not true.

## 3. Decisions

**F-a. "Unavailable" means the model could not be asked at all.** The L-pipe output carries `llm_unavailable` with one of these values:

| Value | Meaning |
|---|---|
| `endpoint` | The digest request failed, and there was no pinned digest or no cache to read. |
| `cache_miss` | The endpoint was unreachable and every worker's prompt was missing from the cache. |
| `calls` | The endpoint reported its digest, then every model call failed (timeout, connection or HTTP). |
| none | Any worker got an answer, even an invalid one. A partial outage is visible per worker in the evidence (`dropped`), not in the covariate. |

**F-b. Cache-only reads.** When the endpoint is unreachable, the digest is pinned and a cache is attached, workers read the cache under the pinned digest.
- **Why a hit is safe:** entry 58 checks the served digest before any cache write, so a hit under the pinned digest is exactly the frozen model's answer.
- **A miss** drops the worker (`cache_miss`) without calling the model or writing the cache.
- **Evidence:** it gains `model_source: cache_only` only in this mode, so the evidence of runs with a served model is byte-identical to before.

**F-c. Routed fallback.** If a routed run escalates and the L-pipe reports `llm_unavailable`, the CoE routing step records:
- `fallback: true`;
- `terminal_arm` = `stage1_arm`.

These fields are unchanged:
- `escalate` and `escalation_reason`: what the router decided;
- the fused verdict: D and G only, as before;
- the replayed terminal time, which includes the wait for the failed L-pipe.

No pipeline is started by the fallback:
- With a graph, an escalated run has always already run G-pipe in stage 1 (`decide_g` runs it whenever D alone is infeasible, and the disagreement trigger needs G). The cheap arm is therefore D+G.
- Without a graph, or with G gated off, the cheap arm is D.
- A gated-off pipeline is never turned on, so the ablation variants keep their meaning (LLM-only stays LLM-only).

**F-d. Uniform runs** (noRouter, LLM-only) record the covariate only; they have no arm to fall back to.

**F-e. No new VCL flag.** The fallback is part of the router's behaviour under `cbr_routing`. F-a and F-b add no new behaviour while the model is up. A new flag would change every variant hash frozen in OSF deposit 1.

## 4. Analysis

The covariate goes into the OSF addendum draft (`plan.md`, "LLM availability covariate"):
- It is reported per variant and corpus beside every confirmatory result.
- If any incident in a paired comparison is affected, the comparison is reported with and without the affected incidents.
- Neither variant is rerun selectively.

## 5. Tests

| Area | File | What is covered |
|---|---|---|
| L-pipe | `tests/pipelines/l_pipe/test_unavailable.py` | the served run is unchanged; endpoint down without a cache, or with an unpinned digest; cache-only replay under the pinned digest; a cache miss writes nothing; every call failing; an invalid answer still counts as available |
| Runner, routed | `tests/test_runner_router.py` | escalation with the LLM down stays on D+G; without a graph it stays on D; an available LLM records none; a stopped run records nothing; a uniform run records the covariate only |
| Runner, end to end | `tests/test_runner_lpipe.py::test_model_down_with_a_cache_miss_runs_on_d_and_g` | the real L-pipe with the endpoint down: the run completes, the covariate is recorded and the cache stays empty |
