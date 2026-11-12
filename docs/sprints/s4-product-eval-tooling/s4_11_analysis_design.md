# S4.11 Analysis suite — design (for owner approval)

**Row:** S2-M9-ENG11 · **Effort:** 2 days · **Depends on:** S0.6 (analysis plan), S4.9 (`eval_score`, `eval_run`) · **Status:** draft, 2026-11-12

## 1. Scope and fixed inputs

The suite runs the deposited analysis plan. It never changes what the plan says. Where the plan leaves a computation open, this note proposes one rule, and the chosen rules go into one deviation entry and the OSF addendum draft before any confirmatory data exists. This follows the S4.9 pattern (entry 84).

Read-only inputs:

- `helios/research/analysis_plan.py`: families, ranks, α, tests, directions, strata, asymmetric rule, settings. It is fingerprinted by the OSF freeze and is never edited.
- `research/osf/preregistration.md` §5 and §8, and `docs/tracking/metric_contract.md` (signed, never edited).
- `helios/research/seeds.py`: `bca_seed(hypothesis_id)`, one registered seed per hypothesis.
- Entries 36, 59, 65, 67, 69, 84 and 85. They fix the A-H5 matching, the A-H7 measures, the A-H5 split by stage, the A-H1 split by escalation and both strata.

Data: the harness-written tables `eval_score` (per list) and `eval_run` (per run) only (contract §10, entry 84). Pairing is by case: one run per case, variant and registered seed (D11).

Not in S4.11: the MCAR test and IPW are in S4.10 (row ENG10). The cell rule (at least 80% of cases included) is bookkept by S4.10; S4.11 reads its result.

## 2. What exists

| Item | State |
|---|---|
| `scripts/analyse_results.py` (May, M4) | Two-sided Wilcoxon plus statsmodels Holm on OTel HR@3; drops untestable hypotheses (R1 matrix §2 "ALIGN"). Exploratory only. It is retired by this task and replaced, not extended |
| scipy 1.17, statsmodels 0.14 | Pinned; enough for the binomial, normal, bootstrap and MixedLM pieces |
| Seeds | `bca_seed` slots exist for every A, B and E hypothesis |

## 3. Decisions (for approval)

### T-a. Holm step-down: data order (recommended) or pre-registered order

The pre-registration says: "Holm-Bonferroni step-down … over all eight hypotheses each; α by rank = 0.05 / (9 − rank)", and each hypothesis has a rank (A-H3 = 1, A-H7 = 2, …). The plan does not say whether the step-down walks the hypotheses in the order of their observed p-values or in their registered rank order. The two readings give different results.

