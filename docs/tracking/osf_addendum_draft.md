# OSF addendum · draft

**Status:** DRAFT for the owner, to be deposited on OSF before tag `build-freeze` (S2-BL-05). The freeze record and the frozen rating rubric follow later, in deposit 2 (S5.7). · **Prepared:** 2026-11-18, row S2-M10-RES01, against `main` at `2e81330` · **Covers:** deviation entries 46–91 and the frozen parameter files · **Supersedes:** the addendum bullets in `docs/sprints/s3-routing/plan.md` § OSF addendum, carried in here in full.

## 0. How to read this addendum

- **What it adds to deposit 1.** Deposit 1 holds the pre-registration, the metric contract and the analysis artefacts, signed together (`research/osf/`, `manifest_sig.txt`). Those files are not edited. Every change since then that alters what a pre-registered test measures, or how it is computed, is recorded here.
- **Authority.** Each item cites the signed deviation entries (`deviation_log.jsonl`; HMAC chain, Ed25519 from entry 35, verifiable with the public key alone: `bin/log_deviation.py verify-public`). The entries are authoritative; this text summarises them. Where the two differ, the entry holds.
- **What did not change.** No entry changes a hypothesis, its direction, its comparator, its alpha or its Holm rank. The variant hashes, `variants.py` and the analysis plan (`helios/research/analysis_plan.py`) are unchanged since deposit 1.
- **When.** Every entry was made before any confirmatory data existed. The confirmatory pool (RCAEval, 240 cases, D11) is locked in code until `build-freeze`. All figures quoted below are build data and exploratory.

## 1. Effect on each pre-registered test

| Test | Comparison · metric | What changed in what it measures | Entries |
|---|---|---|---|
| A-H3 | Full vs D · HR@3 | HR@3 is scored on the fused list's terminal ranking. D-pipe parameters frozen | 53, 60 |
| A-H7 | Full vs noLLM · H_fact and H_struct · sign test | H_struct counts invented services and evidence ids as well as malformed answers; noLLM is a structural zero. H_fact no longer uses the ground truth: a claim is supported only if it cites an existing item of the run's own evidence. The LLM narrator picks and orders claims; code writes every sentence. A displayed narrative with no claims has H_fact zero. A-H7 is rejected only when both sign tests reject (intersection-union). Both variants are expected near zero, so A-H7 is likely not rejected | 59, 65, 66, 67, 68, 84, 86 |
| A-H1 | Full vs noLLM · HR@3 | The L-pipe is three single-modality workers with a deterministic merge (at most two on the pool). Full routes cheap-first while noLLM records the would-be escalation, so the two differ only on escalated runs: reported split by escalation | 57, 58, 69, 86 |
| A-H2 | Full vs LLM-only · HR@3 | As A-H1 for the L-pipe; LLM-only uses uniform routing | 57, 58, 69 |
| A-H6 | Full vs G · HR@3, narrative-heavy stratum | Stratum rule and τ_N frozen (median novel-template share on the RCAEval build cases with logs, τ_N 0.000164). Under uniform routing G runs on every incident with a graph. G-pipe frozen as the learned linear ranker | 54, 56, 69, 85 |
| A-H5 | noRouter vs Full · log-CpR at matched HR@3 | Routing modes and frozen router. CpR definition (graph build in the clock, publication sequence, human time only for PROVISIONAL and NON_CONVERGED, price-book-v2 AWS primary). Primary test on cases with the same HR@3 outcome, all cases as sensitivity. Reported split by the Full run's stage (stopped, escalated): the difference comes mainly from earlier first publication, not from skipped LLM calls | 69, 70, 84, 86 |
| A-H4 | Full vs noConsensus · HR@3, ambiguous stratum | MAHC weights pipelines and calibrates its confidence; noConsensus is vote-only Borda on the same per-pipeline lists. The router never reads a fusion output, so both route a case identically | 60–63, 69 |
| A-H8 | Full vs noStructural · HR@3 | The structural bundle now includes the G-pipe trace features built on typed structure; E-H10 attributes the difference | 54, 56 |
| B-H1–B-H5 | Full vs each baseline · HR@3 · McNemar exact mid-p | Baselines read an export of the sealed HELIOS window, never RCAEval's raw folders. Binding runs receive the injection time (RCAEval protocol), with a trigger-time sensitivity phase. A root cause a method never ranks is a miss. TraceRCA requires traces and is excluded with a reason where they are missing | 88, 91 |
| B-H7 | best baseline vs Full · log-CpR | CpR as in A-H5; baselines timed the same way (wall and CPU time inside the container) | 84, 88 |
| B-H6 | best baseline vs Full · log TTCD | TTCD is measured from the shared trigger handover, with graph build inside the clock; censored at 1,800 s | 46, 84, 88 |
| B-H8 | Full vs best baseline · Avg@5 | Input and failure rules as B-H1–B-H5 | 88, 91 |
| Holm, both families | | Step-down Holm in the order of the observed p-values; registered rank breaks ties and sets the report order. An untestable hypothesis stays in the family, unrejected. The fixed-sequence reading is reported beside it | 86 |
| All tests | | Run campaign rules: frozen schedule, outcome classes, retries, cell rule, MCAR and IPW as sensitivity. Covariates: `llm_unavailable`, trigger source, determinism rerun | 73, 87 |

