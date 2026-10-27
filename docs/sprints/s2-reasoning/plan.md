# Sprint S2 — Reasoning, consensus, narratives · plan

**Window:** 7–25 Dec 2026 (15 working days); may start early once the owner confirms, as S1 did (S1 closed 2026-10-27, about five weeks ahead) · **Milestone:** S2-M7 · **Exit tag:** `rb-s2-exit` · **Status:** in progress — started early on 2026-10-27 (owner); end date unchanged

Task details: `docs/tracking/helios_task_breakdown.md` § Sprint S2 (authoritative).

## Goal

The three peer pipelines produce calibrated verdicts; MAHC fuses them with calibrated confidence (IN2); every decision is on the signed Chain-of-Evidence ledger; narratives cite graph evidence and pass the grounding verifier (IN1); the rating protocol for H_fact is ready.

## Entry conditions

`rb-s1-exit` — **met 2026-10-27**: sealed build data (RCAEval 495 build cases, S1.1; 63 trace-bearing OTel build cases, S1.2), UEG-C and pruner (S1.5, S1.7), verdict contract (S1.8), scoring path (S1.9), price book and cost (S1.10). Second rater and adjudicator confirmed (S0.11 L2–L3) before S2.9 training — **open, due 30 Nov**.

## Capacity

15½ days of tasks in 15 working days, plus the raters' training time for S2.9. With an early start the sprint has about eight weeks before 25 Dec; any time left over moves S3 forward to protect the over-committed S4. S2.9 training cannot start before rater 2 is confirmed.

## Tasks

| Task | Tier | Tracking | Effort | Depends on | Done when |
|---|---|---|---|---|---|
| S2.1 D-pipe completion (σ, determinism, anomaly trigger) | T1 | S2-M7-ENG01, ENG09, EVAL01, RES02 | 5 (was 1; design [s2_1_dpipe_trigger_design.md](s2_1_dpipe_trigger_design.md) §6a) | S1.8 | Bitwise rerun equality; shared trigger identical for every system; ≤5% false triggers on each build corpus |
| S2.2 G-pipe learned ranker (D9) | T1 | S2-M7-ENG02 | 3 | S1.5, S1.7, S1.2 | Rerun equality; build-data HR@3 reported (exploratory) |
| S2.3 Lean multi-agent L-pipe | T1 | S2-M7-ENG03 | 3 | S1.8 | Worker verdicts logged; leakage test passes; prompt SHAs frozen |
| S2.4 H_struct records | T1 | S2-M7-ENG04 | ½ | S2.3 | Counts stored per run |
| S2.5 MAHC with calibrated confidence (IN2) | T1 | S2-M7-ENG05 | 2½ | S2.1–S2.3 | σ counterexample (Ch3 p.157) gives different fused rankings; calibration curve reported |
| S2.6 Vote-only aggregator | T1 | S2-M7-ENG06 | ½ | S2.5 | noConsensus differs from Full on a fixture |
| S2.7 Chain-of-Evidence ledger | T1 | S2-M7-ENG07 | 1 | S2.5 | Ledger verifies; tamper test |
| S2.8 Narrative Engine with grounding verifier (IN1) | T1 | S2-M7-ENG08 | 2½ | S2.7 | Every displayed claim cites an element; rejection rate reported |
| S2.9 Rating rubric and blind labelling protocol | T1 | S2-M7-RES01 | 1½ + training | S2.8, S0.11 | κ ≥ 0.7 on 50 build-data narratives; rubric hash recorded |

## Owner items

- *Decided 2026-10-26:* detection trigger option (a) — one frozen, label-free detector gives HELIOS and the five baselines the same trigger time (S2.1; S2-M6-RES04). The detector's parameters need a deviation entry; the true-injection-time run is exploratory only.
- Rater training with rater 2 (S2.9): the 50-narrative training set may run into early January.
- Holiday week 28 Dec – 1 Jan is off.

## Carried in from S1 (exit report §5)

- **Build data for S2.1 and S2.2.** The 63 OTel build cases (`data/otel/`) are the only build data with traces; the RCAEval build corpus has none. Fault visibility varies (S1.2 results): `emailMemoryLeak` is near-silent, and the first repetition has fewer latency-histogram series, so the detector must not assume a fixed series set.
- **Candidate set on OTel graphs** includes demo infrastructure containers (Prometheus, Jaeger, OpenSearch, the collector, the load generator, flagd). Decide in S2.1–S2.2 whether candidates are filtered; a filter is a deviation entry.
- **K-hop check from the repository:** add an `otel_build` corpus to `bin/khop_calibrate.py` (S2.2). The exit check (K = 3, top-n = 50 kept; 63/63 with the floor) was run from a scratch wrapper.
- **σ** is `None` in every verdict until S2.1–S2.3 fill it (S1.8).
- `metric_contract.md` §9 correction waits for the next OSF deposit addendum (S1.8, S1.9).
- Owner, not blocking S2 tasks:
  - **Price book:** the AWS primary profile is fully verified (S3 Standard checked against the AWS price list on 2026-10-27, value unchanged). The GCP and Azure sensitivity profiles are still unverified; any changed value is a deviation entry before `build-freeze`.
  - **Chair call, mid-November 2026:** opportunity-cost figure, retention and review minutes, disclosure of the May capture defects (T13, T17). A call-reference doc with an outcomes table is prepared before the call.
  - **IRB (L1):** in progress, submission expected around 2026-11-03.

## Expected deviation entries

Detector parameters for the trigger (S2.1); G-pipe model and parameters (S2.2); prompts and model version (S2.3); λ and calibration method (S2.5); presentation-order seed block for the labelling tool (S2.9); any rubric decision that changes what H_fact measures.

## Exit criteria

S2.1–S2.8 DONE; S2.9 DONE or its training scheduled before S5; full gate green; tag `rb-s2-exit`; exit report written.

## Risks

| Risk | Mitigation |
|---|---|
| G-pipe learns service identity rather than behaviour (S0.1 F3) | No service identifiers in features; feature-audit test fails training otherwise |
| LLM non-determinism breaks rerun equality | Protocol A (greedy decoding); S5.5 measures token equality |
| noLLM narratives recognisable by style, weakening rater blinding | Neutral claim-plus-evidence format in the labelling tool (S2.9); reported as a limitation |
| κ below 0.7 in training | Revise rubric and retrain; adjudicator on standby |
