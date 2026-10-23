# HELIOS — End-to-End Plan: Full Product Build → Evidence Collection → Analysis

**Version:** first draft · **Written:** 2026-10-22 · **Owner:** AA
**Supersedes for scheduling:** `HELIOS_MVP_Execution_plan_v0.6.md` (MVP/Phase-2 split). It does **not** change the protocol: every protocol change still goes through `bin/log_deviation.py`, and the protocol itself is settled in Phase P0 against `docs/tracking/r1_traceability_matrix.md`.

**Design latitude (owner direction, 2026-10-23).** The goal is a high-quality, production-grade observability product that shows innovation and creativity. Chapter 3 is the **baseline, not the final verdict**: where a different or more creative method gives a better or more production-ready result, prefer it. This plan and the R1 matrix are guides, not rigid specifications. One line does not move: a change that alters what a pre-registered test measures is recorded (deviation entry, pre-registration update) **before** confirmatory data is collected, so the evidence stays valid.

**Shape of the plan, as requested:** build the **complete product** first (every feature of the approved design), freeze it, then run **testing and evidence collection** (confirmatory and exploratory), then **analysis**. No confirmatory data is collected before the build is frozen and the pre-registration is deposited.

**Sources:** approved Chapters 1–3 (`docs/research/Complete_Report.pdf`, cited by printed page "p.NNN"); repository `main` @ `b25c287`; `docs/tracking/r1_traceability_matrix.md` (decisions D1–D8).

---

## 1. Principles every phase inherits

1. **One binary, every variant.** All 8 confirmatory and 7 exploratory variants run from one commit, fixed at freeze; variants differ only by the flag vector the VCL reads at process start (p.106, p.108).
2. **Every contribution is ablatable.** Each C1–C6 mechanism sits behind its Ch3 flag in the `VCLFlag` registry; the disjointness audit must show every boolean flag gating exactly one code path before freeze.
3. **Build data ≠ evidence data.** Development and calibration use only the 20-incident OTel Demo set, the synthetic pre-warm testbed, and fixtures. Confirmatory benchmark incidents are never used to tune anything; the pre-warm testbed is SHA-checked disjoint from them (p.110, p.231).
4. **Unset parameters are fixed before freeze.** Every Ch3 parameter without a value (§3.9) is calibrated on non-confirmatory data, recorded with a deviation entry, and frozen in the pre-registration.
5. **Failures are covariates, never silent fallbacks** (p.139): sampling downgrade, pipeline unavailability, non-convergence, twin staleness, DP-budget exhaustion, adversarial input, HIS contention, constraint-empty fallback, control-plane degradation.
6. **Engineering gate on every change:** tracking row (IN_PROGRESS → DONE), PR, the full pre-push gate (ruff/black incl. `bin/`, mypy strict, pytest ≥ 90% coverage, `verify_ledgers.py`, `verify_captures.py`, `verify_osf_freeze.py`, tracking `--range`), tests that fail if the feature is removed, and a deviation entry when there is an analytic consequence.

---

## 2. Where the build starts (main @ `b25c287`)

| Area | Exists today | Missing for the full product |
|---|---|---|
| C1 spine | VCL (14 flags), variant hashes, snapshot registry, integrity gate, deviation / exclusion / reconciliation ledgers with signed anchors, capture seals, disjointness audit, OSF freeze tooling, CI | Ch3 flag registry, Ed25519 signatures (D7), seed register, price book, run-orchestrator cell bookkeeping, failure-covariate schema, full disjointness coverage |
| L0 ingest | Recorded OTel Demo capture (P1–P3 Parquet), sealed | P4 cognitive telemetry, P5 business telemetry, Drain3/LogEDL log processing, live OTLP ingest, Privacy Gateway, ARM, tiered sampling |
| L1 UEG-C | Structural + call edges, PPR pruner | Four typed edge kinds with composition rules, ARS and Transaction/KPI nodes, Algorithm 5 pruner to spec, multi-tenant partitions, `tenant=self` |
| L2 pipelines | D-pipe (statistical), G-pipe (PPR), L-pipe (single prompt, llama3.1:8b, Ollama) | Trained graph-ML G-pipe (D9), (μ, σ, cost, latency) verdict contract, multi-agent L-pipe (Orchestrator, Specialization Gate, worker mesh, Persona Profiles, Knowledge Cortex, Sentinels, Fallback Agent, LLM Gateway), Protocol A serving |
| L3 coordination | Uniform Borda behind `mahc` | MAHC (Algorithm 3), vote-only aggregator, ORAR (Algorithm 1), ACP (Algorithm 2), two-stage reward, CoE ledger, Narrative Engine |
| L4 action | — | HITL gate with α, FGSV (Algorithm 4) + digital twin + ASRE, actuation, Monitor Agent, Critic Agent, remediation templates |
| Product shell | CLI scripts | API, HITL console, incident / CoE view, admin (α, decision rights), Helm deployment, multi-tenancy, auth |
| Evaluation infra | 20-incident exploratory corpus, HR@3 analysis script | Five benchmark adapters, fault injection (Chaos-Mesh, ChaosBlade, NIKA Tier 4), delayed-label injection, pre-warm testbed, baselines, all metrics, full analysis suite, GPU environment |

