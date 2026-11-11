# S4.9 Metrics suite (design)

Row S2-M9-ENG09 · Tier 1 · 2026-11-11 · **Approved 2026-11-11 (M-a to M-h as recommended)**

## 1. What is asked

Breakdown S4.9: HR@k, Avg@5, MRR, CpR, time to correct diagnosis (TTCD), time to triage (TTT), H_struct, H_fact (verifier output plus κ over the two raters), non-convergence count. Done when the fixture values match a hand computation.

Fixed points this design does not touch:
- `docs/tracking/metric_contract.md` is signed into OSF deposit 1 and is never edited. Where this design settles a choice the contract leaves open, the choice goes into a deviation entry and the OSF addendum draft, before any confirmatory data exists.
- Definitions already changed by entries stay as those entries say: entry 46 (TTCD and TTT start at the trigger handover), entry 59 (H_struct option b), entry 60 (one fused verdict per run; first and terminal publication; replayed concurrency), entry 65 (H_fact against cited evidence, no ground truth), entry 69 (routed runs: staged timing), entries 71–72 (detection delay, operational TTCD, split by trigger source).
- Scoring happens after dispatch only. No pipeline reads a score, and the pool stays locked until `build-freeze` (`PoolLockedError` stays as it is).

## 2. What exists and what is missing

| Metric | Today | Gap |
|---|---|---|
| HR@1/3/10, Avg@5, MRR | `helios/evaluation/scoring.py` → `eval_score`, per fused and per-pipeline list | None. Kept as is. `helios/evaluation/metrics.py` (May `hr_at_k` stub, used only by its own test and `helios/evaluation/__init__.py`) is retired into `scoring.py` |
| CpR | `cost.py::cpr(usage, requests_human, ttcd_s, book)` | Nothing calls it per run yet: it needs TTCD and a rule for `requests_human` (M-c) |
| TTT | `fusion_row.first_ms`: replayed time from the first pipeline's start | **Leaves out graph build** (S2-BL-13). Entry 46 starts the clock at handover, before the UEG-C is built (M-a) |
| TTCD | Not computed | Built from the run's publications (M-b) |
| Operational TTCD, detection delay | `trigger_row.known_at_s` stored | Not computed |
| H_struct | `hstruct_row` (outputs, failed, structural_zero) | Per-case ratio not computed |
| H_fact | `rater_agreement.py::h_fact` from the annotations ledger | A narrative with no claims gives `None`, but the contract says **0** (M-d); not joined to runs |
| Verifier labels, grounding rejection rate | `narrative_row` slots, attempts, fallbacks | Not aggregated |
| Non-convergence, HITL rate, routed arm, LLM consulted | `fusion_row.non_converged`, `state`; CoE routing step | Not aggregated |
| Strata (ambiguous, narrative-heavy) | Not computed; τ_N not set | M-e |
| Confidence calibration, RRE, false-accept rate | `fusion_row.confidence`; reward ledgers; FGSV not built | Descriptive or exploratory (M-f) |

## 3. Decisions (for approval)

### M-a. Graph build counts in TTT and TTCD, as a measured record

Entry 46 starts the clock when the trigger is handed over (`trigger_row.handover_unix`). The runner then builds the UEG-C and only afterwards starts the pipelines. `fusion_row.first_ms` counts from the pipelines' (replayed) start, so today TTT leaves out graph building.

- **Recommended (a):** the runner writes graph build as its own `timing_row` (pipeline `ueg_c`: started at handover, published when `incident_graph` returns). Then **elapsed_ms = graph_build_ms + the replayed publication time**. When no graph is built (no traces, or `l2b_graph` OFF), `graph_build_ms` is the measured near-zero gap. Every variant gets the same rule. The UEG-C digest and every verdict stay as they are; only a timing row is added.
- (b) Derive it with no runner change: earliest pipeline `started_unix` − `handover_unix`. This includes trigger and registry writes and is less explicit. It stays as the fallback for rows written before (a).

