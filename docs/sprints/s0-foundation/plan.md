# Sprint S0 — Foundation · plan

**Window:** 2–13 Nov 2026 (10 working days) · **Milestone:** S2-M5 · **Exit tag:** `rb-s0-exit` · **Status:** closed 2026-10-24 ([exit report](exit_report.md))

*Recorded 2026-10-24 from the plan approved on 2026-10-23 (`helios_e2e_product_plan_2026-10.md` § S0, `helios_task_breakdown.md` § Sprint S0). The sprint ran 23–24 Oct, ahead of its window.*

## Goal

Align the protocol to the approved Chapter 3 and the owner's decisions D1–D12, then make it public and binding: OSF deposit 1.

## Entry conditions

- Proposal approved by the chair (2026-09-23).
- Integrity audit A–D merged (2026-10-22); the e2e plan and the 21-week re-baseline approved (2026-10-23).

## Tasks

| Task | Tier | Tracking | Effort | Depends on | Done when |
|---|---|---|---|---|---|
| S0.1 Dataset check (RCAEval licence, labels, modalities; AIOpsLab feasibility) | T1 | S2-M5-RES01 | done before the breakdown | — | Go / no-go per dataset recorded |
| S0.2 Protocol decisions as signed deviation entries | T1 | S2-M5-RES03 | ½ | — | Entries for every decision that changes the protocol |
| S0.3 Corpus and run design (D11) | T1 | S2-M5-RES02 | approved before the breakdown | S0.1 | Design approved by the owner |
| S0.4 Flag registry renamed to Ch3 names | T1 | S2-M5-ENG01 | 2 | S0.2 | Registry tests; 17 flags |
| S0.5 15 variants from Ch3 Table 17 and p.153 | T1 | S2-M5-ENG02 | 1 | S0.4 | Unique hashes |
| S0.6 Analysis plan, Families A, B, E | T1 | S2-M5-ENG03 | 1½ | S0.5 | Matches Ch3 Table 18 with D6 clarifications |
| S0.7 Metric contract | T1 | S2-M5-RES04 | 1 | — | One definition per metric; strata |
| S0.8 Seed register | T1 | S2-M5-ENG04 | ½ | — | Deterministic seed functions; layout hashed |
| S0.9 Ed25519 layer; integrity audit step E | T1 | S2-M5-ENG05 | 1½ | — | Public-key verification; prereg in `manifest_sig` |
| S0.10 Pre-registration, chair call, OSF deposit 1 | T1 | S2-M5-GATE01 | 1½ + call | S0.2–S0.9 | DOI in the deviation log; tag `osf-deposit-1` |
| S0.11 Lead-time items (owner) | — | S2-M5-RES05 | ongoing | — | Submitted / booked |

## Owner items

Chair call (baselines D5, CHASE value, clarifications D6); OSF account and upload; IRB application for RQ4 (D12); compute and API budget; baseline environments. (The second rater and adjudicator were added during the sprint, in S0.11.)

## Expected deviation entries

One per protocol decision (D1–D12, RB1–RB3, IN1–IN3), the flag rename, the variant rebuild, the analysis plan, the metric contract, the seed register, the Ed25519 layer, the call outcome and the DOI.

## Exit criteria

S0.1–S0.10 DONE; full gate green on main; DOI in the deviation log; lead-time items submitted or booked.

## Risks

- The chair does not agree the baselines or the CHASE value → the deposit waits.
- A protocol change found after the deposit → OSF addendum plus deviation entry.
