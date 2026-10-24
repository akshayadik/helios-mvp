# Sprint S0 — exit record

**Date:** 2026-10-24 · **Tracking:** S2-M5-GATE02 · **Tag:** `rb-s0-exit` on main `4b637a8` (merge of PR #52) · **Plan:** [plan.md](plan.md); `docs/tracking/helios_task_breakdown.md` § S0 exit gate

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

## 4. Retrospective

### Plan vs actual

| | Planned | Actual |
|---|---|---|
| Window | 2–13 Nov 2026 (10 working days) | 23–24 Oct 2026 (2 days), closed 9 days before the window opened |
| Scope | S0.1–S0.11 | S0.1–S0.10 done; S0.11 open (owner items) |
| Added during the sprint | — | Baseline Docker environments (S0.11), rating-rubric task S2.9, deviation entry 38 |
| Deviation entries | one per decision and change | 15 (entries 24–38) |
| PRs | — | 16 (#38–#53), each through review and the full gate |
| Tests at exit | — | 588 passing, coverage 91.82% |

### Decisions and why

| Decision | Why | Record |
|---|---|---|
| Evidence from 240 recorded RCAEval cases, not 16,000 live runs (RB1, D11) | Feasible by 31 March with clean separation of build and confirmatory data | entry 25; `docs/tracking/s0_3_d11_corpus_run_design.md` |
| 8B model for confirmatory runs, 70B as sensitivity (RB2) | Runs on owner hardware; 70B only if budget allows | entry 26 |
| Five baselines B1–B5 in priority order, alternates CIRCA then CausalRCA; CHASE value 0.60 with 0.61 in the sensitivity band | Agreed with the chair on the call; chosen from published RE2-TT results | entry 36; call-reference doc |
| Ed25519 signatures on top of the HMAC chain (D7) | Anyone can verify the log with the public key, without the secret | entry 35 |
| Binding seed register with a fixed block layout | Ch3 p.108 range; two confirmatory runs never share a seed | entry 34 |
| `PipelineVerdict.cpr` renamed to `mrr` | The field held a reciprocal rank, not a cost; CpR now means only cost | entry 33 |
| OSF foreknowledge: "observed the data, not performed the analyses" | S0.1 inspected labels and one pool case, and published RE2-TT results shaped baseline choice; saying so is stricter than claiming no contact | OSF registration |
| Rating rubric deposited at deposit 2, not deposit 1 | A rubric can only be trialled on real narratives; Ch3 already puts rater calibration before confirmatory labelling | entry 38 |

### What went wrong, and what changed because of it

| Problem | How it was caught | Change |
|---|---|---|
| CI failed on `loo_cv_cpr` after the `cpr → mrr` rename: only the ablation notebook read that key | CI notebook job | Notebook execution added to the local gate (CLAUDE.md); renames now search `*.ipynb` |
| Baseline accuracy figures in the call doc were written without checking the source paper | Caught before the call, when the cells were checked against the paper | Values re-checked against the paper's Table 6; a weak method (multi-source CIRCA) dropped from the shortlist |
| First pre-registration draft labelled only a sample of narratives for hallucination, contrary to Ch3 | Check against Ch3 before deposit | Aligned to every Full and noLLM narrative; plan documents still said "sample" until S0.11 fixed them |
| Regenerating the freeze after the DOI re-stamped every timestamp in the deposited JSON | `git diff` against the deposited commit | Deposited bytes restored; only `manifest_sig` recomputed; rule saved: never `--generate` after a deposit |
| The deposited metric contract says the rubric was deposited; it was not | S0.11 planning | Deviation entry 38 |
| gitleaks flagged four identifiers named `*_KEY` | Pre-commit | Renamed (`*_FIELD`, `*_VAR`) rather than allow-listed |
| An immutable tracker column (`Gate`) edited on a new DONE row | Tracking validator (R5) | Reverted before commit |
| Changing into a subdirectory blocked every tool call: hooks use relative paths | Session lock-up, recovered by the owner running `! cd` | Fix proposed (`$CLAUDE_PROJECT_DIR` in hook commands), awaiting owner approval |

### Design-science notes (for Chapter 4)

- **The integrity layer (C1) was evaluated in use, not only in tests.** During S0 it caught real errors before they reached main: the tracking validator (R5), the OSF freeze check (re-stamped timestamps), the CI notebook job (stale key), pre-commit secret scanning (key-like names), and `verify-public` confirming 38 entries with only the public key. Entry 35 was also verified independently with `openssl`.
- **The protocol artefact went through two external evaluations:** the chair's review on the call (every proposal agreed) and public registration on OSF (DOI 10.17605/OSF.IO/KMR3D), with the deposited archive matched byte for byte to commit `524b621`.
- **Build–evaluate cycles in S0:** the metric contract (MRR conflated with CpR, then separated); the labelling protocol (sample, then every narrative, then rubric timing in entry 38); the baselines (draft shortlist, then corrected against the source, then agreed with the chair).

## 5. Carried into S1 and later

- **S0.11 owner items** (L1 IRB, L2 second rater, L3 adjudicator, L6–L7 budgets, L9 Docker memory, L10 backups): see the register.
- **AIOpsLab feasibility spike:** S1 (S0.1 recommendation).
- **Pool sealing:** the pool manifest is hashed when the pool is sealed in S1.1 (S0.3 exit check).
- **Deposit 2 content already committed to:** the rating rubric (entry 38, task S2.9) and the build-freeze record (S5.6–S5.7).
- **Documentation found stale at the S0 sync** (fixed in the sync: dashboard, document register, seed register, variant registry; carried to S1: `ablation_architecture.md` flag names, new validity threats, missing `data/snapshot_registry.jsonl`). `vcl_manifest_tracking.md` should have been updated in S0.4–S0.5 (PR #43); it was added late.
- **Known test quirk:** `test_no_helios_paths_registered_at_stage0` fails when its file runs alone (also on main); the full suite passes. Not fixed in S0.

Next: Sprint S1 — data and graph (`helios_task_breakdown.md` § S1), starting with S1.1.
