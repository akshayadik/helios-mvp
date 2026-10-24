# HELIOS OSF Pre-registration — deposit 1

**Title:** HELIOS: A Hybrid Multi-Pipeline Root Cause Analysis Framework for Microservices

**Author:** Akshay Adik (DBA candidate, Golden Gate University) · **Dissertation chair:** Dr. Anil Kumar Vuppala

**Status:** Deposited on OSF 2026-10-24, DOI 10.17605/OSF.IO/KMR3D (§14). Every choice below was agreed with the dissertation chair on a call (outcome reported 2026-10-24; deviation entry 36). **Prepared:** 2026-10-24. **Replaces:** the undeposited freeze of 2026-05-19 (deviation entry 24).

---

## 1. What binds

1. **The approved Chapter 3** (chair approval 2026-09-23) is the reference protocol (owner decision D1).
2. **This document** records how that protocol is carried out on the evidence that can be collected by 2027-03-31, and resolves the twelve internal inconsistencies of Chapter 3 (§9). Each change to Chapter 3 is a signed deviation entry (§13).
3. **The machine-readable artefacts** in §12 are generated from the code and bind together with this text: the hypothesis tables in §5 are produced from `helios/research/analysis_plan.py`, the variants in §3 from `helios/vcl/variants.py`, the metric definitions are `docs/tracking/metric_contract.md`, and `manifest_sig.txt` covers all of them and this file.
4. After deposit, any change is a new deviation entry plus an addendum. **No change is made after confirmatory data has been seen.**

---

## 2. Research questions (Chapter 3)

- **RQ1.** To what extent will the co-deployment of statistical, graph-machine-learning, and large language model reasoning as peer pipelines under identical inputs improve root-cause-analysis accuracy and reduce cost per resolution compared with baseline systems that deploy a single reasoning modality or a sequential pipeline?
- **RQ2.** To what extent will the integration of self-telemetry into the same diagnostic apparatus enable the detection and mitigation of reasoning failures within the AI system itself?
- **RQ3.** To what extent will each named architectural mechanism of HELIOS (C2 cognitive telemetry, C3′ fidelity-gated shadow validation, C4 uncertainty-aware hierarchical consensus, C5 meta-observability, C6 cost-aware adaptive routing) individually contribute to diagnostic accuracy, cost efficiency and safety, as determined by ablation?
- **RQ4.** To what extent will the Chain-of-Evidence narrative improve SRE interpretation of RCA output, measured by correct-interpretation rate, time to decision and self-reported trust in a within-subjects user study?

Family A answers RQ1 and RQ3, Family B answers RQ1 against external systems, and Family E carries RQ2, RQ4 and the remaining mechanisms as exploratory evidence.

---

## 3. Artefact and variants

HELIOS runs three peer pipelines on the same content-hashed graph snapshot: a statistical D-pipe, a graph G-pipe (learning-to-rank over personalised PageRank, D9) and an LLM L-pipe (Llama-3.1-8B, greedy decoding, D3). Their ranked lists are fused by uncertainty-aware hierarchical consensus (MAHC) with calibrated confidence (IN2), routed by a cost-aware router that consults the LLM only when cheaper evidence is inconclusive (IN3), and explained by a Chain-of-Evidence narrative whose every claim cites a graph element and is checked by a grounding verifier (IN1).

Every mechanism is behind one of 16 boolean feature flags (`helios/vcl/registry.py`). Each variant is one binary with flags switched off; its identity is the SHA-256 of its full configuration. VCL freeze: `helios/vcl/variants.py` git blob `21944caef2612033de8d196c435e617fb57f9498`.

