# Sprint S4 — exit record

**Date:** 2026-11-14 · **Tracking:** S2-M9-GATE01 · **Tag:** `rb-s4-exit` on `main` `5cd8b37` (merge of PR #98), annotated and pushed · **Plan:** [plan.md](plan.md); `docs/tracking/helios_task_breakdown.md` § S4

S4 was scheduled for 18–29 January 2027. It started early on 11 November (owner) and closed on 14 November. Every S4 change merged through a PR with a green CI run (PRs #88–#98).

## 1. Exit criteria

| Criterion | Result | Evidence |
|---|---|---|
| Tier-1 tasks DONE | Met | S4.1, S4.2, S4.3, S4.8, S4.9, S4.10, S4.11 DONE (rows ENG01–03, ENG08–11), plus S4.9b (ENG12) |
| RES01 DONE | Met | D11 compute recheck, 2026-11-11 ([s4_d11_compute_recheck.md](s4_d11_compute_recheck.md)); run design unchanged, no entry |
| Each Tier-2 task DONE behind its flag, or recorded as moved | Met | All four built. S4.6 behind `fgsv_ks_gate` (`VCLFlag.FGSV_KS_GATE`) and S4.7 behind `iol_self_telemetry` (`VCLFlag.IOL_SELF_TELEMETRY`), entry 89. S4.4 and S4.5 as product settings outside the VCL manifest (owner decision 2026-11-11, option a): `HELIOS_PII_REDACTION`, `HELIOS_ACTION_MODE`. None moved to Stage B |
| Full gate green on main | Met | §2 |
| CI green on the S4 merges | Met | PRs #88–#98 all checks green; `main` `5cd8b37`: CI (8 jobs, including Console) and Ledger Verification both succeeded |
| Tag `rb-s4-exit` pushed | Met | Annotated tag on `5cd8b37`, pushed 2026-11-14 |
| Exit report, with the status of every carried-in item | Met | This document; §4 |

## 2. Gate on main `5cd8b37`

Run with `set -o pipefail`; exit status 0.

| Step | Result |
|---|---|
| ruff check, ruff format, black | clean (388 files) |
| mypy (strict) | no issues |
| pytest | full suite passes; coverage 96.59% (threshold 90%; 96.20% at the S3 exit) |
| verify_ledgers | deviation and reconciliation chains and anchors verified |
| log_deviation verify-public | 89 entries; 35–89 Ed25519-signed; every byte covered by the signed anchor |
| verify_captures | 20 May captures verified (window hash and content seal) |
| verify_osf_freeze --verify | all artefacts match; freeze intact |
| validate-tracking | clean; every tracker commit valid (range mode) |
| ablation notebook | executes |
| console tests (`node --test tests/console/`) | 16 pass (CI job `console` since S4.2) |

## 3. What S4 delivered

| Task | Row | SHA | Merge | Deviation |
|---|---|---|---|---|
| Plan refresh with the S3 carry-overs | — | — | #88 | — |
| RES01 D11 compute recheck: the response cache shares worker calls across variants, so the escalation share does not drive compute; the narrator does. E1 + E3 about 5–6 h central, 11–14 h conservative | RES01 | `756e604` | #88 | — |
| S4.9 Metrics suite: `eval_run` with TTT and TTCD (graph build in the clock, entry 46), operational TTCD, CpR, H_struct, H_fact, trigger-source split, `llm_unavailable` covariate | ENG09 | `7aac9db` | #89 | 84 |
| S4.9b Narrative-heavy stratum (A-H6): τ_N frozen on RCAEval build | ENG12 | `73f391f` | #90 | 85 |
| S4.11 Analysis suite: Wilcoxon, sign test, McNemar exact mid-p, step-down Holm in data order, BCa for Family E, E-H5 in both forms | ENG11 | `6cc9c1c` | #91 | 86 |
| S4.10 Run orchestrator and integrity: schedule (1,920 + 1,200 + exploratory, rerun and E-H5 strides), campaigns with resume, cell rule, MCAR and IPW, per-campaign ledgers; determinism compare | ENG10 | `0a921a8` | #92, #93 | 87 |
| S4.8 Baselines from the RCAEval suite: five methods in pinned images, `--network none`, export from the sealed window, PDiagnose adapter, trace baselines on OTel build captures | ENG08 | `f32e224` | #94 | 88 |
| S4.1 API: FastAPI api-v1 (incidents, verdicts, CoE, view tokens, HITL decisions, health); key digests; signed decisions ledger | ENG01 | `fa41e9c` | #95 | — |
| S4.3 Compose deployment: API, model server pinned by digest with a digest check, runner, admin; fresh-clone install verified | ENG03 | `03c0a30` | #96 | — |
| S4.2 Approval console (RQ4 instrument): build-free console behind nginx with a strict CSP; reveal after the view token; client and hidden-time measures; blind participant keys; simulated HITL reviewer; API v1.1 | ENG02 | `7c6be65` | #97 | — |
| S4.4 PII redaction, S4.5 shadow and recommendation modes, S4.6 FGSV lite, S4.7 IOL lite; API v1.2 | ENG04–07 | `66c1fe2` | #98 | 89 |

### Main results (build data, exploratory)

- **Orchestrator (S4.10 §7).** OTel v3 build campaign: 693 runs, scores identical to the S4.11 build run. Live-model determinism rerun: 0 of 48 pairs non-deterministic (fused lists and L-pipe outputs identical in all 48).
- **Analysis (S4.11 §7).** OTel v3, 8 variants, 504 runs. Under the fixed sequence, A-H3 blocks everything after it; A-H5 is driven by the opportunity cost in CpR.
- **Baselines (S4.8 §7, entry 88).** All five ran on all 63 OTel v3 cases. Family B is fully testable: B-H1 to B-H5 and B-H8 fall below their thresholds, B-H6 and B-H7 do not. BARO gives identical AC@1 and AC@3 on the export and on RCAEval's native files (495 cases). Every baseline ranking was identical in the determinism rerun.
- **Console (S4.2 §7).** Server time to decision is at least the browser's, larger by 7–13 ms; no participant-key response carries a variant name; simulated HITL recorded 282 decisions.
- **Compose (S4.3 §7).** Fresh clone to model check in 159 s (including the model pull); rankings equal the host's.
- **Tier 2 (S4.4–S4.7 §7).** Full's verdicts are identical with `iol_self_telemetry` and with `fgsv_ks_gate` ON and OFF. FGSV's KS gate marks 52% of clean OTel targets STALE; on Full's own top-1, FGSV accepts 12 of 32 wrong targets (noFGSV 32 of 32) and 12 of 31 correct ones, and replay does not separate HELIOS's own mistakes. IOL's frozen rule detects slowdowns of ×5 and ×8 within 3 runs, never ×2 or ×3. Redaction changes no build-data prompt.

## 4. Carried-in items

| Item | Status |
|---|---|
| Entry conditions (`rb-s3-exit`, baseline images, Docker memory, clean tree, S2-M9 rows) | All met at the refresh (plan § Entry conditions) |
| S2-M9-RES01 D11 compute recheck | Done 2026-11-11; run design unchanged, no entry |
| S2-BL-13 timing (graph build in TTT, first publication, hardware, non-convergence beside TTT) | Done in S4.9 (entry 84): graph build about 0.4 s, inside TTT and TTCD |
| S2-BL-18 remainder (state of the first publication) | Done in S4.9: TTT is the first publication whatever its state, and both states are scored |
| Operational TTCD and detection delay (entries 71, 72); trigger-source split | Done in S4.9: exploratory columns beside TTCD |
| `llm_unavailable` covariate (S3.5) | Done in S4.9: carried into every scored row |
| A-H5 split by stage, A-H1 split by escalation (S3.1 §2, §10) | Done in S4.9 and S4.11 (descriptive, BCa) |
| Metric contract read-only | Kept: no edit; changed definitions are in entries 84–89 and the OSF addendum draft |
| Schedule refuses exploratory variants without a flag reader | Done in S4.10. noFGSV and noIOL now run (S4.6, S4.7 built); noCogni and HIS3 stay refused (Stage B) |
| Fixed first variant per case; determinism rerun bypasses the cache | Done in S4.10 (noRouter first; 10% stride rerun) |
| Family E BCa without Holm; exploratory never labelled confirmatory | Done in S4.11 |
| E-H5 in both forms until the addendum decision | Built (S4.11); the decision is still open (§6) |
| PDiagnose adapter with departures recorded; alternates | Done (entry 88 item 4); no alternate needed |
| Trace baselines on OTel build captures; `--network none`; no pool before `build-freeze` | Done (S4.8) |
| Tier-2 items decided on content | Decided 2026-11-11 and built (§1) |
| IRB status (L1) | Open, owner. The console is built and verified; the study runs only if approval arrives by 2027-02-05 |
| Rater 2 and adjudicator (L2, L3) | Open, owner, due 30 Nov |
| S2.9 rater training, rubric freeze | Open, before S5 |
| OSF addendum deposit | Open: now entries 46–89 and the S4 frozen files (§6) |
| Backups (`.env`, `.env.labelling`, response cache, labelling data; L10) | Open, owner |
| GCP and Azure price-book profiles | Open, owner, before `build-freeze` |
| Hook commands use `$CLAUDE_PROJECT_DIR` | Open, owner |
| Chair call preparation (end of November) | Open: agenda in §5 |

## 5. Retrospective

### Plan vs actual

| | Planned | Actual |
|---|---|---|
| Window | 18–29 Jan 2027 (10 working days) | 11–14 Nov 2026 (4 days), closed about nine weeks before the window opened |
| Effort | 13½ days of tasks plus about 2 days carried in | Every task done, including all four Tier-2 items; S4.9b added (narrative-heavy stratum) |
| Deviation entries | PDiagnose, alternates, TTT with graph build, new VCL flags, FGSV and IOL parameters, D11 if changed, Tier-2 moves | 6 (entries 84–89): metrics (84), τ_N (85), analysis (86), schedule and integrity (87), baselines (88), FGSV and IOL lite (89). No new VCL flag, no alternate baseline, no Tier-2 move, D11 unchanged |
| Merges | — | 11 PRs (#88–#98), each through CI |
| Model runs | — | All on build data. OTel v3 build campaign (693 runs) and live determinism rerun (48); baseline campaign on 63 OTel cases and export check on 495 RCAEval cases; compose fresh-clone run with the CPU model server; Tier-2 walk-through (5 arms × 63 cases, cache only). The pool was never read |

### Decisions and why

| Decision | Why | Record |
|---|---|---|
| Evidence path first (metrics, analysis, orchestrator, baselines), product shell after | Phase E depends on the evidence path; the shell does not | Plan § Capacity |
| Graph build counted inside TTT and TTCD | Entry 46 starts the clock at the trigger handover; graph build uses the trigger | entry 84 |
| Holm in data order is binding; the fixed-sequence reading is reported | As pre-registered; the build run shows A-H3 would block everything under a fixed sequence | entry 86 |
| Determinism measured by a 10% stride rerun with the cache bypassed, no new seed block | Keeps the registered seeds; the rerun store stays separate from the analysis | entry 87 |
| Baselines read an export of the sealed HELIOS window, never RCAEval's raw folders | Same bytes for HELIOS and baselines; no label-bearing folder names | entry 88 |
| API never holds a deviation secret; key digests only; decisions in their own signed ledger | The product shell must not be able to touch the evidence ledgers | S4.1 design |
| Console reveals a case only after its view token is issued; participant keys are blind | The RQ4 timing must start when the case is visible, and participants must not learn the condition | S4.2 design |
| S4.4 and S4.5 as product settings outside the VCL manifest | A new VCL flag changes every variant hash and `variants.py`; both settings are off or without effect in evidence runs | owner 2026-11-11 |
| FGSV: Chapter 3's KS gate kept although it marks 52% of clean targets STALE | The OTel v3 normal period really drifts; an effect-size or per-series gate did not help; STALE is a first-class covariate in Ch3 | owner 2026-11-14; entry 89 |
| IOL: E-H6 as a severity ladder (×2, ×3, ×5, ×8), not one factor | The frozen rule misses ×3 on noisy per-run timings; a ladder reports where detection stops instead of picking the factor that works | owner 2026-11-14; entry 89 |

### What went wrong, and what changed because of it

| Problem | How it was caught | Change |
|---|---|---|
| The first determinism `compare` reported 48 of 48 runs unequal | Reading the differences | It compared per-call wall time and cache flags, which the rerun changes by design; fixed to ignore operational fields and to report template-fallback narratives as not comparable (PR #93) |
| The compose image exposed three missing pieces: pyyaml not a main dependency, the runner cache on a read-only mount, no git for `build_frozen` | First container run | All three fixed; `build_frozen` fails closed without git (S4.3) |
| The research hook blocks the loopback and any-address IP literals | Hook refusal | Owner authorised the loopback literal; never constructed to get past the hook |
| A browser-automation tool keeps every page visible, so hidden-tab time could not be shown directly | Walk-through | Hidden time checked with real `visibilitychange` events and an overridden `document.hidden` (2,208.5 ms recorded for 2,200 planned) |
| The first E-H6 attempt (×3) found nothing | Walk-through | Severity ladder question to the owner; reported, not hidden |
| FGSV calibration over every candidate (J = 0.48) overstated replay's value on the targets HELIOS actually proposes | Walk-through on Full's own top-1 | Reported in entry 89 and design §7.3; E-H4 reported with the gate/replay split |
| The PII ruleset id did not change when a rule's check changed | Second scan | `RULES_VERSION` is part of the id |
| An experiment-log file was swept into a tracker commit by `commit -a` | `git show --stat` before pushing | Commit redone without it; explicit paths only |

### Design-science notes (for Chapter 4)

- **Evaluation tooling as part of the artefact.** The orchestrator, integrity gate, cell rule and determinism rerun turn the pre-registration into code paths that refuse what the plan does not allow (pool before `build-freeze`, variants without a flag reader, exploratory labelled confirmatory).
- **Timing metrics are noisy where variants differ little.** Two build runs that differ only in measured timing moved A-H5's p by an order of magnitude. Token-level determinism is not timing determinism.
- **The product shell and the evidence path are kept apart by construction.** The API cannot hold a deviation secret; the console's measures sit beside the server's own clock; shadow mode and redaction are settings that the confirmatory path refuses or ignores.
- **Lite mechanisms can be honest about their limits.** FGSV's gate does almost all of its work and its replay does not separate HELIOS's own mistakes; IOL's shared detector sees only large degradations. Both are reported as such rather than tuned until E-H4 and E-H6 look good.

### To raise at the chair call (end of November)

- CpR and A-H5: the opportunity-cost share and the timing-noise sensitivity (S4.10 §7 options);
- O-e (cell rule narrowing) and O-g (stride subsets);
- injection time for baselines (binding) with the trigger-time sensitivity row (entry 88);
- the TraceRCA reference filter (entry 88 item 10);
- E-H4 and E-H6 as lite mechanisms: the 52% STALE share, replay's weak separation, the E-H6 ladder;
- E-H5 addendum decision (carried from S3).

## 6. Carry-overs

| Item | Owner | Date | Note |
|---|---|---|---|
| OSF addendum deposit (entries 46–89; S4 frozen files `fgsv_params.json`, `iol_injection.json`, `narrative_tau.json`) | AA, Claude | Before `build-freeze` | S2-BL-05 |
| E-H5 addendum decision (RRE selection between Full and noReconcile) | AA | Before `build-freeze` | S3.3 design §6 item 3; both forms built |
| IRB (L1); rater 2 and adjudicator (L2, L3; row S2-M5-RES05) | AA | 2027-02-05; 30 Nov | Console ready |
| S2.9 rater training, rubric freeze, row S2-M7-RES01 | AA, Claude | Before S5 | Needs rater 2 |
| Pool-only checks after `build-freeze`: span status-code format in pool traces; rebuilt log and trace series (export) | Claude | After `build-freeze` | S4.8 open item |
| Backups (`.env`, `.env.labelling`, response cache, labelling data; L10) | AA | Now | S2-BL-17, -19 |
| GCP and Azure price-book profiles | AA | Before `build-freeze` | S1 carry-over |
| Hook commands use `$CLAUDE_PROJECT_DIR` | AA | Any time | Open since S0 |
| Chair call reference doc with an outcomes table | Claude | From about 2026-11-20 | Agenda §5 |
| Stage B: FGSV full twin and a replay that separates near-miss targets; IOL sensitivity beyond the shared detector; NER redaction | Claude | Stage B | Added to `docs/sprints/stage-b/plan.md` § Carried in from Stage A |
| S5 plan refresh (capacity, owner items, carry-overs) | Claude | Before S5 starts | Root CLAUDE.md § Sprints, step 5 |
