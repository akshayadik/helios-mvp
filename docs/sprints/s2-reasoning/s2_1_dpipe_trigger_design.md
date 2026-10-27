# S2.1 — D-pipe completion and the shared detection trigger · design

**Task:** S2.1 (tracking S2-M7-ENG01) · **Date:** 2026-10-27 · **Status:** for owner approval · **Depends on:** S1.8 verdict contract, S1.7 K-hop pruner, S1.2 OTel build corpus · **Owner decisions:** detection trigger option (a) (S2-M6-RES04, 2026-10-26); the points marked *owner* below (2026-10-27)

## 1. Intent

Every incident in the evaluation needs one **shared starting point**: the moment a label-free detector decides "something is wrong here". HELIOS and the five baselines all receive this same trigger, and none of them ever sees the true injection time (metric contract §1). The trigger:

- tells each system **when** the incident starts and **where** to look first (its suspect services seed the K-hop pruner, S1.7);
- starts the clock for time to correct diagnosis (B-H6);
- is the anchor that lets D-pipe compare "before" with "after", instead of scoring the whole window as one block.

S2.1 also finishes D-pipe so it can take part in the confirmatory runs at all: today it reads only the OTel latency histograms, so on RCAEval's metric format (plain per-service series under `service_name`, no histograms) it finds no services and abstains — on the build corpus and, in the same way, on every confirmatory case.

## 2. Decisions already made

| # | Decision | Who |
|---|---|---|
| D-a | One frozen, label-free detector, tuned on build data only, gives every system the same trigger time; an exploratory run with the true injection time bridges to published RCAEval scores and never enters a confirmatory test | owner, 2026-10-26 |
| D-b | The trigger fires at the **first moment a single signal looks wrong**, not when evidence is strong enough to page someone | owner, 2026-10-27 |
| D-c | **Every trigger is treated as genuine at run time.** All systems run their full analysis from it. Afterwards, the evaluation step labels it a *true* or *false* trigger using the signed ground truth; the pipelines never see that label | owner, 2026-10-27 |
| D-d | **Time to correct diagnosis starts at the detection trigger** (the D11 wording), not at system start: data loading and pipeline start-up are outside the measured time. This changes the deposited metric contract §4, so it needs a deviation entry before confirmatory data, a note in the next OSF deposit addendum, and an item in the mid-November chair-call document | owner, 2026-10-27 |
| D-e | **At most 5% false triggers on build data.** Reason (owner): build data is cleaner than live traffic, and a 10% rate would inflate to 20–30% live and flood the LLM pipelines with cost and queueing | owner, 2026-10-27 |
| D-f | **Exclude the test harness and the observability stack from the root-cause candidate pool, but keep their telemetry visible.** Owner's reasons: the load generator and flag service are synthetic testbed artefacts, so their anomalies are testbed noise that would waste compute and inflate false triggers. The ground truth never injects into Prometheus or the collector, so naming a real but out-of-scope failure there would be scored as a false positive for HELIOS and the baselines alike. Their health metrics stay in the graph and in the evidence: if telemetry drops for an application service, HELIOS must be able to recognise a broken collector instead of hallucinating an application fault. Logged as a deviation entry (§5.1a). This closes the S1 carry-over on infrastructure candidates | owner, 2026-10-27 (revised the same day; first answer was "keep them") |

| D-g | **OTel `_sum` series are gauges, not counts.** They are summed durations, so a Poisson floor would make their scale depend on the unit (seconds vs milliseconds); they get the relative gauge floor. The Poisson floor stays for event counts only: `_total`, `_count`, `_bucket` counters, RCAEval `error`, log line counts | owner, 2026-10-27 (before calibration) |
| D-h | **Direction of resource signals.** Workload and socket count in both directions (a drop means a crash, starvation or a broken connection). CPU and memory count rises only: a drop is a secondary symptom of a workload collapse, and tracking it would inflate false triggers during upstream outages. Applies to the trigger and to D-pipe. Other metrics keep their previous behaviour (trigger: both directions; D-pipe: rises) | owner, 2026-10-27 (before calibration) |

