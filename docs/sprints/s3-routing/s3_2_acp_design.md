# S3.2 Action-Class Predictor (design)

Row S2-M8-ENG02 · Tier 2 · Flag `acp_stateful` (`VCLFlag.ACP_STATEFUL`; OFF = HELIOS-noACP) · 2026-11-08 · Owner scope 2026-11-07: exploratory, kept out of HELIOS-Full's confirmatory path · Owner 2026-11-08: build S3.2, move S3.4 to Stage B · **Draft for owner approval**

## 1. What Chapter 3 asks for

Algorithm 2 (Ch3 p.115) is a small supervised classifier run before pipeline dispatch:
- **Inputs:** the L1 snapshot and the incident signature. Structural features: node count, edge-class counts, anomaly-seed type, recent-deployment overlap, fault-signature hash, pillar-availability flags.
- **Outputs:**
  - softmax over {schema change, data mutation, config change};
  - a log WAL-replay size estimate;
  - a blast-radius tier.
- **Use:** the router (Algorithm 1) reads this block as extra features.
- **Weights:** frozen for the confirmatory protocol.
- **Ablation:** `acp_stateful` OFF (HELIOS-noACP) replaces the ACP with a uniform prior. E-H8 (exploratory) compares Full and noACP on latency-constraint satisfaction.

## 2. What the build data allows

**No realised remediation labels.** Neither RCAEval nor the OTel captures record what fixed an incident. So the only label available is the injected fault type, through a fixed map.

| Build fault types | Cases |
|---|---|
| RCAEval cpu, mem, disk | 90 each |
| RCAEval delay, loss, socket | 90, 90, 15 |
| RCAEval code-level f1–f4 | 10, 3, 10, 7 |
| OTel v3, nine flags | 7 each (63) |

**Ch3's three classes don't fit this data.** None of these faults is fixed by a schema change or a data mutation. A softmax over Ch3's three classes would have two classes with no training examples.

**No WAL estimate.** No captured service has a write-ahead log, so the log WAL-replay size has nothing to learn from.

**The router is already frozen without ACP.** The S3.1 design (§5.2) said ACP output is appended to the router features "only if S3.2 is built and frozen before the router's freeze". The router froze in S3.1 (entry 70, hash 94707eca) without it.

## 3. Decisions (for approval)

**P-a. Class set: remediation families the data can label** (deviation from Ch3's class set, recorded in the pre-run entry). The softmax runs over four classes. The map is fixed before any fit:

| Class | Typical remediation | Build fault types mapped |
|---|---|---|
| `resource` | restart, scale, raise a limit | cpu, mem, disk; OTel adHighCpu, adManualGc, emailMemoryLeak |
| `network` | network policy, routing, retry/timeout settings | delay, loss, socket |
| `config` | flip a flag, revert a config value | OTel adFailure, cartFailure, paymentFailure, paymentUnreachable, productCatalogFailure, recommendationCacheFailure |
| `code` | roll back a release | RCAEval f1–f4 |

- Ch3's `schema change` and `data mutation` move to Stage B, where they need incidents with realised remediations (B4, ACP retraining).
- The log WAL-replay size estimate is recorded as not applicable to the corpus, and also moves to Stage B.

**P-b. Features: label-free, observable at dispatch.** About ten:
- the frozen S2.5 signal-type indicators;
- pillar availability (metrics, logs, traces present);
- snapshot node count and edge-class counts (call edges; inferred edges);
- D-pipe top-1 score share;
- the D-pipe top-1 metric family (CPU, memory, disk, latency, error, network).

Two of Ch3's features are dropped:
- **Fault-signature hash:** a hash carries no ordinal information for a linear model, and would act as a case identifier.
- **Recent-deployment overlap:** no deployment events are captured.

The leakage test is extended: no feature may read the label file, the fault name or the capture directory name.

**P-c. Blast-radius tier: deterministic, not learned.**
- It comes from the snapshot's call graph: the number of services that transitively call the D-pipe top-1 service.
- Tiers: 1 for none or one caller, 2 for two to four, 3 for five or more.
- `unknown` when the snapshot has no call edges (every RCAEval case).

There is no label to learn it from, and a rule is auditable.

**P-d. Model and fit.**
- Multinomial logistic regression on standardised features, L2 with λ = 1 (the router's value; no tuning).
- Fitted once on all 558 build cases (495 RCAEval and 63 OTel v3).
- Reported, exploratory and build data only: five-fold cross-fitted accuracy, macro-F1, log loss and per-class confusion.
  - Folds are stratified by corpus and class.
  - The fold seed comes from `helios/research/seeds.py`.
- One fit run, with a refusal to overwrite its report, as in the S3.1 build tools.
- Parameters frozen to `data/frozen/acp_params.json` with a hash recorded in the freeze entry.

**P-e. Use in HELIOS-Full: recorded, not routed.**
- With `acp_stateful` ON, the ACP block (class probabilities, predicted class, blast-radius tier) is written to the CoE `R` step.
- The frozen router does not read it, so routing, fusion and every confirmatory measure are unchanged. A test checks this: Full's published list and routed arm must be identical with `acp_stateful` ON and OFF over the build corpora.
- The narrator does not cite the ACP block. It is not pipeline evidence, so H_fact and narrative scoring are unchanged.
- With `acp_stateful` OFF, the record is a uniform prior and tier `unknown`, as Ch3 specifies.

**P-f. E-H8 in Stage A.**
- Since the router does not read the ACP, Full and noACP route identically, so E-H8's latency-constraint satisfaction cannot differ by construction. τ_lat never binds on build data in any case (L max 23 s against 90 s).
- E-H8 is recorded in the OSF addendum draft as **not testable in Stage A**, with the reason.
- In Stage B the router is refit with the ACP block as features, and E-H8 is evaluated exploratorily there.

The alternative is to refit a candidate router with the ACP features now, on build data only, not adopted. That costs about one more day and gives no confirmatory gain.

## 4. Deliverables and effort

| Step | Work | Effort |
|---|---|---|
| 1 | Pre-run entry (this design, the class map, P-f) | — |
| 2 | `helios/acp/`: features, class map, blast-radius rule, model, params with hash, gated by `acp_stateful`; tests (leakage, gating, uniform prior, hash stability, Full routing unchanged ON vs OFF) | 1 day |
| 3 | CoE `R` step field; narrator exclusion test | ¼ day |
| 4 | `bin/acp_fit.py`: one cross-fitted fit, report `calibration/acp_fit.json`, freeze; freeze entry | ½ day |
| 5 | Full gate, tracking row DONE, PR | ¼ day |

S3.4 (Knowledge Cortex) moves to Stage B in the same pre-run entry: row S2-M8-ENG04 becomes DEFERRED with its reference.

## 5. Risks

- **The ACP is close to a fault-family classifier.** The signal-type indicators and the D-pipe metric family nearly name the class. High cross-fitted accuracy is expected and says little about real remediation prediction; the report says so.
- **Class imbalance.** `code` has 30 build cases and `config` 42, against 195 for `network` and 291 for `resource`. Macro-F1 and the per-class confusion are reported beside accuracy.
- **OTel classes are corpus-specific.** `config` comes only from OTel and `code` only from RCAEval, so the corpus is close to a feature. The per-corpus confusion makes this visible.
