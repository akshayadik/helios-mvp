# Sprint S0 — exit record

**Date:** 2026-10-24 · **Tracking:** S2-M5-GATE02 · **Tag:** `rb-s0-exit` on main `4b637a8` (merge of PR #52) · **Plan:** `helios_e2e_product_plan_2026-10.md` § S0, `helios_task_breakdown.md` § S0 exit gate

S0 was scheduled for 2–13 November 2026 and closed early, on 24 October.

## 1. Exit criteria

| Criterion | Result | Evidence |
|---|---|---|
| S0.1–S0.10 DONE (breakdown, S0 exit gate) | Met | Tracking rows S2-M5-RES01–RES04, ENG01–ENG05, GATE01 all DONE |
| Full pre-push gate green on main | Met | §2 |
| OSF deposit 1 with DOI in the deviation log (plan S0.6) | Met | DOI 10.17605/OSF.IO/KMR3D; deviation entry 37; tag `osf-deposit-1` → `524b621` |
| Ledgers verify (plan S0.5) | Met | HMAC chains and anchors; Ed25519 `verify-public` with the public key only |
| Lead-time items submitted or booked (plan S0.7 / breakdown S0.11) | **Not met: carried over** | IRB not yet submitted; second rater and adjudicator not yet recruited. Tracked in S2-M5-RES05 with needed-by dates (`s0_11_lead_time_register.md`). Neither blocks S1: RQ4 is exploratory, and rating starts in phase E |

## 2. Gate on main `4b637a8`

| Step | Result |
|---|---|
| ruff check, ruff format, black | clean (136 files) |
| mypy (strict) | no issues in 136 source files |
| pytest | 588 passed; coverage 91.82% (threshold 90%) |
| verify_ledgers | deviation and reconciliation chains verified; exclusion ledger empty |
| log_deviation verify-public | 38 entries; 4 Ed25519-signed; every byte covered by the signed anchor |
| verify_captures | all captures verified (window hash and content seal) |
| verify_osf_freeze --verify | all artefacts match; freeze intact |
| validate-tracking | clean |
| ablation notebook | executes |

## 3. What S0 delivered

| Task | Row | SHA | Deviation |
|---|---|---|---|
| S0.1 dataset check (RCAEval GO; AIOpsLab spike moved to S1) | RES01 | `e854c0a` | — |
| S0.2 protocol decisions as signed entries | RES03 | `431b069` | 24–30 |
| S0.3 corpus and run design (D11), approved | RES02 | `d975842` | 25 |
| S0.4 flag registry to Ch3 names (17 flags) | ENG01 | `0af2346` | 31 |
| S0.5 15 variants from Ch3 Table 17 and p.153 | ENG02 | `0af2346` | 31 |
| S0.6 analysis plan, Families A, B, E | ENG03 | `86a8c87` | 32 |
| S0.7 metric contract; cpr → mrr | RES04 | `74ba779` | 33 |
| S0.8 seed register 10,000,000–10,009,999 | ENG04 | `a91534f` | 34 |
| S0.9 Ed25519 layer; audit step E | ENG05 | `83f4308` | 35 |
| S0.10 pre-registration, chair call, OSF deposit 1 | GATE01 | `524b621` | 36, 37 |
| S0.11 lead-time register, baseline environments (open) | RES05 | — | 38 |

## 4. Carried into S1 and later

- **S0.11 owner items** (L1 IRB, L2 second rater, L3 adjudicator, L6–L7 budgets, L9 Docker memory, L10 backups): see the register.
- **AIOpsLab feasibility spike:** S1 (S0.1 recommendation).
- **Pool sealing:** the pool manifest is hashed when the pool is sealed in S1.1 (S0.3 exit check).
- **Deposit 2 content already committed to:** the rating rubric (entry 38, task S2.9) and the build-freeze record (S5.6–S5.7).
- **Known test quirk:** `test_no_helios_paths_registered_at_stage0` fails when its file runs alone (also on main); the full suite passes. Not fixed in S0.

Next: Sprint S1 — data and graph (`helios_task_breakdown.md` § S1), starting with S1.1.