| D-i | **Short-history and many-series corrections.** The first calibration (grid fixed in advance) found no setting at or below 5% false triggers on both corpora (best: about 20% on each, with 41 of 63 OTel faults missed); most false triggers fired just after the four-bucket warm-up, where a scale from four points is noisy. Fix, approved by the owner: each bucket's z is shrunk by a Student-t prediction-interval factor for its number of past points (about 3.7 with four points, near 1 with many), and a service's largest score is divided by the Bonferroni factor for its number of series; both at tail probability 0.001, fixed before the rerun. No parameter refers to a position | owner, 2026-10-27 (after the first calibration) |

## 3. Goals, non-goals, anti-goals

**Goals**
1. A detector that, for any sealed window (RCAEval or OTel), returns a trigger record: trigger time, the suspect services at that time, and how the trigger was reached. It is deterministic and label-free.
2. Runner order changed so the trigger runs first; its suspects are passed to `khop_prune(seeds=...)`, and its time is handed to every pipeline and recorded for every baseline run.
3. D-pipe that works on both corpora's metric formats, uses the trigger to split each window into a reference part and an incident part, fills σ, and loads its frozen parameters (today it silently runs on code defaults, not the values in `research/osf/thresholds.json`).
4. Bitwise rerun equality: two separate processes on the same window produce identical bytes for the trigger record and the D-pipe verdict.
5. A post-run trigger classification (true / false / no trigger) and a calibration report on build data.

**Non-goals**
- Live, streaming detection (Stage B, B1). Here the detector reads a recorded window after the fact.
- Time-to-detect as a metric. On recorded windows "how fast the fault became visible" is not measured; only compute time after the trigger is (D-d).
- The G-pipe learned ranker (S2.2) and MAHC's use of σ (S2.5). S2.1 only produces σ.
- Computing TTCD itself (evaluation tooling, S4). S2.1 records the timestamps TTCD needs.

**Anti-goals** (would make this a failure even if it "works")
- Any path by which the injection time, the fault, or a label reaches the detector, D-pipe, the runner, or a baseline's input. The S1.9 leakage scan must keep passing with the new code on the run path.
- Calibrating anything on the confirmatory pool, or looking at pool outcomes before `build-freeze`.
- A detector that meets 5% by never firing: missed triggers are reported next to false ones, and the tuning rule (§5.3) prefers early, real triggers.
- Different trigger times for HELIOS and a baseline on the same case.
- Editing deposited files (`research/osf/*`, `docs/tracking/metric_contract.md`) or the seed register.

## 4. Constraints

- Every HELIOS mechanism stays behind a flag and ablatable. D-pipe's new parts (format-neutral parsing, trigger split, σ) sit under the existing `VCLFlag.DPIPE` (propagation stays under `VCLFlag.DPIPE_PROPAGATION`). **The trigger is not a HELIOS component and gets no VCL flag:** it is shared evaluation input, like the recorded window, given identically to every variant and every baseline, and no hypothesis ablates it. Adding a flag would change the 17-flag registry and every variant hash fingerprinted by OSF deposit 1. Its module still references the VCL (it reads the manifest for logging) so `flag-guard` passes. *(My call — see §8.)*
- `TelemetryWindow` is frozen and its hash covers the window; the trigger must not be written into the window or the sealed manifest (the window is what the pool seal binds).
- Python 3.11 only; no new dependency unless pinned exactly and justified.
- Calibration uses build data only: RCAEval build (495 cases, metrics and logs, no traces) and the S1.2 OTel build corpus (63 cases, all three modalities). Build labels may be used for calibration (D11).
- Parameters chosen on build data are frozen with a deviation entry before `build-freeze` and travel in OSF deposit 2.
- Output of any tool that touches labelled data is counts and aggregates only.

## 5. Design

### 5.1 The trigger record

A small immutable record per (incident, detector version):

| Field | Meaning |
|---|---|
| `trigger_time` | the recorded-time instant the detector fires (seconds, same clock as the window) |
| `suspects` | services whose signal looked wrong at that instant, ordered by strength, at most the pruner's seed count (3) |
| `source` | `threshold` (a signal crossed the frozen threshold) or `fallback` (§5.2) |
| `detector_hash` | hash of the detector's frozen parameters and code version |

It is computed by the runner **before** the UEG-C is pruned, stored with the run (result store), and is the only time anchor any system receives. It is computed for every variant, including those with D-pipe OFF: the trigger is shared evaluation infrastructure, not D-pipe's vote.

**Data each system sees:** the whole recorded window plus the trigger record, as RCAEval's baselines normally take a whole window plus an anomaly time. Nothing is cut at the trigger.