- **Recommended (a): standard Holm.** Sort the eight observed p-values in ascending order and compare the k-th smallest with 0.05 / (9 − k). Stop at the first one that fails; it and everything after it are not rejected. The registered rank sets only the tie order and the report order, and the α column of the table is the threshold "if tested k-th". This is what "Holm-Bonferroni step-down" names, and it keeps the family-wise error at 0.05 under any dependence.
- (b) Fixed-sequence: test in rank order (A-H3 at 0.00625, then A-H7 at 0.007143, …) and stop at the first failure. This also controls the error rate, but a miss on A-H3 blocks every later hypothesis.
- Either way, a hypothesis that cannot be tested gets no p-value. It is placed last, counts as not rejected and is never dropped from the family (pre-registration §5). The adjusted p-values (Holm's step-down maximum) are reported too.

**This is a reading of the pre-registration, so it is a chair-call item.** The suite builds both readings. The approved one is the binding output; the other is reported as a sensitivity row, labelled as such.

### T-b. Wilcoxon signed-rank: zeros, ties and the exact distribution

- Differences are a − b in the registered direction (for A-H5, B-H6 and B-H7 the side named first is predicted to cost more or take longer). The test is one-sided, with the alternative "a greater".
- **Zeros dropped** (Wilcoxon's method). **Ties get midranks.** The p-value is the **exact conditional distribution** of the signed-rank statistic given the observed midranks, enumerated over all sign patterns by dynamic programming over doubled midranks (which are integers). This is deterministic, needs no normal approximation and is exact under ties.
- With no non-zero difference, the hypothesis is tested but not rejected (p is the maximum, recorded as such).
- **Finding, no change proposed.** HR@3 per case is a 0/1 outcome, so the paired difference is −1, 0 or +1. With zeros dropped, every non-zero |d| ties, and the Wilcoxon test becomes the exact sign test on discordant pairs. This holds for A-H1, A-H2, A-H3, A-H4, A-H6 and A-H8 (and it is McNemar's exact test without the mid-p). The reports say so beside each of those tests. The test runs as registered.

### T-c. A-H7 sign test over two measures

The plan names "H_fact, H_struct" for one rank. The contract says "the rater labels are the A-H7 measure" and "the per-case sign of (Full − noLLM), sign test".

- **Recommended (a): an intersection–union test.** One exact one-sided sign test on H_fact (rater labels) and one on H_struct, each on the per-case sign of (Full − noLLM) with zeros dropped. A-H7 is rejected only when both are rejected; its p-value is the larger of the two. This keeps one Holm slot and controls the error rate without adjustment.
- (b) H_fact only as the binding test, with H_struct descriptive.
- (c) One sign test on the per-case sum H_fact + H_struct.
- Under entries 65 and 67 the H_fact difference is expected near zero, and noLLM's H_struct is a structural zero (entry 59). Under (a), A-H7 is likely to stay unrejected, as entry 65 already records. The test runs as registered. A case with pending labels has no H_fact (entry 84) and leaves the pair, counted.

### T-d. A-H5 matched HR@3, and its splits

- **Primary (contract §5):** the cases where noRouter and Full have the same HR@3 outcome; Wilcoxon on log-CpR (noRouter − Full). The share of matched cases is reported.
- **Sensitivity:** all cases, as registered.
- **Split by stage** (entry 69): stopped versus escalated, for the Full run. It is descriptive, with BCa intervals.
- **Pending the chair call (S4.9 CpR finding):** log-CpR without the opportunity component is computed as a descriptive column, labelled exploratory. It becomes a registered sensitivity analysis only if the owner chooses option (b) with its own entry.

### T-e. McNemar exact mid-p (B-H1 to B-H5)

Let b be the cases where Full hits and the baseline misses, and c the reverse; n = b + c. The one-sided mid-p is P(X > b) + ½ P(X = b), with X ~ Binomial(n, ½). With n = 0 the hypothesis is tested but not rejected. Computed with exact rational arithmetic (`fractions`) and then converted, so the fixture values are exact.

### T-f. Effect sizes

- **BCa:** scipy `bootstrap` (method BCa, 10,000 paired resamples of cases, `random_state = bca_seed(id)`). The statistic is the mean paired difference of the primary metric (delta HR@3, delta log-CpR, …), matching the registered expected effect. When every resample gives the same value (BCa undefined), the point estimate is reported with no interval and the reason.
- **Cliff's δ** with every Wilcoxon, as registered: over all cross pairs (a_i, b_j), (#a > b − #a < b) / (n_a n_b). It ignores the pairing; the reports say so.
- **Hodges–Lehmann** for every paired difference: the median of the Walsh averages of the differences. On 0/1 outcomes it is often 0, which is reported as is.
- **Cohen's h** for HR@3 proportions, beside the registered commitment (h ≥ 0.276).

### T-g. Sensitivity analyses (registered list)

- **Group-level Wilcoxon:** per-group means of each variant over the 78 groups (system × root-cause service × fault, from the signed ground truth after the freeze), then the same exact Wilcoxon.
- **Rank-based mixed model:** pooled ranks of the outcome over both variants, regressed on variant with a random intercept per group (statsmodels MixedLM, REML). The coefficient and its one-sided p are reported. **ICC** = group variance / (group + residual variance).
- **Benjamini–Hochberg** at q = 0.05 within each family, as a sensitivity row.
- **Paired t on log values** for B-H6 and B-H7 (log time, log-CpR). For B-H8 (Avg@5, not a log quantity) the paired t runs on the raw values. The plan says "log values for B-H6–B-H8"; this reading needs one line in the entry.

### T-h. Sanity floors (contract §8)

- **Random over all services:** per case, k / n_services (capped at k ≥ n), where n is the number of `candidate_services` in the case's signed ground truth, averaged over cases.
- **Prior-only:** 3/5 for HR@3, as registered.
- **HELIOS-D:** measured.

These are reported beside every HR@k result.

### T-i. Confirmatory guard ("refuses to label exploratory data confirmatory")

A run of the suite is **confirmatory** only when every input row is on the pool corpus, tag `build-freeze` exists, every variant hash matches the frozen `variant_hashes.json`, and `metrics_version` and the price-book digest match the frozen record. Otherwise every output is labelled **exploratory** and carries no "rejected" wording (p-values are reported as descriptive). The guard is a function with its own tests. Family E is always exploratory: BCa only, never Holm.

### T-j. Outputs

`bin/analyse.py` writes one versioned JSON (`analysis-v1`) and a Markdown table per family. It records:

- per hypothesis: n pairs, n excluded with reason, test, statistic, p, the Holm threshold and decision, BCa, Cliff's δ, HL, Cohen's h and the asymmetric-rule wording;
- the sanity floors, the sensitivity rows and the splits (A-H5 by stage, A-H1 by escalation, `llm_unavailable` with and without);
- digests of the input tables, the `analysis_plan.json` hash and the seeds used.

It prints counts and statistics only, never case IDs. E-H5 is built in both forms (registered default, plus the S3.3 §6 same-case form) until the addendum decision.

## 4. Deviation entry and addendum

One entry before merge records T-a to T-h as computational rules: the Holm reading, Wilcoxon zeros and exactness, the A-H7 combination, the McNemar mid-p formula, the BCa statistic, Cliff's δ and HL, the sensitivity details, the random floor and the confirmatory guard. No hypothesis, comparison, metric, α or rank changes. The same text goes into the OSF addendum draft.

## 5. Deliverables and effort

| Item | Effort |
|---|---|
| `helios/analysis/tests.py`: exact Wilcoxon, sign test, McNemar mid-p, paired t | ½ day |
| `helios/analysis/effects.py`: BCa, Cliff's δ, HL, Cohen's h; `multiplicity.py`: Holm (both readings), BH; `sensitivity.py`: group-level, mixed model, ICC | ½ day |
| `helios/analysis/run.py`: pairing from `eval_score` / `eval_run`, families, strata, splits, floors, guard; `bin/analyse.py`; retire `scripts/analyse_results.py` | ½ day |
| Fixtures with hand-computed values (one per test, Holm both readings, BH, BCa reproducibility under the seed, HL, Cliff's δ, ICC on a balanced design), and an exploratory build run on OTel v3 (Full vs noRouter, Full vs noLLM, as data exist) | ½ day |

**Done when** (task breakdown): fixture data reproduces hand-computed statistics.

## 6. Risks

| Risk | Handling |
|---|---|
| The Holm reading is contested at the chair call | Both readings built; the approved one binds; the entry records it |
| Binary HR@3 makes Wilcoxon a sign test | Reported as a finding; the test runs as registered |
| BCa degenerate on near-constant differences | Point estimate without interval, with the reason |
| Exploratory output mistaken for confirmatory | Guard plus "exploratory" labels on every output; tests |
