# HELIOS Metric Contract

**Date:** 2026-10-24 · **Tracking:** S2-M5-RES04 · **Status:** part of the pre-registration; deposited with OSF deposit 1. Any later change is a deviation entry, and no change is allowed after confirmatory data has been seen.

**Sources:** approved Ch3 §3.9 (p.203-204), Table 18; owner decisions D6, D10, D11 (deviation entries 24, 25, 29); `helios/research/analysis_plan.py` (which metric each hypothesis uses); `s0_3_d11_corpus_run_design.md`. Every mechanism measured here stays behind its `VCLFlag`.

**One rule above all:** each metric has exactly one definition, given here. Earlier meanings of "CpR" (Correct Prediction Rate, Causal Precision-Recall, reciprocal rank) are retired (§9).

---

## 1. Where and how everything is measured

| Rule | Definition |
|---|---|
| Measurement point | The **fused ranked list** a variant publishes (MAHC output in Full; vote-only output in noConsensus; the single pipeline's list, passed through, in D, G and LLM-only). Per-pipeline lists are also stored, for diagnostics |
| Scoring | Computed **after dispatch** by the evaluation harness, from stored outputs joined to the sealed ground-truth file. Ground truth, case names and injection time are never given to any pipeline (D11 §3) |
| Candidate set | **All services** of the system observed in any modality, after name normalisation; HELIOS never receives the injected-service set |
| Pairing | Variants and baselines are paired **by case** |
| Missing values | Never imputed: a run that does not produce a metric is excluded through the integrity gate, with an exclusion-ledger entry and its covariates |

---

## 2. Accuracy

| Metric | Definition | Used by |
|---|---|---|
| **HR@k** | Per case: 1 if the ground-truth root-cause service is among the top *k* of the fused list, else 0. Per variant: mean over cases. k ∈ {1, 3, 10} | A-H1–A-H4, A-H6, A-H8 (HR@3); B-H1–B-H5 (paired binary HR@3) |
| **Avg@5** | Avg@k = (1/k) · Σ_{j=1..k} HR@j, with k = 5, as defined by RCAEval (Pham et al., arXiv 2412.17015) | B-H8 (closes D6 item 2) |
| **MRR** | Per case: 1 / (rank of the ground-truth service in the fused list); 0 if it is absent. Per variant: mean | Descriptive only. This is the value the May code called "cpr" |

---

## 3. Cost — CpR (Cost per Resolution)

**CpR** is the five-component cost of one incident, in one currency, under the price book frozen before the build freeze (`docs/tracking/price_book.md`, S1.10):

| Component | On recorded cases |
|---|---|
| Token cost | Tokens in and out × per-token price (zero for local inference, recorded as such) |
| Infrastructure | CPU-seconds and GPU-seconds used by the run × per-second coefficients |
| Storage | Bytes ingested and stored for the incident × per-byte coefficient |
| Human time | Review minutes implied by the verdict state × per-minute rate: a verdict that requests a human (PROVISIONAL with HITL, non-convergence) carries the price-book review time; an automatic CONFIRMED verdict carries none |
| Opportunity | Time to correct diagnosis (§4) in minutes × per-minute cost of an unresolved incident |

CpR = sum of the five; analysed as **log(CpR)** (A-H5, B-H7). Per-component values are reported descriptively. CpR is always positive because infrastructure time is never zero.

**"CpR at matched HR@3" (A-H5):** the primary comparison of log-CpR between HELIOS-noRouter and HELIOS-Full uses the cases where both variants have the same HR@3 outcome (both hit or both miss); the share of matched cases is reported. A sensitivity analysis compares log-CpR over all cases.

---

## 4. Time

| Metric | Definition | Used by |
|---|---|---|
| **Time to correct diagnosis (TTCD)** | Wall-clock seconds from **invocation of the system on the recorded incident window** to the first published verdict (PROVISIONAL or CONFIRMED) whose top-1 is the ground-truth service. If no published verdict is correct, the value is **censored at 1,800 s** (Ch3's incident window). Baselines are timed the same way, on the same hardware. Analysed as log(TTCD) | B-H6 (D10) |
| **True MTTR** | Detection to restored service with live remediation, within [t_inj, t_inj + 1,800 s] (Ch3 p.203) | Exploratory, Stage B (OTel Demo testbed) |
| **Time to triage (TTT)** | Invocation to publication of the first PROVISIONAL verdict | E-H2 |
| **Time to decision (TTD)** | In the RQ4 user study: from showing a scenario to the participant's accept / escalate / reject choice | E-H7 (renamed from "TTT", D6 item 10) |
| Latency | Per-plane span durations (p50 / p95 / p99), descriptive | — |

---

## 5. Hallucination (A-H7)

| Metric | Definition |
|---|---|
| **H_fact** | Per case: unsupported atomic claims / all atomic claims in the published narrative; 0 when the narrative has no claims. Claims are extracted by the deterministic parser; a claim is *supported* when it cites a graph element that exists and supports it, and — for root-cause claims — agrees with the ground truth |
| **H_struct** | Per case: agent tool calls or outputs failing schema validation / all agent tool calls or outputs; 0 when there are none |

- **Labelling (Ch3 §3.8, inter-rater protocol).** Two independent raters, blind to variant, label every published narrative of HELIOS-Full and HELIOS-noLLM against rubrics deposited with the pre-registration; Cohen's κ ≥ 0.7 is required, and a third adjudicator re-labels below 0.7. Raters are calibrated on a 50-instance training subset from build data before confirmatory labelling. The rater labels are the A-H7 measure.
- **Grounding verifier (IN1).** The verifier's own claim labels are reported beside the rater labels (agreement, κ) as evidence for IN1; they never replace the rater labels in A-H7.
- **Variants without the L-pipe** produce a deterministic narrative from the statistical and graph evidence; it is scored the same way. They make no agent tool calls, so H_struct is a structural zero, recorded as such.
- **Test:** the per-case sign of (Full − noLLM), sign test, as pre-registered.

---

## 6. Consensus, routing and learning (descriptive or exploratory)

| Metric | Definition |
|---|---|
| Non-convergence count | Cases where MAHC does not converge within 90 s (Ch3 p.144) |
| HITL escalation rate | Share of cases whose verdict requests a human decision |
| Routed arm | Arm chosen per case; share of cases in which the LLM was consulted (IN3 evidence) |
| Confidence calibration | Calibration curve of MAHC's stated confidence against HR@3 (IN2 evidence) |
| Grounding rejection rate | Share of narrative claims the verifier removed (IN1 evidence) |
| RRE | Per case on the delayed-label subset: 1 if the provisional and the terminal reward have different signs, else 0 (E-H5) |
| False-accept rate | Share of fidelity-broken shadow validations that still PASS (E-H4) |

---

## 7. Strata

Both strata are fixed from data that does not depend on the outcome or on which of the two compared variants ran; thresholds are set on build data and frozen before the build freeze.

| Stratum | Definition | Why this way |
|---|---|---|
| **Ambiguous** (A-H4) | A case is ambiguous when, in the HELIOS-Full run, the pipelines that returned a list **do not agree on the top-1 service** (at least two distinct top-1s). HELIOS-noConsensus fuses exactly the same per-pipeline lists, so the stratum is identical for both variants | Uses only pre-fusion outputs, never the ground truth |
| **Narrative-heavy** (A-H6) | A case is narrative-heavy when the share of its post-injection log lines that match log templates **not seen in the pre-injection half** is at or above τ_N, the **median** of that share over the build data. Computed by the evaluation harness from the input logs | Uses only the input telemetry; the median keeps both strata usable for power |

---

## 8. Sanity floors

Reported beside every HR@k result (D11 §6):

| Floor | Definition |
|---|---|
| Random over all services | Expected HR@k of a uniform random ranking of all services in the system |
| Prior-only | Expected HR@k of a uniform random ranking of only the 5 injected services (HR@3 = 3/5 = 0.60) |
| HELIOS-D | Measured |

---

## 9. Retired and renamed terms

| Old usage | Where | Now |
|---|---|---|
| "CpR" = reciprocal rank | May code: `PipelineVerdict.cpr`, D-pipe verdict, calibration output `loo_cv_mean_cpr` | **MRR** (`PipelineVerdict.mrr`, `loo_cv_mean_mrr`, `thresholds.json` `loo_cv_mrr`) |
| "CpR" = Correct Prediction Rate | `docs/evaluation/cpr_definition.md` | Retired; that page now points here |
| "CpR" = Causal Precision-Recall | `docs/helios_project_summary.md` | Retired; corrected to Cost per Resolution |
| `ConsensusVerdict.cpr` | Consensus layer | Keeps the name: it **is** CpR (cost); a placeholder until the price book exists (S1.10) |
| "TTT" in E-H7 | Ch3 Table 18 | Time to decision (TTD) |
| log-MTTR in B-H6 | Ch3 | Time to correct diagnosis on recorded data; true MTTR exploratory (D10) |

---

## 10. Where values are stored

Scores live in a separate `eval_score` table written by the scoring path (S1.9), keyed by run, case and variant; pipeline result rows keep only what the pipelines produced. Analysis reads `eval_score` only.
