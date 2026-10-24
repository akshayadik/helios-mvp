# Phase E — Evidence collection · plan

**Window:** 15 Feb – 12 Mar 2027 (20 working days) · **Milestone:** S2-M11 · **Exit tag:** `rb-e-exit` (proposed) · **Status:** planned

Task details: `docs/tracking/helios_task_breakdown.md` § Phase E (authoritative); design: `docs/tracking/s0_3_d11_corpus_run_design.md`.

## Goal

Run the frozen build on the sealed confirmatory pool and collect every pre-registered measurement. **No code changes.**

## Entry conditions

Tag `build-freeze`; OSF deposit 2 DOI in the deviation log; rubric frozen; raters trained (κ ≥ 0.7); compute decided (S0.11 L5).

## Streams

| Stream | Tracking | Work | Done when |
|---|---|---|---|
| E1 Confirmatory ablation (Family A) | S2-M11-EVAL01 | 8 variants × 240 pool cases (1,920 runs) | Every cell complete or excluded with reasons |
| E2 Baselines (Family B) | S2-M11-EVAL02 | 5 baselines × 240 cases (1,200 runs) | Paired tables complete |
| E3 Exploratory | S2-M11-EVAL03 | Built Tier-2 variants × 240 | Results labelled exploratory |
| E4 RQ4 user study | S2-M11-RES01 | If IRB approved: 24 participants, Full vs noExpl, Latin square | Dataset stored; IRB number logged |
| E5 Rating | S2-M11-RES02 | Two raters label every Full and noLLM narrative (480 each); κ ≥ 0.7; adjudicator below; judges if budget | Agreement reported |
| E6 Sensitivity | S2-M11-EVAL04 | 70B subset if budget; 10% rerun replication | Reported |

## Owner items

Rater 2 and adjudicator available for E5; RQ4 sessions with participants (E4, if approved).

## Rules

- A defect found here is fixed under a deviation entry; affected runs are rerun or excluded with ledger entries, never edited.
- Runs use registered seeds only; the run seed is set by case position in the sealed pool order and the system slot.
- Labelling starts only after deposit 2 carries the frozen rubric.

## Exit criteria

Every cell complete or formally excluded; inclusion reported; 10% clean-environment replication; tag `rb-e-exit`; exit report written.
