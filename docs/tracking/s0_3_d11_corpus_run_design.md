# S0.3 — D11: Corpus and run design (DRAFT for owner review)

**Date:** 2026-10-23 · **Tracking:** S2-M5-RES02 · **Builds on:** `s0_1_dataset_check.md` (findings F1–F5) · **Status:** draft — nothing here is frozen until the owner approves it and it is deposited in OSF deposit 1.

**Recommendation in one paragraph.** Use all **240 RCAEval multi-source cases** (RE2-OB, RE2-TT, RE3-OB, RE3-TT; 78 service-and-fault groups) as the confirmatory pool, sealed and untouched until phase E. Build and calibrate HELIOS only on data outside that pool: the OTel Demo testbed (20 existing incidents plus about 60 new captures, all with traces) and RCAEval's 495 trace-free cases (RE1, RE2-SS, RE3-SS). Run every confirmatory variant and every baseline once per case with a registered seed, rank over **all** services of each system, and report three sanity floors. This keeps the evidence clean, keeps all 78 groups for power, and gives the trained parts enough trace-bearing data.

---

## 1. Confirmatory pool

| Dataset | Cases | Groups (service × fault) | Modalities | Fault family |
|---|---|---|---|---|
| RE2-OB (Online Boutique) | 90 | 30 | metrics, logs, traces | cpu, mem, disk, delay, loss, socket |
| RE2-TT (Train-Ticket) | 90 (89 with logs) | 30 | metrics, logs, traces | same |
| RE3-OB | 30 | 10 | metrics, logs, traces | code-level f1–f5 |
| RE3-TT | 30 | 8 | metrics, logs, traces | code-level f1–f4 |
| **Total** | **240** | **78** | | |

- The one RE2-TT case without logs (`re2tt_ts-auth-service_cpu_1`) stays in the pool with a `logs_missing` covariate; the integrity gate never imputes.
- The pool is **sealed** in S1: every case is converted to the HELIOS recorded format, sealed (deviation 23 mechanism), and listed with its seal hash in the corpus manifest. The adapter refuses to load a pool case before phase E.
- **AIOpsLab**: if the S1 spike succeeds, its recorded problems join the pool as a third system under an addendum to this design, before the freeze.

---

## 2. Calibration and build data (never in the pool)

| Source | Cases | Traces | Used for |
|---|---|---|---|
| OTel Demo testbed, existing captures | 20 | yes | everything trace-based |
| **OTel Demo testbed, new captures (S1–S2)** | about 60 | yes | G-pipe ranker training, router initialisation, MAHC confidence calibration, λ, K/top-n |
| RCAEval RE1 (OB, SS, TT) | 375 | no | D-pipe and metric-feature tuning |
| RCAEval RE2-SS, RE3-SS | 120 | no (metrics + logs) | log templates, L-pipe prompt and worker tuning |

**Why new OTel captures:** no RCAEval case outside the pool has traces, and 20 trace-bearing incidents are too few to train the G-pipe ranker and calibrate consensus confidence well. The capture tooling already exists (deviation 12), so about 60 more incidents across the existing five fault types is a few days of S1–S2 work and directly improves product quality.

**Rejected alternatives**

| Option | Why not |
|---|---|
| Hold out a slice of the pool for calibration (e.g. the socket fault: 30 cases) | Leaves 210 cases in 68 groups — below the 73 that the Ch3 power analysis needs if repetitions are highly correlated (§5); and the analyst would see confirmatory-system data before the freeze |
| Cross-fitting (train on one system, evaluate on the other, in phase E) | Strong generalisation claim, but parameters would be produced after the freeze, contradicting Ch3's frozen-parameter commitment and complicating the VCL; kept as a possible Stage B robustness study |

---

## 3. Leakage and validity controls

| Control | Addresses | Implementation |
|---|---|---|
| **Opaque incident IDs** — random 128-bit IDs from the seed register; the real case name exists only in the sealed ground-truth file | F1 (case names contain the answer) | Adapter test: no case name, root-cause service or fault string appears in any pipeline input, snapshot, prompt or stored narrative |
| **Rank over all services** of the system (union of services seen in any modality; Online Boutique about 12, Train-Ticket dozens) | F2 (only 5 services ever fail) | HELIOS never receives the injected-service set |
| **Service-agnostic features** in every trained part (anomaly scores, graph position, error and latency shifts — no service names or service-index features) | F3 (RE1 and RE2 share root services) | Feature audit test per trained part before the freeze |
| **Name normalisation** per system (`frontendservice` ↔ `frontend`) | F4 | Table in the adapter, tested on every pool case at sealing |
| **Partial trace coverage** handled: services seen only in metrics/logs become graph nodes with their missing edge kinds recorded | F5 | Graph builder test |
| **Pool sealed until phase E** | Analyst bias | Adapter refuses pool cases before the `build-freeze` tag exists |
| **Every trained part stays behind its `VCLFlag`** | Ablation discipline | Disjointness audit before the freeze |