**Suspects as pruner seeds:** suspects that are not production services in the UEG-C (for example a service seen only in metrics) are dropped before `khop_prune(seeds=...)`; if none remain, the pruner chooses its own seeds as today, and the run records `seeds_from_trigger = false`.

**Externally supplied trigger (exploratory only).** The runner can take a precomputed trigger record instead of running the detector. This is the plug-in for D-a's exploratory "true injection time" run: a tool under `helios/adapters/` (outside the leakage-scanned run path, like the S1.2 campaign) writes trigger records from the signed ground truth into a separate file, and the run writes to a separate result store. The runner refuses an external trigger when the evaluation phase is confirmatory. The exploratory run itself is phase E work; S2.1 builds only the plug-in and the refusal test. *(Builder's call: whether the detector lives in `helios/pipelines/d_pipe/` or its own module under `helios/telemetry/`, as long as it sits on the leakage-scanned run path and is flag-compliant.)*

Baselines receive `trigger_time` wherever they would normally take an injection or anomaly time (RCAEval's methods take an anomaly timestamp). The baseline harness is S4.8; S2.1 provides the stored record and a fixture test proving HELIOS and a baseline wrapper read the same value.

### 5.1a Candidate pool: out-of-scope services (D-f)

A fixed, per-testbed list of **out-of-scope services**, frozen with the deviation entry and hashed into `detector_hash` and the run record:

| Testbed | Test harness | Observability stack |
|---|---|---|
| OTel Demo 2.2.0 | `load-generator`, `flagd`, `flagd-ui` | `prometheus`, `jaeger`, `opensearch`, `grafana`, `otel-collector` |
| RCAEval (RE1–RE3) | none | none (the recorded systems carry no harness or monitoring services as services) |

Application dependencies stay in scope (for example `kafka`, `valkey-cart`, `postgresql`). *(The exact names are checked against the S1.2 corpus's 28 services when the list is frozen; the RCAEval "none" is checked against the build corpus's service names.)*

What the list does, and does not do:

- **Not a trigger source or suspect.** The detector ignores out-of-scope services when deciding whether and when to fire, and never names them as suspects.
- **Never a ranked candidate.** Every system's published ranking excludes them: HELIOS's pipelines and MAHC rank only in-scope services. The same filter is applied to each baseline's ranked output before scoring (S4.8), so the rule is identical for every system.
- **Still visible as evidence.** Their nodes, edges and telemetry stay in the UEG-C and in every pipeline's input. The pruner may keep them as context nodes, but they are never seeds. Narratives may cite them, for example "telemetry from the collector stopped at 10:02".
- **Scoring.** HR@k and MRR are computed over the in-scope ranking. Scoring refuses a ground-truth label that is on the out-of-scope list, which should never happen.

### 5.2 How the detector decides

1. Per service, build signals in fixed buckets from **metrics and logs only**: every metric series (counters differenced, as `anomaly_intensity.py` already does), log volume and novel-template count when logs exist. Services come from `service_name`, else `job`, so both corpora work. **Traces are not used by the detector:** the RCAEval build corpus has none, so a trace signal could never be calibrated on the corpus family of the confirmatory pool, and the 5% guarantee would not carry over. Traces remain fully available to the pipelines. *(My call — see §8.)*
2. Score each bucket against that series' own history **up to that bucket** (an expanding robust baseline: median and MAD of the earlier buckets, after a short warm-up). This is what makes "first moment it looks wrong" meaningful: a bucket is judged only against what came before it, never against the future.
3. The trigger fires at the first bucket where any service's strongest signal exceeds the frozen threshold for long enough (a persistence of one or more buckets — a tuned parameter). The suspects are the services above threshold in that bucket, strongest first.
4. **If nothing ever crosses**, the trigger falls back to the bucket of maximum intensity, and `source = fallback`. Every case must be analysed, so a case with no clear signal still gets a trigger; fallbacks are counted and reported separately from threshold triggers. *(My call — see §8.)*

Using the existing anomaly-intensity code as the signal layer is preferred over a second implementation; the difference is step 2's causal (past-only) baseline, which the whole-window robust z in `anomaly_intensity.py` does not have.

### 5.3 Tuning rule (build data only)

**Window position gives the answer away, so the detector must not be able to use it.** In the build data the injection sits at the exact middle of the window: 489 of 495 RCAEval build windows (the RCAEval windows are centred on the injection) and all 63 OTel build windows (5 minutes before and after, by our protocol). The confirmatory pool is expected to follow the RCAEval convention. A detector whose tuned parameters encode "fire about half-way" would meet the 5% target without detecting anything. Three safeguards, all part of the design:

1. **Warm-up is fixed, not tuned,** and short: at most a fifth of the shortest build window (the shortest build windows are a few minutes long), chosen before the calibration run.
2. **No parameter refers to absolute or relative position** in the window; the detector only ever compares a bucket with the buckets before it.
3. **Position-invariance audit**, part of the done-when: rerun the selected setting on each build window cropped at several fixed fractions of its pre-injection part (deterministic crops, no randomness; the crop fractions fixed before the run). The false-trigger rate must stay at or below 5% under every crop, and the median delay must not change by more than one bucket. A setting that fails the audit is rejected.

Two RCAEval build cases (both RE1-OB) have an injection time outside their window; they are excluded from calibration and listed in the report. The same check runs on the pool only after `build-freeze`.

The free parameters are the threshold, the persistence and the bucket size. For each candidate setting, on each build corpus:

- **false trigger:** the trigger time is before the true injection time;
- **missed trigger:** `source = fallback`;
- **delay:** trigger time minus injection time, for true triggers.

Rule, fixed before the run: among settings whose false-trigger rate is **at most 5% on each build corpus separately** (RCAEval build and OTel build), choose the one with the smallest median delay; ties go to fewer missed triggers, then to the less sensitive setting. If no setting meets 5% on both corpora, the calibration stops and the result goes to the owner — the target is not relaxed silently. *(Per-corpus rather than pooled is my call — see §8.)*

The calibration also reports, as exploratory figures: how often the root cause is among the suspects; how often it is within the K-hop reach of the suspects; and the false-trigger rate per fault type on the OTel corpus (`emailMemoryLeak` is expected to be hard).

### 5.4 Post-run trigger classification

After a run is scored, the evaluation step (alongside the S1.9 scoring path, outside the pipelines) labels each trigger:

| Label | Rule |
|---|---|
| true | threshold trigger at or after the injection time |
| false | threshold trigger before the injection time |
| no trigger | fallback |

Stored per incident with the scores; reported as trigger precision and miss rate per corpus and, after the freeze, on the pool. Every system shares the trigger, so a false trigger affects all of them equally; it is reported, never corrected.

### 5.5 D-pipe completion

- **Formats.** Stage A reads per-service signals in a format-neutral way: OTel histograms and status codes as today, plus RCAEval's plain per-service series (latency, CPU, memory, error and similar suffixes, under `service_name`). Which RCAEval suffixes map to "latency" and "error" is a fixed table, recorded in the design note.
- **Trigger split.** Each service's score compares the incident part (from the trigger on) with the reference part (before the trigger), instead of a whole-window summary. *(My call: this is the natural use of the shared anchor, and it also makes D-pipe less sensitive to where the window happens to start.)*
- **σ.** σ expresses how unsure the ranking is, from the score spread: high when the top candidates' scores are close together, low when the top candidate clearly stands apart. It lies between zero and one, and is rounded with the same rule as μ (`MU_DIGITS`) so reruns are bitwise equal. *(The exact formula is the builder's, provided the S2.5 σ counterexample (Ch3 p.157) can be expressed with it; documented in the design note.)*
- **Parameters.** D-pipe's weights are recalibrated on build data with the new formats and the trigger split, stored in a new frozen parameter file loaded by the runner (not `research/osf/thresholds.json`, which is deposited), and recorded with a deviation entry. The runner must fail loudly if the file is missing, never fall back to code defaults.
- **Recalibration objective,** fixed before the run: maximise the mean of the per-corpus HR@3 on the two build corpora (RCAEval build and OTel build weighted equally), with the frozen detector's trigger (never the true injection time). Ties go to the setting closest to the May frozen values. The grid is the existing D-pipe grid (`dpipe_config.py`) plus the new split parameter, if any. Build-data HR@3 is reported per corpus as exploratory.