Family E (exploratory, BCa, no Holm):
- **E-H2 (TTT).** TTT is measured from the trigger handover to the first publication, whatever its state (entries 46, 84).
- **E-H4 and E-H6.** Tests of the lite FGSV and IOL mechanisms (entry 89).
- **E-H5.** Offline replay with a two-stage reward (entries 74, 75); the selection of its pool subset is fixed in §2.7. Which form of E-H5 is binding is still an owner decision (§5).
- **E-H8.** Moves to Stage B, because the frozen router does not read the ACP (entries 82, 83).
- **E-H1 and E-H9.** Untestable in Stage A: no consumer for `p4_cognitive` or `his_tier` (entry 90).

## 2. Changes by area

### 2.1 Corpora, scope and the shared trigger (entries 47–52)

- **Out-of-scope services** (entry 47). The test harness (load-generator, flagd, flagd-ui) and the observability stack (prometheus, jaeger, opensearch, grafana, otel-collector) are excluded from trigger decisions, suspects, pruner seeds and every system's ranking, for HELIOS and the baselines alike. No RCAEval build service name is on the list; the pool's names are checked at `build-freeze`.
- **OTel build corpora** (entries 48, 50). `otel_build_v2`, then `otel_build_v3` (9 faults × 7 repetitions, normal period varied per case, 300 s fault period) replace v1 for calibration. All are build data.
- **Trigger precision** (entry 49). A threshold trigger counts as false only when its bucket ends more than 60 s before the recorded injection time; the untolerated rate is reported beside it.
- **Detector trigger-v2, frozen** (entries 51, 52). Metrics and logs only, never raw spans; causal robust z against past values. Every system's trigger, and the TTCD and TTT anchor, come from this detector; confirmatory runs refuse provisional parameters. Build results: RCAEval 3.4% false triggers; OTel v3 none false, 32 of 63 without a trigger.

### 2.2 Pipelines (entries 53–58)

- **D-pipe** (entry 53). Reads both metric formats; parameters frozen; propagation has no effect on build data.
- **G-pipe** (entries 54–56). Learned linear ranker with ten weights over D-pipe's score, a PPR score and trace-graph features (call edges, leads, wait share, ghost edges), selected leave-one-root-service-out on the 63 OTel v3 cases; plain PPR where the trace features cannot be computed, and under noStructural. The 20 earlier OTel captures (deposit 1 data) were dropped from G-pipe selection; this is recorded as a validity threat for the May results.
- **L-pipe** (entries 57, 58). The single prompt `rca_v1` (still on disk unchanged, deposit 1) is replaced in the run path by three single-modality workers (metric, log, trace) and a deterministic merge. Worker prompts and the model digest are frozen. On the pool the L-pipe has at most two workers (k ≤ 2). Operation and message words remain in prompts (residual cue).

### 2.3 Fusion, confidence and publication (entries 59–63)

