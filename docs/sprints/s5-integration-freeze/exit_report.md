# Sprint S5 — exit record

**Date:** 2026-11-20 · **Tracking:** S2-M10-GATE03 · **Exit tag:** `build-freeze`, annotated, on `main` `c4037c0` (merge of PR #113), pushed 2026-11-20; deposit tag `osf-deposit-2` on `3e657eb` · **Gate run on:** `main` `59dad6a` (merge of PR #116) · **Plan:** [plan.md](plan.md); `docs/tracking/helios_task_breakdown.md` § Sprint S5

S5 was scheduled for 1–12 February 2027. Its verification part started early on 15 November (owner), and the sprint closed on 20 November, about eleven weeks before its window. Every S5 change merged through a PR: the plan-refresh PR, then #101–#116. **Stage A build complete:** the evidence build is frozen, the confirmatory pool opens only for that build, and both freeze inputs are public on OSF.

## 1. Exit criteria

| Criterion | Result | Evidence |
|---|---|---|
| S5.1–S5.7 DONE | Met | Rows EVAL01–EVAL05, GATE01, GATE02 DONE (§3) |
| RES01 DONE | Met | S2-M10-RES01 DONE (`0a18b92`, #106): S4 documentation carry-ins and the addendum draft |
| Tag `build-freeze` | Met | Annotated, on `c4037c0`, created on the owner's OK. `bin/build_freeze.py --check` and `--verify` pass on a fresh worktree of the tag |
| Deposit-2 DOI in the deviation log | Met | Entry 103: DOI 10.17605/OSF.IO/8PJ5A; zip SHA-256 `cf11125d375b…` confirmed through the OSF API; tag `osf-deposit-2` |
| Full gate green on main | Met | §2 |
| Exit report, with the status of every carried-in item | Met | This document; carried-in items in §4.4 |
| Rating rubric trialled and frozen (S5 entry condition; row S2-M7-RES01) | **Partly met** | The rubric was frozen and deposited (entry 102, SHA-256 `f705edb81576…`) but not trialled: rater training needs raters, recruited in December (owner decision). Carried over (§5) |
| P1 component-review items closed before the freeze | **Not met for CR-03** | CR-03 (CONFIRMED less reliable than PROVISIONAL on RCAEval) is open, and the MAHC state rule was frozen as built. CR-21 and CR-22 were fixed in the S5.4 report and are now marked DONE in the backlog. Carried over (§5) |

## 2. Gate on main `59dad6a`

Run with `set -o pipefail` on `46bef2a`, which is `59dad6a` plus the commit that opens the GATE03 row (tracker only).

| Step | Result |
|---|---|
| ruff check, ruff format, black | clean (407 files) |
| mypy (strict) | no issues |
| pytest | full suite passes; coverage 96.82% (threshold 90%; 96.59% at the S4 exit) |
| verify_ledgers | deviation and reconciliation chains and anchors verified; exclusion ledger empty |
| log_deviation verify-public | 103 entries; 35–103 Ed25519-signed; every byte covered by the signed anchor |
| verify_captures | all captures verified (window hash and content seal) |
| verify_osf_freeze --verify | all artefacts match; freeze intact |
| validate-tracking | clean; every tracker commit valid (range mode) |
| ablation notebook | executes |
| console tests (`node --test tests/console/*.test.mjs`) | 16 pass. The gate's first attempt passed the directory instead of the glob, which Node 26 treats as a failing test file; rerun as CI runs it |
| `bin/build_freeze.py --check` | frozen build: `main` still matches the record at the tag |

## 3. What S5 delivered

| Task | Row | SHA | Merge | Deviation |
|---|---|---|---|---|
| Plan refresh with the S4 carry-overs and the proposed split (verify now, freeze when its inputs are in) | — | — | plan-refresh PR | — |
| S5.2 Disjointness certification: the audit recognises manifest readers; every boolean flag gates exactly one code path; three no-consumer flags declared and tested | EVAL02 | `1ea6272` | #101 | 90 |
| S5.1 System test: all 13 runnable variants end to end on both build corpora, 7,254 runs, no exclusions; noCogni and HIS3 refused with the recorded reason | EVAL01 | `5693319` | #102 | — |
| S5.5 LLM determinism probe: 8 of 57 RCAEval metric-worker prompts answer differently when asked again (0 of 17 on OTel); top-1 and top-3 set unchanged in every changed pair | EVAL05 | `2cffb8d` | #103 | 91 |
| S5.3 Exploratory pilot on build data, with the determinism join and the numbers for L5–L7 | EVAL03 | `69015ef` | #104 | 91 |
| S5.4 Clean-environment replication: every HELIOS snapshot hash and ranking reproduces on a fresh clone; Multi-source RCD reorders 3 of 495 RCAEval cases | EVAL04 | `2273a12` | #105 | — |
| RES01 S4 documentation carry-ins and the OSF addendum draft | RES01 | `0a18b92` | #106 | — |
| S5 reporting rules in the analysis (analysis-v2) | ENG01 | `eef31c8` | #107 | 93–96 |
| Price book v3: GCP and Azure profiles verified; router stamp | ENG02 | `e3e4758` | #107 | 97 |
| CR-02 D-pipe call edges | ENG03 | `5efd348` | #108 | 98 |
| CR-01 router reward fitted to the top-1 hit, re-frozen | ENG04 | `496962e` | #108 | 99 |
| S5.3 reading refreshed after CR-01 and CR-02 | EVAL06 | `ee64627` | #108 | 98, 99 |
| S5.4 HELIOS part rerun on a fresh clone after CR-01 and CR-02 | EVAL07 | `ee64627` | #108 | 98, 99 |
| Replication compare: rows moved only by timing-derived hypotheses | ENG05 | `c789e2c` | #109 | — |
| OSF addendum 1 (entries 46–99), DOI 10.17605/OSF.IO/VG5TE; E-H5 reading decided | RES02 | `168d6a0` | #110, #111 | 92, and the deposit entry `fec687b3c173` |
| S5.6 Build freeze: the record tool and the frozen-build pool gate (#112); entry and record (#113); tag `build-freeze`; tests keep this repository locked (#114) | GATE01 | `c4037c0` | #112–#114 | 101 |
| S5.7 OSF deposit 2: rubric frozen before training (#115), deposit recorded (#116), DOI 10.17605/OSF.IO/8PJ5A, tag `osf-deposit-2` | GATE02 | `3e657eb` | #115, #116 | 102, 103 |

### Main results (build data, exploratory)

- **Every variant runs (S5.1).** 7,254 runs on OTel v3 and RCAEval build, no exclusions and no run errors; every switched-off flag leaves its mark on every run, and no flag does anything the S5.2 certificate does not declare.
- **Determinism (S5.5).** Greedy decoding is not fully deterministic on this model server (8 of 57 RCAEval prompts). The effect on rankings is small: one RCAEval case changed for 9 variants, never in top-1 or the top-3 set.
- **Pilot after CR-01 and CR-02 (S5.3 refresh).** HELIOS-Full's top-1 rises on every build directory and its top-3 rises or holds; no Family A or B reading flips against HELIOS. A-H1 on OTel weakens (noLLM gains more from CR-02 than Full). The compute projection for phase E is about 5 h on this machine (L5: no rented compute).
- **Replication (S5.4 and its rerun).** HELIOS reproduces exactly on a fresh clone, before and after CR-01 and CR-02: every outcome, snapshot hash, per-pipeline ranking and fused ranking of 7,254 runs; analyses identical outside the timing-derived fields. Multi-source RCD's reordering (CR-23) was accepted as an environment difference and gets a reporting rule (entry 96).
- **Freeze (S5.6).** 245 frozen files, frozen-paths digest `8078c267c95f…`. The pool opens only for a checkout that holds the tag, the tagged record and every frozen file unchanged; a pool campaign records the digest and refuses another build.

## 4. Retrospective

### 4.1 Plan vs actual

| | Plan | Actual |
|---|---|---|
| Window | 1–12 Feb 2027, 10 working days, no slack | 15–20 Nov 2026 (verification from 15 Nov; freeze and deposit on 20 Nov) |
| Tasks | S5.1–S5.7, RES01 | All of them, plus eight rows the sprint found it needed: ENG01–ENG05, EVAL06, EVAL07, RES02 |
| Freeze inputs | Frozen rubric, E-H5 decision, GCP and Azure profiles, chair call | E-H5 (entry 92), price-book-v3 (entry 97) and addendum 1 in; rubric frozen before training (entry 102); chair call skipped (owner, 20 Nov) |
| Deviation entries | Freeze record, rubric hash, deposit-2 DOI, possibly S5.2 | 14 entries, 90–103 |

### 4.2 Decisions and why

- **Verify now, freeze when the inputs are in** (plan refresh). The verification part needed only build data, so it ran eleven weeks early; the one-way steps waited for their inputs. This left room for CR-01 and CR-02 before the freeze.
- **Component review before the freeze** (backlog, 16 Nov). The S5.1 and S5.3 build campaigns were read component by component. Two ranking changes (CR-01, CR-02) went through design note, owner-approved entry, re-freeze and a replication rerun; the reporting gaps became rules (entries 93–96); the rest was deferred, refused or recorded.
- **A freeze enforced by code, not by a tag** (S5.6 design). The tag alone used to unlock the pool. The design added a record of every frozen file and a divergence check that every pool gate runs, so Stage B on `main` is locked out of the pool by construction.
- **Chair call skipped** (owner, 20 Nov). The S5 plan listed the end-of-November call as a freeze input. The owner chose not to wait; feedback after the freeze goes through a deviation entry or is reported as a limitation (entry 101).
- **Rubric frozen before rater training** (owner, 20 Nov, entry 102). Raters are recruited in December, after the confirmatory runs. Freezing the rubric now keeps it independent of the results; A-H7 is tested whatever the other results are.

### 4.3 What went wrong and what changed

- **Baseline export defect (S5.5).** Every RCAEval baseline rerun failed on a defect in the baseline export when a modality was missing. Fixed with export v2 and the Family B input rules (entry 91) before the pilot.
- **Baseline nondeterminism (S5.4).** Multi-source RCD reorders its list on 3 of 495 cases with identical inputs. Diagnosed, accepted as an environment difference, and given a reporting rule (entry 96, CR-23).
- **Replication compare too strict (ENG05).** Rows whose own p-value was identical were reported as differing because a timing-derived hypothesis moved past them in the step-down order. The compare now names these rows as moved by timing.
- **Tests depended on the tag (#114).** Once `build-freeze` existed, a clean checkout of `main` was the frozen build, so two tests that relied on the pool being always locked failed in CI. An autouse fixture now keeps this repository locked in tests, while the freeze tests' temporary repositories get the real check. `tests/` is not frozen, so at the tag itself the two tests still see an open pool and fail; this does not affect any evidence run.
- **Secret scanner false positive (#113).** gitleaks read three SHA-256 digests in the record as API keys. The record is allowlisted like `poetry.lock`.
- **CR-03 left open.** The P1 item on MAHC's CONFIRMED label was not fixed before the freeze. CpR reads the state, so a change now needs a deviation entry and a rerun. Carried over (§5).

### 4.4 Items carried in from S4

| Item | Status |
|---|---|
| `ablation_architecture.md` stale for S4 | Done in RES01 (v0.14, 2026-11-18) |
| `r1_traceability_matrix.md` §2 note on FGSV and IOL lite | Done in RES01 |
| OSF addendum draft without S4 items | Done: addendum 1 covers entries 46–99 and was deposited (VG5TE) |
| S5.1 includes noFGSV and noIOL; noCogni and HIS3 refused | Done (S5.1) |
| S5.3 joins `determinism.json` into `eval_run` | Done (S5.3) |
| Pool-only checks after `build-freeze` (span status-code format, rebuilt series) | Carried to phase E, first day (§5) |

### 4.5 Design-science notes (Chapter 4)

- **Build–evaluate episode: pilot → component review → change → re-evaluate → replicate.** The S5.3 pilot exposed a router reward misaligned with the top-1 measure and a D-pipe that ignored observed call edges. Both were redesigned (CR-01, CR-02), re-frozen, re-piloted and replicated on a fresh clone before the freeze, all on build data. This is the last evaluation loop that may change the artefact before the confirmatory evidence.
- **Freeze as an artefact property.** The freeze is part of the artefact (C1): the VCL-side divergence check makes "only the frozen build reads the confirmatory pool" a property the code enforces and a test checks, not a convention.
- **Instrument fixed before data.** The H_fact rubric and the build are fixed and public before any confirmatory narrative or result exists; the order of freeze, deposit and data collection is visible in the signed log (entries 101–103) and the OSF time stamps.

## 5. Carried over

| Item | Owner | Due | Reference |
|---|---|---|---|
| Recruit two raters and one adjudicator (systems background, external) | AA | December 2026 | Entry 102; row S2-M5-RES05 |
| Rater training on build data to κ ≥ 0.7 with the frozen rubric; `bin/label_server.py keygen` and the `.env.labelling` backup; row S2-M7-RES01 DONE | AA, Claude | December 2026 – early January 2027 | Entry 102 |
| Confirmatory labelling of the 480 Full and noLLM pool narratives; A-H7 reported as incomplete, never dropped, if not done by 31 March | Raters, adjudicator | Before 31 March 2027 | Entry 102 |
| CR-03 MAHC CONFIRMED label: decide between a Stage B fix and a reported limitation. CpR reads the state, so any change to the frozen build needs a deviation entry and a rerun | AA | Before phase A reporting | Backlog CR-03 |
| Open P2 and P3 component-review items (CR-04 to CR-08, CR-12, CR-13, CR-15, CR-19, CR-20): Stage B or phase A | AA, Claude | Stage B plan | Component review backlog |
| Phase E pool-only checks (span status-code format, rebuilt series) | Claude | Phase E, first day | S4 carry-over |
| Phase E plan refresh: start date, capacity, raters' timing, runs from the `build-freeze` checkout | Claude | Before phase E starts | `docs/sprints/e-evidence/plan.md` |
| Compute decisions L6 (larger-model sensitivity) and L7 (judge models) from the S5.3 numbers | AA | 5 February 2027 | Row S2-M5-RES05 |
| IRB approval for RQ4 (E4 only) | AA | 5 February 2027 | L1 |
| Back up `.env` (HMAC secret, Ed25519 private key), the L-pipe response cache and `data/labelling/build` | AA | Now | L10 |
| Hook commands use `$CLAUDE_PROJECT_DIR` (`.claude/settings.json` change) | AA | Any time | Open since S0 |