---

## 3. Target product: feature inventory

Every buildable feature in the approved design, grouped by layer. "Phase" = where it is built (§5). Flags use the Ch3 names (assuming D2(a)).

### 3.1 Cross-cutting — Evaluation plane (C1)

| Feature | Must do (Ch3) | Flag | Serves | Phase |
|---|---|---|---|---|
| VCL | Content-hashed manifest at start; immutable flag vector; verifies every loaded artefact hash (LinUCB/ACP params, container digest, weights SHA-256, model IDs, corpus) and blocks on divergence (p.108, p.211, p.222) | — | all | P0, P8 |
| Snapshot registry | Every pipeline consumes the declared snapshot; same snapshot per (incident, seed) (p.108, p.143) | — | all | exists; P1 |
| Metric integrity gate | Reject incomplete runs, no imputation; cell needs ≥ 320/400 paired observations (p.111, p.161) | — | all | P7 |
| Exclusion ledger + MCAR/IPW | Signed; feeds χ² MCAR test (α = 0.05) and IPW sensitivity (p.162) | — | all | exists; P7 |
| Deviation log | Signed JSONL; **Ed25519** per Appendix (p.233); OSF deposit at every commit | — | all | P0 |
| Reconciliation ledger | Pairs provisional and terminal reward; RRE per incident (p.145) | `reconcile_terminal` | E-H5 | P3 |
| Run orchestrator | Dispatch schedule; completion state per variant–benchmark–metric cell; blocks aggregation until complete or excluded (p.160, p.168) | — | all | P7 |
| Seed register | Seeds 10,000,000–10,009,999 binding; L-pipe seed per (incident, seed) (p.108, p.225) | — | all | P0 |
| Price book | Per-token and per-compute-second coefficients frozen at pre-registration (p.108, p.202) | — | A-H5, B-H7 | P7 |
| Disjointness / hidden-coupling audit | Each flag toggles a disjoint path (p.138, p.204) | — | all A-H | every phase; certified P8 |
| Failure-as-covariate schema | The nine failure kinds recorded per run (p.139) | `sampling_regime_tag`, `his_tier` | all | P1, P5 |

### 3.2 L0 — Telemetry ingress (Data plane)

| Feature | Must do (Ch3) | Flag | Serves | Phase |
|---|---|---|---|---|
| Five-pillar ingestion | OTLP gRPC/HTTP; P1 metrics, P2 traces, P3 logs (Drain3 templates + LogEDL vacuity), P4, P5; DaemonSet collectors with a one-hundred-millicore CPU limit per node (p.117, p.119, p.142) | — | all | P1 |
| Recorded + live ingest | `ingest_mode` recorded for evaluation; live OTLP for the product | `ingest_mode` | product | P1 |
| P4 cognitive telemetry | MCP reasoning-step spans, tool-call schema validation (source of H_struct), goal-drift cosine distance, loop depth, CoT drift (p.119, p.165) | `p4_cognitive` | E-H1, A-H7 | P1, P2 |
| P5 business telemetry | Revenue signals, SLO-breach penalties, service tiers → economic edges (p.119, p.125) | — | BEL, CpR | P1 |
| Privacy Gateway | PII + NER redaction before the control plane, structure-preserving placeholders; per-tenant DP with ε of one per tenant and δ as stated on p.160 (the PDF text layer is unreadable there — read it from the rendered page), 24 h rolling windows (p.160, p.211) | — | governance | P5 |
| Adversarial Robustness Monitor | Prompt-injection, telemetry-poisoning and emission-anomaly detection; periodic attestation; adversarial incidents stratified out of confirmatory cells (p.118, p.161) | ARM | covariate | P5 |
| Tiered adaptive sampling | Tier A eBPF baseline; Tier B SLO-pressure adjustment; Tier C full sampling in the affected K-hop neighbourhood; downgrade when memory > 80% or CPU > 90%; log `sampling_regime=downgraded` (p.143, p.161) | `sampling_regime_tag` | covariate | P5 |
| Internal Observability Loop | HELIOS's own telemetry into the same UEG-C under `tenant=self`; three query kinds (p.148, p.158–159) | `iol_self_telemetry` | E-H6, RQ2 | P5 |

### 3.3 L1 — UEG-C (Data / Reasoning planes, C2)

| Feature | Must do (Ch3) | Flag | Serves | Phase |
|---|---|---|---|---|
| UEG-C store | One representation of all five pillars; four typed edge kinds (structural, behavioural, causal, economic) with composition rules; Agent-Reasoning-Step and Transaction/KPI nodes; graph-partition tenant isolation (p.119, p.140, p.155, p.211) | — | C2 | P1 |
| Structural bundle | `ueg_structural=OFF`: one untyped edge kind, training on the full graph instead of the pruned subgraph, ARS nodes demoted to text (p.152) | `ueg_structural` | A-H8, E-H10 | P1, P2 |
| K-hop Pruner (Algorithm 5) | K-hop expansion over structural + behavioural edges, top-n by PPR restart probability, drop causal/behavioural edges below Pearson r = 0.7, 10,000-edge budget, typical 50–200 nodes, hash to the registry (p.143, p.147) | — | all | P1 |

