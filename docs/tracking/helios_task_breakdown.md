# HELIOS — Task Breakdown (every task as a module)

**Written:** 2026-10-23 · **Owner:** AA · **Companion to:** `helios_e2e_product_plan_2026-10.md` (schedule, principles, decisions) and `s0_3_d11_corpus_run_design.md` (corpus and runs).

**How to use.** Pick the next task whose dependencies are done. Open its tracking row (ID shown) as IN_PROGRESS in its own commit, do the steps, check every "Done when" item, run the full pre-push gate, then flip the row to DONE with the implementation SHA. "Deviation" says whether the change needs a `bin/log_deviation.py` entry before merging. Effort is in working days. **Sprints:** each sprint has a folder under `docs/sprints/` with its `plan.md` (sprint view of these modules) and, at its exit gate, an `exit_report.md` (criteria, gate, deliverables, retrospective, carry-overs; template in `docs/sprints/README.md`). Every exit gate also refreshes `dashboard.md` and `tracking_documents_register.md`. Chapter 3 is the baseline, not the final verdict: a better design is welcome — just record any change to what a pre-registered test measures before confirmatory data exists.

**Tracking milestone per sprint:** S0 = `S2-M5`, S1 = `S2-M6`, S2 = `S2-M7`, S3 = `S2-M8`, S4 = `S2-M9`, S5 = `S2-M10`, Evidence = `S2-M11`, Analysis = `S2-M12`, Stage B = `S3-M13` … `S3-M17`. Each task gets its own row (`{milestone}-{ENG|RES|EVAL|GATE}{nn}`).

**Tier key:** T1 = in the evidence build (confirmatory + core product). T2 = in the evidence build if ready by the freeze, otherwise Stage B. T3 = Stage B.

---

## Overview

| Sprint | Window | Tasks | Purpose |
|---|---|---|---|
| S0 Foundation | 2–13 Nov 2026 | S0.1–S0.11 | Protocol aligned to Ch3, OSF deposit 1 |
| S1 Data and graph | 16 Nov – 4 Dec | S1.1–S1.10 | Sealed datasets, typed incident graph, scoring path |
| S2 Reasoning | 7–25 Dec | S2.1–S2.9 | Pipelines, consensus, grounded narratives |
| S3 Routing | 4–15 Jan 2027 | S3.1–S3.5 | Cheap-first router, learning |
| S4 Product + evaluation tooling | 18–29 Jan | S4.1–S4.11 | API, console, baselines, metrics, analysis |
| S5 Integration + freeze | 1–12 Feb | S5.1–S5.7 | Verification, build freeze, OSF deposit 2 |
| E Evidence | 15 Feb – 12 Mar | E1–E6 | Confirmatory, baseline, exploratory runs |
| A Analysis | 15–31 Mar | A1–A6 | Results ready 31 March |
| Stage B | 15 Feb – end Jul | B1–B5 | Rest of the full product |

---

# Sprint S0 — Foundation (2–13 Nov 2026)

### S0.1 — Dataset check ✅ DONE
- **Tracking:** S2-M5-RES01 (DONE, `e854c0a`) · **Record:** `docs/tracking/s0_1_dataset_check.md`
- **Outcome:** RCAEval GO (239 full-modality cases); AIOpsLab spike planned for S1; findings F1–F5.

### S0.2 — Record protocol decisions in the deviation log
- **Goal:** Every decision D1–D12 and RB1–RB3 that changes the protocol has a signed deviation entry before code changes depend on it.
- **Tier:** T1 · **Tracking:** S2-M5-RES03 · **Effort:** ½ · **Depends on:** —
- **Steps:**
  1. List decisions with analytic consequence: D1 (Ch3 replaces May freeze), RB1 (recorded datasets), RB2/D3 (8B confirmatory), RB3 (two-stage scope, Stage B items), D4 (router initialisation), D8 (H4b in Stage B), D9 (learned ranker), D10 (diagnosis time for B-H6), D11 (corpus and runs).
  2. One `bin/log_deviation.py` entry per decision family, each with clause, change, reason, analytic consequence.
  3. Mirror the new rows into `docs/tracking/deviation_log.md`.
- **Done when:** `bin/verify_ledgers.py` passes; mirror rows match signature prefixes.
- **Deviation:** this task *is* the deviation entries.

