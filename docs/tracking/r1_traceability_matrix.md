# R1 Traceability Matrix — Approved Chapter 3 vs Frozen Code Protocol

**Status:** DRAFT FOR REVIEW. Nothing in code, `research/osf/`, `variants.py` or the ledgers has been changed by this document.
**Prepared:** 2026-10-22, against `main` @ `b25c287` (after integrity-audit steps A–D).
**Owner:** AA.

**How to use this matrix (owner direction, 2026-10-23):** Chapter 3 is the baseline, not the final verdict. "ALIGN" here means "the default unless a better, more production-grade or more innovative method is chosen". Departing from Ch3 is allowed and encouraged where it improves the product; what is required is that any change to a pre-registered test is recorded before confirmatory data is collected.

**Sources**

| Tag | Source |
|---|---|
| **Ch3** | `docs/research/Complete_Report.pdf`, chair-approved 2026-09-23 (DDDR response 2026-10-04). Citations are *printed page numbers* (p.NNN). The prose cites tables by older numbers ("Table 3" = printed Table 18; "Table 2" = printed Table 17) and sections shifted by one (e.g. "§3.6.7" = printed §3.7.7). |
| **Ch1** | Same PDF, Chapter 1 (p.21). |
| **Code** | `helios/research/analysis_plan.py`, `helios/vcl/variants.py`, `helios/vcl/registry.py`, pipelines, `scripts/analyse_results.py`. |
| **OSF** | `research/osf/*.json`, `research/osf/preregistration.md` (frozen 2026-05-19 at Milestone 3; **not deposited**, DOI placeholder). |

**How to read the Resolution columns**

| Code | Meaning |
|---|---|
| **ALIGN** | Change code / OSF artefacts to match Ch3. One deviation entry per change family (the May freeze is not deposited, so this is an internal correction, not a public protocol deviation). |
| **CLARIFY** | Ch3 is ambiguous or internally inconsistent. Fix the operational definition in the OSF pre-registration before deposit, without changing any hypothesis direction, variable or test. Log a deviation entry and note it for the chair. |
| **FEASIBILITY** | Ch3 requires something not available. Either build it or contract scope with a deviation entry whose analytic consequence is explicit. Needs a decision (§12). |
| **KEEP** | Code already matches Ch3. |

---

## 1. Summary