| Variant | Kind | Flags off (vs HELIOS-Full) | Hypotheses | Config hash (first 16) |
|---|---|---|---|---|
| HELIOS-Full | Confirmatory | none (all 16 on) | A-H1, A-H2, A-H3, A-H4, A-H5, A-H6, A-H7, A-H8, B-H1..B-H8 | `5382fafae6db0a7c` |
| HELIOS-noLLM | Confirmatory | `l2c_llm` | A-H1, A-H7 | `7f82c31138c78b3d` |
| HELIOS-LLM-only | Confirmatory | `acp_stateful`, `cbr_routing`, `dpipe`, `dpipe_propagation`, `gpipe`, `l2b_graph`, `mahc_hierarchical`, `reconcile_terminal` | A-H2 | `b16c8aa62dfa253e` |
| HELIOS-D | Confirmatory | `acp_stateful`, `cbr_routing`, `gpipe`, `l2b_graph`, `l2c_llm`, `mahc_hierarchical`, `reconcile_terminal` | A-H3 | `794a1bab0b827ce5` |
| HELIOS-noConsensus | Confirmatory | `mahc_hierarchical` | A-H4 | `40360d2e8e841d52` |
| HELIOS-noRouter | Confirmatory | `cbr_routing` | A-H5, E-H2 | `69a0ed936c929c61` |
| HELIOS-G | Confirmatory | `acp_stateful`, `cbr_routing`, `dpipe_propagation`, `l2c_llm`, `mahc_hierarchical`, `reconcile_terminal` | A-H6 | `7b3c08e169c2e5a6` |
| HELIOS-noStructural | Confirmatory | `ueg_structural` | A-H8, E-H10 | `a6a64740c3150ae9` |
| HELIOS-noCogni | Exploratory | `p4_cognitive` | E-H1 | `77393185f21c62f1` |
| HELIOS-noACP | Exploratory | `acp_stateful` | E-H8 | `2f4866e6e670419e` |
| HELIOS-noReconcile | Exploratory | `reconcile_terminal` | E-H5 | `003940202112a3a5` |
| HELIOS-HIS3 | Exploratory | `his_tier` | E-H9 | `b6f325139863755d` |
| HELIOS-noFGSV | Exploratory | `fgsv_ks_gate` | E-H4 | `4b7d1c9aa21f78ef` |
| HELIOS-noIOL | Exploratory | `iol_self_telemetry` | E-H6 | `af55fe7c01817a42` |
| HELIOS-noExpl | Exploratory | `coe_narrative` | E-H7 | `e65e0d47a54e7774` |

---

## 4. Evidence design (D11, deviation entry 25)

| Item | Commitment |
|---|---|
| Confirmatory pool | All **240 RCAEval multi-source cases**: RE2-OB 90, RE2-TT 90, RE3-OB 30, RE3-TT 30 (78 service × fault groups; metrics, logs, traces). Pham et al., arXiv 2412.17015; data under MIT / CC BY 4.0 |
| Pool handling | Converted to the HELIOS recorded format, **sealed** (SHA-256 per file, HMAC seal) and listed in `corpus_manifest.json` before the build freeze; the adapter refuses pool cases until the `build-freeze` tag exists. `re2tt_ts-auth-service_cpu_1` has no logs and stays in with a `logs_missing` covariate |
| Build and calibration data | Never from the pool: the OTel Demo testbed (20 sealed captures + about 60 new ones), RCAEval RE1 (375 cases, no traces), RE2-SS and RE3-SS (120 cases, no traces) |
| Leakage controls | Opaque 128-bit incident IDs (case names contain the answer); ranking over **all** services of the system, never the injected set; service-agnostic features in every trained part; per-system name normalisation; injection time never given to HELIOS |
| Runs | 8 confirmatory variants × 240 cases = 1,920 runs; 5 baselines × 240 cases = 1,200 runs; each Stage A exploratory variant × 240 cases |
| Seeds | One seed per (case, system) from the register 10,000,000-10,009,999 (§8; `seeds.json`, layout SHA-256 `ce0cab374e9a…`). A 10% rerun of L-pipe cases measures token-sequence equality; any difference is recorded as a covariate |
| Inclusion | A run with a missing measurement is excluded, never imputed, and recorded in the HMAC-chained exclusion ledger with its covariates; a variant × system × metric cell enters inference only with ≥ 80% of its cases |
| Unit of analysis | The case, paired across variants and baselines. Power: Chapter 3 requires n = 73 pairs (84 with attrition) for Cohen's h = 0.276 at α = 0.00625; the pool gives 240 cases in 78 groups, with group-level and mixed-model sensitivity analyses for within-group correlation |
| Timeline | Build freeze (tag `build-freeze`) mid-February 2027; confirmatory runs and analysis by 2027-03-31 |

---

## 5. Hypotheses