### 3.4 L2 — Peer reasoning pipelines (Reasoning plane)

| Feature | Must do (Ch3) | Flag | Serves | Phase |
|---|---|---|---|---|
| Verdict contract | Each pipeline consumes the same hashed snapshot, shares no state, emits (ranked list, μ, σ, cost, latency) (p.137, p.140) | — | all | P2 |
| D-pipe | Statistical RCA + anomaly trigger for Tier C; bitwise-reproducible settings (p.143, p.138, p.223) | `dpipe` (implementation) | A-H3 | P2 |
| G-pipe | "Graph machine-learning reasoning" (p.103), trained on the pruned subgraph (p.152), deterministic | `l2b_graph` | A-H6 | P2 (D9) |
| L-pipe multi-agent | Reflective Orchestrator (SOP lookup), Adaptive Specialization Gate, worker mesh (metric, trace, log-evidential, cognitive sentinel, value-impact, ethics, reward) emitting (μ, σ) to MAHC, Persona Profiles refreshed only at episode boundaries (p.142, p.215) | `l2c_llm` | A-H1, A-H2, A-H7 | P2 |
| Knowledge Cortex | RAG store for SOPs with a warm tier from historical incidents; DP-budgeted aggregate queries (p.136, p.214) | — | all | P2 |
| Cognitive Sentinels + Deterministic Fallback Agent | Detect HELIOS's own LLM degradation; fallback SOPs for about 30% of common fault kinds, alerting-only + HITL for the rest; never silent (p.205–206) | — | E-H6 | P5 |
| LLM Gateway | Per-episode token accounting for CpR; saturation visible via IOL (p.165, p.158) | — | A-H5, B-H7 | P2 |
| Protocol A serving | Llama-3.1-70B-Instruct, vLLM 0.6.x, greedy, max 4096 output tokens, `enforce_eager`, TP = 4 on 4× A100 80GB; token-sequence equality check; Protocol B (API) sensitivity only (p.138, p.210, p.223) | — | all L-pipe claims | P7 (D3) |

### 3.5 L3 — Coordination and consensus (Coordination plane)

| Feature | Must do (Ch3) | Flag | Serves | Phase |
|---|---|---|---|---|
| ACP (Algorithm 2) | Features from snapshot + signature; softmax over {schema change, data mutation, config change}, log expected WAL-replay size, blast-radius tier; Adam lr 1e-4, batch 32, ≤ 50 epochs, patience 5; frozen for confirmatory runs; noACP = uniform latency prior (p.146, App. B.1) | `acp_stateful` | E-H3/E-H8 | P3 |
| ORAR (Algorithm 1) | LinUCB over arms {D, G, L, D+G, D+L, G+L, Full}; minimise cost − bonus subject to τ_acc, τ_lat; empty feasible set → Full + `constraint-empty-fallback` covariate; static policy frozen after pre-warm; noRouter = `cbr_routing=uniform` (p.143, p.145) | `cbr_routing` | A-H5, E-H2 | P3 |
| Two-stage reward + regularisers | Provisional reward at 1–5 min (HITL acceptance, self-consistency, realised CpR); terminal update at post-mortem, idempotent; anti-reward-hacking: variance penalty, diversity bonus, 5% held-out double diagnosis (p.112, p.145, p.206) | `reconcile_terminal` | E-H5 | P3 |
| HIS tagging | Every latency and cost measurement tagged with its hardware-isolation tier (p.159) | `his_tier` | E-H9 | P5 |
| MAHC (Algorithm 3) | Priors fault-type → service-family → global with back-off; down-weight by σ; weighted Borda; variance Σw²σ²; entropy floor λ → PROVISIONAL + HITL; Fast-Path PROVISIONAL ≤ 30 s, CONFIRMED on convergence, non-convergence at 90 s → elevated PROVISIONAL + HITL; output is the HR@k measurement point (p.144, p.146–147, p.157) | `mahc_hierarchical` | A-H4 | P3 |
| Vote-only aggregator | Same tuple, same location, scalar votes (p.116) | `mahc_hierarchical=OFF` | A-H4 | P3 |
| Chain-of-Evidence ledger | Append-only, signed, replicated decision trail (routing, fallbacks, adversarial events, ethics audits, α in force, who was asked, shadow result, what was written) (p.140, p.129–130, p.209) | — | all | P3 |
| Narrative Engine | Renders the CoE as narrative; claim-extraction parser for H_fact; noExpl keeps only the ranked list (p.140, p.163, p.165) | `coe_narrative` | E-H7, A-H7 | P3 |

### 3.6 L4 — Action and learning (Learning plane)

