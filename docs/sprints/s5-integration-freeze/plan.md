# Sprint S5 — Integration and freeze · plan

**Window:** 1–12 Feb 2027 (10 working days) · **Milestone:** S2-M10 · **Exit tag:** `build-freeze` · **Status:** planned

Task details: `docs/tracking/helios_task_breakdown.md` § Sprint S5 (authoritative).

## Goal

Prove every variant runs end to end, certify the flags, pilot the whole pipeline on build data, then freeze the evidence build and deposit the freeze addendum on OSF. **Stage A build complete.**

## Entry conditions

`rb-s4-exit`. Rating rubric trialled and ready to freeze (S2.9).

## Capacity

8 days of tasks in 10 working days: 2 days of slack before the freeze.

## Tasks

| Task | Tier | Tracking | Effort | Done when |
|---|---|---|---|---|
| S5.1 System test of every variant | T1 | S2-M10-EVAL01 | 2 | 15 variants run end to end on build data |
| S5.2 Disjointness certification | T1 | S2-M10-EVAL02 | 1 | Every boolean flag gates exactly one code path; zero uncovered |
| S5.3 Exploratory pilot on build data | T1 | S2-M10-EVAL03 | 2 | Pilot report labelled exploratory; metrics, cost and timing populated |
| S5.4 Clean-environment replication | T1 | S2-M10-EVAL04 | 1 | Snapshot hashes and fused rankings reproduce on a fresh checkout |
| S5.5 LLM determinism probe | T1 | S2-M10-EVAL05 | ½ | Token-equality rate measured |
| S5.6 Build freeze | T1 | S2-M10-GATE01 | 1 | Tag `build-freeze`; VCL blocks any divergence |
| S5.7 OSF deposit 2 (freeze record + rating rubric) | T1 | S2-M10-GATE02 | ½ + upload | DOI in the deviation log |

## Owner items

- Decisions due 5 Feb from the S5.3 pilot numbers: compute for the campaign (S0.11 L5), 70B subset (L6), judge models (L7).
- OSF upload for deposit 2 (same account as deposit 1).
- IRB approval needed by about 5 Feb for RQ4 to run in phase E.

## Expected deviation entries

Freeze record (commit SHA, image and model digests, parameter hashes, price book, pool manifest); rubric hash (entry 38 follow-up); Tier-2 items moved to Stage B; the deposit-2 DOI.

## Exit criteria

S5.1–S5.7 DONE; tag `build-freeze`; deposit-2 DOI in the deviation log; exit report written.

## Risks

| Risk | Mitigation |
|---|---|
| A defect found after the freeze | Phase E rule: deviation entry; rerun or exclude with ledger entries, never edit |
| Pilot shows the campaign does not fit phase E on local hardware | Decide on rented compute by 5 Feb (L5) |