All confirmatory tests are one-sided in the stated direction: the side named first (`a`) is predicted to score higher. For cost and time (A-H5, B-H6, B-H7) the side named first is the one predicted to cost more or take longer. Holm-Bonferroni step-down runs separately within Family A and within Family B over all eight hypotheses each; α by rank = 0.05 / (9 − rank). A hypothesis that cannot be tested counts as not rejected and is never dropped. **Asymmetric rule:** for flagged hypotheses a non-rejection is reported as inconclusive at the delivered power, not as evidence of no effect.

### Family A — ablation (confirmatory)

| ID | Rank | α | Comparison (a vs b) | Primary metric | Test | Stratum | Asymmetric rule | Expected effect | Chapter 3 |
|---|---|---|---|---|---|---|---|---|---|
| A-H3 | 1 | 0.00625 | HELIOS-Full vs HELIOS-D | HR@3 | wilcoxon_signed_rank | — | — | delta HR@3 >= 0.15 | Table 18 p.171 |
| A-H7 | 2 | 0.007143 | HELIOS-Full vs HELIOS-noLLM | H_fact, H_struct | sign_test | — | — | hallucination rates at or near zero without the L-pipe, above zero under Full | Table 18 p.179; power p.200 |
| A-H1 | 3 | 0.008333 | HELIOS-Full vs HELIOS-noLLM | HR@3 | wilcoxon_signed_rank | — | — | delta HR@3 >= 0.10 | Table 18 p.169 |
| A-H2 | 4 | 0.01 | HELIOS-Full vs HELIOS-LLM-only | HR@3 | wilcoxon_signed_rank | — | — | delta HR@3 >= 0.10 | Table 18 p.170 |
| A-H6 | 5 | 0.0125 | HELIOS-Full vs HELIOS-G | HR@3 | wilcoxon_signed_rank | narrative_heavy | — | delta HR@3 >= 0.12 | Table 18 p.178 |
| A-H5 | 6 | 0.016667 | HELIOS-noRouter vs HELIOS-Full | log-CpR at matched HR@3 | wilcoxon_signed_rank | — | — | delta log-CpR >= 0.60 (uniform routing costs more) | Table 18 p.172 |
| A-H4 | 7 | 0.025 | HELIOS-Full vs HELIOS-noConsensus | HR@3 | wilcoxon_signed_rank | ambiguous | yes | delta HR@3 >= 0.05 (underpowered, disclosed) | Table 18 p.177; p.191, p.195 |
| A-H8 | 8 | 0.05 | HELIOS-Full vs HELIOS-noStructural | HR@3 | wilcoxon_signed_rank | — | yes | delta HR@3 >= 0.08 (underpowered, disclosed) | Table 18 p.180; p.191, p.195 |

### Family B — HELIOS against baselines (confirmatory)

BASELINE-1 to BASELINE-5 are the methods of §6, in that priority order. BEST-BASELINE is the baseline with the highest HR@3 on the pool.

| ID | Rank | α | Comparison (a vs b) | Primary metric | Test | Asymmetric rule | Expected effect | Chapter 3 |
|---|---|---|---|---|---|---|---|---|
| B-H1 | 1 | 0.00625 | HELIOS-Full vs BASELINE-1 | HR@3 (paired binary) | mcnemar_exact_mid_p | yes | powered region p_disc >= 0.30 with r >= 0.70 | Table 18 p.173; Panel D p.200-201; clarification D6 item 8 |
| B-H2 | 2 | 0.007143 | HELIOS-Full vs BASELINE-2 | HR@3 (paired binary) | mcnemar_exact_mid_p | yes | powered region p_disc >= 0.30 with r >= 0.70 | Table 18 p.173; Panel D p.200-201; clarification D6 item 8 |
| B-H3 | 3 | 0.008333 | HELIOS-Full vs BASELINE-3 | HR@3 (paired binary) | mcnemar_exact_mid_p | yes | powered region p_disc >= 0.30 with r >= 0.70 | Table 18 p.173; Panel D p.200-201; clarification D6 item 8 |
| B-H4 | 4 | 0.01 | HELIOS-Full vs BASELINE-4 | HR@3 (paired binary) | mcnemar_exact_mid_p | yes | powered region p_disc >= 0.30 with r >= 0.70 | Table 18 p.173; Panel D p.200-201; clarification D6 item 8 |
| B-H5 | 5 | 0.0125 | HELIOS-Full vs BASELINE-5 | HR@3 (paired binary) | mcnemar_exact_mid_p | yes | powered region p_disc >= 0.30 with r >= 0.70 | Table 18 p.173; Panel D p.200-201; clarification D6 item 8 |
| B-H7 | 6 | 0.016667 | BEST-BASELINE vs HELIOS-Full | log-CpR | wilcoxon_signed_rank | — | delta = 0.80 (HELIOS costs less) | Table 18 p.174 |
| B-H6 | 7 | 0.025 | BEST-BASELINE vs HELIOS-Full | log time to correct diagnosis | wilcoxon_signed_rank | — | delta = 0.60 (HELIOS diagnoses faster) | Table 18 p.174; D10 (deviation 29) replaces log-MTTR on recorded data |
| B-H8 | 8 | 0.05 | HELIOS-Full vs BEST-BASELINE | Avg@5 | wilcoxon_signed_rank | — | delta Avg@5 >= 0.10 | Table 18 p.175; Avg@5 defined in the metric contract (D6 item 2) |