- **H_struct** (entry 59). Recorded per run and pipeline (`hstruct_row`).
- **One fused verdict per run** (entry 60). HR@k is scored on its terminal list. MAHC weights each pipeline's vote; noConsensus uses vote-only Borda.
- **Calibrated confidence** (entries 61–63). Four features (top-1 share, normalised entropy, fused sigma, top-1 agreement), logistic step and isotonic calibration, frozen from build run 3. The confidence and the CONFIRMED or PROVISIONAL state never enter the ranking. The confidence separates right from wrong only modestly (entry 63).

### 2.4 Metric definitions (entries 46, 71, 72, 84, 85)

The metric contract is signed into deposit 1 and is not edited (entry 72), so these definitions live here.

- **Clock** (entries 46, 84). TTT and TTCD start when a system is handed the shared trigger record; the contract's "invocation" wording is superseded. Building the incident graph is inside the clock (about 0.4 s per run on OTel build data; none without traces).
- **Publication sequence** (entry 84). A run publishes its first list and, when different, its terminal list (routed: the cheap list, then the escalated one). A non-converged run's in-time list counts as published at 90 s. TTT = graph build + first publication. TTCD = graph build + the earliest publication whose top-1 is the root cause, censored at 1,800 s. The narrator runs after publication; its time is reported as time to narrative and is never part of TTT or TTCD.
- **CpR human time** (entry 84). Review time is charged when the published state is PROVISIONAL or NON_CONVERGED, never for CONFIRMED. Primary price profile: price-book-v2, AWS; GCP and Azure as sensitivity columns.
- **H_fact** (entries 65, 84). An atomic claim is supported only if it cites an existing item of the run's evidence; agreement with the ground truth is no longer part of the rule. Unlabelled claims leave the case's H_fact empty and are counted, never imputed.
- **Detection delay** (entries 71, 72). Recorded seconds from the trigger's anchor (`trigger_time_s`) to the earliest instant a live detector could have issued it (`known_at_s`). For a threshold trigger that is the end of the last persistence bucket; for the fallback, the end of the scored window; external triggers have none. It is identical for every system on an incident, and descriptive.
- **Operational TTCD** (entries 71, 84). Detection delay + TTCD, censored at 1,800 s. Exploratory; reported beside TTCD, never replacing it in B-H6, CpR or A-H5.
- **Trigger-source split** (entry 71). TTCD and TTT are split by trigger source (threshold, fallback), with the fallback share reported beside every timing result.
- **Narrative-heavy stratum** (entry 85). Drain3 templates mined over the whole window. Share = novel post-injection lines / post-injection lines. A case is narrative-heavy when its share is at or above τ_N = 0.000164 (median over 120 RCAEval build cases with logs; frozen in `narrative_tau.json`). A case without post-injection logs has no stratum and is counted. The injection time is read only by the evaluation harness. The build logs are Sock Shop only, while the pool is Online Boutique and Train Ticket, so the pool split may be unbalanced; stratum sizes per system are reported with A-H6.

### 2.5 Chain of Evidence and narratives (entries 64, 66–68)

- **CoE file per orchestrator run** (entry 64). One signed entry per stored run (HMAC chain, plus Ed25519 for confirmatory runs). Confirmatory CoE files go into the OSF deposit and can be verified offline with `bin/verify_ledgers.py --coe`.
- **Narrative engine** (entries 66–68). One narrative per stored run, written from that run's CoE entry alone. HELIOS-noExpl shows the ranked list only. The LLM narrator picks and orders claims, and code writes the sentences (owner decision (b), 2026-11-01). The prompt SHA and parameters hash are frozen and recorded in each CoE entry. Rankings, scores, confidence and state are identical with the narrator on and off. CpR includes the narrator's tokens for LLM variants.

### 2.6 Routing (entries 69, 70, 73)

- **Routed** (`cbr_routing` ON: Full, noLLM, noConsensus, noStructural, exploratory variants). Two-stage cheap-first: the cheap arm (D or D+G) is fused and published at once; the L-pipe runs only on D/G disagreement or when the cheap arm's lower-bound accuracy is below τ_acc.
- **Uniform** (`cbr_routing` OFF: noRouter, LLM-only, D, G). Every enabled pipeline on every incident.
- **Reachable arms.** The router chooses only among the arms that are ON (S3.1 R-c), so the reachable arm set differs between variants that remove an arm (entry 90).
- **Splits.** A-H5 is reported split by stage (stopped, escalated); A-H1 split by escalation.
- **Router frozen** (entry 70). `router_params.json`. Build: RCAEval routed HR@3 96.57% against uniform 97.37%, with 298 of 495 cases stopping on the D-pipe.
- **LLM availability covariate** (entry 73). Every run that asked the L-pipe records `llm_unavailable` in its routing step: `endpoint`, `cache_miss`, `calls`, or none. A routed run whose escalation met an unavailable LLM publishes its cheap arm. Reported per variant and corpus beside every confirmatory result. A comparison with any affected pair is reported with and without the affected incidents; nothing is rerun selectively.