| Feature | Must do (Ch3) | Flag | Serves | Phase |
|---|---|---|---|---|
| HITL gate with α | Risk tiers by α; DB modifications, network-policy changes and rollbacks always need a human; α unset by default (firm sets it); immutable accept/escalate/reject log (p.118, p.127–128, p.212) | HITL | E-H7, covariate | P4 |
| FGSV (Algorithm 4) | Twin execution only if a one-sided two-sample KS test passes at α_ks = 0.05 (β_ks = 0.20 for d = 0.3); blast radius vs baseline → FAIL; KS failure → STALE + `shadow_suspended=true`; no production write without twin validation (p.144, p.147, p.156) | `fgsv_ks_gate` | E-H4 | P4 |
| ASRE | Structural, WAL-replay (+5–30 s for stateful), probabilistic-sketch modes (p.147, p.215) | — | — | P4 |
| Digital twin | Pillar-matched twin with Istio-style traffic mirroring (p.156) | — | E-H4 | P4 |
| Actuation + remediation templates | Sole execution boundary; versioned template library (SEAN); feeds provisional reward; MTTR window [t_inj, t_inj + 1800 s] (p.139, p.144, p.203) | — | B-H6 | P4 |
| Monitor Agent | Ethics constraints on every automated action; ethics-compliance rate (p.165, p.212) | — | descriptive | P4 |
| Critic Agent | Post-incident five-component CpR under the price book; per-component breakdown (p.165, p.203) | — | A-H5, B-H7 | P4 |
| Learning loops | MAML-Quick retraining (CPU/GPU hours reported); weekly bias-audit recalibration and weekly ACP retraining in production mode only — off in confirmatory runs (p.144, p.146, p.165) | — | descriptive | P4 |

### 3.7 Product shell and operations

Ch3 specifies no API, UI or storage engine; these are product decisions, kept minimal and outside the protocol (ADRs in P0.6).

| Feature | Must do | Phase |
|---|---|---|
| Control-plane isolation | Dedicated tainted K8s node pool; ResourceQuota of 8 CPU / 32 GiB per incident; control plane within 5–10% of cluster capacity (p.117, p.136) | P6 |
| Deployment | Helm charts for HELIOS, the pre-warm testbed (p.231) and the twin; container images pinned by digest | P6 |
| API | Incident submission, verdict retrieval, CoE retrieval, HITL decisions, admin (α, decision rights); API keys | P6 |
| HITL console + incident view | Ranked list, CoE narrative (switchable for noExpl), accept/escalate/reject with timing capture — also the RQ4 study instrument | P6 |
| Governance configuration | Decision-rights table (8 rules, Table 16 p.129–130); adoption stages shadow → recommendation → automatic action (p.128) | P6 |
| Multi-tenancy | Graph-partition isolation, per-tenant DP budgets, `tenant=self` partition (p.211, p.160, p.158) | P5, P6 |
| Self-observability SLOs | Per-plane span histograms (TTD, TTT, latency p50/p95/p99) (p.165); the 150 ms latency SLO for the reasoning tier (p.217) | P5, P6 |
| Security | PII / secret scanning (existing gitleaks + PII tooling), dependency pinning, signed images, audit trail | P6 |
| Documentation | Operator guide, deployment guide, API reference, reproduction guide | P6, P8 |

### 3.8 Explicitly out of scope (Ch3 defers these)

Multi-incident cascade correlation; formal coverage over unknown faults; partially instrumented or non-OTel estates; reduced-capability mode evaluation; industrial or multi-site replication; independently built pre-warm testbed; external cognitive-fault corpus; confirmatory FGSV/IOL tests and confirmatory online ORAR; flag-interaction effects; larger role-stratified user study; firm-level adoption or revenue estimates; legal liability for automatic changes (p.136, p.157, p.159, p.165, p.205, p.208, p.213–217). Building any of these needs a new pre-registration.

### 3.9 Parameters Ch3 leaves unset — calibrate before freeze

| Parameter | Used by | Calibrated on | Phase |
|---|---|---|---|
| MAHC entropy floor λ; prior back-off minimum-sample thresholds | MAHC | OTel set + pre-warm testbed | P3 |
| τ_acc, τ_lat, LinUCB exploration coefficient, feature set (12–18 features) | ORAR | pre-warm testbed (Algorithm B.1) | P3 |
| Hop limit K, top-n | Pruner | OTel set | P1 |
| Blast-radius threshold, twin KS sample size | FGSV | twin + testbed | P4 |
| Tier B SLO-pressure rule | Sampling | testbed | P5 |
| Design-committed HIS tier (only HIS-3 is named) | HIS | testbed | P5 |
| Adaptive Specialization Gate function | L-pipe | OTel set | P2 |
| Avg@5 definition; "ambiguous" and "narrative-heavy" strata; "matched HR@3" | Metrics | definition (matrix §10) | P0 |
| α (autonomic threshold) | HITL | **not set** — firm-set by design; evaluation runs with HITL simulated per protocol | — |

---

## 4. Decision gates (from the R1 matrix, plus one new)

