# HELIOS — End-to-End Plan: Product Build → Evidence Collection → Analysis

**Version:** second draft, re-baselined 2026-10-23 to the GGU deadline; full product scope kept, built in two stages · **Owner:** AA
**Deadline:** **results ready by 2027-03-31** (evidence collected and analysed); Chapters 4–5 are written after.
**Supersedes for scheduling:** `HELIOS_MVP_Execution_plan_v0.6.md` and this plan's first draft (60-week full scope). It does **not** change the protocol by itself: protocol changes go through `bin/log_deviation.py`, mostly in sprint S0, against `docs/tracking/r1_traceability_matrix.md`.

**Design latitude (owner direction, 2026-10-23).** The goal is a high-quality, production-grade observability product that shows innovation and creativity. Chapter 3 is the **baseline, not the final verdict**: where a different or more creative method gives a better or more production-ready result, prefer it. This plan and the R1 matrix are guides, not rigid specifications. One line does not move: a change that alters what a pre-registered test measures is recorded (deviation entry, pre-registration update) **before** confirmatory data is collected, so the evidence stays valid.

**Sources:** approved Chapters 1–3 (`docs/research/Complete_Report.pdf`, printed page "p.NNN"); repository `main` @ `b72f4cd`; R1 matrix (decisions D1–D9); RCAEval benchmark ([paper](https://arxiv.org/abs/2412.17015), [code](https://github.com/phamquiluan/rcaeval), [data](https://zenodo.org/record/14504480)).

---

## 0. Re-baseline decisions (approved 2026-10-23)

The full Ch3 scope needs about 60 weeks to reach analysis; the deadline leaves 21. The owner approved:

| # | Decision | Effect |
|---|---|---|
| RB1 | **Recorded-dataset evaluation.** Confirmatory and baseline evidence come from recorded, labelled multi-source incidents — **RCAEval RE2** (270 cases with metrics, logs and traces; Online Boutique, Sock Shop, Train-Ticket; 11 fault types) plus AIOpsLab where it can be run in time — instead of building five live fault-injection environments | Removes months of infrastructure; restates the corpus and the 16,000-run design in the pre-registration (S0); licence and labels verified in week 1 |
| RB2 | **8B model for confirmatory runs** (D3 option b; deviations 15–16 already logged). A rented 70B run on a subset is a sensitivity check if budget allows | L-pipe claims are stated for the 8B model |
| RB3 | **Full product scope, built in two stages — nothing is cut** (owner, 2026-10-23). **Stage A** (evidence build): Tier 1 and, if ready, Tier 2, frozen mid-February for the confirmatory evidence. **Stage B**: the rest of the full product (Tier 3) is built straight on, February–July 2027, into the same product behind feature flags, and evaluated exploratorily after March (§11) | Results by 31 March cover the Stage A build; the full product is still built |
| RB4 | **21-week timeline** (§6) | Freeze mid-February; evidence to mid-March; analysis to 31 March |
| IN1 | **Evidence-grounded narratives.** Every claim in the Chain-of-Evidence narrative cites a UEG-C node or edge; a verifier drops ungrounded claims before display, and its rejections are logged | Lowers H_fact (A-H7), raises trust (RQ4), product differentiator |
| IN2 | **Calibrated uncertainty in consensus.** MAHC outputs a ranked set with a calibrated confidence, calibrated on the calibration split only | Honest product output; sharper A-H4 signal |
| IN3 | **Cheap-first routing.** The router runs the statistical and graph pipelines first and calls the LLM only on disagreement or low confidence (Ch3's Non-LLM-First Gate, made central) | Lower CpR (A-H5); explainable cost/benefit |

Calibration and training (G-pipe ranker, router initialisation, MAHC calibration, λ) use only a **calibration partition** that is disjoint from confirmatory cases and fixed with a registered seed in S0 (candidate: RCAEval RE1/RE3 + a stratified slice of RE2 + the 20-incident OTel set). Confirmatory cases stay sealed until phase E.

---

## 1. Principles every sprint inherits

1. **One binary, every variant.** All variants run from one commit fixed at freeze; variants differ only by the flag vector the VCL reads at start (p.106, p.108).
2. **Every contribution is ablatable.** Each mechanism sits behind its flag in the `VCLFlag` registry; the disjointness audit must show every boolean flag gating exactly one code path before freeze.
3. **Build data ≠ evidence data.** Only the calibration partition and fixtures are used to build and tune.
4. **Unset parameters are fixed before freeze**, on calibration data, each with a deviation entry.
5. **Failures are covariates, never silent fallbacks** (p.139).
6. **Engineering gate on every change:** tracking row (IN_PROGRESS → DONE), PR, full pre-push gate (ruff/black incl. `bin/`, mypy strict, pytest ≥ 90% coverage, `verify_ledgers.py`, `verify_captures.py`, `verify_osf_freeze.py`, tracking `--range`), tests that fail if the feature is removed, deviation entry when there is an analytic consequence.
7. **Quality, without cutting scope.** Every feature ships production-grade (tests, docs, operability) or it is not done. If time runs short before the freeze, Tier 2 moves to Stage B rather than Tier 1 being rushed; nothing is dropped from the product.
8. **The frozen evidence build is never touched.** Stage B work happens after the `build-freeze` tag, on `main` behind its feature flags; the confirmatory runs execute from the frozen commit only.

---

## 2. Where the build starts (main @ `b72f4cd`)

| Area | Exists today | Still to build |
|---|---|---|
| C1 spine | VCL (14 flags), variant hashes, snapshot registry, integrity gate, ledgers with signed anchors, capture seals, disjointness audit, OSF tooling, CI | Ch3 flag registry, seed register, price book, cell bookkeeping, Ed25519 (D7) |
| Ingest | Recorded OTel Demo capture (20 incidents), sealed | RCAEval RE2 (+ AIOpsLab) adapters, log templates |
| Graph | Structural + call edges, PPR pruner | Four typed edge kinds, Algorithm 5 pruner, structural bundle |
| Pipelines | D-pipe, G-pipe (PPR), L-pipe (single prompt, llama3.1:8b) | Verdict contract, trained graph ranker (D9), lean multi-agent L-pipe, token accounting |
| Coordination | Uniform Borda behind `mahc` | MAHC + calibrated confidence, vote-only, router, ACP, reconciliation, CoE + grounded narrative |
| Product | CLI scripts | API, approval console, compose deployment |
| Evaluation | HR@3 script | Scoring path, all metrics, baselines, run orchestrator, analysis suite |

---

## 3. Scope by tier

Nothing in this section is cut (full product scope). Tier 1 = in the Stage A evidence build, frozen mid-February (confirmatory + core product). Tier 2 = in the Stage A build if ready by the freeze (exploratory evidence); otherwise built in Stage B. Tier 3 = Stage B: built after the freeze, February–July 2027, behind feature flags, evaluated exploratorily after March (§11). "S" = sprint (§5).

### 3.1 C1 and evaluation plane

| Feature | Tier · Sprint | Notes |
|---|---|---|
| VCL with full artefact-hash verification | T1 · S0, S5 | Ch3 p.108, p.211 |
| Flag registry (D2) + 15 variants re-derived | T1 · S0 | Matrix §5 |
| Seed register 10,000,000–10,009,999 | T1 · S0 | p.108 |
| Ed25519 deviation-log signatures (D7) | T1 · S0 | Small change; examiner-verifiable |
| Price book (frozen coefficients) | T1 · S1 | p.108 |
| Metric integrity gate, exclusion ledger, MCAR + IPW | T1 · S4 | p.111, p.162 |
| Run orchestrator with cell bookkeeping | T1 · S4 | p.160 |
| Failure covariates (pipeline unavailable, non-convergence, constraint-empty fallback, LLM unavailable) | T1 · S2–S4 | Remaining covariates follow their Tier-3 features |
| Reconciliation ledger + RRE | T2 · S3 | E-H5 |
| Disjointness certification | T1 · S5 | Zero uncovered flags |

### 3.2 Ingest and graph (L0–L1)

| Feature | Tier · Sprint | Notes |
|---|---|---|
| Recorded dataset adapters: RCAEval RE2, OTel set, AIOpsLab if runnable; every case sealed | T1 · S1 | RB1 |
| Log templates (Drain3) | T1 · S1 | LogEDL vacuity → T3 |
| Typed UEG-C: structural, behavioural, causal, economic edges with composition rules; ARS nodes for HELIOS's own agent steps | T1 · S1 | C2; A-H8 |
| Structural bundle (`ueg_structural=OFF`: untyped edges, no subgraph-aware training, ARS demoted) | T1 · S1–S2 | A-H8 |
| K-hop pruner (Algorithm 5; r = 0.7, 10,000-edge budget) | T1 · S1 | K and top-n calibrated |
| Schema-validation records of HELIOS's own tool calls (source of H_struct) | T1 · S2 | A-H7 |
| P4 MCP spans, goal drift, loop depth; P5 business telemetry | T3 | |
| Live OTLP ingest | T3 | Product follow-up |
| PII redaction before any LLM call (pattern-based) | T2 · S4 | Full DP gateway → T3 |
| Adversarial monitor, eBPF tiered sampling, multi-tenant partitions, IOL | IOL lite T2 · S4; rest T3 | |

### 3.3 Reasoning (L2)

| Feature | Tier · Sprint | Notes |
|---|---|---|
| Verdict contract (ranked list, μ, σ, cost, latency) | T1 · S1 | All pipelines |
| D-pipe: σ estimate, determinism settings | T1 · S2 | A-H3 |
| G-pipe (D9): learning-to-rank over PPR scores and graph features, trained on the calibration partition; PPR scores rounded with the `canonical_json` rule before ordering or hashing | T1 · S2 | "Graph machine-learning reasoning" (p.103), cheap and deterministic |
| Lean multi-agent L-pipe: orchestrator + metric, trace and log workers + narrator, each emitting (μ, σ); simple Persona Profiles | T1 · S2 | A-H1, A-H2, A-H7 |
| LLM Gateway token accounting | T1 · S1 | CpR |
| Knowledge Cortex (SOP retrieval from the calibration partition) | T2 · S3 | |
| Fallback when the LLM is unavailable (route to D+G, logged as covariate) | T2 · S3 | Full sentinel + fallback agent → T3 |
| 70B Protocol A serving | T3 (sensitivity if budget) | RB2 |

### 3.4 Coordination (L3)

| Feature | Tier · Sprint | Notes |
|---|---|---|
| MAHC (Algorithm 3) + **calibrated confidence (IN2)**; entropy floor λ; PROVISIONAL / CONFIRMED states | T1 · S2 | A-H4 |
| Vote-only aggregator (`mahc_hierarchical=OFF`) | T1 · S2 | A-H4 |
| Chain-of-Evidence ledger (signed, append-only) | T1 · S2 | |
| Narrative Engine + **evidence-grounding verifier (IN1)** | T1 · S2 | A-H7, RQ4 |
| Router (Algorithm 1, static) with **cheap-first gate (IN3)**; initialised from the calibration partition (D4 option b); `cbr_routing=uniform` for noRouter | T1 · S3 | A-H5 |
| ACP (Algorithm 2) | T2 · S3 | E-H3/E-H8 |
| Two-stage reward + delayed labels injected on recorded cases | T2 · S3 | E-H5 |
| HIS tiers, 1,200-incident synthetic pre-training set | T3 | E-H9; replaced by RB3 initialisation |

### 3.5 Action, product and evaluation

| Feature | Tier · Sprint | Notes |
|---|---|---|
| Critic Agent: five-component CpR from the price book | T1 · S1, S4 | A-H5, B-H7 |
| HITL gate + approval console (ranked set, grounded narrative with noExpl toggle, accept/escalate/reject with timing) | T1 · S4 | RQ4 instrument; simulated HITL in runs |
| API (incidents, verdicts, CoE, decisions) + docker-compose deployment | T1 · S4 | Helm → T3 |
| Shadow / recommendation modes (no production write path) | T2 · S4 | Automatic action → T3 |
| FGSV lite: KS gate + replay on recorded data, PASS / FAIL / STALE | T2 · S4 | Full twin, ASRE, remediation templates → T3 |
| Monitor Agent, learning loops, multi-tenant admin | T3 | |
| Baselines: five from the RCAEval suite (D5), run on the same cases; CHASE as published-score comparison | T1 · S4 | Family B |
| Metrics: HR@1/3/10, Avg@5, MRR, CpR, TTT, H_fact (verifier + two-rater sample), H_struct, non-convergence | T1 · S4 | MTTR → D10 |
| Analysis suite: Wilcoxon, sign test, McNemar exact mid-p, Holm per family, BCa, Cliff's δ, Hodges–Lehmann, BH and mixed-model sensitivity | T1 · S4 | |
| H4b scaling sub-study, Tier-4 cognitive faults (E-H1), Qwen contrast | T3 | Limitation or follow-up |

---

## 4. Decisions

All decided by the owner on 2026-10-23 except D11, which is prepared in S0 for review. Each protocol-relevant decision is logged through `bin/log_deviation.py` when it is implemented in S0, and is agreed with the guide on a call (D5, D6, the two-stage scope); outcomes are recorded in the Claude Doc "HELIOS pre-registration clarifications — call reference".

| # | Decision | Outcome |
|---|---|---|
| D1 | Which document binds | **(a) Approved Ch3 is the reference; the undeposited May freeze is replaced.** The code must reflect Ch3, used as the baseline under the design-latitude rule |
| D2 | Flag registry | **(a) Rename code flags to the Ch3 names and add the five missing Ch3 flags** — no mapping table |
| D3 | LLM for confirmatory runs | **8B (RB2)**; 70B sensitivity if budget |
| D4 | Router pre-training | **Initialise from the calibration partition (RB3)**; 1,200-incident set deferred |
| D5 | Five baselines | **Five methods from the RCAEval suite, run on the same cases; CHASE kept as the published-score anchor.** Shortlist to the chair after the S0 dataset check |
| D6 | Ch3 inconsistencies | **Accept the proposed clarifications as pre-registration text; walk the guide through them on a call before data collection, outcome recorded in the call-reference doc** |
| D7 | Deviation-log signatures | **(a) Add Ed25519, public key deposited on OSF; keep the HMAC chain underneath** |
| D8 | H4b scaling study | **Stage B, after 31 March** (RB3), under its own pre-registration |
| D9 | G-pipe | **(a) Lightweight learned ranker over PPR scores and graph features, trained on calibration data only** |
| D10 | MTTR on recorded data | **(c) Both:** B-H6 uses time-to-correct-diagnosis on recorded cases (deviation entry); true MTTR with live remediation on the OTel Demo as an exploratory result |
| D11 | Corpus and run design for RB1 (confirmatory cases, calibration partition, seeds, cells, power) | **Open** — prepared in S0.3 for review before OSF deposit 1 |
| D12 | RQ4 user study | **Submit the IRB application this week**; the study runs mid-February to mid-March if approval arrives by early February, otherwise later without affecting confirmatory results |

---

## 5. Sprints

Twenty working weeks (the 28 Dec – 1 Jan week is off). Every sprint ends with the full engineering gate and a tag `rb-sN-exit`.

### S0 — Foundation (2 weeks, 2–13 Nov)

| WP | Work | Exit check |
|---|---|---|
| S0.1 | Verify RCAEval RE2: licence, labels, modalities; AIOpsLab feasibility check | Go/no-go per dataset recorded |
| S0.2 | Decisions D1, D2, D5, D6, D7, D9–D12 recorded; call with the guide (D5, D6, two-stage scope), outcome recorded in the call-reference doc | Tracker + deviation entries |
| S0.3 | Corpus and run design (D11): confirmatory cases, calibration partition with registered seed, power check | Partition manifest hashed |
| S0.4 | Flag registry + 15 variants; analysis plan Families A, B, E; metric contract (CpR = cost; MRR; Avg@5; strata; MTTR per D10) | Hashes unique; plan matches matrix §2–§4 as adapted |
| S0.5 | Seed register; Ed25519; audit step E | Ledgers verify |
| S0.6 | **OSF deposit 1** (hypotheses, variants, metrics, analysis plan, corpus design, Stage B scope) | DOI in the deviation log |
| S0.7 | Lead-time items: IRB (D12), GPU/API budget, baseline environments | Submitted / booked |

### S1 — Data and graph (3 weeks, 16 Nov – 4 Dec)

| WP | Work | Exit check |
|---|---|---|
| S1.1 | Dataset adapters → sealed recorded windows (RE2, OTel, AIOpsLab if go) | Every case sealed and reproducible |
| S1.2 | Log templates; typed UEG-C with composition rules; structural bundle | Cross-domain path test; noStructural changes the snapshot hash |
| S1.3 | K-hop pruner to Algorithm 5; K, top-n calibrated | 50–200-node outputs on calibration data |
| S1.4 | Verdict contract; LLM token accounting; price book; scoring path (post-dispatch, never fed to pipelines) | HR@k and cost recorded for every pipeline row |

### S2 — Reasoning, consensus, narrative (3 weeks, 7–25 Dec)

| WP | Work | Exit check |
|---|---|---|
| S2.1 | D-pipe σ; G-pipe learning-to-rank (D9) with rounding | Rerun equality; calibration HR@3 reported (exploratory) |
| S2.2 | Lean multi-agent L-pipe with (μ, σ) per worker; schema-validation records (H_struct) | Worker verdicts logged |
| S2.3 | MAHC + calibrated confidence (IN2); vote-only aggregator | σ counterexample (p.157) gives different fused rankings; λ and calibration logged as deviations |
| S2.4 | CoE ledger; Narrative Engine + grounding verifier (IN1) | Every displayed claim cites a graph element; ungrounded claims rejected in tests |

### S3 — Routing and learning (2 weeks, 4–15 Jan)

| WP | Work | Exit check |
|---|---|---|
| S3.1 | Router (Algorithm 1) with cheap-first gate (IN3), initialised on calibration data, frozen | Arm recorded per run; VCL verifies frozen parameters |
| S3.2 | ACP; two-stage reward on injected delayed labels; Knowledge Cortex; LLM-unavailable fallback (Tier 2) | Each behind its flag, or recorded as cut |

### S4 — Product shell and evaluation tooling (2 weeks, 18–29 Jan)

| WP | Work | Exit check |
|---|---|---|
| S4.1 | API + approval console + compose deployment | Fresh install from compose; RQ4 timing capture works |
| S4.2 | PII redaction, shadow/recommendation modes, FGSV lite, IOL lite (Tier 2) | Each behind its flag, or recorded as cut |
| S4.3 | Baselines from the RCAEval suite; all metrics; run orchestrator; integrity gate, MCAR, IPW; analysis suite | Fixture data reproduces hand-computed statistics; full schedule dry-runs |

### S5 — Integration and freeze (2 weeks, 1–12 Feb)

| WP | Work | Exit check |
|---|---|---|
| S5.1 | System test of every variant; disjointness certification | Zero uncovered flags |
| S5.2 | Exploratory pilot on calibration data; clean-environment replication | Pilot report labelled exploratory; hashes reproduce |
| S5.3 | **Build freeze**: commit SHA, image digests, model digest, router/ACP/ranker parameter hashes, price book, case manifest with seals | Tag `build-freeze` |
| S5.4 | **OSF deposit 2** (freeze addendum); Tier-2 cuts recorded | DOI in the deviation log; **product build complete** |

---

## 6. Phase E — Evidence collection (4 weeks, 15 Feb – 12 Mar)

No code changes. A defect found here is fixed under a deviation entry; affected runs are rerun or excluded with ledger entries, never edited.

| Stream | Work |
|---|---|
| E1 Confirmatory ablation (Family A) | 8 variants over the confirmatory cases per the D11 design |
| E2 Baselines (Family B) | HELIOS-Full vs the five baselines on the same cases |
| E3 Exploratory family | Built Tier-2 variants only; the rest reported as deferred |
| E4 RQ4 user study | Only if IRB approval arrives by early February (D12) |
| E5 Rating | H_fact: verifier output + two blind raters on a stratified sample (κ ≥ 0.7); FAE judges if budget |
| E6 Sensitivity | 70B subset if budget; MTTR on the live OTel Demo if D10 (b)/(c) |

Exit: every cell complete or formally excluded; inclusion reported; 10% clean-environment replication.

---

## 7. Phase A — Analysis (3 weeks, 15–31 Mar)

| Step | Work |
|---|---|
| A1 | Family A: Wilcoxon (sign test for A-H7), one-sided where pre-registered, Holm over 8, asymmetric rule for A-H4 and A-H8 |
| A2 | Family B: McNemar exact mid-p (B-H1–B-H5); Wilcoxon (B-H6–B-H8); separate Holm family |
| A3 | Effect sizes and intervals; sensitivity analyses; MCAR / IPW |
| A4 | Exploratory family with BCa, clearly separated |
| A5 | C1 evidence (verification, completion, ledger counts) and innovation evidence (grounding-verifier rejection rate, confidence calibration, cheap-first savings) |
| A6 | Results package: tables, figures, deviation summary, replication bundle — **results ready 31 March** |

---

## 8. Calendar

| Sprint / phase | Weeks | Dates |
|---|---|---|
| S0 Foundation | 2 | 2–13 Nov 2026 |
| S1 Data + graph | 3 | 16 Nov – 4 Dec |
| S2 Reasoning, consensus, narrative | 3 | 7–25 Dec |
| (holiday) | — | 28 Dec – 1 Jan |
| S3 Routing + learning | 2 | 4–15 Jan 2027 |
| S4 Product + evaluation tooling | 2 | 18–29 Jan |
| S5 Integration + freeze | 2 | 1–12 Feb |
| E Evidence collection | 4 | 15 Feb – 12 Mar |
| A Analysis | 3 | 15–31 Mar |
| Stage B product build (Tier 3, §11) | ~20 | 15 Feb – end of Jul 2027 (alongside E and A, then full time) |

No slack is built in. If a sprint slips, Tier 2 work in S3–S4 moves to Stage B first (it is not dropped); the freeze date moves only if Tier 1 is at risk, and then by taking time from E3/E5, never from E1/E2 or A1/A2.

---

## 9. Resources

| Resource | Need | When |
|---|---|---|
| Compute | One GPU workstation or rented GPU for 8B inference over the campaign; 70B subset if budget | S2 onward; E |
| Datasets | RCAEval (Zenodo), AIOpsLab if feasible | S0.1 |
| Approvals | GGU IRB (D12); agreement with the guide on D5, D6 and the two-stage scope (call) | S0 |
| People | Two raters (H_fact sample); 24 participants if RQ4 runs | E |
| APIs | Judge models for FAE (optional) | E |

---

## 10. Risks

| Risk | Response |
|---|---|
| RCAEval licence or labels unsuitable | Decide in S0.1; fallback AIOpsLab recorded runs + OTel set, smaller corpus with power restated |
| Tier 1 slips | Cut Tier 2; then narrow exploratory streams; confirmatory streams and analysis are protected |
| Calibration leaks into confirmatory data | Partition manifest hashed in S0; adapters refuse confirmatory cases before phase E |
| Baselines fail to run on RE2 | Choose other suite methods; record substitutions before the freeze |
| IRB late | RQ4 moves after 31 March (D12) |
| Defect during phase E | Deviation entry; rerun or exclude with ledger entries |
| Stage B features are not in the confirmatory results | Confirmatory claims cover the frozen Stage A build; Stage B features are evaluated exploratorily after March under their own pre-registration |
| Stage B work disturbs the evidence build | Confirmatory runs execute only from the `build-freeze` commit; the VCL blocks any divergent artefact hash |

---

## 11. Stage B — completing the full product (15 Feb – end of Jul 2027)

Nothing from the full design is dropped: Stage B builds the rest of the product (Tier 3, plus any Tier 2 that missed the freeze) on `main` after the `build-freeze` tag, behind feature flags, to the same engineering gate. It starts alongside evidence collection and analysis (which are mostly compute and statistics) and becomes full time after 31 March. The full feature definitions (Ch3 page references, parameters) are in the first draft of this plan (git history, commit `c0fe406`) and in the R1 matrix.

| Sprint | Window | Work |
|---|---|---|
| B1 | 15 Feb – 31 Mar (alongside E and A) | Live OTLP ingest; P4 cognitive telemetry (MCP spans, goal drift, loop depth) and P5 business telemetry; Helm production deployment; multi-tenant administration |
| B2 | Apr | Full Privacy Gateway with per-tenant differential privacy; Adversarial Robustness Monitor with attestation; eBPF tiered adaptive sampling |
| B3 | May | Full digital twin with traffic mirroring; ASRE (structural, WAL-replay, sketch); versioned remediation templates; automatic-action adoption stage under α; Monitor Agent |
| B4 | Jun | Full Cognitive Sentinels + Deterministic Fallback Agent; full IOL; HIS tiers; learning loops (MAML-Quick, ACP retraining, bias audit) in production mode; 1,200-incident synthetic pre-training testbed |
| B5 | Jul | Stage B evaluation, exploratory and pre-registered separately: E-H1 (Tier-4 cognitive faults), full E-H4 (twin), E-H6 (IOL), E-H9 (HIS), H4b scaling sub-study, 70B Protocol A and Qwen contrast, FAE judging at scale. **Full product complete** |

Stage B results are exploratory additions; they never alter the confirmatory results produced from the frozen Stage A build.

---

## 12. Tracking

Each work package gets rows in `docs/tracking/helios_mvp_tracking.md` under new milestone sections (`S2-M5-…` onward, one per sprint; validator format `S{n}-M{m}-{TYPE}{nn}`), IN_PROGRESS before work and DONE with SHA + evidence after. The Milestone 4 rows still PLANNED (S1-M4-RES01/RES02/EVAL01/GATE01) close as superseded by S5.2, with a deviation reference.