### 2.7 Reward, E-H5 and the delayed-label subset (entries 74, 75)

- **Two-stage reward.** Offline replay only, through a thawed copy of the router. Departures from Chapter 3: the corpora (D11), r1 without HITL acceptance or CpR, single-pipeline stops excluded from RRE, and the stream seed taken from the existing `orar_prewarm_order` slot. A terminal reward that arrives before its provisional reward applies whole (entry 75).
- **Pool subset.** The pool replay runs after the confirmatory runs are scored, on a seeded 25% of each pool corpus. The selection rule (seed and stratification) is fixed here before `build-freeze`.
- **Reporting.** RRE and learning curves with BCa intervals, outside the Holm family.

### 2.8 OTel fix attempt and held-out v4 (entries 76–81)

- **Adoption rule.** A pre-registered rule for a refit chain (fixes A and B), read once on the held-out OTel v4 corpus (36 cases, sealed, manifest digest 22248602f708) and RCAEval build.
- **Result.** The refit tied the frozen chain (v4 30 of 36, RCAEval build 478 of 495) and was not adopted, so every frozen parameter stays as it was.
- **Reported.** The frozen chain's v4 result (HELIOS-Full and noRouter, per fault type) and the null result of the fixes. v4 is not part of the confirmatory pool.

### 2.9 ACP and Knowledge Cortex (entries 82, 83)

- **ACP built as exploratory** behind `acp_stateful`. It predicts four remediation families mapped from injected fault types (resource, network, config, code), in place of Chapter 3's schema change, data mutation and config change. It is recorded in the CoE and not read by the frozen router, so E-H8 cannot differ between Full and noACP in Stage A and moves to Stage B.
- **Build figures** (cross-fitted): 78.85% accuracy against 52.15% for always predicting the majority family.
- **Knowledge Cortex** (S3.4) moved to Stage B.

### 2.10 Analysis rules (entry 86)

- **Holm.** As in §1.
- **Wilcoxon signed-rank.** Differences in the registered direction, one-sided, zeros dropped, midranks, exact conditional p-value. On 0/1 HR@3 outcomes it equals the exact sign test on discordant pairs, which is reported beside it.
- **A-H7.** Two exact sign tests, joined as an intersection-union test.
- **A-H5.** Matched cases primary, all cases as sensitivity. Stage splits are descriptive. Log-CpR without the opportunity component is an exploratory column.
- **Other rules.** McNemar exact mid-p for B-H1 to B-H5; effect sizes and BCa intervals as registered; sanity floors as in contract §8.

### 2.11 Run campaign (entry 87)

- **Schedule.** One frozen schedule per corpus, a pure function of the sealed manifest's case order, the case-to-system map and the variant catalogue, with its digest in every run's context.
- **Order.** Inside a case, HELIOS-noRouter runs first, so the run that fills the response cache is the same variant on every case.
- **Outcomes.** Passed, or excluded as the integrity gate decides; a seal failure is an exclusion with a ledger entry. Infrastructure errors are retried at most twice, then excluded. Configuration refusals stop the campaign and are not exclusions.
- **Cell rule.** A passed run without a value for a cell metric is excluded for that metric only. A hypothesis whose cell fails the 80% rule on one benchmark system is tested on the others, and a non-rejection is then reported as inconclusive at delivered power.
- **Missing data.** MCAR test and inverse-probability weighting as sensitivity results only.
- **Determinism.** A 10% stride rerun with the response cache bypassed.

### 2.12 Baselines (entries 88, 91)

