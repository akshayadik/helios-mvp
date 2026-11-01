# Sprint S2 — exit record

**Date:** 2026-11-01 · **Tracking:** S2-M7-GATE01 · **Tag:** `rb-s2-exit` on local main `d3c492b` (merge of `s2/rubric`), annotated, **not yet pushed** · **Plan:** [plan.md](plan.md); `docs/tracking/helios_task_breakdown.md` § S2

S2 was scheduled for 7–25 December 2026. It started early on 27 October (owner) and closed on 1 November. From 30 October GitHub Actions minutes ran out: on the owner's instruction every later change was gated locally and merged into local main without a push (backlog S2-BL-16). At this exit local main is 141 commits ahead of `origin/main`; the branch, the tag and one PR go up together when minutes return.

## 1. Exit criteria

| Criterion | Result | Evidence |
|---|---|---|
| S2.1–S2.8 DONE | Met | Rows S2-M7-ENG01–ENG11, S2-M7-EVAL01, S2-M7-RES02 all DONE (§3) |
| S2.9 DONE, or its training scheduled before S5 | Met (scheduled) | The instrument is built and merged (rubric draft, planted claims, labelling sets, server, annotations ledger, κ and H_fact analysis; training round 1 and onboarding sets built). Rater training needs rater 2 (due 30 Nov) and runs December – early January, before the S5 freeze. Row S2-M7-RES01 stays IN_PROGRESS (§5) |
| Full pre-push gate green on main | Met | §2 |
| Tag `rb-s2-exit` | Met (local) | Annotated tag on `d3c492b`; pushed with the next push |
| Exit report written | Met | This document |

## 2. Gate on main `d3c492b`

| Step | Result |
|---|---|
| ruff check, ruff format, black | clean (296 files) |
| mypy (strict) | no issues in 296 source files |
| pytest | 1,451 tests pass; coverage 95.87% (threshold 90%) |
| verify_ledgers | deviation and reconciliation chains verified; exclusion ledger empty |
| log_deviation verify-public | 68 entries; 34 Ed25519-signed (35–68); every byte covered by the signed anchor |
| verify_captures | 20 May captures verified (window hash and content seal) |
| capture_campaign verify | 63 OTel build cases intact; signed ground truth verified |
| verify_osf_freeze --verify | all artefacts match; freeze intact |
| validate-tracking | clean; every tracker commit since S1 valid (range mode) |
| ablation notebook | executes |

## 3. What S2 delivered

| Task | Row | SHA | Merge | Deviation |
|---|---|---|---|---|
| S2.1 Shared label-free detection trigger; TTCD and TTT from the trigger | ENG01, RES02 | `0587d52` | #71 | 46, 47 |
| S2.1 D-pipe completion: format-neutral Stage A (RCAEval and OTel) | ENG09 | `171f551` | #72 | — |
| S2.1 OTel signal repair found in calibration; v3 build campaign | ENG10 | `19a6953` | #73 | 48, 50, 51 |
| S2.1 Calibration: detector frozen (60 s / 10 / 3), D-pipe frozen | EVAL01 | `638ed06` | #73 | 49, 52, 53 |
| S2.2 G-pipe culprit-versus-victim ranker (learned, frozen) | ENG02 | `6944cb2` | #74, #75 | 54, 55, 56 |
| S2.3 Lean multi-agent L-pipe; prompts and model frozen | ENG03 | `000375a` | #76, local `e6e8c88` | 57, 58 |
| S2.4 H_struct records | ENG04 | `7885c0c` | local `46d4b76` | 59 |
| Tracking validator: malformed (R0) and vanished (R9) rows | ENG11 | `e82930d` | local `a06cfec` | — |
| S2.5 MAHC with calibrated confidence (IN2), frozen from build run 3 | ENG05 | `304019d` | local `b8ab679`, `fdd5ab6` | 60–63 |
| S2.6 Vote-only aggregator (HELIOS-noConsensus) | ENG06 | `1683020` | local `fdd5ab6` | 60 |
| S2.7 Chain-of-Evidence ledger (signed, one entry per stored run) | ENG07 | `e171b06` | local `9a7e8dc` | 64 |
| S2.8 Narrative Engine with grounding verifier (IN1); narrator frozen | ENG08 | `b1d8fff` | local `26df955`, `1dbb492` | 65–68 |
| S2.9 Rating rubric and blind labelling instrument (training pending) | RES01 | — | local `d3c492b` | (one entry at the rubric freeze) |
| S2 backlog to revisit (S2-BL-01…20) | — | — | local `bbb51ba`, `31cf1e8` | — |

## 4. Retrospective

### Plan vs actual