---

## 4. Run design

| Item | Design |
|---|---|
| Unit of analysis | One case; variants and baselines are paired by case |
| Confirmatory runs (Family A) | 8 variants × 240 cases = **1,920 runs** |
| Baseline runs (Family B) | 5 baselines × 240 cases = **1,200 runs** (CHASE as the published-score anchor) |
| Exploratory runs | Each Tier-2 variant built by the freeze × 240 cases |
| Seeds | One registered seed per (case, variant) from the seed register. The L-pipe uses greedy decoding, so it is deterministic in principle: a **10% rerun** measures actual token-sequence equality, and any non-equal rerun is recorded as a covariate. Trained parts use registered training seeds; a robustness check retrains them with 5 seeds and reports the spread (exploratory) |
| Cells | variant × system (OB, TT) × metric; a cell enters inference only with ≥ 80% of its cases included (Ch3's rule) |
| Strata reported | RE2 (resource and network faults) vs RE3 (code-level faults); fault type; system |
| Compute estimate | About 1,500 runs invoke the L-pipe; with the cheap-first router and about 5 model calls per L-pipe run on the 8B model on this machine (Apple M5 Pro), roughly 30–50 hours — comfortably inside the 4-week evidence window |

---

## 5. Power, with clustering stated honestly

- Ch3's power analysis needs **n = 73** paired incidents (84 with 15% attrition) to detect Cohen's h ≥ 0.276 at one-sided α = 0.00625 with 80% power.
- The pool has **240 cases in 78 groups** of about 3 repetitions. If repetitions behave independently, effective n is 240 (2.9× the requirement). If they are strongly correlated, effective n falls toward the **78 groups** — just above the 73 minimum, below the 84 that allows for attrition.
- **Pre-registered handling:** the primary test stays case-level Wilcoxon, paired by case (Ch3). Two sensitivity analyses account for clustering: (i) Wilcoxon on group-level means (n = 78), (ii) the rank-based mixed model Ch3 already lists, with a random intercept per group. The intraclass correlation is reported. The existing asymmetric rule applies: a non-rejection where the design effect drops power below 80% is reported as inconclusive at delivered power, not as evidence of no effect.

---

## 6. Sanity floors (reported beside every HR@k result)

| Floor | Definition | Expected HR@3 |
|---|---|---|
| Random over all services | Uniform random ranking of every service in the system | About 3/12 for Online Boutique; far lower for Train-Ticket |
| **Prior-only** | Uniform random ranking of only the 5 injected services (knowledge HELIOS is never given) | 3/5 = 0.60 — equal to the CHASE-adjusted baseline, so beating it shows diagnosis rather than base-rate knowledge |
| Metric-only floor | HELIOS-D alone (A-H3's comparison) | Measured |

---

## 7. D10 metrics on this corpus

| Metric | Definition on recorded cases |
|---|---|
| **Time to correct diagnosis (B-H6)** | Elapsed HELIOS processing time from the detection trigger to the first published verdict (PROVISIONAL or CONFIRMED) whose top-1 is the ground-truth service; censored at the processing limit when never correct. Baselines are timed the same way on the same hardware |
| **True MTTR (exploratory)** | Detection → restored service with live remediation on the OTel Demo testbed. **Note:** remediation and actuation are Stage B features (sprint B3), so this exploratory result arrives in Stage B, not by 31 March |

---

## 8. What needs the owner's decision

1. **Approve the pool and the build data split** (§1–§2), including about 60 new OTel Demo captures in S1–S2.
2. **Approve the controls** (§3), the run design (§4) and the clustering treatment (§5).
3. **Note the D10 timing** (§7): the live-MTTR exploratory result comes in Stage B.

On approval, this design goes into OSF deposit 1, the plan's calibration-partition wording is updated to match, tracking row S2-M5-RES02 closes, and the adapters in S1 implement §3.