### 5.6 Determinism

No randomness anywhere in the detector or D-pipe. Sort every service and series iteration; fix float reduction order; round every stored float with the `canonical_json` rule. Done-when test: two **separate processes** on the same sealed window produce byte-identical canonical JSON for the trigger record and the D-pipe verdict.

### 5.7 TTCD timestamps

The runner records, per system, the wall-clock moment it hands over the trigger (the start of the measured time) and the moment each verdict is published. TTCD itself is computed in the evaluation tooling (S4). The same applies to time to triage (TTT, E-H2), which today also starts at "invocation": see §8.

## 6. Protocol records

| Record | When |
|---|---|
| Deviation entry: TTCD (and TTT, if confirmed) start at the detection trigger (metric contract §4 differs) | before code that measures it merges |
| Deviation entry: out-of-scope service list per testbed (test harness and observability stack excluded from triggers, suspects and rankings for every system; telemetry kept), D-f | before the candidate filter merges (row ENG01) |
| Deviation entry: detector design and frozen parameters; D-pipe recalibration and new parameter file | when calibration is final, before `build-freeze` |
| OSF deposit addendum note (with the S1 §9 correction) | next deposit |
| Chair-call item: TTCD anchor change, false-trigger target and handling | mid-November call document |
| Validity threat: shared trigger quality (false and missed triggers affect all systems; build data cleaner than live) | with the calibration PR |
| Validity threat: injection at the window midpoint (RCAEval windows centred on the injection; OTel windows by protocol) — position carries the label for any method that can use it; safeguards in §5.3, and baselines' use of position checked in S4.8 | with the calibration PR |
| S1.1 data note: two RCAEval build cases with the injection outside the window | with the calibration PR |