| | Planned | Actual |
|---|---|---|
| Window | 7–25 Dec 2026 (15 working days) | 27 Oct – 1 Nov 2026 (6 days), closed five weeks before the window opened |
| Effort | 15½ days of tasks plus rater time | S2.1–S2.8 done; S2.9's instrument done, its rater training waiting for rater 2 |
| Added during the sprint | — | OTel signal repair and v3 campaign (ENG10), tracking validator fix (ENG11), backlog of 20 items, the narrator's change to pick-and-order (owner decision N-k) |
| Deviation entries | Trigger, G-pipe, L-pipe, MAHC, narrator, rubric seed block | 23 (entries 46–68). Seven came from defects or review findings (48, 50, 51, 55, 62, 67, 68) |
| Merges | — | 6 PRs (#71–#76) before the Actions quota ran out, then 11 local `--no-ff` merges, each through the full local gate |
| Tests at exit | — | 1,451 (780 at the S1 exit); coverage 95.87% (94.40% at the S1 exit) |
| Model runs | — | L-pipe rounds 1–2 and final; MAHC build runs 1–3; narrator rounds 1–3 and two held-out runs; build ledgers for rater training (all on the local llama3.1:8b, digest `46e0c10c039e`) |

### Decisions and why

| Decision | Why | Record |
|---|---|---|
| One frozen, label-free detector gives every system the same trigger; TTCD and TTT count from it | The deposited contract gives no pipeline the injection time; baselines must see the same inputs | entries 46, 49, 52 |
| D-pipe rebuilt as one format-neutral Stage A over RCAEval and OTel, weights frozen | Both build corpora with one code path; the per-channel evidence later feeds the CoE ledger | entry 53 |
| G-pipe: a learned linear ranker over trace-graph features, chosen by a rule fixed before the selection run (50/63 on OTel) | Culprit-versus-victim needs direction; the rule kept the choice honest | entries 54–56 |
| L-pipe: three workers on raw telemetry only, deterministic merge, aliases in prompts, round-1 prompts frozen with the model digest | Keeps the LLM away from other pipelines' output; the cache makes reruns cheap and exact | entries 57, 58 |
| MAHC: signal-type priors, a calibrated confidence and a floor chosen per corpus; runs 1–2 withdrawn, run 3 frozen | Run 1 used a pipeline-count proxy; run 2's calibrator was over-regularised | entries 60–63 |
| CoE: HMAC per entry plus an Ed25519-signed anchor; one evidence namespace (D/G/L) as the narrator's only citation source | Every decision and every narrative claim traceable and checkable offline | entry 64 |
| H_fact judged against the cited evidence, never the ground truth | Keeps hallucination separate from diagnostic accuracy and keeps raters blind | entry 65 (owner N-e) |
| Narrator: the LLM picks and orders code-written, verified claims (owner decision N-k after rounds 1–2 failed) | LLM-written sentences under a closed vocabulary fell back to the template in nearly all slots (round 1) and in 28–66% of slots (round 2) | entries 66–68 |
| Template narrator for noLLM, D and G (never a model) | No LLM in the baselines (S2-BL-15) | entry 66 (owner N-a) |
| Rater protocol: two external raters and an adjudicator; one claim at a time, shuffled across arms; planted known-wrong claims; every pool narrative labelled; adjudicated consensus primary | Blinding, a usable κ at near-zero prevalence, and attention checks | S2.9 design R-a…R-o; entry at the rubric freeze |

### What went wrong, and what changed because of it

| Problem | How it was caught | Change |
|---|---|---|
| **OTel log capture read the wrong fields since May** (every log had empty service and severity); demo traffic too low; histogram buckets inflated a correction; MAD-zero count series masked their own bursts | S2.1 calibration run 4: the detector missed 51/63 OTel cases | ENG10 fixes; OTel v3 campaign (63 cases, 25 users, span metrics); detector trigger-v2. Entries 50, 51 |
| The v3 campaign crashed mid-run (OpenSearch restarted under memory pressure) | Campaign log | Capture retry (3 tries, 120 s apart); campaign resumed, 63/63 with no retries after |
| G-pipe review: May captures' spans misattributed; root-service folds leaked | Fresh review (S2.2) | Selection on the 63 v3 cases only (threat T20); folds by root service (entry 55, corrected by 56) |
| MAHC runs 1 and 2 withdrawn | Run results reviewed before freezing | Run 3 frozen (entries 61–63); runs 1–2 kept on record |
| The tracking validator silently dropped malformed rows, so a column-shifted DONE row passed | S2.3 docs | Rules R0 and R9 (ENG11) |
| CoE: an HMAC-secret holder could cut entries and have the next keyed run re-sign them | Fresh review (S2.7) | Monotonic signing per file; one file per orchestrator run |
| Narrator rounds 1–2: the 8B model could not write sentences that pass the verifier | Machine report (no ground truth) | Pick-and-order (N-k): full acceptance and no fallback on dev and held-out (by construction; the verifier checks every candidate first) |
| **Narrative log quotes were digest wording, not logged text**; earlier a metric digest line was quoted as "logged" | Round-3 smoke test; then the PR-2 review | Log quotes come only from the logged template inside an L-pipe log line (entries 67, 68) |
| S2.9: planted claims were mass duplicates (8 sources for 132 items); the ordered header revealed HELIOS-Full on 43 of 99 verification steps | Fresh review (S2.9) | Each source used once, a per-category floor and a per-kind cap; unordered header; blinding check split by leak and shared kinds; training data rebuilt |
| GitHub Actions minutes exhausted | 30 Oct | Local gate and local `--no-ff` merges; no push until minutes return (S2-BL-16) |
| A type error was committed because a check piped mypy through `tail` | The next check | Every check chain now runs with `pipefail` |
| The Mac slept for three hours during narrator round 1 (battery nearly empty) | Gap in the Ollama log | Rounds run on mains power; cached answers made the rerun cheap |

### Design-science notes (for Chapter 4)

- **Calibration as an evaluation episode for the testbed itself.** S2.1's calibration was meant to tune a detector; its failure on OTel (51/63 missed) exposed four defects in the capture layer that had been there since May. Fixing the instrument before tuning the artefact changed the build data (v3) and the threats register (T19–T21).
- **Generate-and-check beats instruct-and-hope for small models.** The narrator moved from "the LLM writes, the verifier checks" (rounds 1–2) to "code writes verified candidates, the LLM selects and orders" (round 3). Grounding then holds by construction and the LLM's contribution narrows to selection; A-H7's Full-vs-noLLM difference is expected near zero and will be reported as observed.
- **Every fresh whole-branch review found something the tests did not:** signature laundering (S2.7), containment bypasses (S2.8 PR 1), digest-wording log quotes (S2.8 PR 2), duplicate planted claims and a header arm leak (S2.9). One review per branch on the most capable model, after the implementer's own tests, was the cheapest place to catch these.
- **Pre-registration pressure surfaces as deviation entries, not silent changes.** 23 entries in six days, all before any confirmatory data exist; seven came from defects or reviews. Each records its analytic consequence, and S2-BL-05 tracks what the OSF addendum must carry.
- **Integrity tooling paid for itself again:** the leak test, the tracking validator's range mode, the signed ledgers' tamper tests, and the freeze tests (prompt SHA, parameter hashes) each blocked a mistake during the sprint.

### To raise at the chair call

From the backlog (`backlog.md`) and the sprint:

- A-H4 power on build data (MAHC near null on the ambiguous stratum; S2-BL-02);
- the build-to-pool shift (the pool has traces, build RCAEval does not; S2-BL-01);
- the routing gate costing G-pipe cases (S2-BL-06, S3.1);
- the fallback trigger time using the window peak (non-causal; S2-BL-12);
- A-H7 expected near zero under pick-and-order (entries 65–68);
- the OSF addendum contents (S2-BL-05: entries 46–68, the H_fact definition, the narrator change, the S2.9 entry).

## 5. Carry-overs

| Item | Owner | Date | Note |
|---|---|---|---|
| S2.9 rater training to κ ≥ 0.7, rubric freeze (hash), S2.9 deviation entry (design §6), row S2-M7-RES01 DONE | AA (owner), Claude | Rater 2 by 30 Nov; training Dec – early Jan; before S5 | Owner steps: `label_server.py keygen > .env.labelling` (back it up), add R1, R2 and the adjudicator, open the tunnel |
| IRB, second rater, adjudicator (S0.11 L1–L3; row S2-M5-RES05) | AA | 30 Nov | Carried since S0 |
| Push local main (141+ commits), tag `rb-s2-exit`, one PR, one CI run | AA, Claude | When Actions minutes return | S2-BL-16 |
| OSF addendum (entries 46–68; H_fact definition; narrator pick-and-order) | AA, Claude | Before `build-freeze` | S2-BL-05 |
| Back up `.env`, `.env.labelling`, the L-pipe response cache and the build ledgers (`data/labelling/build`) | AA | Now | S2-BL-17, S2-BL-19 |
| Backlog S2-BL-01…20 (threats, weak components, measurement, debt) | AA, Claude | Revisit after S2 (owner) | `backlog.md`; deferred review minors of S2.7–S2.9 included |
| S3 plan refresh (capacity, owner items, carry-overs) | Claude | Before S3 starts | Root CLAUDE.md § Sprints, step 5 |