- **Input.** Each run exports the sealed HELIOS window into RCAEval's file layout after the same hash and seal check as HELIOS. The 15-second log and trace series that multi-source methods read are rebuilt by HELIOS.
- **Anomaly time.** Binding runs receive the injection time from the signed ground truth (RCAEval protocol), read by the harness only. A sensitivity phase reruns every baseline with HELIOS's own trigger time under the same seed.
- **Output.** Metric-level ranks map to services by RCAEval's rule; a root cause never ranked is a miss.
- **PDiagnose.** A faithful port with six recorded departures.
- **Wrappers.** `sli` passed as None (main.py derives it from the folder name, which carries the root cause).
- **Timing and cost.** Measured inside the container.
- **Missing modalities** (entry 91, export rcaeval-export-v2). Captures without traces or logs export header-only files, so the four baselines that can run produce rankings. TraceRCA requires traces: on a capture without them it is excluded before the container starts (`modality_absent`). A TraceRCA cell may then fail the cell rule and its comparison become untestable rather than decided by construction. The "excluded baseline cases as misses" sensitivity row still reports the miss reading.

### 2.13 Tier-2 lite mechanisms (entry 89)

- **FGSV lite** (`fgsv_ks_gate`). One remediation proposal per run for the fused top-1.
  - **KS gate.** Chapter 3's gate (alpha_ks 0.05, Holm across pillars) on the twin (earlier half of the normal period) against production (later half).
  - **Replay.** ASRE structural mode only.
  - **Outcomes.** PASS, FAIL or STALE; HELIOS-noFGSV records the proposal as UNVALIDATED.
  - **Build results.** The KS gate marks 52% of clean OTel targets STALE (owner decision 2026-11-14: Chapter 3's gate kept, STALE reported as a covariate). On Full's own top-1, replay passes wrong and correct targets alike.
  - **Reporting.** E-H4 is reported with the gate and replay split, and the unperturbed false-accept rate beside the perturbed contrast.
- **IOL lite** (`iol_self_telemetry`).
  - **Mechanism.** Control-plane self-telemetry as a `tenant=self` partition read by the frozen trigger rule (threshold 10, persistence 3); the pipelines rank on the production graph only.
  - **E-H6 injection.** Multiplies the recorded model compute time from run 30 by a frozen ladder (×2, ×3, ×5, ×8).
  - **Build result.** Detection at ×5 and ×8 within 3 runs, never at ×2 or ×3.
- **Effect on HELIOS-Full.** Its verdicts are identical with either flag on or off.

### 2.14 Flag disjointness (entry 90)

- **Gated region.** A flag's gated region is every runtime location in `helios/` that reads it.
- **Certificate.** 13 flags covered; 3 declared without a consumer in Stage A (`p4_cognitive`, `his_tier`, `sampling_regime_tag`); 9 declared interaction rows over 6 flag sets; no violation (`docs/tracking/disjointness_audit_log.md`).
- **Reporting.** With `l2b_graph` OFF the G-pipe cannot run, so a comparison involving that flag also removes the G-pipe.

## 3. Frozen parameter files

The parameter hashes the runs record (`parameter_hashes` in each CoE entry), the model and image digests, and the freeze commit go into the freeze record (S5.6) and deposit 2. Listed here: each file's SHA-256 at this draft (`main` `2e81330`) and its last commit.

| File | What | Entry | Last commit | SHA-256 |
|---|---|---|---|---|
| `data/frozen/trigger_detector.json` | Shared detection trigger (trigger-v2) | 52 | `b71d1c0` | `2f84aeb253827b650a4ecb3f41df2cecb2cf10f8be32bfbd8e4bc7e6eb149684` |
| `data/frozen/dpipe_params.json` | D-pipe | 53 | `638ed06` | `359c0e46556d0a96ee14603254499a8b8e11b560cc634c8c1b6cac7f526e0ed2` |
| `data/frozen/gpipe_params.json` | G-pipe learned ranker | 56 | `6944cb2` | `3d96133c45888dc738991918812d7f0ff400bb72c43c9e3db8d8d4173f143e4c` |
| `data/frozen/mahc_params.json` | MAHC priors and calibrator | 63 | `304019d` | `da515633aede45a8b5e871383f6deed53358afd19cbf87898ac09c19a31d3634` |
| `data/frozen/narrator_params.json` | Narrator (pick and order) | 67, 68 | `232f529` | `f735153cc70f13f5e0aa6f3c7cd510a00b578fa0f4c66ebdbe8761e0430dcf7c` |
| `data/frozen/router_params.json` | Router (cbr_routing) | 70 | `31e0cb5` | `f087515cc76a8fb5ed5484c078f9379feadcd8a206a923e2b1452a9ec35fb50c` |
| `data/frozen/acp_params.json` | ACP (exploratory) | 83 | `9d1cd3b` | `b0282ded64099959eeb42a32f04e09f9e92b3e36691a76c94985db8c5872d50f` |
| `data/frozen/narrative_tau.json` | τ_N, narrative-heavy stratum | 85 | `d748fe5` | `887c2746934b0a252fbba18320e243e0d38aa0fc4fd0611ea90567ce37ace546` |
| `data/frozen/fgsv_params.json` | FGSV lite | 89 | `66c1fe2` | `2f71ac08424d4fdccb370b7d4d3143805c8a173871df966597a6c17ae34725fc` |
| `data/frozen/iol_injection.json` | IOL lite E-H6 ladder | 89 | `66c1fe2` | `c6cd5b319a76e517e51b0bbfabdb1355ff529e5091eeb7d3a33c10654eebb47a` |

The L-pipe worker prompt SHAs and the model digest are frozen in code (`lpipe_config.WORKER_PROMPT_SHAS`, entry 58) and are checked by the compose `model-check` service. The price book is price-book-v2 (AWS primary); its GCP and Azure profiles are open (§5).

## 4. Proposed additions from S5, not yet entries

These come from the S5.3 pilot, the S5.4 replication and the component review (`docs/sprints/s5-integration-freeze/`, backlog CR-items). None changes a hypothesis or test. Each is a reporting rule the owner may add before deposit; any that the owner adopts gets its own deviation entry first.

1. **Graph comparisons on systems without traces** (CR-09). On captures without traces the G-pipe has no graph: HELIOS-G then ranks as HELIOS-D does (on RCAEval build, HELIOS-G, HELIOS-D and noLLM give identical rankings). *Proposed rule:* on a pool system without traces, A-H6 and other comparisons that need the G-pipe are reported as untestable on that system, not as a non-rejection. Whether pool captures carry traces is not read before `build-freeze` (entry 91).
2. **Timing noise in CpR and TTCD readings** (CR-10). The S5.4 replication reran the build campaigns on identical code and data. Every accuracy result was identical, while timing-derived p-values moved, for example OTel B-H7 from about 0.038 to about 0.099, flipping a descriptive reading. The median log-CpR also sits at the censoring cap for many systems. *Proposed rule:* report the censored share beside every CpR and TTCD result, and state that timing-derived results carry run-to-run noise of this size.
3. **HR@3 near ceiling** (CR-11). Full reaches 96–98% HR@3 on RCAEval build, so the Family A top-3 tests have few discordant pairs. *Proposed rule:* report HR@1 and MRR beside each HR@3 test as exploratory columns.
4. **Multi-source RCD nondeterminism** (CR-23, owner decision 2026-11-18). With identical input, seed and image, Multi-source RCD returned a different ranked list on 3 of 495 RCAEval build cases. HR@1 and HR@3 were unchanged; Avg@5 and MRR changed on two cases. *Proposed rule:* state that Multi-source RCD's lower ranks can move between reruns, and report the baseline determinism rerun beside B-H5 and, if it is the best baseline, B-H8 (Avg@5).

## 5. Open before deposit (owner)

| Item | Why it matters here | Record |
|---|---|---|
| E-H5 form: RRE selection between Full and noReconcile | Decides which E-H5 reading the addendum registers; both are built | S3.3 design §6 item 3; S4 exit §6 |
| GCP and Azure price-book profiles | CpR sensitivity columns (§2.4) | S4 exit §4 |
| §4 proposals adopted or declined | Each adopted rule needs its entry before deposit | §4 |
| Chair call (end of November) | Topics: CpR and A-H5, cell rule narrowing, baselines' injection time, the §4 items | S4 exit §5 |
| Router and structural changes (CR-01, CR-02), if pursued | Would change frozen parameters: new freeze entries, and this draft is updated | Component review backlog |