1. **Holm ranks match; hypothesis content does not.** Rank 1–8 in code are A-H3, A-H7, A-H1, A-H2, A-H6, A-H5, A-H4, A-H8 — the Ch3 order exactly. But 4 of 8 Family A hypotheses have the wrong comparison and/or metric in code (A-H1, A-H2, A-H5, A-H7), and 2 have the wrong status (A-H4, A-H8).
2. **CpR means Cost per Resolution everywhere in Ch3** (19 occurrences, one meaning). In the repo it means four different things, and the only computed "CpR" is reciprocal rank in D-pipe. No cost is computed anywhere.
3. **The flag registry is not the Ch3 registry.** Ch3 names twelve flags (`l2c_llm, p4_cognitive, mahc_hierarchical, cbr_routing, l2b_graph, acp_stateful, reconcile_terminal, fgsv_ks_gate, iol_self_telemetry, coe_narrative, his_tier, sampling_regime_tag`) plus `ueg_structural`. The code has `cbr` read as *case-based reasoning* and a separate `router`; in Ch3 **CBR is cost-based routing (ORAR)** and `cbr_routing=uniform` *is* HELIOS-noRouter (p.142). Ch3's `fgsv`, `iol`, `coe_narrative`, `his_tier` have no flag in code.
4. **Six code flags gate nothing** (`lpipe, cbr, p4_cognitive, router, acp, reconcile`); ORAR, ACP, MAHC (proper), cognitive nodes, FGSV, IOL are not implemented. Comparing Full vs noRouter, noP4, noCBR, noACP or noReconcile today compares identical pipelines under different hashes.
5. **The approved Ch3 itself has internal inconsistencies** that must be settled in the OSF pre-registration (§10): CHASE adjustment arithmetic, undefined Avg@5, A-H7's status, E-H3 = E-H8, corpus arithmetic, H4b bounds.
6. **Eight decisions are yours (or the chair's) to make before any code changes** — §12.

---

## 2. Family A — ablation, confirmatory (Holm family 1)

Ch3 refs: Table 18 p.169–180; Holm order p.192; power Table 22 p.198–200.

| ID | Holm | Ch3: comparison · metric · test · status · expected effect | Code / OSF today | Gap | Resolution |
|---|---|---|---|---|---|
| **A-H1** | 3 | Full vs **HELIOS-noLLM** · HR@3 · Wilcoxon · Confirmatory · ΔHR@3 ≥ 0.10 (p.169) | Full vs "baseline (fixed threshold)" · HR@3; `analyse_results.py` skips it (no "baseline" rows) | Wrong comparison; untestable as coded | **ALIGN** comparison to noLLM. The fixed-threshold comparison is not a Ch3 hypothesis — keep only as a descriptive baseline, if at all |
| **A-H2** | 4 | Full vs **HELIOS-LLM-only** · **HR@3** · Wilcoxon · Confirmatory · ΔHR@3 ≥ 0.10 (p.170) | Full vs **HELIOS-noGraph** · **CpR** | Wrong variant and wrong metric | **ALIGN**: variant LLM-only (§5), metric HR@3 |
| **A-H3** | 1 | Full vs HELIOS-D · HR@3 · Wilcoxon · Confirmatory · ΔHR@3 ≥ 0.15 (p.171) | Same | HR@3 is never computed on the official run path (no ground truth passed; analysis recomputes from consensus rows) | **KEEP** hypothesis; scoring path fixed in R2 |
| **A-H4** | 7 | Full vs HELIOS-noConsensus (**vote-only** aggregation) · HR@3 **on ambiguous-incident stratum** · Wilcoxon · **Confirmatory (underpowered, disclosed; asymmetric rule)** · ΔHR@3 ≥ 0.05 (p.177, p.192, p.195) | Same pair · HR@3 (all incidents) · **exploratory** | Status; stratum missing; "MAHC" in code is uniform Borda, and `mahc=false` falls to a passthrough that takes the D-pipe list (not vote-only) | **ALIGN** status → confirmatory + asymmetric rule. **CLARIFY** "ambiguous stratum" definition. MAHC proper + vote-only Borda in R2 |
| **A-H5** | 6 | Full vs HELIOS-noRouter (`cbr_routing=uniform`) · **CpR at matched HR@3** · Wilcoxon · Confirmatory · Δlog-CpR ≥ 0.60 (p.172) | Same pair · **HR@3** · confirmatory in plan, **exploratory** in variant map / `variant_hashes.json` | Wrong metric; status conflict inside the freeze; no router exists | **ALIGN** metric to log-CpR (cost); status confirmatory. **CLARIFY** "matched HR@3". ORAR in R2 |
| **A-H6** | 5 | Full vs **HELIOS-G** · HR@3 **on narrative-heavy incidents** · Wilcoxon · Confirmatory · ΔHR@3 ≥ 0.12 (p.178) | **HELIOS-G vs HELIOS-D** (gate-conditional, filter `narrative != 'gpipe-gated-or-skipped'`) · "cond. confirmatory" | Wrong comparison (G vs D instead of Full vs G); stratum missing; added gate filter not in Ch3 | **ALIGN** to Full vs G. **CLARIFY** "narrative-heavy" definition. The gate filter becomes descriptive (it was a May design choice, deviation 14) |
| **A-H7** | 2 | noLLM: **H_fact and H_struct at or near zero vs > 0 under Full** · **sign test** · Confirmatory (p.179, p.200) | Full vs noLLM · **HR@3** | Wrong metric and test; no hallucination measurement exists | **ALIGN** metric/test. Measurement (rubrics, two raters, κ ≥ 0.7) is R2/R4 work. **CLARIFY** Ch3 p.116 calls hallucination "descriptive … will not enter the confirmatory set" — contradicts A-H7 (§10) |
| **A-H8** | 8 | Full vs HELIOS-noStructural (untyped edges + no subgraph-aware training + ARS nodes demoted) · HR@3 · Wilcoxon · **Confirmatory (underpowered, disclosed)** · ΔHR@3 ≥ 0.08 (p.180, p.152) | Same pair · HR@3 · **exploratory**; flag only drops structural edges | Status; bundle is narrower than Ch3 | **ALIGN** status; full bundle in R2. Within-bundle attribution stays E-H10 |

**Family-level items**

| Item | Ch3 | Code / OSF | Resolution |
|---|---|---|---|
| α | Rank-1 α 0.00625 per family; Holm step-down (p.192) | Fixed per-rank α `0.05/(9−rank)` in plan; `analyse_results.py` uses statsmodels step-down and drops NaN hypotheses (family shrinks) | **ALIGN**: one Holm implementation over all 8, untestable hypotheses counted as non-rejected, never dropped |
| Sidedness | One-sided where direction pre-registered (p.192) | OSF one-sided; `analyse_results.py` two-sided (deviation 21, exploratory only) | **ALIGN** confirmatory analysis one-sided |
| Binding test | Wilcoxon (A-H7 sign test); paired-t sensitivity only (p.201) | Wilcoxon only | **ALIGN** |
| Asymmetric rule (A-H4, A-H8) | Non-rejection reported as "inconclusive at delivered power", locked at freeze (p.191, p.219) | Absent | **ALIGN** into analysis plan + report text |
| Effect reporting | BCa (10,000 resamples, pre-registered seed sequence), Cliff's δ, Hodges–Lehmann (p.202) | Rank-biserial r only | **ALIGN** in R2 analysis command |

---

## 3. Family B — baseline comparison, confirmatory (separate Holm family)

Ch3 refs: Table 18 p.173–175; Holm order p.192; Panel D p.200–201; CHASE adjustment Table 20 p.196–197.

| ID | Ch3 | Code / OSF today | Resolution |
|---|---|---|---|
| **B-H1–B-H5** | Full vs **five priority-ranked baselines**, one each · paired binary HR@3 · **McNemar exact mid-p, one-sided** · ordered by expected discordance | B-H1 CHASE HR@3, B-H2 RCACopilot HR@3, B-H3 CHASE CpR, B-H4 RCACopilot CpR, B-H5 CHASE log-MTTR · all "deferred" | **ALIGN** structure. **FEASIBILITY/DECISION D5**: Ch3 never names the five baselines (§10.4) |
| **B-H6** | Full vs best baseline · log-MTTR · Wilcoxon (paired t sensitivity) · δ = 0.60 | CHASE · hallucination rate | **ALIGN** |
| **B-H7** | Full vs best baseline · **log-Cost (CpR)** · Wilcoxon · δ = 0.80 · Holm position right after B-H1–B-H5 | CHASE · "CoE score" | **ALIGN** |
| **B-H8** | Full vs best baseline · **Avg@5** · Wilcoxon · ΔAvg@5 ≥ 0.10 | CHASE · macro-F1 | **ALIGN** metric; **CLARIFY** Avg@5 (never defined in Ch3, §10.2) |
| CHASE adjustment | Published 0.72 → AIOpsLab-equivalent **0.60**, ±25% sensitivity (p.194–197) | Baseline 0.60 hard-coded in `analysis_plan.json` | **CLARIFY** arithmetic (§10.1) |
| RCACopilot | No baseline role or adjustment in Ch3 (Ch1–2 prose only) | Baseline for B-H2, B-H4 | Drop unless chosen under D5 |

---

## 4. Family E — exploratory (BCa, no Holm)

| ID | Ch3 variant · metric | Code | Resolution |
|---|---|---|---|
| E-H1 | HELIOS-noCogni · HR@3 on Tier 4 (n = 12) | HELIOS-noP4 exists; `p4_cognitive` gates nothing; no ARS node | Rename variant; implement in R2 |
| E-H2 | HELIOS-noRouter · TTT | No TTT measurement | R2 (TTT = detection → MAHC PROVISIONAL publication) |
| E-H3 / E-H8 | Both HELIOS-noACP · latency-constraint satisfaction (identical text) | noACP exists; `acp` gates nothing | **CLARIFY** (§10.5); implement ACP in R2 |
| E-H4 | HELIOS-noFGSV · false-accept rate under fidelity-break perturbation | No flag, no FGSV | Needs `fgsv_ks_gate` flag (D2) |
| E-H5 | HELIOS-noReconcile · RRE on 25% delayed-label subset | noReconcile exists; `reconcile` gates nothing | R2 |
| E-H6 | HELIOS-noIOL · detection latency under injected degradation | No flag, no IOL | Needs `iol_self_telemetry` flag (D2) |
| E-H7 | HELIOS-noExpl vs Full · interpretation, time-to-decision, trust (RQ4, n = 24, within-subjects) | No flag, no narrative toggle | Needs `coe_narrative` flag (D2); IRB |
| E-H9 | HELIOS-HIS3 · Δ-latency per HIS tier | No flag | Needs `his_tier` flag (D2) |
| E-H10 | noStructural sub-mechanism attribution (descriptive) | — | R2/R5 analysis |

---

## 5. Variants and flags

### 5.1 Confirmatory variants

| Ch3 variant (Table 17, p.149–152) | Code variant | Match? | Resolution |
|---|---|---|---|
| HELIOS-Full | HELIOS-Full | Yes (names) | Re-derive flags from Ch3 registry |
| HELIOS-noLLM (A-H1, A-H7) | HELIOS-noLLM | Yes | Ch3 has two noLLM rows differing only in the CBR cell ("ON {D, G}" vs "ON") — **CLARIFY** (§10.6) |
| **HELIOS-LLM-only** (A-H2): L2C ON, L2B OFF, ACP OFF, MAHC/CBR/Reconcile passthru | **HELIOS-noGraph**: L2B off, G-pipe off, **D-pipe on** | **No** | **ALIGN**: replace noGraph with LLM-only (D and G off) |
| HELIOS-D (A-H3) | HELIOS-D | Yes | Note: in code D-pipe propagation never runs for D (needs a UEG-C, which `l2b_graph=false` prevents) |
| HELIOS-noConsensus (A-H4): MAHC OFF → vote-only | HELIOS-noConsensus: `mahc=false` → passthrough of D-pipe list | **Behaviour wrong** | **ALIGN**: `mahc_hierarchical=false` must run uniform vote-only fusion |
| HELIOS-noRouter (A-H5): `cbr_routing=uniform` | HELIOS-noRouter: `router=false` | Flag name/semantics | **ALIGN** to `cbr_routing` |
| HELIOS-G (A-H6) | HELIOS-G | Yes | — |
| HELIOS-noStructural (A-H8) | HELIOS-noStructural | Partial | Full bundle (R2) |

All eight `variant_config_hash` values will change — expected and correct, because the May freeze is replaced, not amended.

### 5.2 Exploratory variants

| Ch3 (p.153) | Code | Resolution |
|---|---|---|
| HELIOS-noCogni (E-H1) | HELIOS-noP4 | Rename |
| HELIOS-noACP (E-H8) | HELIOS-noACP | Keep name; behaviour R2 |
| HELIOS-noReconcile (E-H5) | HELIOS-noReconcile | Keep name; behaviour R2 |
| HELIOS-HIS3 (E-H9) | — | Add (flag `his_tier`) |
| HELIOS-noFGSV (E-H4) | — | Add (flag `fgsv_ks_gate`) |
| HELIOS-noIOL (E-H6) | — | Add (flag `iol_self_telemetry`) |
| HELIOS-noExpl (E-H7) | — | Add (flag `coe_narrative`) |
| — | HELIOS-noMAHC | **Remove**: same flags and same hash as noConsensus (14 unique hashes across 15 variants) |
| — | HELIOS-noCBR | Remove (CBR is routing; covered by noRouter) |
| — | HELIOS-live | Not a Ch3 variant; keep only as an ingest-mode test fixture, outside the variant registry |
| — | HELIOS-noLLM-noGraph | Not a Ch3 variant; remove |

### 5.3 Flag registry

| Ch3 flag (p.137–138, p.142) | Code flag | Gates code today? |
|---|---|---|
| `l2c_llm` | `l2c_llm` | Yes (`run_lpipe`) |
| `p4_cognitive` (scoped to L-pipe visibility) | `p4_cognitive` | No |
| `mahc_hierarchical` | `mahc` | Gates uniform Borda (not MAHC) |
| `cbr_routing` (ORAR) | `cbr` + `router` | No |
| `l2b_graph` | `l2b_graph` | Yes (`build_ueg_c`) |
| `acp_stateful` | `acp` | No |
| `reconcile_terminal` | `reconcile` | No |
| `fgsv_ks_gate` | — | — |
| `iol_self_telemetry` | — | — |
| `coe_narrative` | — | — |
| `his_tier` | — | — |
| `sampling_regime_tag` | — | — |
| `ueg_structural` (used by noStructural; missing from the "twelve" list) | `ueg_c_structural` | Manifest check only |
| — (pipeline-level flags not in Ch3) | `dpipe`, `dpipe_propagation`, `gpipe`, `lpipe`, `ingest_mode` | `dpipe`, `gpipe` yes; `lpipe` no |

**Resolution:** **DECISION D2** — adopt the Ch3 registry names and add the five missing flags, keeping the pipeline-level flags the code needs (`dpipe`, `gpipe`, `ingest_mode`) as implementation detail documented in the pre-registration. The disjointness audit then must report every boolean flag covered exactly once (R2 exit criterion).

---

## 6. Metrics

| Metric | Ch3 definition | Code / docs today | Resolution |
|---|---|---|---|
| **HR@k** | Fraction of incidents with ground-truth root cause in top-k of the **MAHC consensus** list (p.203) | D-pipe stores top-3 only; official path never scores; analysis recomputes HR@3 from `consensus_verdict` | **ALIGN** in R2: score after dispatch, from the fused list, never feeding ground truth to a pipeline |
| **CpR** | Five-component sum (token, infrastructure, storage, human-minute, opportunity) under a pre-registered price book; log-transformed for A-H5 / B-H7 (p.203, p.108) | Four meanings: Correct Prediction Rate (`docs/evaluation/cpr_definition.md`), Causal Precision-Recall (`docs/helios_project_summary.md`), Cost per Resolution (consensus placeholder), **reciprocal rank** (`d_verdict.py`, and frozen `thresholds.json` `loo_cv_cpr` = 0.442222) | **ALIGN**: CpR = cost only. Rename reciprocal rank to **MRR** (descriptive, Ch3 lists MRR among descriptive metrics p.203–204); correct the docs; price book + cost computation in R2 |
| **Avg@5** | Used for B-H8; **never defined** | Not implemented | **CLARIFY** (§10.2) |
| **MTTR / log-MTTR** | Detection → post-remediation telemetry restoration within [t_injection, t_injection + 1800 s], log-transformed (p.203) | Not implemented; deviation 16 already excludes Ollama latency from MTTR | R2/R4; depends on D3 (serving) |
| **H_fact / H_struct** | Atomic-claim parser + two blind raters, κ ≥ 0.7, rubrics deposited (p.162, p.203) | Docs only (`docs/evaluation/hallucination.md` gives a different formula, κ > 0.75) | **ALIGN** docs to Ch3; build in R2 |
| **TTT** | Detection → MAHC PROVISIONAL publication (p.203) | Not implemented | R2 |
| **RRE** | Sign discrepancy provisional vs terminal reward, delayed-label subset only (p.112) | Not implemented | R2 |
| **CoE quality** | FAE-Score, three judge models, 10% human-anchored, descriptive (p.204) | Docs only (0–4 rubric) | **ALIGN** docs |

---

## 7. Run design, model, seeds

| Item | Ch3 | Code / OSF | Resolution |
|---|---|---|---|
| Run matrix | 8 variants × 5 benchmarks × 40 faults × 10 seeds = 16,000 runs; 400 paired observations per cell; a cell enters inference only with ≥ 320 included (p.106, p.111, p.161) | Exploratory: 20 OTel incidents; `NUM_INCIDENTS = 20` | **KEEP** exploratory pilot; confirmatory corpus is R4 |
| Benchmarks | AIOpsLab (primary), DeathStarBench, Train-Ticket, PetShop, OpsEval (p.131) | `corpus_manifest.json`: AIOpsLab, 174, deferred | R4 |
| 174-fault corpus | Tier 1: 96 · Tier 2: 36 · Tier 3: 30 · Tier 4: 12 (p.132–134) | Deferred | R4; **CLARIFY** arithmetic (§10.7) |
| **Seeds** | **Seed register 10,000,000 – 10,009,999 is binding** (p.108); BCa seed sequence pre-registered; pre-warm sequence of 1,200 | One global seed value (42) and one LLM seed value (42) | **ALIGN**: generate and freeze the register; map (incident, seed index) → seed |
| **LLM** | Protocol A: Llama-3.1-70B-Instruct, vLLM 0.6.x, greedy, TP = 4 on 4× A100 80GB; Qwen-2.5-72B contrast; 200-prompt ε probe (p.138, p.210, App. B) | llama3.1:8b via Ollama (deviations 15, 16) | **DECISION D3** |
| **ORAR pre-warm** | 1,200 synthetic Chaos-Mesh incidents on an isolated three-service testbed; LinUCB + ACP frozen, hashes in the manifest; disjointness check vs the corpus (p.108–110, App. B.1) | No router, no testbed | **DECISION D4** |
| Delayed-label subset | 25% of AIOpsLab + Train-Ticket, log-normal delays (p.112) | Not implemented | R4 |
| **H4b scaling sub-study** | Ch1: estate size from one hundred to 5,000 services; Ch3: 500, 1,000, 2,500, 5,000 synthetic services; Plane-2 latency SLO 150 ms; "separate pre-registered experiment" (p.21, p.217) | Not planned | **DECISION D8** |

---

## 8. Integrity mechanisms vs Ch3

| Ch3 commitment | Repo today | Resolution |
|---|---|---|
| Deviation-log entries carry an **Ed25519 signature** over the preceding fields (App. p.233) | HMAC-SHA256 chain + signed head anchor (deviation 22). Tracker row S0-D2-ENG01 already notes "Ed25519 migration deferred" | **DECISION D7** |
| Deviation log deposited at OSF "at every commit", freeze date and DOI recorded in the log (p.202, p.209) | Not deposited | R1 deposit |
| Corpus fixed at freeze with SHA-256 per instance (p.111, p.161) | Exploratory captures sealed (HMAC, deviation 23); `corpus_manifest.json` lists snapshot hashes only | **ALIGN** (audit step E): add seal hashes to the corpus manifest |
| Variant flag matrix bound to the binary commit (p.202) | `vcl_freeze_sha` pins `variants.py` blob | **KEEP** mechanism |
| `preregistration.md` content | Not covered by `manifest_sig.txt` (audit step E) | **ALIGN** |

---

## 9. Code/document drift to clean up during R1

Not protocol decisions — stale or contradictory repo documents, corrected in the same R1 change set:

- `docs/evaluation/cpr_definition.md`, `docs/helios_project_summary.md` (CpR meanings, "consensus not yet created"), `docs/tracking/ablation_architecture.md` (noLLM → A-H1 etc.), `docs/tracking/hypothesis_variant_metric_mapping.md` (α 0.00625 on every row; Family B called "sensitivity").
- `docs/osf_protocol_v0.md` §3.2 says noMAHC also sets `cbr=false` (code does not); §7 still freezes 70B/vLLM.
- `research/osf/prompt_sha.json` cites "deviation entries 11-12" for the model change; they are 15 and 16.
- Passthrough fusion priority uses `d_pipe/g_pipe/l_pipe` but stored rows use `dpipe/gpipe/lpipe`, so priority never matches (`helios/consensus/uniform_borda.py`).
- Disjointness audit scans the D-pipe stub, not the production `run_dpipe`.
- Deviation 20 calls `RunOrchestrator` frozen; deviation 23 changed it (logged, consistent, but the "frozen" claim should be retired in the pre-registration).

---

## 10. Inconsistencies inside the approved Chapter 3

These are in the approved text, so the code cannot "match" them. Each needs a **CLARIFY** decision recorded in the OSF pre-registration and a deviation entry, and the chair should be told before deposit.

1. **CHASE adjustment arithmetic.** Component midpoints are −0.05, −0.03, −0.03, which sum to **−0.11**, but the stated midpoint total is −0.12, giving the binding baseline 0.60 (p.194, Table 20). Using −0.11 gives 0.61. *Proposal:* pre-register the sum of the stated components (0.61) or restate one component; either way the ±25% sensitivity band stays.
2. **Avg@5 is never defined**, yet it is the binding B-H8 metric. *Proposal:* define it in the pre-registration (e.g. mean over k = 1..5 of HR@k), citing the source used by the benchmark literature.
3. **A-H7 vs p.116.** A-H7 is confirmatory, but p.116 says hallucination "will not enter the confirmatory hypothesis set". *Proposal:* Table 18 and the Holm order bind (A-H7 is rank 2); treat p.116 as superseded, record it.
4. **The five B-family baselines are never named or ordered.** Table 14 (CHASE, mABC, TAMO, Flow-of-Action, FrugalGPT) is design positioning only; FrugalGPT is a cost cascade, not an RCA system; only CHASE has a score adjustment. → **DECISION D5**.
5. **E-H3 and E-H8 are textually identical** (noACP, latency-constraint satisfaction). *Proposal:* retire E-H3 as a duplicate; nine distinct exploratory hypotheses.
6. **Two HELIOS-noLLM rows** in Table 17 differ in the CBR cell. *Proposal:* one variant; CBR routes over {D, G} when L is absent.
7. **Corpus arithmetic.** The "174-fault subset of the 200-fault ablation corpus" includes Tiers 2–4 and DeathStarBench, and the "remaining 26" are said to be PetShop + OpsEval (which would be 80 at 40 each); ablation power uses n = 174 while cells use 400 paired observations. *Proposal:* restate the corpus partition precisely at the confirmatory corpus freeze (R4), before any confirmatory run.
8. **B-family power claim vs Panel D.** Text says n = 174 supports B-H1–B-H5 at p_disc ≥ 0.30, r ≥ 0.70; Panel D rates (0.30, 0.70) as "Marginal" (~218). *Proposal:* extend the asymmetric rule to B-H1–B-H5 explicitly.
9. **Strata never operationalised:** "ambiguous-incident stratum" (A-H4), "narrative-heavy incidents" (A-H6), "matched HR@3" (A-H5). *Proposal:* operational definitions fixed in the pre-registration before any confirmatory data.
10. **"TTT" means two things** (time-to-triage; time-to-decision in E-H7). *Proposal:* rename E-H7's measure TTD.
11. **H4b** has no test, no CpR bound, and different ranges in Ch1 and Ch3. → **DECISION D8**.
12. **E-H7 analysis** uses a Shapiro–Wilk-gated t/Wilcoxon choice, which p.201 rejects for the B family. *Proposal:* Wilcoxon binding, t as sensitivity (consistent with p.201).
13. **Smaller items** (record, no decision): table/section cross-references off by one after the Business Evaluation Layer insert; recomputed Cohen's h values differ in the third decimal (e.g. h(0.60→0.73) = 0.277 vs stated 0.276); log-normal delay quantiles p75/p95 recompute lower than stated; ε probe "200 prompts from the 174-fault corpus" is impossible without replacement.

---

## 11. What is already right

- Holm ranks 1–8 and the α at rank 1 (0.00625).
- HELIOS-Full, noLLM, D, G, noConsensus, noRouter, noStructural exist as names.
- HR@3 as primary metric for A-H1, A-H2, A-H3, A-H4, A-H6, A-H8.
- G-pipe as personalised PageRank, L-pipe greedy decoding protocol, prompt SHA freeze, OSF artefact generation and verification machinery.
- Integrity infrastructure (ledgers with anchors, capture seals, tracking validator, CI) — stronger than Ch3 requires, except the Ed25519 point (D7).

---

## 12. Decisions needed before R1 changes anything

**Outcome (owner, 2026-10-23):** D1 (a), D2 (a), D5 (RCAEval suite + CHASE anchor), D6 (accept; discussed with the guide on a call), D7 (a), D9 (a, learned ranker over PPR) adopted as recommended; D3, D4 and D8 settled by the re-baseline (8B; calibration-partition initialisation; H4b deferred). New decisions D10 (MTTR split) and D12 (IRB now) are in `helios_e2e_product_plan_2026-10.md` §4. The table below is kept as the record of the options considered.

| # | Decision | Options | Recommendation |
|---|---|---|---|
| **D1** | Binding order | (a) Approved Ch3 binds; the May freeze is replaced before deposit · (b) May freeze binds, Ch3 differences logged as deviations | **(a)** — the freeze is not deposited, and the committee approved Ch3 |
| **D2** | Flag registry | (a) Adopt Ch3's twelve names + `ueg_structural`, add `fgsv_ks_gate`, `iol_self_telemetry`, `coe_narrative`, `his_tier`, `sampling_regime_tag`; keep `dpipe`/`gpipe`/`ingest_mode` as documented implementation flags · (b) keep code names, map them in a table | **(a)** — the pre-registration should use the approved vocabulary |
| **D3** | LLM for confirmatory runs | (a) Llama-3.1-70B on vLLM, 4× A100 (rent cloud GPUs for R5) · (b) keep 8B/Ollama, deviation already logged; confirmatory L-pipe claims bounded to 8B · (c) 70B for confirmatory only, 8B for pilots | **(c)** if GPU budget allows; otherwise (b) with the bound stated in Ch4 |
| **D4** | ORAR pre-warm corpus (1,200 synthetic incidents) | (a) Build the testbed + injection (R2/R4 effort) · (b) Published initialisation, deviation; A-H5 becomes "static routing under published parameters" | **(a)** if R4 timeline allows; the A-H5 claim depends on it |
| **D5** | Five B-family baselines | Name and order them now (candidates: CHASE + RCA systems with public artefacts or published AIOpsLab numbers); each needs a score-adjustment rule like CHASE | Decide with the chair; must be in the deposit |
| **D6** | §10 clarifications | Accept the proposed clarifications (§10.1–10.12) as pre-registration text, inform the chair | Accept, with a short memo to the chair |
| **D7** | Deviation-log signature | (a) Add Ed25519 signatures (public key in the OSF deposit, so examiners can verify without the secret); keep HMAC chain · (b) Deviation: HMAC only | **(a)** — real auditability gain, small change |
| **D8** | H4b scaling sub-study | (a) Separate pre-registration + experiment after R5 · (b) Limitation in Ch5 | Decide with the chair; Ch1 promises it |

---

## 13. Proposed R1 sequence (after decisions)

1. Tracking rows (S1-M4-ENG09 onward), IN_PROGRESS.
2. Metric contract memo (CpR = cost; MRR; Avg@5; strata definitions) — one deviation entry.
3. Flag registry + variants per D2; `analysis_plan.py` Family A/B/E per §2–§4; Holm/sidedness/asymmetric rule — one deviation entry ("protocol aligned to approved Ch3; May freeze superseded").
4. Doc drift cleanup (§9).
5. Audit step E: `preregistration.md` in the manifest signature; seal hashes in `corpus_manifest.json`; Ed25519 if D7(a).
6. Regenerate `research/osf/` with `verify_osf_freeze.py --generate`; pre-push gate; PR.
7. Memo to chair (D5, D6, D8); then OSF deposit and DOI into the deviation log.

Implementation of the mechanisms themselves (ORAR, MAHC, ACP, cognitive nodes, FGSV, IOL, scoring path, cost) is R2, against the registry fixed here.