### S0.3 — Corpus and run design (D11) ✅ APPROVED
- **Tracking:** S2-M5-RES02 (DONE, `d975842`) · **Record:** `docs/tracking/s0_3_d11_corpus_run_design.md` (lands on `main` with PR #40).

### S0.4 — Rename the feature-flag registry to Ch3 names (D2)
- **Goal:** One vocabulary in code, pre-registration and dissertation.
- **Tier:** T1 · **Tracking:** S2-M5-ENG01 · **Effort:** 2 · **Depends on:** S0.2
- **Steps:**
  1. In `helios/vcl/registry.py` and `helios/vcl/config.py` (`VCLManifest`): `mahc` → `mahc_hierarchical`; `cbr` + `router` → `cbr_routing` (value: routed / uniform); `acp` → `acp_stateful`; `reconcile` → `reconcile_terminal`; `ueg_c_structural` → `ueg_structural`.
  2. Add `fgsv_ks_gate`, `iol_self_telemetry`, `coe_narrative`, `his_tier`, `sampling_regime_tag`.
  3. Keep `dpipe`, `gpipe`, `ingest_mode` as documented implementation flags; decide whether `lpipe` and `dpipe_propagation` fold into Ch3 flags (record the choice).
  4. Update every `@gated_by` use, `helios/vcl/disjointness.py`, tests, and `VCLFlag.bool_flags()`.
- **Done when:** gate green; no old flag name left (`git grep`); disjointness audit lists every flag.
- **Files:** `helios/vcl/registry.py`, `config.py`, `decorators.py`, `disjointness.py`, all gated modules, tests.
- **Deviation:** yes (registry change; hashes change).

### S0.5 — Rebuild the 15 variants from Ch3 (Table 17, p.153)
- **Goal:** Variants that match the approved design.
- **Tier:** T1 · **Tracking:** S2-M5-ENG02 · **Effort:** 1 · **Depends on:** S0.4
- **Steps:**
  1. Confirmatory 8: Full, noLLM, **LLM-only** (replaces noGraph: D and G off), D, noConsensus (vote-only), noRouter (`cbr_routing=uniform`), G, noStructural.
  2. Exploratory 7: noCogni, noACP, noReconcile, HIS3, noFGSV, noIOL, noExpl.
  3. Remove noMAHC, noCBR, live, noLLM-noGraph (keep "live" only as a test fixture outside the registry if still needed).
  4. Keep variant helpers outside `variants.py` (it is hashed): use `helios/vcl/catalog.py`.
- **Done when:** 15 unique hashes (test); `test_all_variant_hashes_are_unique` extended to exploratory variants.
- **Files:** `helios/vcl/variants.py`, `catalog.py`, tests.
- **Deviation:** yes (with S0.4's entry or its own).

### S0.6 — Analysis plan for Families A, B and E
- **Goal:** `helios/research/analysis_plan.py` states the approved tests exactly.
- **Tier:** T1 · **Tracking:** S2-M5-ENG03 · **Effort:** 1½ · **Depends on:** S0.5
- **Steps:**
  1. Family A per Ch3 Table 18 (A-H1 noLLM HR@3; A-H2 LLM-only HR@3; A-H3 D; A-H4 noConsensus on the ambiguous stratum, confirmatory with asymmetric rule; A-H5 noRouter log-CpR at matched HR@3; A-H6 G on narrative-heavy incidents; A-H7 noLLM H_fact/H_struct sign test; A-H8 noStructural, asymmetric rule). Holm order unchanged.
  2. Family B: B-H1–B-H5 McNemar exact mid-p vs five baselines (names filled after S0.10); B-H6 time to correct diagnosis (D10); B-H7 log-CpR; B-H8 Avg@5.
  3. Family E: E-H1–E-H10 (E-H3 retired as duplicate of E-H8), BCa, no Holm.
  4. One-sided where directional; step-down Holm over the full family (never drop untestable hypotheses); asymmetric rule; three sanity floors (D11 §6); clustering sensitivity (D11 §5).
- **Done when:** a test asserts the table against the Ch3 extract in `r1_traceability_matrix.md`.
- **Deviation:** yes.

### S0.7 — Metric contract and docs clean-up
- **Goal:** Each metric has one definition everywhere.
- **Tier:** T1 · **Tracking:** S2-M5-RES04 · **Effort:** 1 · **Depends on:** —
- **Steps:**
  1. Write `docs/tracking/metric_contract.md`: HR@k at the fused output; Avg@5 (defined, D6 item 2); MRR (the old "CpR" reciprocal rank); CpR = five-component cost under the price book, log-transformed; time to correct diagnosis (D11 §7); H_fact / H_struct; TTT vs TTD; strata definitions (ambiguous, narrative-heavy, matched HR@3).
  2. Rename `PipelineVerdict.cpr` → `mrr` (schema version bump) and every caller; keep the old value's meaning.
  3. Fix drift listed in the matrix §9 (`docs/evaluation/cpr_definition.md`, `helios_project_summary.md`, `hypothesis_variant_metric_mapping.md`, `ablation_architecture.md`, `prompt_sha.json` note, passthrough name mismatch in `uniform_borda.py`, disjointness audit pointing at the D-pipe stub).
- **Done when:** `git grep -i "cpr"` shows only the cost meaning or explicit MRR history notes.
- **Deviation:** yes (schema bump).

### S0.8 — Seed register
- **Goal:** Binding seeds 10,000,000–10,009,999 (Ch3 p.108) with a deterministic mapping.
- **Tier:** T1 · **Tracking:** S2-M5-ENG04 · **Effort:** ½ · **Depends on:** —
- **Steps:** extend `helios/research/seeds.py`: register range; `seed_for(case_id, variant, purpose)`; seeds for opaque-ID generation, training, BCa; tests for stability.
- **Done when:** same inputs → same seed across runs and machines.
- **Deviation:** yes (replaces the single seed value).

### S0.9 — Ed25519 deviation-log signatures (D7) and audit step E
- **Goal:** Anyone can verify the deviation log with a public key; the pre-registration text is covered by the OSF signature.
- **Tier:** T1 · **Tracking:** S2-M5-ENG05 · **Effort:** 1½ · **Depends on:** —
- **Steps:**
  1. Generate an Ed25519 key pair; private key in `.env` (never committed), public key committed and later deposited.
  2. Add an Ed25519 signature over each new entry (keep the HMAC chain underneath); `verify_ledgers.py` checks both; older entries remain HMAC-only (documented).
  3. `bin/verify_osf_freeze.py`: include `preregistration.md` in `manifest_sig`; add seal hashes to `corpus_manifest.json`.
  4. Tests: tampered entry fails the public-key check; missing key handled.
- **Done when:** gate green; a verification command that needs only the public key.
- **Deviation:** yes.

### S0.10 — Pre-registration package, call with the guide, OSF deposit 1
- **Goal:** The approved protocol is publicly time-stamped.
- **Tier:** T1 · **Tracking:** S2-M5-GATE01 · **Effort:** 1½ (+ your call) · **Depends on:** S0.2–S0.9
- **Steps:**
  1. Regenerate `research/osf/` with `bin/verify_osf_freeze.py --generate`.
  2. Rewrite `research/osf/preregistration.md`: hypotheses, variants, metrics, D6 clarifications, D11 design, Stage B scope, deviation summary.
  3. **You:** call with the guide using the call-reference doc; fill its outcome table; confirm the five baselines (D5) and the CHASE value.
  4. Apply call outcomes; regenerate; full gate.
  5. **You:** upload to osf.io under your account.
  6. Record the DOI in the deviation log and `preregistration.md`.
- **Done when:** DOI recorded; `verify_osf_freeze.py --verify` passes; tag `osf-deposit-1`.
- **Deviation:** the DOI entry.

### S0.11 — Lead-time items (you)
- **Tracking:** S2-M5-RES05 · **Effort:** ongoing
- **Steps:** IRB application for RQ4 (D12) this week; GPU / API budget decision (70B sensitivity, judge models); baseline environments for the chosen RCAEval methods.
- **Register:** `docs/tracking/s0_11_lead_time_register.md` (items L1–L10 with needed-by dates, owner and status). Second rater and adjudicator added; baseline-environment spike done there.

### S0 exit gate
- **Tracking:** S2-M5-GATE02 · **Done when:** S0.2–S0.10 DONE, gate green, tag `rb-s0-exit`. ✅ Closed 2026-10-24: `docs/sprints/s0-foundation/exit_report.md`.

---

# Sprint S1 — Data and graph (16 Nov – 4 Dec)

### S1.1 — RCAEval adapter with sealing and leakage controls
- **Goal:** All RCAEval cases in the HELIOS recorded format, sealed, with no label leakage.
- **Tier:** T1 · **Tracking:** S2-M6-ENG01 · **Effort:** 3 · **Depends on:** S0.8
- **Steps:**
  1. Download from Hugging Face per case (pool: RE2-OB, RE2-TT, RE3-OB, RE3-TT; build data: RE1, RE2-SS, RE3-SS) into a data directory outside git, with checksums.
  2. Convert to `TelemetryWindow` + P1–P3 Parquet; assign **opaque incident IDs** from the seed register; write the ground-truth file (real case names only there).
  3. Per-system service-name normalisation table (F4); services seen only in metrics/logs kept (F5).
  4. Seal every case (`helios/telemetry/seal.py`); build the pool manifest with seal hashes; adapter refuses pool cases before the `build-freeze` tag.
  5. Leakage test: no case name, root-cause service or fault string in any pipeline input, snapshot, prompt or stored text.
- **Done when:** 240 pool + 495 build cases sealed; leakage test passes; pool manifest hash recorded.
- **Files:** new `helios/adapters/rcaeval.py`, `helios/adapters/names.py`, tests.
- **Deviation:** no (implements D11).

### S1.2 — New OTel Demo captures (~60 incidents)
- **Goal:** Enough trace-bearing build data to train and calibrate.
- **Tier:** T1 · **Tracking:** S2-M6-RES01 · **Effort:** 2 · **Depends on:** —
- **Steps:** run the existing capture tooling across the five fault types and several services; seal each; label; keep strictly as build data.
- **Done when:** ~80 OTel incidents sealed (20 old + new), all verify.

### S1.3 — AIOpsLab recording spike (2 days)
- **Goal:** Decide whether AIOpsLab joins the Stage A pool.
- **Tier:** T2 · **Tracking:** S2-M6-RES02 · **Effort:** 2 · **Depends on:** —
- **Steps:** install `kind` and `helm`; deploy one app; inject one problem; export and convert telemetry to the sealed format.
- **Done when:** go → addendum to D11 before the freeze; no-go → Stage B, recorded.

### S1.4 — Log templates
- **Tier:** T1 · **Tracking:** S2-M6-ENG02 · **Effort:** 1 · **Depends on:** S1.1
- **Steps:** Drain3 template extraction over P3 logs; template counts and novelty per service per window as features.
- **Done when:** templates stable across reruns; tests.

### S1.5 — Typed incident graph (UEG-C)
- **Goal:** Four edge kinds with composition rules (C2).
- **Tier:** T1 · **Tracking:** S2-M6-ENG03 · **Effort:** 3 · **Depends on:** S1.1, S1.4
- **Steps:**
  1. `helios/schemas/ueg_c.py`: structural, behavioural, causal, economic edge kinds; Agent-Reasoning-Step and Transaction/KPI node types (schema bump).
  2. `helios/graph/ueg_c_builder.py`: build all four from traces, metrics, logs; composition rules for cross-domain paths; nodes for metric/log-only services.
- **Done when:** cross-domain path test; snapshot hash stable; partial-trace test.
- **Deviation:** yes (schema bump).

### S1.6 — Structural bundle (`ueg_structural`)
- **Tier:** T1 · **Tracking:** S2-M6-ENG04 · **Effort:** 1 · **Depends on:** S1.5
- **Steps:** OFF = one untyped edge kind, full-graph training, ARS nodes as flat text; gated function.
- **Done when:** noStructural changes the snapshot hash on a structural fixture.

### S1.7 — K-hop pruner (Algorithm 5)
- **Tier:** T1 · **Tracking:** S2-M6-ENG05 · **Effort:** 1 · **Depends on:** S1.5
- **Steps:** K-hop over structural + behavioural edges; top-n by PPR; drop causal/behavioural edges below r = 0.7; 10,000-edge budget; hash output; calibrate K and top-n on build data.
- **Done when:** 50–200 nodes on build incidents; calibration logged.
- **Deviation:** yes (K, top-n values).

### S1.8 — Verdict contract
- **Tier:** T1 · **Tracking:** S2-M6-ENG06 · **Effort:** 1 · **Depends on:** S0.7
- **Steps:** `PipelineVerdict` carries ranked list, μ, σ, cost, latency (schema bump); all pipelines emit it.
- **Done when:** round-trip and stability tests updated.
- **Deviation:** yes (schema bump).

### S1.9 — Scoring path
- **Goal:** Scores computed after dispatch, never fed to a pipeline.
- **Tier:** T1 · **Tracking:** S2-M6-ENG07 · **Effort:** 1 · **Depends on:** S1.8
- **Steps:** `helios/evaluation/scoring.py` (the existing `helios/evaluation` package, not a new `helios/eval`): HR@1/3/10, Avg@5, MRR from per-pipeline and fused lists joined to ground truth; stored in a separate `eval_score` table; test that `run_dpipe` and others never receive ground truth.
- **Done when:** fixture scores match hand-computed values.

### S1.10 — Price book, token accounting, cost
- **Tier:** T1 · **Tracking:** S2-M6-ENG08 · **Effort:** 1 · **Depends on:** S1.8
- **Steps:** LLM gateway counts tokens per episode; `docs/tracking/price_book.md` coefficients (local GPU seconds, storage, human-minute, opportunity) with sources; `helios/evaluation/cost.py` five-component CpR.
- **Done when:** hand-computed cost matches on a fixture.
- **Deviation:** yes (price book values).

### S1 exit gate
- **Tracking:** S2-M6-GATE01 · tag `rb-s1-exit`; exit report `docs/sprints/` (S1 folder) and documentation sync.

---

# Sprint S2 — Reasoning, consensus, narratives (7–25 Dec)

### S2.1 — D-pipe completion
- **Tier:** T1 · **Tracking:** S2-M7-ENG01 · **Effort:** 1 · **Depends on:** S1.8
- **Steps:** σ estimate from score spread; deterministic settings; anomaly trigger for the graph neighbourhood.
  - **Detection trigger — owner decision (a), 2026-10-26 (S2-M6-RES04):** one frozen, label-free detector, tuned on build data only, gives every system — HELIOS and the five baselines — the same trigger time; no pipeline or baseline receives the true injection time (metric contract). The detector's parameters are frozen with a deviation entry before build-freeze. Its seeds feed the K-hop pruner (S1.7, `khop_prune(seeds=...)`); time to correct diagnosis (B-H6) is measured from this trigger.
  - An exploratory run gives every system the true injection time, to bridge to published RCAEval scores; it is reported separately and never enters a confirmatory test.
- **Done when:** bitwise rerun equality; trigger time identical for HELIOS and the baselines on a fixture.

### S2.2 — G-pipe learned ranker (D9)
- **Goal:** "Graph machine-learning reasoning", trained, deterministic, service-agnostic.
- **Tier:** T1 · **Tracking:** S2-M7-ENG02 · **Effort:** 3 · **Depends on:** S1.5, S1.7, S1.2
- **Steps:**
  1. Features per service: PPR score (rounded with the `canonical_json` rule), graph centrality, anomaly scores, error and latency shifts, log-template novelty — **no service identifiers** (F3).
  2. Learning-to-rank model trained on build data only, with a registered seed; parameters hashed into the manifest.
  3. Feature-audit test: training fails if a service-identity feature is present.
- **Done when:** rerun equality; build-data HR@3 reported (exploratory).
- **Deviation:** yes (model and parameters).

### S2.3 — Lean multi-agent L-pipe
- **Tier:** T1 · **Tracking:** S2-M7-ENG03 · **Effort:** 3 · **Depends on:** S1.8
- **Steps:** orchestrator + metric, trace and log workers + narrator; each emits (μ, σ); simple Persona Profiles (tool permissions); prompts registered with SHA; only opaque IDs in prompts.
- **Done when:** worker verdicts logged; leakage test still passes; prompt SHAs frozen in the registry.
- **Deviation:** yes (prompts, model version).

### S2.4 — H_struct records
- **Tier:** T1 · **Tracking:** S2-M7-ENG04 · **Effort:** ½ · **Depends on:** S2.3
- **Steps:** record schema-validation results of every agent tool call/output.
- **Done when:** counts stored per run.

### S2.5 — MAHC with calibrated confidence (IN2)
- **Tier:** T1 · **Tracking:** S2-M7-ENG05 · **Effort:** 2½ · **Depends on:** S2.1–S2.3
- **Steps:** hierarchical priors with back-off; σ weighting; weighted Borda; entropy floor λ; PROVISIONAL / CONFIRMED with 30 s / 90 s timing; calibrated confidence for the ranked set, calibrated on build data.
- **Done when:** the σ counterexample (Ch3 p.157) gives different fused rankings; calibration curve reported.
- **Deviation:** yes (λ, calibration method).

### S2.6 — Vote-only aggregator
- **Tier:** T1 · **Tracking:** S2-M7-ENG06 · **Effort:** ½ · **Depends on:** S2.5
- **Steps:** `mahc_hierarchical=OFF` → uniform vote over pipelines that returned a list; same output shape and location.
- **Done when:** noConsensus differs from Full on a fixture.

### S2.7 — Chain-of-Evidence ledger
- **Tier:** T1 · **Tracking:** S2-M7-ENG07 · **Effort:** 1 · **Depends on:** S2.5
- **Steps:** signed, append-only decision trail per incident (routing, fallbacks, verdict states, evidence references), using the anchored ledger mechanism.
- **Done when:** ledger verifies; tamper test.

### S2.8 — Narrative Engine with grounding verifier (IN1)
- **Tier:** T1 · **Tracking:** S2-M7-ENG08 · **Effort:** 2½ · **Depends on:** S2.7
- **Steps:** narrator writes claims that cite graph node/edge IDs; deterministic claim parser; verifier drops claims whose cited element does not exist or does not support the claim; rejections logged; `coe_narrative=OFF` shows the ranked list only.
- **Done when:** every displayed claim cites an element (test); rejection rate reported.

### S2.9 — Rating rubric and blind labelling protocol (H_fact)
- **Goal:** Two raters can label every Full and noLLM narrative blind to variant, against a frozen rubric, before any confirmatory narrative exists.
- **Tier:** T1 · **Tracking:** S2-M7-RES01 · **Effort:** 1½ (+ owner and rater training time) · **Depends on:** S2.8, S0.11 (L2, L3)
- **Steps:**
  1. Rubric: what counts as one atomic claim; "supported" (the cited element exists and supports it; root-cause claims also agree with the ground truth); worked examples from build data.
  2. Labelling tool: shows each narrative as claims plus the evidence each cites, in one neutral format for all variants (the deterministic noLLM narrative must not be recognisable by style); presentation order shuffled with a seed from a new register block (needs a deviation entry); rater labels stored per claim; κ computed by S4.9.
  3. Training set: 50 narratives from build data. Both raters label; compute κ; discuss disagreements; revise the rubric; repeat until κ ≥ 0.7.
  4. Freeze the rubric (hash) and add it to OSF deposit 2 (S5.7) before confirmatory labelling.
- **Done when:** κ ≥ 0.7 on the training set; rubric hash recorded; tool tested on fixtures.
- **Deviation:** the presentation-order seed block; any rubric decision that changes what H_fact measures.

### S2 exit gate
- **Tracking:** S2-M7-GATE01 · tag `rb-s2-exit`; exit report `docs/sprints/` (S2 folder) and documentation sync.

---

# Sprint S3 — Routing and learning (4–15 Jan 2027)

### S3.1 — Router with cheap-first gate (IN3)
- **Tier:** T1 · **Tracking:** S2-M8-ENG01 · **Effort:** 3 · **Depends on:** S2.5, S1.10
- **Steps:** LinUCB over arms {D, G, L, D+G, D+L, G+L, Full}; statistical + graph first, LLM only on disagreement or low confidence; constraint-empty fallback to Full (covariate); initialised on build data, frozen, hashed; `cbr_routing=uniform` for noRouter.
- **Done when:** routed arm recorded per run; VCL verifies frozen parameters at start.
- **Deviation:** yes (initialisation, thresholds).

### S3.2 — Action-Class Predictor
- **Tier:** T2 · **Tracking:** S2-M8-ENG02 · **Effort:** 2 · **Depends on:** S1.5
- **Steps:** Algorithm 2 features; softmax over schema / data / config change + blast-radius tier; trained on build data; `acp_stateful=OFF` → uniform prior.
- **Done when:** gated; parameters hashed.

### S3.3 — Two-stage reward and delayed labels
- **Tier:** T2 · **Tracking:** S2-M8-ENG03 · **Effort:** 2 · **Depends on:** S3.1
- **Steps:** provisional reward + terminal update; injected delays on build cases; RRE; reconciliation ledger records.
- **Done when:** provisional/terminal pairs verify; `reconcile_terminal=OFF` writes none.

### S3.4 — Knowledge Cortex
- **Tier:** T2 · **Tracking:** S2-M8-ENG04 · **Effort:** 1½ · **Depends on:** S2.3
- **Steps:** SOP retrieval index built from build data only (hash check excludes pool cases).
- **Done when:** retrieval tests; pool-exclusion test.

### S3.5 — LLM-unavailable fallback
- **Tier:** T2 · **Tracking:** S2-M8-ENG05 · **Effort:** ½ · **Depends on:** S3.1
- **Steps:** route to D+G when the LLM fails; covariate recorded.

### S3 exit gate
- **Tracking:** S2-M8-GATE01 · tag `rb-s3-exit`; exit report `docs/sprints/` (S3 folder) and documentation sync.

---

# Sprint S4 — Product shell and evaluation tooling (18–29 Jan)

### S4.1 — API
- **Tier:** T1 · **Tracking:** S2-M9-ENG01 · **Effort:** 1½ · **Depends on:** S2.7
- **Steps:** incidents, verdicts, CoE, HITL decisions, health; API keys; OpenAPI spec; contract tests.

### S4.2 — Approval console (RQ4 instrument)
- **Tier:** T1 · **Tracking:** S2-M9-ENG02 · **Effort:** 2 · **Depends on:** S4.1, S2.8
- **Steps:** ranked set with confidence; grounded narrative with evidence links (toggle for noExpl); accept / escalate / reject with decision timing; simulated-HITL mode for runs.
- **Done when:** walk-through; timing capture verified.

### S4.3 — Compose deployment
- **Tier:** T1 · **Tracking:** S2-M9-ENG03 · **Effort:** ½ · **Depends on:** S4.1
- **Steps:** docker-compose for API, console, store, model server; images pinned by digest.
- **Done when:** fresh install works from the compose file alone.

### S4.4 — PII redaction (T2) · S4.5 — Shadow / recommendation modes (T2) · S4.6 — FGSV lite (T2) · S4.7 — IOL lite (T2)
- **Tracking:** S2-M9-ENG04 … ENG07 · **Effort:** ½ each (FGSV lite 1)
- **Steps:** pattern-based redaction before any LLM call; modes that never write to production; KS gate + replay on recorded data with PASS / FAIL / STALE; HELIOS self-telemetry into the graph under `tenant=self` (basic).
- **Done when:** each behind its flag with tests, or recorded as moved to Stage B.

### S4.8 — Baselines from the RCAEval suite (D5)
- **Tier:** T1 · **Tracking:** S2-M9-ENG08 · **Effort:** 2 · **Depends on:** S1.1, S0.10
- **Steps:** run the five agreed methods in an isolated environment on the same cases; common output format; CHASE as the published-score anchor (agreed value).
- **Done when:** each baseline produces ranked lists on build data; licences recorded.

### S4.9 — Metrics suite
- **Tier:** T1 · **Tracking:** S2-M9-ENG09 · **Effort:** 1½ · **Depends on:** S1.9, S2.4, S2.8
- **Steps:** HR@k, Avg@5, MRR, CpR, time to correct diagnosis, TTT, H_struct, H_fact (verifier output + κ over the two raters' labels from the S2.9 tool), non-convergence count.
- **Done when:** fixture values match hand computation.

### S4.10 — Run orchestrator and integrity
- **Tier:** T1 · **Tracking:** S2-M9-ENG10 · **Effort:** 1½ · **Depends on:** S4.9
- **Steps:** schedule for 1,920 + 1,200 runs + exploratory; cell bookkeeping (variant × system × metric, ≥ 80% rule); integrity gate; exclusion ledger; MCAR test and IPW.
- **Done when:** dry run of the full schedule on fixtures.

### S4.11 — Analysis suite
- **Tier:** T1 · **Tracking:** S2-M9-ENG11 · **Effort:** 2 · **Depends on:** S0.6
- **Steps:** Wilcoxon, sign test, McNemar exact mid-p, step-down Holm per family, asymmetric rule, BCa (10,000 resamples, registered seeds), Cliff's δ, Hodges–Lehmann, group-level Wilcoxon, rank-based mixed model, ICC, three sanity floors; refuses to label exploratory data confirmatory.
- **Done when:** fixture data reproduces hand-computed statistics.

### S4 exit gate
- **Tracking:** S2-M9-GATE01 · tag `rb-s4-exit`; exit report `docs/sprints/` (S4 folder) and documentation sync.

---

# Sprint S5 — Integration and freeze (1–12 Feb)

### S5.1 — System test of every variant
- **Tracking:** S2-M10-EVAL01 · **Effort:** 2 · **Done when:** 15 variants run end to end on build data.

### S5.2 — Disjointness certification
- **Tracking:** S2-M10-EVAL02 · **Effort:** 1 · **Done when:** every boolean flag gates exactly one code path; zero uncovered.

### S5.3 — Exploratory pilot on build data
- **Tracking:** S2-M10-EVAL03 · **Effort:** 2 · **Done when:** pilot report labelled exploratory; metrics, cost and timing all populated.

### S5.4 — Clean-environment replication
- **Tracking:** S2-M10-EVAL04 · **Effort:** 1 · **Done when:** snapshot hashes and fused rankings reproduce on a fresh checkout.

### S5.5 — LLM determinism probe
- **Tracking:** S2-M10-EVAL05 · **Effort:** ½ · **Done when:** token-equality rate measured on repeated prompts.

### S5.6 — Build freeze
- **Tracking:** S2-M10-GATE01 · **Effort:** 1
- **Steps:** freeze commit SHA, image and model digests, ranker/router/ACP parameter hashes, price book, pool manifest; Tier-2 items not ready recorded as moved to Stage B.
- **Done when:** tag `build-freeze`; VCL blocks any divergence.

### S5.7 — OSF deposit 2 (freeze addendum)
- **Tracking:** S2-M10-GATE02 · **Effort:** ½ (+ your upload)
- **Steps:** addendum with the freeze record (S5.6) and the frozen rating rubric (S2.9).
- **Done when:** DOI in the deviation log. **Stage A build complete.**
- **Exit report:** `docs/sprints/s5-integration-freeze/exit_report.md` and documentation sync.

---

# Phase E — Evidence collection (15 Feb – 12 Mar)

No code changes; defects → deviation entry, rerun or exclude with ledger entries. Plan and exit report: `docs/sprints/e-evidence/`.

| Task | Tracking | Work | Done when |
|---|---|---|---|
| E1 Confirmatory ablation | S2-M11-EVAL01 | 8 variants × 240 pool cases from the frozen build | Every cell complete or excluded with reasons |
| E2 Baselines | S2-M11-EVAL02 | 5 baselines × 240 cases | Paired tables complete |
| E3 Exploratory | S2-M11-EVAL03 | Built Tier-2 variants × 240 | Results labelled exploratory |
| E4 RQ4 user study | S2-M11-RES01 | If IRB approved: 24 participants, Full vs noExpl, Latin square | Dataset stored; IRB number logged |
| E5 Rating | S2-M11-RES02 | H_fact: two raters label every Full and noLLM narrative (480 each; κ ≥ 0.7; adjudicator below); judges if budget | Agreement reported |
| E6 Sensitivity | S2-M11-EVAL04 | 70B subset if budget; 10% rerun replication | Reported |

---

# Phase A — Analysis (15–31 Mar)

| Task | Tracking | Work |
|---|---|---|
| A1 Family A | S2-M12-EVAL01 | Wilcoxon / sign test, Holm, asymmetric rule, against floors |
| A2 Family B | S2-M12-EVAL02 | McNemar mid-p, Wilcoxon, separate Holm |
| A3 Sensitivity | S2-M12-EVAL03 | Group-level, rank mixed model, ICC, BH, MCAR/IPW |
| A4 Exploratory | S2-M12-EVAL04 | BCa estimates, clearly separated |
| A5 C1 + innovation evidence | S2-M12-EVAL05 | Verification rates; grounding rejection rate; confidence calibration; cheap-first savings |
| A6 Results package | S2-M12-GATE01 | Tables, figures, deviation summary, replication bundle — **results ready 31 March** |

Plan and exit report: `docs/sprints/a-analysis/`.

---

# Stage B — Completing the full product (15 Feb – end of Jul 2027)

Built on `main` after the `build-freeze` tag, behind feature flags (`VCLFlag`), to the same gate; never touches the frozen evidence build. Full feature definitions: first draft of the e2e plan (commit `c0fe406`) and the R1 matrix.

| Module | Tracking | Window | Contents |
|---|---|---|---|
| B1 Ingest and deployment | S3-M13 | 15 Feb – 31 Mar | Live OTLP ingest; P4 cognitive telemetry (MCP spans, goal drift, loop depth); P5 business telemetry; Helm production deployment; multi-tenant administration |
| B2 Privacy and robustness | S3-M14 | Apr | Full Privacy Gateway with per-tenant differential privacy; Adversarial Robustness Monitor with attestation; eBPF tiered adaptive sampling |
| B3 Safe action | S3-M15 | May | Full digital twin with traffic mirroring; ASRE (structural, WAL-replay, sketch); remediation templates; automatic-action stage under α; Monitor Agent; **live MTTR measurement (D10)** |
| B4 Self-healing and learning | S3-M16 | Jun | Full Cognitive Sentinels + Deterministic Fallback Agent; full IOL; HIS tiers; learning loops in production mode; 1,200-incident synthetic pre-training testbed |
| B5 Stage B evaluation | S3-M17 | Jul | E-H1 (Tier-4 cognitive faults), full E-H4, E-H6, E-H9, H4b scaling, 70B and Qwen contrast, FAE at scale — each pre-registered separately. **Full product complete** |

Each Stage B module is broken into tasks with the same template (goal, steps, done when, tracking) when its sprint starts. Plans and exit reports: `docs/sprints/stage-b/` and one folder per module.
