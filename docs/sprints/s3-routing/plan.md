# Sprint S3 — Routing and learning · plan

**Window:** 4–15 Jan 2027 (10 working days); may start early once the owner confirms, as S1 and S2 did (S2 closed 2026-11-01, about eight weeks ahead) · **Milestone:** S2-M8 · **Exit tag:** `rb-s3-exit` · **Status:** closed 2026-11-09 ([exit report](exit_report.md)); refreshed 2026-11-06 with the S0–S2 carry-overs

Task details: `docs/tracking/helios_task_breakdown.md` § Sprint S3 (authoritative).

## Goal

The cheap-first router (IN3) sends statistical and graph evidence first and calls the LLM only on disagreement or low confidence, with frozen, hashed parameters. Tier-2 learning parts (ACP, two-stage reward, Knowledge Cortex, LLM fallback) are built behind their flags (`VCLFlag`: `cbr_routing`, `acp_stateful`, `reconcile_terminal`) or recorded as moved to Stage B.

## Entry conditions

| Condition | State (2026-11-06) |
|---|---|
| `rb-s2-exit`: MAHC (S2.5) and cost accounting (S1.10) for the router; L-pipe (S2.3) for the Knowledge Cortex | **Met** (tag on `d3c492b`, local) |
| Local `main` pushed, `rb-s2-exit` pushed, one PR with a green CI run (S2-BL-16) | **Open** — `main` is 146 commits ahead of `origin/main`; nothing since S2.3 PR 2 has run in CI. Do this before S3 code lands, so S3 is not stacked on an unverified base |
| Working tree clean of unregistered data | **Open** — untracked `data/otel/pilot_v3/` (3 captures) and `data/otel/ground_truth_pilot_v3.json`, 269 uncommitted lines in `experiments/experiment_log.csv`, local edits in `external/otel-demo-pinned` (`.env`, `src/flagd/demo.flagd.json`). Decide: seal and register as build data (deviation entry), or discard. Router initialisation (S3.1) must not read unsealed data |
| S2-M8 tracking rows (ENG01–ENG05, GATE01) added | Open — added at sprint start |

## Capacity

9 days of the breakdown's tasks in 10 working days, plus about 2 days of carried-in work (below). Only S3.1 is Tier 1. With the early-start precedent, time is not the constraint; the order of work is: entry conditions → S3.1 → carried-in engineering items → Tier 2. Any slack left over moves forward to S4, which is over by 3½ days.

## Tasks

| Task | Tier | Tracking | Effort | Depends on | Done when |
|---|---|---|---|---|---|
| S3.1 Router with cheap-first gate (IN3) | T1 | S2-M8-ENG01 | 3 | S2.5, S1.10 | Routed arm recorded per run; VCL verifies frozen parameters at start |
| S3.2 Action-Class Predictor | T2 | S2-M8-ENG02 | 2 | S1.5 | Gated; parameters hashed |
| S3.3 Two-stage reward and delayed labels | T2 | S2-M8-ENG03 | 2 | S3.1 | Provisional/terminal pairs verify; `reconcile_terminal=OFF` writes none |
| S3.4 Knowledge Cortex (SOP retrieval, build data only) | T2 | S2-M8-ENG04 | 1½ | S2.3 | Retrieval tests; pool-exclusion test |
| S3.5 LLM-unavailable fallback | T2 | S2-M8-ENG05 | ½ | S3.1 | Route to D+G on LLM failure; covariate recorded |

S3.1 design: [s3_1_router_design.md](s3_1_router_design.md) (approved 2026-11-06, R-a…R-e as recommended) · [implementation plan](s3_1_implementation_plan.md).

### OTel fix and the order of work (owner, 2026-11-07)

The OTel build diagnosis (`otel_diagnosis/README.md`) found all 13 misses visible in the data, and three causes in the implementation.

**Owner decisions:**
- **OTel fix scope.** Fixes A and B are built now (row S2-M8-ENG06; design `s3_otel_fix_design.md`):
  - A: error origin as a G-pipe feature;
  - B: D-pipe memory.
  - Fix C (caller-confined errors, recommendationCacheFailure) moves to Stage B.
- **S3.2 ACP and S3.4 Knowledge Cortex stay exploratory.** They are kept out of HELIOS-Full's confirmatory path, so the only change to the frozen chain before the S3 exit is the OTel fix.

**Order of work.** The frozen chain (D-pipe → G-pipe → MAHC → router) is refit once:

