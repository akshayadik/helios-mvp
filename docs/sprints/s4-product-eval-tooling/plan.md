# Sprint S4 — Product shell and evaluation tooling · plan

**Window:** 18–29 Jan 2027 (10 working days) · **Milestone:** S2-M9 · **Exit tag:** `rb-s4-exit` · **Status:** planned

Task details: `docs/tracking/helios_task_breakdown.md` § Sprint S4 (authoritative).

## Goal

HELIOS usable as a product (API, approval console, compose deployment), and everything needed to produce the evidence: baselines, metrics, run orchestrator with integrity gate, and the analysis suite.

## Entry conditions

`rb-s3-exit`. Baseline Docker environments from the S0.11 spike (`baselines/rcaeval/`); Docker memory at least 16 GB (S0.11 L9).

## Capacity

13½ days of tasks in 10 working days: over by 3½. The Tier-2 items S4.4–S4.7 (2½ days) move to Stage B first; the rest is Tier 1 and must not be rushed. Starting S1 early is the main way to recover this.

## Tasks

| Task | Tier | Tracking | Effort | Depends on | Done when |
|---|---|---|---|---|---|
| S4.1 API | T1 | S2-M9-ENG01 | 1½ | S2.7 | OpenAPI spec; contract tests |
| S4.2 Approval console (RQ4 instrument) | T1 | S2-M9-ENG02 | 2 | S4.1, S2.8 | Walk-through; timing capture verified |
| S4.3 Compose deployment | T1 | S2-M9-ENG03 | ½ | S4.1 | Fresh install from the compose file alone |
| S4.4–S4.7 PII redaction, shadow modes, FGSV lite, IOL lite | T2 | S2-M9-ENG04 … ENG07 | 2½ | — | Each behind its flag, or recorded as moved to Stage B |
| S4.8 Baselines from the RCAEval suite (D5) | T1 | S2-M9-ENG08 | 2 | S1.1, S0.10 | Each baseline produces ranked lists on build data; licences recorded |
| S4.9 Metrics suite | T1 | S2-M9-ENG09 | 1½ | S1.9, S2.4, S2.8 | Fixture values match hand computation |
| S4.10 Run orchestrator and integrity | T1 | S2-M9-ENG10 | 1½ | S4.9 | Dry run of the full schedule on fixtures |
| S4.11 Analysis suite | T1 | S2-M9-ENG11 | 2 | S0.6 | Fixture data reproduces hand-computed statistics |

S4.11 depends only on S0.6 and can be built earlier, in any sprint with slack.

## Owner items

- Docker memory (S0.11 L9) before S4.8.
- IRB approval status: S4.2 is the RQ4 instrument; the study runs only if approval arrives by early February.

## Expected deviation entries

PDiagnose adapter and any departure from RCAEval's script (S4.8); a baseline replaced by an alternate (S4.8; logged before phase E); Tier-2 items moved to Stage B.

## Exit criteria

Tier-1 tasks DONE; each Tier-2 task DONE behind its flag or recorded as moved; full gate green; tag `rb-s4-exit`; exit report written.

## Risks

| Risk | Mitigation |
|---|---|
| PDiagnose (B4) is a one-case script in RCAEval (S0.11 finding) | Faithful adapter with every departure recorded; alternates CIRCA, then CausalRCA |
| Trace-based baselines first run only now (no trace data outside the pool in RCAEval) | Run on OTel build captures converted to RCAEval format |
| CausalRCA takes 5–7 minutes per case | Used only if needed as an alternate; budget about a day for 240 cases |
| Over-committed sprint | Tier 2 to Stage B; S4.11 built early |