### Family E — exploratory

Estimates with BCa intervals; no p-value claims. Stage A items use the evidence build; Stage B items are evaluated after 2027-03-31 under addenda.

| ID | Comparison | Primary metric | Method | Stage | Status | Chapter 3 |
|---|---|---|---|---|---|---|
| E-H1 | HELIOS-Full vs HELIOS-noCogni | HR@3 on Tier-4 cognitive faults | bca | B | exploratory | Table 18 p.181 |
| E-H2 | HELIOS-noRouter vs HELIOS-Full | time to triage | bca | A | exploratory | Table 18 p.182 |
| E-H3 | HELIOS-Full vs HELIOS-noACP | latency-constraint satisfaction | bca | — | retired | Table 18 p.183; duplicate of E-H8 (D6 item 5) |
| E-H4 | HELIOS-noFGSV vs HELIOS-Full | false-accept rate under fidelity-break perturbation | bca | A (lite, if built) / B (full twin) | exploratory | Table 18 p.184 |
| E-H5 | HELIOS-noReconcile vs HELIOS-Full | reward reconciliation error on the delayed-label subset | bca | A | exploratory | Table 18 p.185 |
| E-H6 | HELIOS-noIOL vs HELIOS-Full | detection latency under injected control-plane degradation | bca | A (lite, if built) / B (full) | exploratory | Table 18 p.176 |
| E-H7 | HELIOS-Full vs HELIOS-noExpl | correct interpretation; time to decision; trust (RQ4 user study) | wilcoxon_paired_with_bca | A (if IRB approved) | exploratory | Table 18 p.189; p.163-165; D6 items 10 and 12 |
| E-H8 | HELIOS-Full vs HELIOS-noACP | latency-constraint satisfaction | bca | A | exploratory | Table 18 p.186 |
| E-H9 | HELIOS-HIS3 vs HELIOS-Full | per-incident latency by isolation tier | bca | B | exploratory | Table 18 p.187 |
| E-H10 | HELIOS-Full vs HELIOS-noStructural | delta HR@3 attributed across the structural sub-mechanisms | descriptive_with_bca | A | exploratory | Table 18 p.188 |

---

## 6. Baselines (D5, agreed with the chair)

