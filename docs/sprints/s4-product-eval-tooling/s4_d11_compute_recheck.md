# D11 compute recheck against the measured escalation share

**Date:** 2026-11-11 · **Tracking:** S2-M9-RES01 · **Carried from:** S3 exit report §6 · **Reads:** build data only (L-pipe response cache, S2.8 narrator report, S3.1 router report); no pool data or labels

The D11 run design (`docs/tracking/s0_3_d11_corpus_run_design.md` §4, approved 2026-10-23, in OSF deposit 1) estimated "about 1,500 runs invoke the L-pipe … roughly 30–50 hours" on the 8B model on this machine, assuming the cheap-first router. That document is frozen in deposit 1 and is not edited; this note replaces its estimate for planning (S0.11 L5, S5.3 pilot).

## Result

**The escalation share does not drive compute.** The L-pipe workers' inputs do not depend on the variant, so the variants of one incident share one set of worker calls through the response cache (`helios/pipelines/l_pipe/cache.py`, S2.3 design §5.6). HELIOS-LLM-only and HELIOS-noRouter call the L-pipe on every case anyway, so every pool case's worker calls are made once, whatever the router does. The router's share changes the *recorded* cost and timing of each run (CpR and TTT replay the cached call's tokens and wall time), not the wall-clock compute of the campaign.

**What does drive compute is the LLM narrator**, which was not in the May estimate. It runs on every run of every variant with `l2c_llm` and `coe_narrative` ON, escalated or not (`helios/orchestrator/runner.py`, step N), and its prompt is built from the variant's own CoE entry, so it is counted here without cache sharing.

| Scenario | Wall-clock model time for E1 + E3 |
|---|---|
| Central: measured mean times per call kind, no slot retries | **5–6 h** |
| Conservative: every call at the overall mean | **11–14 h** |
| Extreme: every call at the 90th percentile, every narrator slot retried once | **52–67 h** |

Each range runs from 7 to 9 narrated variants (below) and includes the 10% determinism rerun, which bypasses the cache. Phase E (15 Feb – 12 Mar) has about 26 days. Even the extreme case fits on this machine. **No change to the run design, so no deviation entry.**

## Inputs

| Input | Value | Source |
|---|---|---|
| Pool | 240 cases | D11 §1 |
| Worker calls per pool case | 2 (metric and log; the trace worker is off on RCAEval-format data) | S2.3 (entry 57, L-f); S2-BL-01 |
| Unique worker calls | 480 | 240 × 2, shared by every LLM variant |
| Calls in the build cache | 4,900; mean wall time 8.45 s; median 5.74 s; 90th percentile 21.17 s | `data/cache/lpipe_cache.sqlite` (read-only) |
| Worker vs narrator call time | Long prompts (over 1,200 tokens, 2,672 calls): mean 13.18 s; short prompts (2,228 calls): mean 2.79 s | Same cache. The cache stores no call kind; long = worker and short = narrator is inferred from prompt size and call counts. The S5.3 pilot checks it |
| Narrator calls per narrative | 2.27 (560 slots over 247 RCAEval held-out narratives); first-pass slot acceptance on held-out: every slot, so no retries | `docs/sprints/s2-reasoning/calibration/narrator_final.json` |
| Router escalation share | RCAEval build 197 of 495 held out (39.8%); OTel build 63 of 63. Pool share unknown (RCAEval *with* traces, never seen by the router, S2-BL-01) | S3.1 design §11 |

## Which variants call the model

| Variant | Family | Workers | Narrator |
|---|---|---|---|
| HELIOS-Full, HELIOS-noConsensus, HELIOS-noStructural | A | On escalation (routed) | LLM, every run |
| HELIOS-LLM-only, HELIOS-noRouter | A | Every case (uniform) | LLM, every run |
| HELIOS-noLLM, HELIOS-D, HELIOS-G | A | Never | Template, no model call |
| HELIOS-noACP, HELIOS-noReconcile | E | On escalation | LLM, every run |
| HELIOS-noFGSV, HELIOS-noIOL | E | On escalation | LLM, every run — **only if S4.6 / S4.7 are built by the freeze** |
| HELIOS-noExpl | E | On escalation | None (`coe_narrative` OFF) |
| HELIOS-noCogni, HELIOS-HIS3 | E | — | Not run in phase E (below) |

That gives 7 narrated variants (5 confirmatory and 2 exploratory), or 9 if S4.6 and S4.7 are built: 1,680–2,160 narrated runs, 3,809–4,897 narrator calls.

**Runs that invoke the L-pipe** (the May figure's unit), with 6–8 routed LLM variants: 1,053–1,244 at the RCAEval build share, up to 1,920–2,400 if the pool escalates every case. The May figure of about 1,500 sits inside this range. With the cache it no longer measures compute.

## Exploratory variants whose mechanism is not built

Five flags have no consumer outside `helios/vcl/`: `p4_cognitive`, `fgsv_ks_gate`, `iol_self_telemetry`, `his_tier` and `sampling_regime_tag`. Today HELIOS-noCogni, HELIOS-noFGSV, HELIOS-noIOL and HELIOS-HIS3 therefore behave exactly like HELIOS-Full. D11 §4 already schedules exploratory runs only for "each Tier-2 variant built by the freeze", and E-H1 (cognitive) and E-H9 (HIS tiers) are Stage B work (B1, B4, B5). So noCogni and HIS3 are left out of phase E without any change to the design. noFGSV and noIOL run only if S4.6 and S4.7 are built. S4.10's schedule must enforce this rule and refuse an exploratory variant whose flag has no consumer, so that no Full duplicate is reported as an ablation.

## Consequences for S4 and S5

- **S4.10 (orchestrator).** Ordering does not change outputs (greedy decoding, cache keyed on content), but the first run of a case records the wall time that every later variant replays. The schedule should make that first run the same for every case (for example, HELIOS-noRouter first) and record the order. The determinism rerun must bypass the cache.
- **S4.9 (metrics).** CpR and TTT stay per run (replayed), so the router's saving shows in A-H5 as designed; this note does not affect any metric.
- **S5.3 pilot.** Measures worker and narrator time per call on build data with the call kind recorded, and confirms the attribution above. On the pool, Train-Ticket digests are longer than SockShop's, which the conservative and extreme rows allow for.
- **L5 (compute decision, 5 Feb).** Local compute is sufficient on every scenario here. L6 (70B subset) and L7 (judge models) are separate and not covered.
