# Validity Tracking

**Purpose:** Internal, construct, and external validity threats and mitigations (proposal §3.9.1–3.9.3). Includes ground-truth labelling protocol boundaries and examiner-facing threat analysis.

**Schema version:** v1.0 (frozen 2026-05-15)
**Update cadence:** At each major stage gate
**Owner:** AA
**Reference:** Proposal §3.9.1 (internal), §3.9.2 (construct), §3.9.3 (external)

---

## Column Definitions

| Column | Meaning |
|---|---|
| `Category` | `internal` / `construct` / `external` |
| `Threat_ID` | Sequential threat identifier |
| `Description` | What the threat is |
| `Mitigation` | How HELIOS addresses it |
| `Artefact_evidence` | Code / doc that implements the mitigation |
| `Status` | `Mitigated` / `Partial` / `Pending` |

---

## Entries

### Internal Validity

| Category | Threat_ID | Description | Mitigation | Artefact_evidence | Status |
|---|---|---|---|---|---|
| Internal | T1 | History effect — external events during data collection alter results | Fixed 5-minute capture windows; OTEL Demo is an isolated Docker Compose environment with no external network access | `TelemetryWindow.window_start_iso / window_end_iso`; `helios/telemetry/otel_demo_capture.py` | Mitigated for exploratory phase |
| Internal | T2 | Instrumentation — measurement tool changes observed system behaviour | Passive telemetry only (Prometheus scrape, Jaeger sampling, OpenSearch collect); no active probes or synthetic traffic injected | `helios/telemetry/otel_demo_capture.py` — read-only backend queries | Mitigated |
| Internal | T8 | Ablation confounding — disabling one flag inadvertently affects multiple code paths | DisjointnessAuditor (static `__gated_by__` scan + dynamic coverage.py diff) enforces that each VCL flag gates exactly one pipeline function | `helios/vcl/disjointness.py` — CI PASSED at Milestone 1; `disjointness_audit_log.md` | Mitigated |
| Internal | T10 | Label leakage — case names, paths or fault strings reveal the root cause to a pipeline (S0.1 finding F1: RCAEval case IDs encode it) | Opaque 32-hex incident IDs from the seed register; ground truth only in HMAC-signed files outside the window; leakage tests over every input (S1.1); no run-path entry point accepts ground truth, AST scan and runtime trap (S1.9) | `helios/adapters/rcaeval.py`, `helios/adapters/otel_campaign.py`, `tests/evaluation/test_no_ground_truth_leak.py` | Mitigated |
| Internal | T11 | Local hardware — model time measured on the local machine is priced at a reference cloud GPU's hourly rate, which assumes equal speed | Price book names the reference machine per provider; GCP and Azure sensitivity profiles; per-token pricing from a throughput benchmark proposed | `docs/tracking/price_book.md` (deviation entries 42-43) | Pending — benchmark not run |
| Internal | T18 | Shared trigger quality — every system starts from the same label-free trigger; a false trigger (before the fault) or a missed one (fallback) misleads all of them, and build data is cleaner than live traffic. Telemetry gaps (series that stop) are not a trigger signal in trigger-v1 | False-trigger limit 5% on each build corpus (owner, D-e); per-corpus false and missed rates reported, and on the pool after build-freeze; every trigger classified true / false / no-trigger after scoring; out-of-scope anomalies kept as context | `docs/sprints/s2-reasoning/s2_1_dpipe_trigger_design.md` §5.3–5.4; deviation entries 46–47 | Open — calibration S2-M7-EVAL01 |
| Internal | T19 | Position carries the label — the fault starts at the exact middle of the window in 489/495 RCAEval build windows (RCAEval windows are centred on the injection) and, in the OTel v1 build corpus, in all 63 windows (by protocol). OTel v2/v3 vary the normal period (480–900 s, from the opaque ID, entries 48 and 50), so the onset no longer sits at a fixed share of the window, but the fault period is a fixed 300 s: the injection is always window end − 300 s and can be read from window metadata alone; any method that can use position or the window end could learn it | Detector and D-pipe: fixed warm-up, no position parameters, causal (past-only) scoring; neither reads the window end (checked in the PR 3 review, 2026-10-29); crop-invariance audit over each window's slack (start crops only); baselines', G-pipe's and L-pipe's use of position **and of the window end** checked in S4.8 | `s2_1_dpipe_trigger_design.md` §5.3; `tests/telemetry/test_trigger.py::test_moving_window_start_does_not_move_the_trigger`; `helios/adapters/otel_campaign.py` (POST_S) | Partial — the end-anchored onset of OTel v2/v3 is untested by the audit (start crops only); at the frozen 60 s buckets v3 slack is 0–7 minutes (normal period minus 8 buckets); 59 of 63 cases are audited, 4 have no slack |
| Internal | T20 | Span attribution in the 20 May OTel captures (`data/captures`, OSF deposit 1) — 88–90% of span IDs are listed under several services (up to 9): the May capture stamped every span of a returned trace with the service Jaeger was queried for. Graph structure built from those spans (UEG-C call edges, the May G-pipe disagreement threshold, the exploratory runs) rests on invented edges | Found in the S2.2 PR 1 review (2026-10-30). Excluded from G-pipe build data (63 v3 cases only; deviation entry 55); the span analysis refuses any P2 file with a span under more than one service; v3 captures checked: 0%. May results are not redone in S2.2: reported with this limitation wherever cited | `helios/graph/span_features.py` (`analyse_spans` refusal); `s2_2_gpipe_design.md` §8b | Partial — May exploratory figures and the May threshold carry the defect |
| External | T21 | OTel-to-pool shift for the learned G-pipe ranker — trained and selected on 63 OTel demo cases (one topology, 6 root services, feature-flag faults); the pool is Online Boutique and Train-Ticket (a much larger graph) with CPU, memory, disk, delay, loss, socket and code-level faults. Build lift over D-pipe alone is 2 of 63 cases | Small linear model (ten weights, L2), no service identity (audit; degree features removed), scores normalised per window, held out by root service, simplest-wins rule with a 3-hit margin fixed before the run (entries 54–55); pool result reported whatever it is | `s2_2_gpipe_design.md` §10; `data/frozen/gpipe_params.json` | Open — measured on the pool after build-freeze |