Graph build is measured wall time, not replayed, so it is hardware-specific. Every timing result reports the hardware (S2-BL-13).

### M-b. TTCD from the run's publication sequence

A run publishes at most two fused lists (entries 60, 69):

| Run | Publication 1 | Publication 2 |
|---|---|---|
| Uniform, converged | `first_ms`, `first_ranked` | `terminal_ms`, terminal list |
| Routed, stopped on the cheap arm | `first_ms` (end of the cheap stage), cheap list | — (terminal = first) |
| Routed, escalated | `first_ms`, cheap list | `terminal_ms` (after the L-pipe), terminal list |
| Non-converged | `first_ms`, `first_ranked` | see below |
| Baseline (S4.8) | its runtime, its list | — |

**TTCD** = graph_build + the time of the earliest publication whose top-1 is the ground-truth service; censored at 1,800 s if none is. **TTT** = graph_build + `first_ms` (entry 60: TTT is the first publication, whatever its state).

**Non-converged runs.** MAHC still forms a list from the pipelines in time and labels it NON_CONVERGED, but `terminal_ms` is empty.
- **Recommended (a):** that list counts as published at 90 s (`CONVERGE_MS`), because Ch3 hands a non-converged verdict to a human.
- (b) Only the first publication counts.

(a) gives non-converged runs a chance at a correct diagnosis at 90 s; (b) censors them unless the first list was already right.

**Operational TTCD** = detection delay (`known_at_s − trigger_time_s`) + TTCD, censored at 1,800 s; exploratory. Every timing metric carries the trigger source (threshold / fallback / external) for the split in entry 71.

**The narrator is outside TTT and TTCD.** The verdict is published before its narrative is written, so narrator wall time is recorded separately as *time to narrative* (descriptive) and never added to TTT or TTCD.

### M-c. CpR per run

`cpr()` as built in S1.10, fed per run:
- **usage** = the run's pipeline verdicts plus the narrator's tokens (`incident_usage`);
- **storage** = the window's recorded bytes;
- **TTCD** from M-b, so opportunity cost includes graph build;
- **`requests_human` = published state is PROVISIONAL or NON_CONVERGED.** The contract's "PROVISIONAL with HITL, non-convergence": in evidence runs every PROVISIONAL verdict goes to a human (simulated HITL), so the two coincide. CONFIRMED carries no review time.