| # | Decision | Default assumed by this plan | Blocks |
|---|---|---|---|
| D1 | Approved Ch3 binds; May freeze replaced | Yes | P0 |
| D2 | Ch3 flag registry | Adopt Ch3 names + 5 missing flags | P0 |
| D3 | LLM for confirmatory runs | 70B / vLLM for confirmatory and the ε probe; 8B / Ollama for development | P7 GPU procurement |
| D4 | Router pre-warm corpus | Build the 1,200-incident testbed | P3, P7 |
| D5 | Five B-family baselines | Named with the chair in P0 | P7 |
| D6 | Ch3 clarifications | Accepted, chair informed | P0 |
| D7 | Ed25519 deviation-log signatures | Add, keep HMAC chain | P0 |
| D8 | H4b scaling sub-study | Separate pre-registration, run in phase E | E4 |
| **D9 (new)** | G-pipe: Ch3 calls it "graph machine-learning reasoning" (p.103), trained on the pruned subgraph (p.152); the code's PPR G-pipe is training-free | Trained graph-ML G-pipe with PPR as its seed/feature stage; record in the pre-registration | P2 |

---

## 5. Build phases

Durations assume one developer with AI assistance, five build days a week. Phases P5–P7 overlap with earlier phases where dependencies allow (§8). Every phase ends with the full engineering gate, a tag `build-pN-exit`, and an exploratory smoke run on the OTel set (labelled exploratory).

### P0 — Protocol and architecture foundation (3 weeks)

Settles what is built, so nothing is built twice.

