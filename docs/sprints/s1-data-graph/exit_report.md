# Sprint S1 — exit record

**Date:** 2026-10-27 · **Tracking:** S2-M6-GATE01 · **Tag:** `rb-s1-exit` on main `3d96208` (merge of PR #69) · **Plan:** [plan.md](plan.md); `docs/tracking/helios_task_breakdown.md` § S1

S1 was scheduled for 16 November – 4 December 2026. It started early on 24 October (owner) and closed on 27 October.

## 1. Exit criteria

| Criterion | Result | Evidence |
|---|---|---|
| S1.1–S1.10 DONE, or S1.3 recorded as moved to Stage B | Met | Tracking rows S2-M6-ENG01–ENG09 and S2-M6-RES01–RES05 are all DONE. S1.3 is recorded as no-go for the pool and moved to Stage B (owner decision, S2-M6-RES02) |
| Leakage test passes on every pool and build case | Met | S1.1 adapter leakage test (opaque IDs, no label in any path or field) over 240 pool and 495 build cases. S1.9 `tests/evaluation/test_no_ground_truth_leak.py` (signatures, run-path scan, runtime trap) |
| Full pre-push gate green on main | Met | §2 |
| Tag `rb-s1-exit` | Met | annotated tag on `3d96208`, pushed |
| Exit report written | Met | this document |

## 2. Gate on main `3d96208`

| Step | Result |
|---|---|
| ruff check, ruff format, black | clean (174 files) |
| mypy (strict) | no issues in 174 source files |
| pytest | 780 passed; coverage 94.40% (threshold 90%) |
| verify_ledgers | deviation and reconciliation chains verified; exclusion ledger empty |
| log_deviation verify-public | 45 entries; 11 Ed25519-signed (35–45); every byte covered by the signed anchor |
| verify_captures | 20 May captures verified (window hash and content seal) |
| capture_campaign verify | 63 S1.2 build cases intact; signed ground truth verified |
| verify_osf_freeze --verify | all artefacts match; freeze intact |
| validate-tracking | clean |
| ablation notebook | executes |

## 3. What S1 delivered

| Task | Row | SHA | PR | Deviation |
|---|---|---|---|---|
| S1.1 RCAEval adapter: 240 pool and 495 build cases sealed, pool locked until `build-freeze` | ENG01 | `cbfcab5` | #56 | — |
| S1.4 Log templates (Drain3), reruns identical 120/120 | ENG02 | `edf37e4` | #57, re-landed #58 | — |
| `ablation_architecture.md` v0.8 on the D2 flag names (S0 carry-over) | RES03 | `ab3e19a` | #59 | — |
| S1.5 Typed incident graph (UEG-C schema-draft-v0.2), four edge classes | ENG03 | `bff0e55` | #60 | 39 |
| S1.6 Structural bundle (`ueg_structural` OFF as pre-registered) | ENG04 | `a969421` | #61 | — |
| S1.7 K-hop pruner (Algorithm 5), K = 3, top-n = 50, 50-node floor | ENG05 | `5801c37` | #62 | 40 |
| Detection-trigger decision: option (a), one frozen label-free detector | RES04 | `9dfc1cd` | #63 | — |
| S1.8 Verdict contract (PipelineVerdict schema-draft-v0.5) | ENG06 | `705e0d3` | #64 | 41 |
| S1.9 Scoring path (HR@1/3/10, Avg@5, MRR after dispatch) | ENG07 | `8a39071` | #65 | — |
| S1.10 Price book, token accounting, five-component CpR | ENG08 | `229fc97` | #66 | 42 |
| S1.10 follow-up: price-book-v2 cloud profiles (AWS primary; GCP, Azure sensitivity) | ENG09 | `a7a78f7` | #66 | 43 |
| S1 documentation sync (mirror rows 39–43, validity threats) | RES05 | `8628aa9` | #67 | — |
| S1.3 AIOpsLab spike: conversion works; no-go for the pool, moved to Stage B | RES02 | `cad996f` | #68 | — |
| S1.2 OTel Demo build corpus: 63 sealed cases, signed labels | RES01 | `5bcb18a` | #69 | 44, 45 |

## 4. Retrospective

### Plan vs actual

| | Planned | Actual |
|---|---|---|
| Window | 16 Nov – 4 Dec 2026 (15 working days) | 24–27 Oct 2026 (4 days), closed 3 weeks before the window opened |
| Effort | 16 days of tasks | All ten tasks done, including the Tier-2 S1.3 spike |
| Added during the sprint | — | Detection-trigger decision (RES04), price-book cloud profiles (ENG09), documentation sync (RES05), two capture defects found and fixed |
| Deviation entries | UEG-C, verdict, K, price book, AIOpsLab | 7 (entries 39–45). The expected AIOpsLab addendum was not needed (no-go). Two entries came from defects (44 protocol, 45 span labels) |
| PRs | — | 14 (#56–#69), each through the full gate |
| Tests at exit | — | 780 (588 at S0 exit); coverage 94.40% (91.82% at S0 exit) |
| Data | — | RCAEval: 240 pool + 495 build cases sealed. OTel: 63 new build cases (13 h 40 min campaign). Plus the 20 May captures, 83 sealed OTel incidents in total |

### Decisions and why

| Decision | Why | Record |
|---|---|---|
| One frozen, label-free detector gives HELIOS and the five baselines the same trigger time (option a); a true-injection-time run is exploratory only | The deposited metric contract says no pipeline receives the injection time, and baselines run with the same inputs; (a) needs no protocol change | RES04; S2.1 |
| K = 3, top-n = 50, with a 50-node floor | Pure Algorithm 5 keeps the root cause in at most 376/495 build graphs; with the floor, 492/495. **Re-checked on the trace-bearing S1.2 corpus at the exit:** the same rule picks K = 3, top-n = 50 (root cause kept 62/63 without the floor, 63/63 with it), so no further entry | entry 40; `s1_7_khop_pruner.md`; exit check below |
| Verdict carries status, ranked list, μ, σ, cost and latency; skipped pipelines yield a typed verdict instead of aborting the run | HELIOS-LLM-only aborted on a missing D-pipe verdict; Ch3 L2's typed verdict needs all five fields | entry 41 |
| Price book with named cloud profiles: AWS primary, GCP and Azure as sensitivity | Owner request: every price traceable to a provider's service and machine type; CpR conclusions checked against other CPU:GPU price ratios | entries 42, 43 |
| AIOpsLab: no-go for the confirmatory pool, Stage B exploratory corpus | Conversion works end to end, but its 29 localization problems map to 6–8 fixed root-cause services, its own export is lossy, and its images and charts are unpinned | `s1_3_aiopslab_spike.md` |
| OTel build corpus in its own tree (`data/otel/`), committed to git (22 MB) | `data/captures/` is in the OSF deposit-1 digest; the captures are live recordings that cannot be regenerated, unlike the RCAEval downloads | entry 44; PR #69 |
| Scores and costs computed only after dispatch, outside the pipelines | Labels must never reach a pipeline; the scan makes the boundary testable | S1.9 |

### What went wrong, and what changed because of it

| Problem | How it was caught | Change |
|---|---|---|
| **Span service labels wrong in every OTel capture since May.** The Jaeger fetcher stamped each span of a returned trace with the queried service, so each span appeared several times, mostly under the wrong service | S1.3: converting an AIOpsLab window through the same fetcher gave an implausible graph | Fetcher fixed with a regression test. Entry 45; S1.7's OTel check marked void; threat T17. The S1.2 corpus confirms the fix on live data: no duplicates, 32% of span links cross services |
| **May captures hold no resource metrics.** The metric names they ask for (`up`, `process_*`) do not exist in demo 2.2.0 | S1.2 pilot 1 | Per-container CPU and memory queries; threat T13; May captures stay as deposited and are reported as latency-only |
| New metric queries were not wired into the campaign builder | S1.2 pilot 2 | Test asserting the fetcher's queries; pilot data discarded |
| RCAEval build corpus has no traces | S1.5 | S1.2 moved up so trace-derived edges and K could be checked on build data |
| Pure Algorithm 5 drops the root cause too often on build data | S1.7 calibration | 50-node floor (entry 40) |
| Campaign module first placed in `helios/telemetry/` | S1.9 leakage scan failed in the S1.2 gate | Moved to `helios/adapters/`; the scan worked as designed |
| Stacked PR #57 merged into `s1/start` instead of main | Landing check after merge | Re-landed as #58; rule saved: check PR state and base before pushing |
| `metric_contract.md` §9 needs a correction but is in the deposit-1 digest | S1.8 and S1.9 | Correction goes into the next OSF deposit addendum; file left unchanged |
| `bin/pin-otel-demo.sh` uses GNU `sed -i` and fails on macOS | S1.2 setup | Pinned by hand (same two steps); script fix carried over |
| Changing into a subdirectory locked every tool again (S1.2) | Session lock-up, recovered by the owner | Same as S0; hook-path fix still awaiting owner approval |

### Design-science notes (for Chapter 4)

- **A second testbed acted as a test oracle for the first.** The S1.3 spike was planned as a feasibility check. Pushing an AIOpsLab window through the capture layer exposed a defect that had been in every OTel capture since May (entry 45). Cross-testbed conversion is a cheap evaluation episode for the capture layer and is worth repeating for Stage B corpora.
- **Build → evaluate → rebuild on the pruner.** Algorithm 5 as written (build) kept the root cause in at most 376/495 build graphs (evaluate). A floor was added and the setting chosen by a rule fixed before the run (rebuild, entry 40). The setting was then checked again on a different corpus with trace topology, and the same rule chose the same setting.
- **The integrity layer kept catching errors in use:**
  - the leakage scan flagged a module placed on the run path;
  - the OSF freeze check ruled out storing new captures beside the deposited ones;
  - the tracking validator's range mode checked every tracker commit, merges included;
  - seals and signed labels let three discarded pilots be removed cleanly, with no trace left in the corpus.
- **Pilots before long runs paid for themselves.** Each of the three S1.2 pilots found a defect that would otherwise have spoiled a 13-hour campaign.
- **Fault visibility varies by fault and modality** (S1.2 results): one fault (`emailMemoryLeak`) is near-silent within 5 minutes. A build corpus with hard cases matters for calibrating the label-free detector (S2.1) and for honest exploratory scores.

### Exit check: K on the trace-bearing corpus

Run at the exit with `bin/khop_calibrate.py`'s grid and selection rule on `data/otel/` (63 build cases, exploratory, counts only):

| K | Root cause kept (no floor) | Services kept (median) |
|---|---|---|
| 0 | 15/63 | 3 |
| 1 | 37/63 | 13 |
| 2 | 57/63 | 21 |
| 3 | 62/63 | 25 |

- **Selection:** the rule picks K = 3, top-n = 50, the same as on the RCAEval build corpus. With the 50-node floor the root cause is kept in 63/63.
- **Graph size:** every graph has 28 services, all below the floor.
- **Seeds:** all seeds come from anomalies, and the root cause is among them in 15/63.

The grid was run from a scratch wrapper; adding an `otel_build` corpus option to `bin/khop_calibrate.py` is carried over, so the check reruns from the repository.

## 5. Carried into S2 and later

| Item | Owner | By |
|---|---|---|
| S0.11 owner items: IRB (RQ4), second rater and adjudicator | Owner | rater and adjudicator 30 Nov; IRB before the RQ4 study (S2-M5-RES05) |
| Replace the unverified price-book entries (S3 Standard; all GCP and Azure profiles) from official price lists; any changed value gets a deviation entry | Owner | before `build-freeze` |
| Chair call: opportunity-cost figure (5,600 per minute, sensitivity 14,056), retention and review-minute assumptions, the May capture defects (T13, T17) and how they are disclosed | Owner, with a call-reference doc | next chair call |
| `metric_contract.md` §9 correction | Researcher | next OSF deposit addendum |
| `otel_build` option in `bin/khop_calibrate.py` (K check reruns from the repo) | Researcher | S2.2 |
| Candidate set on OTel graphs includes demo infrastructure containers (Prometheus, Jaeger, OpenSearch, collector, load generator, flagd): decide in S2.1–S2.2 whether candidates are filtered, with a deviation entry if they are | Researcher | S2.2 |
| Longer fault period for `emailMemoryLeak` (near-silent in 5 minutes) | Researcher | Stage B option |
| AIOpsLab exploratory corpus (added to `stage-b/plan.md` in this exit's documentation sync) | Researcher | Stage B |
| `bin/pin-otel-demo.sh` macOS fix (BSD `sed`) | Researcher | when next touched |
| Hook commands to use `$CLAUDE_PROJECT_DIR` (the `cd` lock-up) | Owner approval | open since S0 |
| Move `osf_deposit_1.zip` out of the repository working tree | Owner | any time |

Next: Sprint S2 — reasoning, consensus, narratives (`helios_task_breakdown.md` § S2), starting with S2.1 (label-free detector, option a).