Primary profile: price-book-v2 AWS (the router's hashed profile). GCP and Azure are computed as sensitivity columns only.

### M-d. Hallucination per case

- **H_struct** = Σ failed / Σ outputs over the run's `hstruct_row`; 0 when there are no outputs; `structural_zero` carried as a flag (entry 59).
- **H_fact** = unsupported / claims over the adjudicated rater labels of the run's displayed narrative. **A narrative with no claims scores 0**, as the contract says; `rater_agreement._rate` returns `None` for that case. The suite applies the contract's 0 at the case level, keeps the count of zero-claim narratives, and leaves `rater_agreement.py` unchanged, since the S2.9 instrument reports on it. Pending (unlabelled) claims leave H_fact empty for that case and are counted, never imputed.
- **Beside it** (entry 65; never in its place): the verifier's per-case H_fact, κ between the raters and between the verifier and the consensus, and the grounding rejection rate (claims the verifier removed / claims proposed, from `narrative_row`).

Until rater 2 exists, H_fact runs on fixtures and on the S2.9 training data only.

### M-e. Strata, fixed before the freeze

- **Ambiguous (A-H4):** from the HELIOS-Full run of the case, the pipelines that returned a ranked list disagree on top-1 (at least two distinct top-1s). This reads `result_row` only; no label is used. Every variant's row for that case carries the same flag.
- **Narrative-heavy (A-H6):** the share of the window's post-injection log lines that match templates not seen in the pre-injection half is at least τ_N.
  - The split point is the injection time, which only the harness may read: under the same ground-truth lock as scoring, never passed to a pipeline.
  - τ_N = the median of that share over the build data, computed once and frozen with a deviation entry before `build-freeze` (contract §7).
  - **Recommended:** the median over RCAEval build cases only (the pool is RCAEval). The OTel build share is reported but not pooled, since its log volume differs.

### M-f. Descriptive and exploratory measures

Per run: non-converged flag; published state; HITL request; routed arm, escalated or not, LLM consulted; `llm_unavailable` (S3.5); detection delay; time to narrative. Aggregated by the analysis suite (S4.11), not here. Calibration curve inputs: (confidence, HR@3) pairs. RRE stays in `reward_replay.py` (S3.3). **False-accept rate (E-H4):** the function and its fixture test are built here; its data comes from S4.6.

### M-g. Where the values are stored

Contract §10: "Analysis reads `eval_score` only." `eval_score` is keyed per *list* (fused and each pipeline), while TTCD, CpR, H_fact and the strata belong to a *run*.

- **Recommended (a):** a second harness-written table `eval_run` (one row per run, schema tag `eval-run-v1`), with `metrics_version` and the price-book digest. The addendum states that the analysis reads only the harness-written `eval_*` tables, never pipeline rows: the intent of §10.
- (b) Widen `eval_score` with run-level columns filled only on fused rows. This has no table change but duplicates fields and leaves nulls on every pipeline row.

### M-h. Fixtures and hand computation

- A fixture store with seven hand-built runs:
  - uniform converged;
  - routed, stopped on the cheap arm;
  - routed, escalated, right only after escalation;
  - non-converged;
  - LLM-only with a structural non-zero H_struct;
  - noLLM (structural zero);
  - one baseline row.
- Expected values (TTT, TTCD with and without censoring, operational TTCD, the five CpR components, H_struct, H_fact including a zero-claim narrative, the strata) are worked out by hand in a table in the test module, with their arithmetic. The test compares exactly (CpR to 1e-9).
- `bin/score_runs.py` gains `--metrics` to write `eval_run` after `eval_score`. Like today, it prints counts and means only, never case names or labels.
- Exploratory run on build data (RCAEval build and OTel v3, existing stores): TTT and TTCD distributions before and after M-a, to show what graph build adds. Reported, not tuned to.

## 4. Deviation entry and addendum

One entry after approval, before the code merges. It covers:
- M-a: graph build inside TTT and TTCD, recorded as a timing row; this implements entry 46;
- M-b: the publication sequence, the non-converged rule and the narrator outside the clock;
- M-c: the `requests_human` rule;
- M-d: zero-claim H_fact = 0 at the case level;
- M-g: the `eval_run` table.

τ_N gets its own freeze entry when it is computed (M-e). The same text goes into the OSF addendum draft.

## 5. Deliverables and effort

| Item | Effort |
|---|---|
| Runner: `ueg_c` timing row; store: `eval_run`, `fetch_timing` helpers | ¼ day |
| `helios/evaluation/run_metrics.py`: publication sequence, TTT, TTCD, operational TTCD, CpR wiring, H_struct, H_fact join, strata, descriptive fields; `metrics.py` retired | 1 day |
| τ_N on RCAEval build (frozen file plus entry); fixtures with hand computation; `score_runs.py --metrics`; build-data run | ½ day |

About 1¾ days against the 1½ estimate. The extra quarter day is the runner timing row and the strata, which no task listed.

## 6. Risks

| Risk | Mitigation |
|---|---|
| A metric choice drifts from the signed contract | Contract read-only; every open choice in the entry and the addendum before confirmatory data |
| TTCD looks better than it is because graph build or the narrator is left out | M-a counts graph build; M-b states the narrator rule explicitly |
| H_fact read as zero where labels are missing | Pending claims leave the case empty and are counted; only a narrative with no claims is 0 |
| Strata thresholds chosen after seeing results | τ_N is fixed on build data and frozen by entry before `build-freeze`; ambiguity uses no label |
| Timing is hardware-specific | Hardware recorded in every report; the comparison is paired by case on one machine |