## 6a. Size and tracking

This is several days of work, not the breakdown's one day. It is split into four tracking rows under S2.1 so each lands through its own PR and gate:

| Row | Content | Effort (days) |
|---|---|---|
| S2-M7-ENG01 | Detector, trigger record, runner order, seeds hand-off, external-trigger plug-in, rerun-equality and shared-trigger tests | 1½ |
| S2-M7-ENG09 | D-pipe formats, trigger split, σ, parameter file loading | 1½ |
| S2-M7-EVAL01 | Detector calibration on both build corpora, invariance audit, trigger classification, deviation entry; then D-pipe recalibration and its deviation entry | 1½ |
| S2-M7-RES02 | TTCD / TTT anchor deviation entry (merges before the timestamp code), validity threat, chair-call item | ½ |

About five days in total. S2 started early with about eight weeks before 25 Dec, so the sprint absorbs it; S2.5 waits for σ (row ENG09).

## 7. Done when

- Bitwise rerun equality across processes (trigger record and D-pipe verdict).
- Trigger time identical for HELIOS and a baseline wrapper on a fixture.
- D-pipe ranks (does not abstain) on RCAEval build windows and OTel windows.
- Calibration report on both build corpora: false-trigger rate at most 5% on each, miss rate, median delay, root cause among suspects and within reach; the position-invariance audit passes.
- The runner refuses an externally supplied trigger in a confirmatory run (test).
- Leakage scan passes with the detector on the run path; full gate green.

## 8. Calls I made (owner to check)

1. **Fallback trigger** when nothing crosses the threshold: the bucket of maximum intensity, counted as "no trigger", rather than skipping the case (every case must be analysed).
2. **5% applies to each build corpus separately**, not pooled; the 495 RCAEval cases would otherwise hide a weak result on the 63 OTel cases.
3. **False trigger = fires before the injection**; whether the suspects include the root cause is reported separately, not part of the true/false label.
4. **D-pipe scores "after trigger vs before trigger"** rather than the whole window.
5. **TTT (E-H2) moves to the trigger anchor too**, for the same reason as TTCD, in the same deviation entry.
6. **The trigger runs for every variant and has no VCL flag:** it is shared evaluation input, like the window, not a HELIOS component; a new flag would change every variant hash deposited in OSF deposit 1. The D-pipe flag gates D-pipe's verdict, not the trigger.
7. **The detector uses metrics and logs only,** never traces, so its calibration carries over to the RCAEval pool.
8. **Window-position safeguards:** fixed short warm-up, no position parameters, and a crop-invariance audit that a setting must pass.
9. **D-pipe recalibration objective:** mean of per-corpus build HR@3 with the detector's trigger.
10. **S2.1 split into four tracking rows,** about five days.
11. **The exploratory true-injection-time run** gets only its plug-in in S2.1 (external trigger file from `helios/adapters/`, refused in confirmatory runs); the run itself is phase E.
12. **Out-of-scope list (D-f) applied to baselines too**, by filtering their ranked output before scoring, so the rule is the same for every system; RCAEval's list is empty.