### Construct Validity

| Category | Threat_ID | Description | Mitigation | Artefact_evidence | Status |
|---|---|---|---|---|---|
| Construct | T3 | Construct under-representation — HR@3 alone misses latency and cost dimensions | Every verdict carries the contract (ranked list, mu, sigma, cost as usage, latency; S1.8); HR@1/3/10, Avg@5 and MRR are scored after dispatch (S1.9); CpR is the five-component cost under the frozen price book (S1.10) | `helios/schemas/verdict.py`, `helios/evaluation/scoring.py`, `helios/evaluation/cost.py`, `docs/tracking/price_book.md` | Partial — CpR not stored until MAHC verdict state and TTCD exist (S2) |
| Construct | T4 | Mono-operation bias — single RCA task definition may not generalise | Three peer pipelines over three distinct modalities; 8 ablation variants isolate each component's contribution | VCL + 8 confirmatory variants in `helios/vcl/variants.py` | Mitigated by design |
| Construct | T5 | Hypothesis guessing — user study subjects infer research intent | Double-blind protocol in E-H7 user study; counterbalanced variant presentation order | `[PENDING: Stage 5 — IRB approval required for n=24 SRE user study]` | Pending IRB |
| Construct | T12 | Rater blinding — noLLM narratives are template text, so raters could tell variants apart when labelling H_fact | Rubric written and trialled on build-data narratives (S2.9), frozen by hash and deposited (deposit 2) before confirmatory labelling; blinding procedure in the rubric | Deviation entry 38; `docs/tracking/metric_contract.md` (Labelling) | Pending (S2.9) |
| Construct | T15 | Cost scale — opportunity cost (5,600 per minute, weakly sourced) dominates CpR by orders of magnitude, masking compute differences | log(CpR) analysed; per-component values and a compute-only CpR reported descriptively; sensitivity at EMA's 14,056 per minute and under the GCP and Azure profiles | `docs/tracking/price_book.md`, `helios/evaluation/cost.py` | Partial — chair call |
| Construct | T13 | Missing resource signal — the 20 May OTel captures hold only latency histograms (CPU and memory metric names do not exist in demo 2.2.0), so resource faults show no metric anomaly there | Found in the S1.2 pilot; the S1.2 build corpus records per-container CPU and memory; the May captures are deposited (OSF deposit 1) and stay as they are; results on them are exploratory and labelled latency-only | `docs/sprints/s1-data-graph/s1_2_otel_build_captures.md` | Partial — May captures cannot be re-recorded |
| Construct | T14 | Build labels and balance — the OTel build label is the service whose code reads the fault flag (paymentUnreachable → checkout is a judgement); ad carries 3 of 9 faults | Labelling rule and exclusions recorded (deviation entry 44); per-service counts reported; emailMemoryLeak barely shows within the 5-minute fault period (email memory up 1-2 MiB, median latency x1.12) and is reported per fault as a near-silent case. S2.1 (otel_build_v3, 25 users; deviation entry 52): the frozen detector never triggers on adFailure (about one error a minute at the root), emailMemoryLeak or recommendationCacheFailure (no root signal inside the 5-minute fault period), 21 of the 63 build cases; those windows are analysed whole (fallback) and reported per fault; build data never confirmatory | `helios/adapters/otel_campaign.py` (FAULTS) | Partial |
| Construct | T17 | Span service labels — the OTel trace fetcher stamped every span of a returned trace with the queried service, so every May capture holds each span several times, mostly under the wrong service (found in S1.3) | Fetcher fixed (each span keeps its own process's service, once); S1.2 build corpus recorded with the fix; May captures stay as deposited and their trace-based results are reported as affected (S1.7 captures check void) | Deviation entry 45; `tests/test_capture.py::TestJaegerTracesFetcher::test_spans_keep_their_own_service_and_appear_once` | Partial — May captures cannot be repaired |

### External Validity

| Category | Threat_ID | Description | Mitigation | Artefact_evidence | Status |
|---|---|---|---|---|---|
| External | T6 | Population validity — the testbed is not representative of production microservices | Confirmatory corpus is the 240-case RCAEval pool (RE2/RE3 Online Boutique and Train-Ticket; D11, deviation entry 25), sealed and locked until tag build-freeze; OTel Demo data (20 exploratory + the S1.2 build corpus) never enters a confirmatory test; AIOpsLab joins only if the S1.3 spike is a go (D11 addendum) | `data/rcaeval/pool_manifest.json`, `helios/telemetry/pool_lock.py`, `docs/tracking/s0_3_d11_corpus_run_design.md` | Partial — two application families; generalisation beyond them is a stated limitation |
| External | T7 | Ecological validity — injected faults differ from production incidents | RCAEval faults are published, labelled injections across resource, network and code faults; fault types are stratified in reporting; the OTel build corpus uses the demo's own fault flags | `data/rcaeval/ground_truth_pool.json` (signed, locked), `docs/sprints/s1-data-graph/s1_2_otel_build_captures.md` | Partial — injected, not organic, incidents |
| External | T9 | Production isomorphism — offline post-hoc consensus fusion differs from inline runtime fusion in a production system; latency of the consensus step is not measured in `PipelineVerdict.latency_ms` | M4 is explicitly exploratory (OTEL corpus); system HR@3 is the sole M4 outcome — no latency claim is made for the consensus layer. Production inline fusion is a Phase 2 engineering goal. | `helios/config/m4_ablation.py` note; `data/m4_results.json analysis_type="exploratory"` | Acknowledged — does not affect M4 statistical conclusions; Phase 2 redesign required before MTTR claims |
| External | T16 | Concentrated root causes — few root-cause services per system in the pool (S0.1 finding F2), so a random pick among likely services scores HR@3 ≈ 0.60 | CHASE-adjusted baseline kept at 0.60 (deviation entry 36) and reported beside raw HR@3; label-free anomaly seeds reported as a reference (S1.7: 251/495 build cases) | Deviation entry 36; `docs/sprints/s1-data-graph/s1_7_khop_pruner.md` | Partial |

---

## Future Entries

`[PENDING: Stage 5 — additional construct validity threats for L-pipe prompt design sensitivity, CoE narrative quality inter-rater reliability; external validity threats for multi-cloud generalisation beyond AIOpsLab benchmarks]`

---

*Last updated: 2026-10-30 (S2.2) — 21 threats catalogued; T21 added (OTel-to-pool shift of the learned G-pipe ranker, entry 56); T20 added (May captures' span attribution, entry 55); T14 extended with the faults the frozen detector never triggers on (entry 52); T19 corrected for OTel v2/v3 (end-anchored onset, PR 3 review); T18–T19 added with the shared detection trigger; T6/T7 rewritten for the RCAEval pool (D11); T10–T12, T15, T16 added (S0 carry-over: F1 leakage, F2 concentration, rater blinding; S1 findings: cost scale, local hardware pricing); T13, T14, T17 added with the S1.2 OTel build corpus (May captures lack resource metrics; build labels and balance; span service labels, deviation entry 45)*
