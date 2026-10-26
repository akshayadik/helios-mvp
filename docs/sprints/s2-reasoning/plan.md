# Sprint S2 — Reasoning, consensus, narratives · plan

**Window:** 7–25 Dec 2026 (15 working days) · **Milestone:** S2-M7 · **Exit tag:** `rb-s2-exit` · **Status:** planned

Task details: `docs/tracking/helios_task_breakdown.md` § Sprint S2 (authoritative).

## Goal

The three peer pipelines produce calibrated verdicts; MAHC fuses them with calibrated confidence (IN2); every decision is on the signed Chain-of-Evidence ledger; narratives cite graph evidence and pass the grounding verifier (IN1); the rating protocol for H_fact is ready.

## Entry conditions

`rb-s1-exit`: sealed build data (S1.1, S1.2), UEG-C and pruner (S1.5, S1.7), verdict contract (S1.8). Second rater and adjudicator confirmed (S0.11 L2–L3) before S2.9 training.

## Capacity

15½ days of tasks in 15 working days, plus the raters' training time for S2.9.

## Tasks

| Task | Tier | Tracking | Effort | Depends on | Done when |
|---|---|---|---|---|---|
| S2.1 D-pipe completion (σ, determinism, anomaly trigger) | T1 | S2-M7-ENG01 | 1 | S1.8 | Bitwise rerun equality |
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