## 8a. Owner's technical review (2026-10-27) and what changed

| Risk raised | Change |
|---|---|
| A flat zero-scale series that moves (0 → 1) hits the z cap and could set off the trigger on one event | Scale floors replace the cap: a Poisson floor for count series (one event from zero gives z = 1) and a relative floor (5% of level) for gauges; a gauge flat at zero gives no evidence until it varies. The cap stays only as a numeric guard |
| When suspects are dropped, the pruner silently picks its own seeds | Suspects are in-scope by construction; out-of-scope anomalies at the trigger are kept in a separate `context` field (evidence, never seeds). Whether the trigger seeded the pruner is stored (`seeds_from_trigger`) and its rate reported in the calibration. Telemetry gaps (series that stop) are a known blind spot of `trigger-v1`, recorded in the validity threat |
| σ = 1 − (s1 − s2)/s1 is unstable for small scores | σ also weighs the raw evidence: σ = 1 − gap × strength, where strength is the top service's raw shift (robust-z units, before max-normalisation) relative to the frozen detector threshold, capped at 1. Weak evidence drives σ towards 1 whatever the gap |
| Cropping can cut into the fixed warm-up, so valid settings fail the audit | Crops take a fraction of the *slack* only (pre-injection span minus warm-up, longest persistence and one bucket); cases without slack are skipped and counted. The OTel audit is weak (60 s of slack with 30 s buckets), and is reported as such |

## 9. Left to the builder

Module placement; bucket size candidates and grid; the σ formula (within §5.5); the RCAEval suffix table; how the trigger record is stored in the result store; the fixture for the shared-trigger test; the format of the calibration report.

## 10. Results

### Row S2-M7-ENG01 (2026-10-27) — provisional parameters

Detector `trigger-v1` with the **provisional** parameters in `data/frozen/trigger_detector.json` (30 s buckets, threshold 6, persistence 2; refused in confirmatory runs until S2-M7-EVAL01 freezes calibrated values). `bin/trigger_check.py`, each corpus run twice in separate processes:

| Corpus | Windows | Threshold triggers | Fallbacks | Records digest (both runs) |
|---|---|---|---|---|
| OTel build (S1.2) | 63 | 63 | 0 | `ef3a45e84c90b4fb1b9c13651dc67ba9fd429c226b1ba281aa57452695e7f1a9` |
| RCAEval build | 495 | 494 | 1 | `8cd38e256ab93e17992c3712009f57192a366cacf6a3735dc64cc5a592fbd71c` |

Whether these triggers are true or false (before the fault) is measured in the calibration (S2-M7-EVAL01), not here: this row does not read labels. The UEG-C captures digest is unchanged by the refactor of `anomaly_intensity` (`945df66330a0`, as recorded in S1.7).

### Row S2-M7-ENG09 (2026-10-27) — D-pipe completion, provisional parameters

D-pipe reads both metric formats (RCAEval plain series; OTel histograms plus container CPU and memory), scores the shift after the trigger against the part before it (robust scale shared with the trigger), adds a resource channel, ranks in-scope services only, and reports σ = 1 − gap × strength (strength = top raw shift relative to the trigger threshold). Parameters come from `data/frozen/dpipe_params.json` (**provisional**: the May values w_error 0.3, ρ 0.2, boost 1, plus w_resource 0.2; refused in confirmatory runs until S2-M7-EVAL01). With the provisional trigger:

| Corpus | Windows | D-pipe ranked | σ reported |
|---|---|---|---|
| OTel build | 63 | 63 | 63 |
| RCAEval build | 495 | 495 (before S2.1: none, every RCAEval window abstained). One window has its trigger at the window start (fallback), so no reference part exists: it is scored over the whole window and gets no σ | 494 |

Rules added in review: a split without a reference or an incident part falls back to the whole-window score; all-zero in-scope scores give ABSTAINED, never a by-name order; each channel is normalised by its largest **in-scope** shift, so out-of-scope services keep their raw evidence but never set the scale. Accuracy on build data is measured in the calibration (S2-M7-EVAL01). Two separate processes give byte-identical D-pipe verdicts (`tests/test_trigger_check_cli.py::test_dpipe_verdict_identical_across_processes`).