| WP | Work | Exit check |
|---|---|---|
| P0.1 | Decisions D1–D9 recorded (tracker + deviation entries) | All nine decided; chair memo sent for D5, D6, D8 |
| P0.2 | Metric contract memo: CpR = five-component cost; MRR; Avg@5; TTT vs TTD; strata definitions | Memo committed; docs drift fixed (matrix §9) |
| P0.3 | Flag registry per D2; 15 variants re-derived from Ch3 Table 17 and p.153; noMAHC/noCBR/live/noLLM-noGraph retired | Unique hashes for all 15; disjointness audit lists all flags (uncovered allowed until P8) |
| P0.4 | Analysis plan Families A, B, E per Ch3 (tests, sidedness, Holm, asymmetric rule) | `analysis_plan.py` matches matrix §2–§4 |
| P0.5 | Seed register generated and frozen; Ed25519 signing added to the deviation log (D7); audit step E (pre-registration in the manifest signature) | Ledgers verify; an examiner can verify signatures with the public key |
| P0.6 | Architecture decision records: storage/graph engine, message bus, API framework, twin technology, plane-numbering map (Ch3's 5 planes vs the "Plane 1–7" references) | ADRs committed |
| P0.7 | **OSF deposit 1 — hypotheses, variants, metrics, analysis plan, seed register** | DOI recorded in the deviation log |

### P1 — Data plane and UEG-C (6 weeks)

| WP | Work | Exit check |
|---|---|---|
| P1.1 | Ingest framework: OTLP live + recorded mode, five pillars, sealed recording of every capture | Live OTel Demo stream and recorded replay give the same window hash |
| P1.2 | P3 log processing: Drain3 templates + LogEDL vacuity | Template and vacuity outputs on the OTel set |
| P1.3 | P4 cognitive telemetry (MCP spans, schema validation, goal drift, loop depth) and P5 business telemetry | Fixtures produce ARS and Transaction/KPI nodes |
| P1.4 | UEG-C store: four typed edge kinds with composition rules, new node types, tenant partitions | Cross-domain path query test; tenant isolation test |
| P1.5 | `ueg_structural` bundle (untyped edges, ARS demotion) | noStructural changes the snapshot hash on a structural fixture |
| P1.6 | K-hop Pruner to Algorithm 5 (r = 0.7, 10,000 edges, hashed output); K and top-n calibrated on the OTel set | 50–200-node outputs on the OTel set; deviation entry for K, top-n |

### P2 — Reasoning pipelines (6 weeks)

| WP | Work | Exit check |
|---|---|---|
| P2.1 | Verdict contract (ranked list, μ, σ, cost, latency) across D, G, L | All three emit the contract; schema version bumped with a deviation entry |
| P2.2 | D-pipe completion: σ estimate, Tier C trigger, determinism settings, subgraph-aware training | Bitwise rerun equality |
| P2.3 | G-pipe per D9: trained graph-ML model on the pruned subgraph, PPR stage retained; PPR scores rounded with the `canonical_json` six-decimal rule before they affect ordering or hashes | Rerun equality (identical rounded score maps on repeat calls); held-out HR@3 on the OTel set (exploratory) |
| P2.4 | L-pipe multi-agent: Orchestrator, Specialization Gate, worker mesh, Persona Profiles (episode-boundary refresh), (μ, σ) emission | Each worker's verdict logged; `p4_cognitive` scoped to L-pipe visibility (p.138 coupling fix) |
| P2.5 | Knowledge Cortex (RAG, warm tier seeded from the OTel set + testbed only) | SOP retrieval tests; no confirmatory incident in the index (hash check) |
| P2.6 | LLM Gateway with per-episode token accounting; model-agnostic serving interface (Ollama for development, vLLM for Protocol A) | Same prompt through both backends; token counts logged |

### P3 — Coordination, consensus and learning (6 weeks)

| WP | Work | Exit check |
|---|---|---|
| P3.1 | MAHC (Algorithm 3): hierarchical priors, σ weighting, weighted Borda, entropy floor, 30 s / 90 s timing; λ calibrated | The conceptual counterexample (σ 0.1 vs 0.8, p.157) yields different fused rankings; deviation entry for λ |
| P3.2 | Vote-only aggregator for `mahc_hierarchical=OFF` | noConsensus emits the same tuple at the same location |
| P3.3 | Pre-warm testbed (D4): three-service testbed, Chaos-Mesh injection, 1,200 incidents, construction parameters pre-registered before generation, Helm chart | Corpus hashed; SHA-intersection check vs benchmark specs empty |
| P3.4 | ACP (Algorithm 2) trained on the testbed (960 / 240 split) and frozen | Parameter SHA-256 in the manifest |
| P3.5 | ORAR (Algorithm 1): LinUCB pre-warm per Algorithm B.1, frozen; constraint-empty fallback; `cbr_routing=uniform` | Routed arm recorded per run; frozen params verified by the VCL at start |
| P3.6 | Two-stage reward, reconciliation, RRE, anti-reward-hacking regularisers (exploratory subset only) | Provisional + terminal records verify under the ledger anchor |
| P3.7 | Chain-of-Evidence ledger (signed, append-only) and Narrative Engine with the claim-extraction parser | `coe_narrative=OFF` yields the ranked list only; parser output deterministic |

### P4 — Action, safety and remediation (6 weeks)

| WP | Work | Exit check |
|---|---|---|
| P4.1 | HITL gate: risk tiers by α, mandatory human approval kinds, immutable decision log, simulated-HITL mode for evaluation runs | Every high-risk action blocked without approval |
| P4.2 | Digital twin with traffic mirroring; ASRE three modes | Twin replays a recorded incident with matched pillars |
| P4.3 | FGSV (Algorithm 4): KS gate, blast radius, PASS / FAIL / STALE, `shadow_suspended` covariate | No production write path bypasses FGSV (test) |
| P4.4 | Actuation boundary + versioned remediation templates; MTTR measurement window | Remediation on the testbed restores telemetry inside 1,800 s |
| P4.5 | Monitor Agent (ethics) and Critic Agent (five-component CpR from the price book) | CpR components on every run |
| P4.6 | Learning loops in production mode (MAML-Quick, weekly ACP retraining, bias audit), hard-disabled under a confirmatory manifest | VCL refuses to start a confirmatory run with any learning loop on |

### P5 — Self-observability, privacy and robustness (5 weeks, overlaps P3–P4)

| WP | Work | Exit check |
|---|---|---|
| P5.1 | IOL: self-telemetry into UEG-C under `tenant=self`; the three query kinds | Injected Gateway saturation is traced to an L-pipe latency anomaly |
| P5.2 | Cognitive Sentinels + Deterministic Fallback Agent (about 30% of fault kinds; alert-only otherwise) | Fallback engages on injected LLM degradation; logged as a covariate |
| P5.3 | Privacy Gateway: PII/NER redaction, structure-preserving placeholders, per-tenant DP budgets with 24 h windows | No raw PII past the gateway (test corpus); budget exhaustion recorded |
| P5.4 | ARM: injection and poisoning detection, attestation challenges | Adversarial fixtures flagged and stratified |
| P5.5 | Tiered adaptive sampling with downgrade rule; `sampling_regime_tag` | Downgrade at the memory/CPU thresholds, recorded |
| P5.6 | HIS tiers and tagging (`his_tier`); design tier fixed | Every latency/cost value carries its tier |

### P6 — Product shell and deployment (5 weeks, overlaps P4–P5)

| WP | Work | Exit check |
|---|---|---|
| P6.1 | API (incidents, verdicts, CoE, HITL decisions, admin), API keys | Contract tests |
| P6.2 | HITL console + incident / CoE view with narrative toggle and decision-time capture (RQ4 instrument) | Usability walk-through; timing capture verified |
| P6.3 | Governance configuration: decision-rights table, adoption stages (shadow / recommendation / automatic) | Shadow mode never writes to production (test) |
| P6.4 | Helm charts (HELIOS, testbed, twin), control-plane node pool and per-incident quotas | Clean install on a fresh cluster from the chart alone |
| P6.5 | Multi-tenant administration; self-observability dashboards (per-plane latency, TTD, TTT) | 150 ms latency SLO measured on a one-hundred-service estate |
| P6.6 | Security hardening (image signing, dependency pins, secret and PII scanning in CI) and operator / API / deployment documentation | Docs build; security checks in CI |

### P7 — Evaluation infrastructure (7 weeks, starts during P4)

| WP | Work | Exit check |
|---|---|---|
| P7.1 | Benchmark adapters: AIOpsLab, DeathStarBench, Train-Ticket, PetShop, OpsEval → recorded, sealed windows | One sealed incident per benchmark through the full path |
| P7.2 | Fault injection: Chaos-Mesh (Tier 2: 9 types × 3 severities × 2 concurrency), ChaosBlade (Tier 3), NIKA-style Tier 4 cognitive faults (6 hallucination + 6 goal-drift kinds) | Each tier produces labelled incidents |
| P7.3 | Delayed-label injection (25% of AIOpsLab + Train-Ticket; log-normal μ_log 8.7, σ_log 1.4) | Delay distribution matches the spec |
| P7.4 | Synthetic perturbation protocols: twin fidelity breaks (E-H4), control-plane degradation (E-H6) | Injectors parameterised and hashed |
| P7.5 | Baselines (D5): five systems with identical telemetry access; configurations published; CHASE adjustment per the clarified rule | Each baseline emits ranked lists in the common format |
| P7.6 | Metrics: HR@1/3/10, Avg@5, MRR, MFR, P/R, macro-F1, log-MTTR, CpR, TTT, TTD, H_fact / H_struct tooling (parser + rater interface, κ), RRE, non-convergence, HITL escalation, CPU/GPU hours, ethics compliance; FAE judge harness | Each metric computed from stored outputs after dispatch, never fed to pipelines |
| P7.7 | Run orchestrator: 16,000-run schedule, cell bookkeeping, ≥ 320/400 cell rule, exclusion + MCAR + IPW | Dry run of the full schedule on fixtures |
| P7.8 | Analysis suite: Wilcoxon, sign test, McNemar exact mid-p, Holm per family, BH sensitivity, BCa (10,000 resamples, registered seeds), Cliff's δ, Hodges–Lehmann, rank-LMM / nparLD / GLMM (R, lme4) sensitivity; exploratory label enforcement | Fixture data reproduces hand-computed statistics |
| P7.9 | Protocol A environment (D3): 4× A100 80GB, vLLM 0.6.x pinned by digest, CUDA 12.1, deterministic flags; ε probe script | Token-sequence equality on repeated prompts |
| P7.10 | Price book coefficients sourced and frozen | Every coefficient cited or measured |

### P8 — Integration, verification and freeze (4 weeks)

| WP | Work | Exit check |
|---|---|---|
| P8.1 | System test: every variant end to end on the OTel set and one incident per benchmark | 15 variants × all paths green |
| P8.2 | Disjointness certification: every boolean flag covered exactly once | Audit report with zero uncovered flags |
| P8.3 | Exploratory pilot on the OTel set (labelled exploratory): shakedown of metrics, timing, cost, exclusions | Pilot report; no confirmatory language |
| P8.4 | Replication from a clean environment (two incidents per variant) | Snapshot hashes and fused rankings match |
| P8.5 | ε determinism probe on the 200-prompt set (p.225) | ε and token-equality rate recorded |
| P8.6 | **Build freeze:** binary commit SHA, container digests, model weight SHA-256, LinUCB/ACP parameter hashes, price book, construction scripts, corpus manifest with seal hashes (174 + reserve), confirmatory corpus partition restated (matrix §10.7) | Tag `build-freeze`; VCL blocks any divergence |
| P8.7 | **OSF deposit 2 — freeze addendum** (artefact hashes, corpus, parameters, baselines) | DOI in the deviation log; **product build complete** |

---

## 6. Phase E — Testing and evidence collection

Nothing here changes code. Any defect found is fixed under a deviation entry; affected runs are re-run or excluded with ledger entries, never edited.

| Stream | Work | Output |
|---|---|---|
| **E1 Confirmatory ablation (Family A)** | 8 variants × 5 benchmarks × 40 faults × 10 seeds = 16,000 runs under Protocol A; per-cell completion tracking | Sealed result store; exclusion ledger; cell completion table |
| **E2 Baseline comparison (Family B)** | HELIOS-Full vs the five baselines on the 174-fault corpus | Paired outcome tables |
| **E3 Exploratory family (E-H1–E-H10)** | 7 exploratory variants; Tier 4 subset (E-H1); delayed-label subset with thawed LinUCB (E-H5); fidelity-break perturbation (E-H4); control-plane degradation (E-H6); HIS-3 (E-H9) | Exploratory result store, labelled |
| **E4 Scaling sub-study (H4b, D8)** | Synthetic estates of 500, 1,000, 2,500, 5,000 services; reasoning-tier latency and CpR vs SLO | Scaling report under its own pre-registration |
| **E5 RQ4 user study (E-H7)** | IRB-approved; n = 24 (12 practitioners, 6 academics, 6 business); 12 stratified scenarios; Full vs noExpl; Latin square | Study dataset; IRB number in the deviation log |
| **E6 Rating** | H_fact / H_struct by two blind raters (κ ≥ 0.7, adjudicator below), 50-instance calibration; FAE-Score by three judge models with 10% human anchoring | Rated datasets with agreement statistics |
| **E7 Sensitivity runs** | Qwen-2.5-72B contrast subset; Protocol B API subset | Sensitivity datasets |

Exit: every cell complete or formally excluded; inclusion reported per cell; replication of 10% of runs from a clean environment.

---

## 7. Phase A — Analysis

| Step | Work |
|---|---|
| A1 | Confirmatory Family A: Wilcoxon (sign test for A-H7), one-sided where pre-registered, Holm over 8, asymmetric rule for A-H4 and A-H8 |
| A2 | Confirmatory Family B: McNemar exact mid-p for B-H1–B-H5; Wilcoxon for B-H6–B-H8; separate Holm family |
| A3 | Effect sizes and intervals: BCa, Cliff's δ, Hodges–Lehmann |
| A4 | Sensitivity: BH q = 0.05, paired t on logs, rank-LMM / nparLD / GLMM, MCAR and IPW, Protocol B and Qwen contrasts |
| A5 | Exploratory family E-H1–E-H10: point estimates + BCa, clearly separated, no Holm |
| A6 | C1 evidence: variant-identity verification rate, snapshot-consumption rate, completion rate, ledger counts |
| A7 | Business Evaluation Layer mapping (Table 15): technical outcomes → stakeholder readings, without firm-level savings claims |
| A8 | Threats to validity; deviation summary; replication package (code, digests, corpus manifest, analysis scripts) deposited with OSF |

Write-up (Chapters 4–5, defence, publications) follows Phase A and is outside this plan.

---

## 8. Indicative calendar

Start 2026-11-02. Weeks are build weeks; holidays and slips move later phases with them.

| Phase | Weeks | Indicative window | Depends on |
|---|---|---|---|
| P0 Protocol foundation | 3 | Nov 2026 | D1–D9 |
| P1 Data plane + UEG-C | 6 | Nov 2026 – Jan 2027 | P0 |
| P2 Reasoning pipelines | 6 | Jan – Feb 2027 | P1 |
| P3 Coordination + learning | 6 | Feb – Apr 2027 | P2 (P3.3 testbed can start in P1) |
| P4 Action + safety | 6 | Apr – May 2027 | P3 |
| P5 Self-observability, privacy | 5 | Mar – May 2027 (overlaps) | P1, P2 |
| P6 Product shell | 5 | Apr – Jun 2027 (overlaps) | P3 |
| P7 Evaluation infrastructure | 7 | Apr – Jun 2027 (overlaps) | P1; P7.9 GPUs booked in P0 |
| P8 Integration + freeze | 4 | Jul 2027 | P1–P7 |
| **Product build complete** | — | **end of Jul 2027** | OSF deposit 2 |
| E Evidence collection | 10–12 | Aug – Oct 2027 | P8; IRB approval for E5 |
| A Analysis | 6 | Nov – Dec 2027 | E |

Lead-time items to start in P0: IRB application (E5), GPU reservation (P7.9, E1), baseline access and licences (P7.5), chair memo (D5, D6, D8).

---

## 9. Resources

| Resource | Need | When |
|---|---|---|
| GPUs | 4× A100 80GB (TP = 4) for Protocol A; plus judge-model API budget | P7.9 setup; E1 campaign |
| Kubernetes | Cluster for testbed, twin, benchmarks, scaling to 5,000 synthetic services | P3 onward; E4 |
| People | Two raters + adjudicator (E6); 24 study participants with honoraria (E5) | Phase E |
| Approvals | GGU IRB (E5); chair sign-off on D5, D6, D8 | P0 |
| External | Benchmark and baseline artefacts; judge-model APIs (GPT-4o, Claude Sonnet, Gemini Pro) | P7 |

---

## 10. Risks

| Risk | Effect | Response |
|---|---|---|
| Scope: the full design is large for one developer | Build-complete date slips past the GGU deadline | Confirm the deadline now; if needed, keep every confirmatory mechanism and descope exploratory-only features first (HIS-3, IOL, FGSV twin depth, ARM attestation) with deviation entries |
| GPU access / cost (D3) | No Protocol A campaign | Book early; fallback (b) with bounded claims |
| Pre-warm testbed (D4) takes longer | ORAR not ready | Start P3.3 during P1; fallback published initialisation with deviation |
| Baselines unavailable to run (D5) | Family B incomplete | Published-score adjustment route, as for CHASE |
| Confirmatory data leaks into development | Confirmatory claims void | Hash checks (pre-warm, Knowledge Cortex, calibration sets); evidence data unsealed only in Phase E |
| A defect found during Phase E | Partial reruns | Deviation entry, rerun or exclude with ledger entries, never edit results |
| IRB delay | RQ4 late | Submit in P0 |
| Unset parameters chosen after seeing confirmatory data | Bias | All fixed in P8.6 from non-confirmatory data, before deposit 2 |

---

## 11. Tracking

Each work package gets tracking rows in `docs/tracking/helios_mvp_tracking.md` under new milestone sections (`S2-M5-…` onward, one milestone per phase, since the validator's ID format is `S{n}-M{m}-{TYPE}{nn}`), IN_PROGRESS before work and DONE with SHA + evidence after. Phase exits are tagged (`build-pN-exit`, `build-freeze`, `evidence-complete`, `analysis-complete`). The Milestone 4 rows still PLANNED (S1-M4-RES01/RES02/EVAL01/GATE01) close as superseded by P8.3, with a deviation reference.