| Step | Work |
|---|---|
| 1 | Merge PR 83 (S3.3) and the diagnosis |
| 2 | OTel-fix design and pre-run entry. Capture the held-out OTel v4 corpus, then seal it and leave it unread. Write the S3.2 and S3.4 design notes |
| 3 | Build fixes A and B on build data |
| 4 | One refit chain: D-pipe → G-pipe → MAHC → router (row S2-M8-ENG07) |
| 5 | Score once on v4 and RCAEval build; adopt or revert by the pre-registered rule — **Done 2026-11-08 (entry 81): old chain kept** (v4 30/36 both chains; RCAEval build 478/495 both) |
| 6 | Rerun the S3.3 replay (run 3) — not needed, chain not adopted (entry 81); build S3.2 and S3.4 as exploratory |
| 7 | S3 exit gate |

### Carried-in items that shape the tasks

**S3.1 router**
- **S2-BL-06, G-pipe gate loss.** The frozen disagreement gate (`DISAGREEMENT_THRESHOLD` = 0.20 in `helios/pipelines/g_pipe/gpipe_config.py`, set in May) runs G-pipe on 44 of 63 OTel cases. Ungated, G-pipe alone scored 50/63, above the fused 49. The router is where this is settled: either the router replaces the gate (G is a cheap arm, as in IN3's "statistical + graph first"), or the gate is kept with a recalibrated threshold. Both change a frozen parameter, so either needs a deviation entry. Report HR@3 for gated, ungated and routed on build data (exploratory).
- **S2-BL-08, modest MAHC confidence.** The router's "low confidence" trigger reads MAHC's calibrated confidence, which separates confirmed from provisional cases only modestly (OTel 0.85 vs 0.72; RCAEval 0.99 vs 0.95; six distinct levels). Pick the low-confidence threshold on that distribution, not on a nominal value, and report the share of cases that reach the LLM per corpus.
- **S2-BL-07, weak L-pipe on OTel.** With L-pipe the weakest pipeline on OTel (44/63), cheap-first routing may also be the more accurate path, not only the cheaper one. Record this as an exploratory build-data observation; do not tune the router to it.
- **S2-BL-01 and S2-BL-03, build → pool shift.** The router is initialised on build data only (63 OTel + 495 RCAEval build cases), frozen and hashed. G-pipe has never seen RCAEval with traces, so the routed-arm split by G participation is pre-registered in the OSF addendum (below), not discovered on the pool.
- **S2-BL-13, timing.** The routed arm changes when the LLM starts. Record each run's arm and the time each pipeline starts, so TTT can be recomputed when S4's scoring path adds graph-build time.
- **Price book (S1 carry-over).** The router's cost term reads price-book-v2's AWS primary profile (verified 2026-10-27). Hash the profile into the router parameters; the unverified GCP and Azure profiles are sensitivity analyses only and must not feed routing.

**S3.4 Knowledge Cortex**
- **S2-BL-07.** The log digest is often empty after the trigger. Check whether SOP retrieval helps the log worker on build data; any gain is exploratory and does not change the frozen L-pipe prompts without an entry.

**S3.5 LLM-unavailable fallback**
- **S2-BL-17.** Cache-only reruns need `data/cache/lpipe_cache.sqlite`, the pinned llama3.1:8b digest and a local Ollama. A cache miss with Ollama down is exactly the fallback case: test that it routes to D+G and records the covariate, without writing to the cache. — **Done 2026-11-07 (entry 73):** cache-only reruns no longer need Ollama (cache read under the pinned digest); a miss records `llm_unavailable=cache_miss`, writes nothing, and the run completes on D and G.

### Engineering items carried in (about 2 days, after S3.1)

| Item | Source | Done when |
|---|---|---|
| Fallback trigger time uses the window peak (non-causal, so TTCD/TTT look ahead); D-pipe propagation inert on build data; scipy `ConstantInputWarning` silenced only in tests | S2-BL-12 | Causal fallback (deviation entry, since the detector is frozen) or documented as a limitation; dead propagation decided (keep behind `dpipe_propagation`, or record); warning handled in code — **Done 2026-11-06 (owner: record and report; entry 71):** anchor unchanged; `known_at_s` and detection delay recorded per trigger (threshold 180 s; fallback median 150 s OTel, 300 s RCAEval build); operational TTCD exploratory, defined in the OSF addendum (contract frozen; entry 72); propagation kept behind `dpipe_propagation` and recorded as inert on build data; constant-series guard removes the warning (scores unchanged) |
| Deferred review minors: vote-only score scale, first-publication state not stored, either-state runner test, unseen-pipeline prior, empty `BuildCase` votes, masking edge cases | S2-BL-18 | Tests first; each fixed or noted in the backlog — **Done 2026-11-06:** either-state runner test pins `provisional`; an all-abstain build case is kept as a provisional miss (test; `BuildCase` stays permissive, since refusing it would drop real misses from the frozen MAHC denominators). **Not changed** (each would alter a frozen output): vote-only score scale (rankings only are compared across methods); unseen-pipeline prior (frozen MAHC); masking edge cases (frozen L-pipe prompts and cache; pool names checked at build-freeze). First-publication state: left to the S4 scoring path (TTT reads the first publication, entry 60) |
| CoE ledger minors: verdict ref is the decision hash, model-hash fallback to the expected digest, G/L evidence refs | S2-BL-20 | Tests first; each fixed or noted — **Done 2026-11-06:** `lpipe_model` is the digest the L-pipe ran with (empty when it did not run); evidence ref only for stored (non-empty) evidence; whole-row verdict hash added under `measured` (refs stay rerun-equal); claim cites outside the digest counted (`unknown_cites`); `anchor_unsigned` stripped only for Ed25519-anchored logs. Fusion ref and F-step state following replayed timing: by design (entry 60) |
| `bin/pin-otel-demo.sh` uses GNU `sed -i` (line 51), which fails on macOS | S1 carry-over | Portable form; script runs on the M5 Pro — **Done 2026-11-06:** `sed -i.bak … && rm -f .env.bak` |
| Four May-plan rows S1-M4-RES01, RES02, EVAL01, GATE01 still PLANNED | Tracker housekeeping | Each DEFERRED with a deviation reference to the re-baselined plan (D11 / e2e plan) — **Done 2026-11-06:** DEFERRED, dev-025 and dev-027 |

Signal-type classification (S2-BL-09: 54% of OTel cases unclassified) is a refit of MAHC's priors. It stays in the backlog unless the router needs it, and is done only with a new entry before any refit.

## Owner items

| Item | Source | Needed by |
|---|---|---|
| Rater 2 and adjudicator recruited; IRB submitted (S0.11 L1–L3, row S2-M5-RES05) | Carried since S0 | 30 Nov 2026 |
| S2.9 rater training to κ ≥ 0.7, rubric freeze (hash), S2.9 deviation entry; row S2-M7-RES01 DONE. Owner steps first: `label_server.py keygen > .env.labelling` (back it up), add R1, R2 and the adjudicator, open the tunnel | S2 exit §5 | End of January 2027, before S5 |
| Back up `.env`, `.env.labelling`, `data/cache/lpipe_cache.sqlite` and `data/labelling/build` | S2-BL-17, S2-BL-19 | Now |
| Chair call, with a call-reference doc and outcomes table prepared first. Agenda: opportunity cost (5,600 per minute, sensitivity 14,056), retention and review minutes, May capture defects (T13, T17); TTT read as first publication (entry 46); A-H4 power and the ceiling (S2-BL-02); H_struct option (b) (S2-BL-14); the pool's two-worker L-pipe; **the router decision on the G-pipe gate (S2-BL-06) and the risk that cheap-first hides LLM value from A-H1/A-H2** | S1 and S2 carry-overs | Before S3.1's parameters are frozen |
| GCP and Azure price-book profiles checked against official price lists; any changed value is a deviation entry | S1 carry-over | Before `build-freeze` |
| Hook commands use `$CLAUDE_PROJECT_DIR` (the `cd` lock-up) — approve the change to `.claude/settings.json` | Open since S0 | Any time |

## OSF addendum (drafted in S3, deposited before `build-freeze`)

S3 adds the router's entries to what the addendum must cover, so the draft starts here rather than in S5:

- entries 46–68 and the S3 entries (router initialisation and thresholds, the G-pipe gate decision);
- the H_fact definition and the narrator's pick-and-order;
- the `metric_contract.md` §9 correction;
- S2-BL-01: an analysis split by G-pipe participation (and by routed arm);
- S2-BL-05: every change since deposit 1 that alters what a confirmatory test measures.
- **A-H5 split by stage** (S3.1 design §2, owner 2026-11-06): log-CpR reported separately for runs that stopped on the cheap arm and runs escalated to the L-pipe, so the early-publication effect and the LLM-savings effect are not read as one;
- **A-H1 split by escalation** (S3.1 design §10): noLLM also routes, so Full and noLLM differ only on escalated runs;
- the meaning of uniform routing (R-b) and the reachable arm set (R-c).
- **Detection delay and operational TTCD** (S2-BL-12, entries 71 and 72). `metric_contract.md` is signed into deposit 1 (`manifest_sig.txt`), so these definitions live in the addendum, not in the contract:
  - *Detection delay*: recorded seconds from the trigger's anchor (`trigger_time_s`) to the earliest instant a live detector could have issued it (`known_at_s`): end of the last persistence bucket (threshold), end of the scored window (fallback); none for external triggers. Identical for every system on an incident. Descriptive.
  - *Operational TTCD*: detection delay + TTCD, censored at 1,800 s. Exploratory; reported beside TTCD, never replacing it in B-H6, CpR or A-H5.
  - TTCD and TTT split by trigger source (threshold / fallback), with the fallback share reported beside every timing result.
  - TTCD and TTT are measured from the trigger handover (entry 46); the contract's "invocation" wording is superseded by entry 46.
- **LLM availability covariate** (S3.5, design note `s3_5_llm_fallback.md`). Every run that asked the L-pipe records `llm_unavailable` in its CoE routing step: `endpoint` (model endpoint unreachable, no usable cache), `cache_miss` (endpoint unreachable, prompt not in the cache), `calls` (every model call failed), or none. A routed run whose escalation met an unavailable LLM publishes its cheap arm (`fallback`). Reported per variant and corpus beside every confirmatory result. A confirmatory comparison is reported with and without its affected incidents if any pair is affected; neither variant is rerun selectively.
- **E-H5 delayed-label subset** (S3.3, design note `s3_3_reward_design.md`, pre-run entry). The pool replay runs after the confirmatory runs are scored, on a seeded 25% of each pool corpus. The selection rule (seed and stratification) is fixed here before `build-freeze`. Rewards, clock, update rule and starting state are as in the build replay; RRE and learning curves are reported with BCa intervals, outside the Holm family.

- **OTel fix and held-out v4** (entries 76–81, design `s3_otel_fix_design.md`). Exploratory, no pipeline change: the OTel v4 corpus (36 cases, sealed, manifest digest 22248602f708) was read once by a pre-registered adoption rule; the refit chain (fixes A and B) tied the frozen chain (v4 30/36, RCAEval build 478/495) and was not adopted. Reported: the frozen chain's v4 result (HELIOS-Full and noRouter, per fault type) and the null result of the fixes. v4 is not part of the confirmatory pool.

- **E-H8 not testable in Stage A; ACP label set** (S3.2, entries 82 and 83, design `s3_2_acp_design.md`). The ACP is built and frozen but recorded only: the frozen router does not read it, so HELIOS-Full and HELIOS-noACP route identically and E-H8's latency-constraint satisfaction cannot differ. E-H8 moves to Stage B (router refit with the ACP block). The ACP predicts four remediation families mapped from injected fault types (resource, network, config, code) in place of Ch3's schema change, data mutation and config change; its build figures are exploratory.
- **S3.4 Knowledge Cortex** moved to Stage B (entry 82).

After the S3.1 build run, recheck the D11 compute estimate (about 1,500 L-pipe runs, 30–50 h) against the measured escalation share: noRouter and LLM-only call the L-pipe on every case.

## Expected deviation entries

Router initialisation and thresholds (S3.1); G-pipe gate decision (S3.1, S2-BL-06); ACP and reward parameters if built (S3.2, S3.3); detection delay and operational TTCD, TTCD/TTT split by trigger source (S2-BL-12, entry 71); pilot_v3 captures if registered as build data; the four May-plan rows marked DEFERRED; Tier-2 items moved to Stage B.

## Exit criteria

S3.1 DONE; each Tier-2 task DONE behind its flag or recorded as moved to Stage B; CI green on the pushed base and on the S3 merge; full gate green; tag `rb-s3-exit` (pushed); exit report written, with the status of every carried-in item above.

## Risks

| Risk | Mitigation |
|---|---|
| Router tuned on data that overlaps the pool | Initialised on build data only; parameters frozen and hashed; pool locked until `build-freeze` |
| Cheap-first gate hides LLM value from A-H1/A-H2 | Routed arm recorded per run; noRouter (uniform) is a confirmatory variant; raised at the chair call |
| Router parameters tuned after inspecting build results (forking paths, S2-BL-04) | One selection run fixed in advance; any rerun is a signed entry and the withdrawn report is kept |
| Large first CI run surfaces environment differences across 146 commits | Push before S3 code; fix CI failures in their own commits, not in S3 work |
| Rater 2 slips past 30 Nov | S2.9 training runs alongside S3; S5 is the hard limit |
