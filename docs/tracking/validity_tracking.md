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

### Construct Validity

| Category | Threat_ID | Description | Mitigation | Artefact_evidence | Status |
|---|---|---|---|---|---|
| Construct | T3 | Construct under-representation — HR@3 alone misses latency and cost dimensions | Every verdict carries the contract (ranked list, mu, sigma, cost as usage, latency; S1.8); HR@1/3/10, Avg@5 and MRR are scored after dispatch (S1.9); CpR is the five-component cost under the frozen price book (S1.10) | `helios/schemas/verdict.py`, `helios/evaluation/scoring.py`, `helios/evaluation/cost.py`, `docs/tracking/price_book.md` | Partial — CpR not stored until MAHC verdict state and TTCD exist (S2) |
| Construct | T4 | Mono-operation bias — single RCA task definition may not generalise | Three peer pipelines over three distinct modalities; 8 ablation variants isolate each component's contribution | VCL + 8 confirmatory variants in `helios/vcl/variants.py` | Mitigated by design |
| Construct | T5 | Hypothesis guessing — user study subjects infer research intent | Double-blind protocol in E-H7 user study; counterbalanced variant presentation order | `[PENDING: Stage 5 — IRB approval required for n=24 SRE user study]` | Pending IRB |
| Construct | T12 | Rater blinding — noLLM narratives are template text, so raters could tell variants apart when labelling H_fact | Rubric written and trialled on build-data narratives (S2.9), frozen by hash and deposited (deposit 2) before confirmatory labelling; blinding procedure in the rubric | Deviation entry 38; `docs/tracking/metric_contract.md` (Labelling) | Pending (S2.9) |
| Construct | T15 | Cost scale — opportunity cost (5,600 per minute, weakly sourced) dominates CpR by orders of magnitude, masking compute differences | log(CpR) analysed; per-component values and a compute-only CpR reported descriptively; sensitivity at EMA's 14,056 per minute and under the GCP and Azure profiles | `docs/tracking/price_book.md`, `helios/evaluation/cost.py` | Partial — chair call |

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

*Last updated: 2026-10-27 (S1) — 14 threats catalogued; T6/T7 rewritten for the RCAEval pool (D11); T10–T12, T15, T16 added (S0 carry-over: F1 leakage, F2 concentration, rater blinding; S1 findings: cost scale, local hardware pricing); T13–T14 (OTel capture findings) arrive with the S1.2 PR*