Five methods from the RCAEval suite run on the same 240 cases, with the same inputs, rankings over all services and registered seeds. CHASE (published HR@3 0.72, adjusted to 0.60 by Chapter 3's rule) is kept as a published-score anchor for the effect-size framing only; it is not run.

| Rank | Method | Data | RE2-TT in Pham et al., Table 6 (AC@3 / Avg@5) |
|---|---|---|---|
| BASELINE-1 | Multi-source BARO | metrics, logs, traces | 0.82 / 0.81 |
| BASELINE-2 | TraceRCA | traces | 0.79 / 0.77 |
| BASELINE-3 | BARO (metrics only) | metrics | 0.82 / 0.80 |
| BASELINE-4 | PDiagnose | metrics, logs, traces | 0.70 / 0.67 |
| BASELINE-5 | Multi-source RCD | metrics, logs, traces | 0.64 / 0.54 |
| Alternates | CIRCA (metrics), then CausalRCA | metrics | 0.47 / 0.46; 0.47 / 0.43 |

**Substitution rule.** Each method gets a feasibility run on build cases only. A method that cannot run on the pool's data is replaced by the next alternate at the same rank; the swap is a deviation entry before the build freeze. Methods with AC@3 below 0.40 on RE2-TT are excluded as uninformative comparators.

---

## 7. Metrics

The single definition of every metric is `docs/tracking/metric_contract.md` (deposited with this file and covered by `manifest_sig.txt`). In brief:

| Metric | Definition | Used by |
|---|---|---|
| HR@k | Ground-truth root-cause service in the top k of the published (fused) list; k = 1, 3, 10 | A-H1–A-H4, A-H6, A-H8, B-H1–B-H5 |
| Avg@5 | Mean of HR@1 … HR@5 (RCAEval definition) | B-H8 |
| CpR | Cost per resolution: token, infrastructure, storage, human-review and opportunity cost under a price book frozen before the build freeze; analysed as log(CpR) | A-H5, B-H7 |
| Time to correct diagnosis | Seconds from invocation to the first published verdict whose top-1 is correct; censored at 1,800 s; analysed as log | B-H6 |
| H_fact, H_struct | Unsupported claims / all claims; failed tool calls / all tool calls; labelled by two raters blind to variant, Cohen's κ ≥ 0.7, third adjudicator below | A-H7 |
| MRR | Reciprocal rank of the ground truth; descriptive | — |

**Strata and matching (agreed with the chair).** *Ambiguous* (A-H4): the pipelines' top-1 services disagree in the HELIOS-Full run. *Narrative-heavy* (A-H6): the share of post-injection log lines with templates unseen before injection is at or above its median on build data. *Matched HR@3* (A-H5): cases where both variants have the same HR@3 outcome; all cases as sensitivity.

**Sanity floors**, reported beside every HR@k: random ranking over all services; prior-only random ranking of the 5 injected services (HR@3 = 0.60); HELIOS-D.

---

## 8. Statistical analysis

| Item | Commitment |
|---|---|
| Binding tests | Wilcoxon signed-rank (one-sided) for paired continuous outcomes; sign test for A-H7; McNemar exact mid-p for paired binary HR@3 (B-H1–B-H5) |
| Multiplicity | Holm-Bonferroni within Family A and within Family B (§5) |
| Effect sizes | BCa intervals with 10,000 resamples (one registered seed per hypothesis), Cliff's δ with every Wilcoxon test, Hodges-Lehmann estimate for every paired difference |
| Sensitivity | Wilcoxon on group means (78 groups); rank-based mixed model with a random intercept per group (ICC reported); Benjamini-Hochberg at q = 0.05; paired t on log values for B-H6–B-H8; MCAR test and inverse-probability weighting for exclusions; 70B L-pipe on a subset if budget allows |
| Effect-size framing | Cohen's h ≥ 0.276 (Chapter 3: target HR@3 0.73 against CHASE-adjusted 0.60). Family B is judged against the run baselines of §6, whose published HR@3 on RE2-TT reaches 0.82 |
| Analysis code | `helios/research/analysis_plan.py` and the analysis command written before the build freeze; run once, unchanged, after the confirmatory runs |

---

## 9. Clarifications of Chapter 3 (D6)

| # | Chapter 3 issue | Resolution |
|---|---|---|
| 1 | CHASE adjustment components sum to −0.11 but the stated total is −0.12 (p.194) | 0.60, the stated value, is kept (agreed with the chair); the arithmetic is recorded and 0.61 is reported inside the ±25% sensitivity band |
| 2 | Avg@5 not defined | Defined as the RCAEval mean of HR@1 … HR@5 (§7) |
| 3 | A-H7 confirmatory in Table 18 but excluded on p.116 | Table 18 and the Holm order bind; A-H7 is rank 2 |
| 4 | Five baselines never named | §6 |
| 5 | E-H3 identical to E-H8 | E-H3 retired; nine distinct exploratory hypotheses |
| 6 | Two HELIOS-noLLM rows in Table 17 | One variant; routing runs over D and G when the L-pipe is off |
| 7 | Corpus arithmetic (174 of 200, 400 pairs per cell) | Superseded by the 240-case design of §4 |
| 8 | B-family power claim conflicts with Panel D | Asymmetric rule extended to B-H1–B-H5 |
| 9 | Strata and matched HR@3 never operationalised | §7 |
| 10 | "TTT" used for two measures | E-H7 measures time to decision (TTD) |
| 11 | H4b has no test | Stage B, under its own pre-registration (D8) |
| 12 | E-H7 uses a Shapiro-Wilk-gated test choice | Wilcoxon binding, paired t as sensitivity |
| 13 | Smaller items (cross-references, h = 0.277 vs 0.276, log-normal quantiles, ε probe size) | Recorded; no analytic consequence |

---

## 10. Scope: Stage A and Stage B (deviation entry 27)

Nothing in the product scope is cut. **Stage A** — every mechanism the confirmatory tests need, plus Tier 2 features ready by the freeze — is frozen mid-February 2027 and produces all confirmatory evidence. **Stage B** builds the rest of the product (February–July 2027) behind the same feature flags; it is evaluated exploratorily after 2027-03-31 and never alters the frozen evidence build. True MTTR with live remediation (D10) and the H4b scaling study (D8) are Stage B.

---

## 11. How to verify this record

| What | How |
|---|---|
| Deviation log, with the public key only | `poetry run python bin/log_deviation.py verify-public` — Ed25519 from entry 35; the signed anchor covers every byte of the log, including the HMAC-only entries 1–34. Public key `keys/deviation_log_ed25519.pub.pem`, SHA-256 `cc10123700fbf26d2cfabb2f8088057f29473830bad83c12cc06651eade1dcaa` |
| Any single signed entry, without project code | `openssl pkeyutl -verify -pubin -inkey keys/deviation_log_ed25519.pub.pem -rawin -in <entry without ed25519_signature, compact sorted JSON> -sigfile <signature bytes>` |
| These artefacts | `poetry run python bin/verify_osf_freeze.py --verify` regenerates every JSON artefact from the code and checks `manifest_sig.txt` |
| Corpus | `corpus_manifest.json` lists the SHA-256 of every file of every case |

---

## 12. Frozen artefacts

| File | SHA-256 |
|---|---|
| `analysis_plan.json` | <!-- SHA:analysis_plan.json -->`34d6a303729bedfeebcc83ede351a93c70c4cd33ffbf0955e1bdd92ca97d6c15` |
| `corpus_manifest.json` | <!-- SHA:corpus_manifest.json -->`a5e1abf14c4a087e0a12d1841a32d22a2b0c2aa4fc5bbd9049861cef2cd6d7b9` |
| `prompt_sha.json` | <!-- SHA:prompt_sha.json -->`6d9b01b76edfaf186d93347f5f56e8e8dc11a12436af2b83254d4bf55254d3cf` |
| `seeds.json` | <!-- SHA:seeds.json -->`8a7f76ac524a2eb5a5f7d197b59bb6ee3518ebeeaf3047ac6991d13a79de2061` |
| `thresholds.json` | <!-- SHA:thresholds.json -->`a90bbe733c28501aec18cf9de7b13412307c11ad1438a3ccbdf97e6530bcd725` |
| `variant_hashes.json` | <!-- SHA:variant_hashes.json -->`d005c59b7d37aef2458519603309a1b97b9df366655d5311919b394b59af0b46` |
| `manifest_sig.txt` | <!-- SHA:manifest_sig.txt -->`e5a076cb816a6cac3f3ddf693639b4335093d08b3e90d03f7955255673570df4` |

`manifest_sig.txt` = SHA-256 over the JSON artefacts above, this file (with the SHA values in this table blanked) and `docs/tracking/metric_contract.md`.

---

## 13. Deviation summary

`deviation_log.jsonl` is authoritative (HMAC-SHA256 chain, signed head anchor, Ed25519 from entry 35); `docs/tracking/deviation_log.md` mirrors it in full.

- **Entries 1–18 (May 2026)** record the exploratory MVP build on the 20-incident OTel corpus: environment, schema, calibration gates, L-pipe serving (8B via Ollama, entries 15–16) and the undeposited May freeze. None bears on the confirmatory evidence; entry 24 supersedes the May protocol.

| # | Date | Change | sig[:16] |
|---|---|---|---|
| 19 | 2026-05-21 | Consensus layer introduced (Uniform Borda, vote-only fusion) | `d22f7735ed58c7db` |
| 20 | 2026-05-21 | Ablation runner: subprocess-isolated per-variant runs | `d3abdcce6bf0f05d` |
| 21 | 2026-05-21 | Exploratory analysis script (May design; superseded by entry 32) | `9102928aa3d6dd45` |
| 22 | 2026-10-22 | Ledger verification hardened: signed head anchors | `971bcaeaafc71d93` |
| 23 | 2026-10-22 | Capture content seals (SHA-256 of manifest and Parquet bytes, HMAC-signed) | `986bd5489b38cb83` |
| 24 | 2026-10-23 | Approved Chapter 3 binds; May freeze superseded; twelve Ch3 inconsistencies to be clarified here (D1, D6) | `da22f8c5329d1daa` |
| 25 | 2026-10-23 | Evidence from 240 recorded RCAEval cases instead of 16,000 live runs (RB1, D11) | `71597715a335e92e` |
| 26 | 2026-10-23 | Confirmatory L-pipe on Llama-3.1-8B, greedy decoding; 70B as sensitivity (RB2, D3) | `bcdcb8ce1a5d2789` |
| 27 | 2026-10-23 | Two-stage build, no scope cut: Stage A frozen mid-February 2027, Stage B to July 2027 (RB3, D4, D8) | `6f7b4e627a3b48a0` |
| 28 | 2026-10-23 | G-pipe as learning-to-rank over personalised PageRank, trained on build data only (D9) | `b575c37d0333033d` |
| 29 | 2026-10-23 | B-H6 measures time to correct diagnosis on recorded cases; true MTTR exploratory (D10) | `213e6a04b379520e` |
| 30 | 2026-10-23 | Design refinements IN1 grounded narratives, IN2 calibrated consensus confidence, IN3 cheap-first routing | `0fc7599419e7cce7` |
| 31 | 2026-10-23 | Flag registry renamed to Ch3 names; 16 boolean flags, 15 variants (D2) | `7a72a78e5e70d17d` |
| 32 | 2026-10-23 | Analysis plan implemented to Ch3 Table 18 with D6, D10, D11 | `a5c96a5dd243facb` |
| 33 | 2026-10-24 | Metric contract: one definition per metric, strata, matched HR@3; cpr renamed mrr | `3bbedb34eef6d803` |
| 34 | 2026-10-24 | Binding seed register 10,000,000-10,009,999 | `5f66223c8394493c` |
| 35 | 2026-10-24 | Ed25519 signatures on the deviation log; pre-registration in manifest_sig; per-file corpus hashes (D7, audit step E) | `dc0af094444ba074` |
| 36 | 2026-10-24 | Chair call outcome: five baselines named in priority order, CHASE value 0.60, clarifications and strata confirmed (D5, D6) | `b468a44e2c78e3eb` |
| 37 | 2026-10-24 | OSF deposit 1: DOI 10.17605/OSF.IO/KMR3D, deposited commit 524b621 (tag osf-deposit-1) | `67070970b2ed4269` |

---

## 14. OSF deposit DOI

**DOI:** [10.17605/OSF.IO/KMR3D](https://doi.org/10.17605/OSF.IO/KMR3D) · **Registration:** https://osf.io/kmr3d · **Registered:** 2026-10-24 (public, OSF Preregistration template).

The deposited text is this file at commit `524b621f24290271fd2f0cd9e53ef361612044dd` (git tag `osf-deposit-1`), attached to the registration as `osf_deposit_1.zip` (SHA-256 `87717b6d5d9bde7bc629569d2fd6ad21b2e81c1ac4bd1ff19516c7b5b1cd9a85`). Three edits were made after the deposit (deviation entry 37): this section, the status line at the top, and row 37 of the deviation summary. Everything else is unchanged from the deposited version; compare with `git diff osf-deposit-1 -- research/osf/preregistration.md`.
