# Sprint S3 — exit record

**Date:** 2026-11-09 · **Tracking:** S2-M8-GATE01 · **Tag:** `rb-s3-exit` on `main` `946f3cb` (merge of PR #86), annotated and pushed · **Plan:** [plan.md](plan.md); `docs/tracking/helios_task_breakdown.md` § S3

S3 was scheduled for 4–15 January 2027. It started early on 6 November (owner) and closed on 9 November. GitHub Actions minutes were back from the start of the sprint. The S2 backlog of local commits went up first (PR #77), and every S3 change then merged through a PR with a green CI run.

## 1. Exit criteria

| Criterion | Result | Evidence |
|---|---|---|
| S3.1 DONE | Met | S2-M8-ENG01 DONE; router frozen, hash `94707eca` (entry 70) |
| Each Tier-2 task DONE behind its flag, or recorded as moved to Stage B | Met | S3.2 DONE behind `acp_stateful` (`VCLFlag.ACP_STATEFUL`), exploratory (entries 82, 83). S3.3 DONE behind `reconcile_terminal` (entries 74, 75). S3.5 DONE under `cbr_routing` (entry 73). S3.4 DEFERRED to Stage B (entry 82) |
| CI green on the pushed base and on the S3 merge | Met | PR #77 (first push since S2) through PR #86; `main` `946f3cb`: CI and Ledger Verification both succeeded |
| Full gate green on main | Met | §2 |
| Tag `rb-s3-exit` pushed | Met | Annotated tag on `946f3cb`, pushed 2026-11-09 |
| Exit report, with the status of every carried-in item | Met | This document; §4 |

## 2. Gate on main `946f3cb`

Run with `set -o pipefail`; exit status 0.

| Step | Result |
|---|---|
| ruff check, ruff format, black | clean |
| mypy (strict) | no issues |
| pytest | full suite passes; coverage 96.20% (threshold 90%; 95.87% at the S2 exit) |
| verify_ledgers | deviation and reconciliation chains and anchors verified |
| log_deviation verify-public | 83 entries; 35–83 Ed25519-signed; every byte covered by the signed anchor |
| verify_captures | 20 May captures verified (window hash and content seal) |
| verify_osf_freeze --verify | all artefacts match; freeze intact |
| validate-tracking | clean; every tracker commit valid (range mode) |
| ablation notebook | executes |

## 3. What S3 delivered

| Task | Row | SHA | Merge | Deviation |
|---|---|---|---|---|
| Plan refresh with S0–S2 carry-overs; first push since S2 | — | `72bdc49` | #77 | — |
| S3.1 Router with cheap-first gate (IN3): two-stage routing, per-arm LinUCB lower bounds, τ_acc within one point of uniform HR@3 per corpus; frozen | ENG01 | `31e0cb5` | #78, #79 | 69, 70 |
| Detection delay and operational TTCD (`known_at_s`); engineering minors (S2-BL-12, -18, -20); `pin-otel-demo.sh` portable | — | — | #80, #81 | 71, 72 |
| S3.5 LLM-unavailable fallback: cheap arm published, `llm_unavailable` covariate; cache-only reruns without Ollama | ENG05 | `4add9d7` | #82 | 73 |
| S3.3 Two-stage reward and delayed labels: offline replay, 96 signed reward ledgers | ENG03 | `b00f0f0` | #83 | 74, 75 |
| OTel build diagnosis (13 misses) | — | — | #84 | — |
| OTel fix A and B, held-out OTel v4 (36 cases, sealed, read once), refit chain; old chain kept | ENG06, ENG07 | `b2fc399` | #85 | 76–81 |
| S3.2 Action-Class Predictor: four remediation families, rule-based blast-radius tier, recorded not routed; fitted once and frozen (`dd7b63d3`) | ENG02 | `32c3a9c` | #86 | 82, 83 |
| S3.4 Knowledge Cortex | ENG04 | — | — | 82 (DEFERRED) |

### Main results (build data, exploratory)

- **Router (S3.1 design §11).** On RCAEval build the router stops before the L-pipe on 298 of 495 held-out cases (60%), costing 0.80 points of HR@3 (96.57% vs 97.37% uniform). On OTel no cheap arm reaches τ_acc, so every case escalates, and HR@3 equals uniform (79.37%).
- **Two-stage reward (S3.3 design §6).** Terminal labels let the router learn to stop on RCAEval: escalation falls from 49% to 26% along a stream. HR@3 drops to 1.16 points below uniform, outside the tolerance τ_acc was frozen under. On OTel, learning changes nothing.
- **OTel fix (design §5).** Validated once on held-out v4: 30/36 for both the frozen and the refit chain; RCAEval build 478/495 for both. The rule kept the old chain.
- **ACP (S3.2 design §6).** Cross-fitted accuracy 78.85% against 52.15% for the majority class; macro-F1 0.717. Config faults: 40/42 correct. Code-level faults: 10/30, mostly read as resource or network.

## 4. Carried-in items

| Item | Status |
|---|---|
| Entry: push local `main`, one PR with green CI (S2-BL-16) | Done: PR #77, before any S3 code |
| Entry: working tree clean of unregistered data | Done at this exit. `pilot_v3` was never registered as build data and is no longer in the working tree (entry 50 records it as not build data). The edit-audit lines in `experiments/experiment_log.csv` are committed. `.envrc` is gitignored. The two edits in the demo submodule stay local and uncommitted: the `DEMO_VERSION` pin written by `bin/pin-otel-demo.sh`, and a blank line the capture tool's flag rewrite removed |
| S2-BL-06, G-pipe gate loss | Settled by the router (entry 69). The PPR gate no longer decides whether G-pipe runs. Uniform routing runs G-pipe wherever a graph exists; routed runs call it when the D arm is infeasible |
| S2-BL-08, modest MAHC confidence | τ_acc was chosen on the held-out lower-bound distribution (R-d), not a nominal value. The L-pipe share is reported per corpus: OTel all 63, RCAEval 197 of 495 held out |
| S2-BL-07, weak L-pipe on OTel | Recorded, not tuned to. On OTel D+L equals D (76.2%), and only Full (79.4%) is above D |
| S2-BL-01 and S2-BL-03, build-to-pool shift | Router, reward, OTel refit and ACP all fitted on build data only. The split by G-pipe participation and by routed arm is in the OSF addendum draft |
| S2-BL-13, timing | Each routed run records its arm and staged timing (entry 69 item 6). Graph-build time is added in the S4 scoring path |
| Price book | price-book-v2 AWS profile, digest `3b0bb925`, hashed into the router parameters. GCP and Azure feed sensitivity only |
| S2-BL-17, cache-only reruns | Done (entry 73) |
| S2-BL-12, -18, -20; `pin-otel-demo.sh`; four May-plan rows | Done 2026-11-06 (plan § Engineering items; entries 71, 72; dev-025, dev-027) |
| S3.4 check of SOP retrieval for the log worker (S2-BL-07) | Not done: S3.4 moved to Stage B (entry 82) |
| D11 compute estimate against the measured escalation share | **Carried over** (§6). Build gives the escalation share (OTel all, RCAEval 40% held out); the pool has traces, so its share is not yet known |

## 5. Retrospective

### Plan vs actual

| | Planned | Actual |
|---|---|---|
| Window | 4–15 Jan 2027 (10 working days) | 6–9 Nov 2026 (4 days), closed eight weeks before the window opened |
| Effort | 9 days of tasks plus about 2 days carried in | S3.1, S3.2, S3.3, S3.5 and the carried-in items done; S3.4 moved to Stage B |
| Added during the sprint | — | OTel build diagnosis, fixes A and B, held-out v4 corpus, refit chain (ENG06, ENG07; owner 2026-11-07) |
| Deviation entries | Router, G-pipe gate, ACP and reward if built, detection delay, Tier-2 moves | 15 (entries 69–83). Two corrected earlier ones: 72 corrects 71, 75 adds to 74 |
| Merges | — | 10 PRs (#77–#86), each through CI |
| Model runs | — | Router build runs 1–2 (run 1 superseded); reward replay run 2 (run 1 stopped at its pair check); OTel v4 capture and one validation (2,124 incident runs); MAHC run 4 and router run 3 on the candidate chain; ACP fit once. All L-pipe answers came from the response cache (llama3.1:8b, digest `46e0c10c039e`) |

### Decisions and why

| Decision | Why | Record |
|---|---|---|
| Cheap-first routing replaces the PPR gate; uniform routing (`cbr_routing` OFF) runs every pipeline | The May gate cost G-pipe cases (S2-BL-06); the router is where cost and accuracy are traded | entry 69 |
| Lower confidence bound against τ_acc, with the exploration bonus subtracted | A frozen policy cannot explore, so uncertainty must mean escalation | entry 69 item 4 |
| τ_acc raised until the refit also meets the one-point tolerance | The refit stops more cases than the held-out models it was chosen on | entry 70 |
| Detection delay and operational TTCD defined in the OSF addendum, not the contract | `metric_contract.md` is signed into deposit 1 | entries 71, 72 |
| On LLM failure, publish the cheap arm and record a covariate; no selective reruns | Availability must not bias variant comparisons | entry 73 |
| Reward learning offline only; static frozen policy for confirmatory runs | Online learning drifted below the frozen tolerance (§3) | entries 74, 75 |
| OTel fix judged once on a new held-out corpus by a rule fixed in advance; tie means keep the old chain | Fixes chosen from diagnosed misses must show a gain on unseen cases | entries 76, 81 |
| ACP over four remediation families, recorded not routed; E-H8 to Stage B | The build data has no realised remediations, WAL or deployments; the router froze before the ACP existed | entries 82, 83 |
| S3.4 Knowledge Cortex to Stage B, with no index built now | No procedure content exists in the build corpora. Pool separation can be enforced just as well in Stage B by a hash test. S4 is over by 3½ days | entry 82; owner 2026-11-08 and 2026-11-09 |

### What went wrong, and what changed because of it

| Problem | How it was caught | Change |
|---|---|---|
| Router run 1: the refit trained on every build case stopped more cases than the held-out models τ_acc was chosen on | Owner review of run 1 | Refit confirmation; τ_acc raised by 0.0006 (entry 70); run 1 kept as superseded |
| Entry 71 came with an edit to `metric_contract.md`, which is signed into OSF deposit 1 | Pre-push freeze check (`verify_osf_freeze --verify`), after the entry was appended | Correction entry 72; definitions moved to the addendum; standing rule never to edit the contract |
| Reward replay run 1: a terminal reward arrived before its provisional reward | Pair check on the first stream, before any result | Entry 75 defines the order; run 1 wrote no report |
| OTel fixes A and B, built on diagnosed misses, did not beat the frozen chain on held-out v4 | Pre-registered adoption rule | Old chain kept (entry 81); the null result is reported; fix C to Stage B |
| A report cited by entry 78 (`gpipe_refit.json`) was left uncommitted | Working-tree check before PR #85 | Committed in PR #85 (`b120e68`) |
| The ACP parameter hash differed between integer and float inputs | Hash-stability test | Parameters cast to float before hashing |
| A file glob printed the pool ground truth's aggregate fault-type counts (no incident IDs, no root causes) | Noticed in the output; disclosed to the owner on 2026-11-08 | The counts match the public D11 composition and were not used; recounts read build files only |

### Design-science notes (for Chapter 4)

- **Cheap-first routing works where a cheap pipeline is already strong.** On RCAEval the router saves L-pipe calls on 60% of cases at 0.8 points. On trace-rich OTel it saves none, and Full's advantage over noRouter can only come from earlier first publication. This is why A-H5 is reported split by stage.
- **Online learning under a frozen threshold drifts.** The two-stage reward taught the router to stop more often, and accuracy fell outside the frozen tolerance. Static policies for confirmatory runs, and an accuracy guard on any production learning loop, follow from this.
- **A held-out corpus with an adoption rule fixed in advance produced a clean null result.** The fixes explained the diagnosed misses but did not generalise to new OTel cases. Without v4, they would have been adopted on build evidence.
- **Symptoms predict the remediation family only partly.** Config faults are recognisable, but code-level faults look like resource or network faults. Ch3's ACP class set cannot be learned from injected-fault corpora; it needs incidents with realised remediations (Stage B).
- **Recorded, not routed.** Tier-2 learning parts (ACP, reward) were built and frozen without touching HELIOS-Full's decisions. Tests check routing equality, which keeps every confirmatory hash unchanged.

### To raise at the chair call (end of November)

- A-H5 split by stage, and the OTel finding that cheap evidence rarely suffices;
- the online-learning drift (S3.3) and the static-policy commitment;
- E-H5 as registered: RRE for Full and noReconcile is measured on different case sets (selection); the addendum decision is open;
- E-H8 not testable in Stage A; the ACP label-set change;
- the OTel v4 null result, and fix C in Stage B.

## 6. Carry-overs

| Item | Owner | Date | Note |
|---|---|---|---|
| D11 compute estimate rechecked against the escalation share (noRouter and LLM-only call the L-pipe on every case) | Claude | S4 start | Plan § OSF addendum, last paragraph |
| E-H5 addendum decision (RRE selection between Full and noReconcile) | AA | Before `build-freeze` | S3.3 design §6 item 3 |
| OSF addendum deposit (entries 46–83; S2 and S3 items in the S3 plan) | AA, Claude | Before `build-freeze` | S2-BL-05 |
| IRB, rater 2, adjudicator (S0.11 L1–L3; row S2-M5-RES05) | AA | 30 Nov | Carried since S0 |
| S2.9 rater training, rubric freeze, row S2-M7-RES01 | AA, Claude | Before S5 | Needs rater 2 |
| Back up `.env`, `.env.labelling`, `data/cache/lpipe_cache.sqlite`, `data/labelling/build` | AA | Now | S2-BL-17, S2-BL-19 |
| GCP and Azure price-book profiles checked | AA | Before `build-freeze` | S1 carry-over |
| Hook commands use `$CLAUDE_PROJECT_DIR` (approve `.claude/settings.json` change) | AA | Any time | Open since S0 |
| Stage B: Knowledge Cortex, ACP follow-ups and E-H8, OTel fix C, accuracy guard for learning loops | Claude | Stage B | Added to `docs/sprints/stage-b/plan.md` § Carried in from Stage A |
| S4 plan refresh (capacity, owner items, carry-overs) | Claude | Before S4 starts | Root CLAUDE.md § Sprints, step 5 |
