# Sprint S4 — Product shell and evaluation tooling · plan

**Window:** 18–29 Jan 2027 (10 working days); starts early once the owner confirms, as S1–S3 did (S3 closed 2026-11-09, about nine weeks ahead) · **Milestone:** S2-M9 · **Exit tag:** `rb-s4-exit` · **Status:** in progress (started early 2026-11-11, owner); refreshed 2026-11-11 with the S3 carry-overs

Task details: `docs/tracking/helios_task_breakdown.md` § Sprint S4 (authoritative).

## Goal

HELIOS usable as a product (API, approval console, compose deployment), and everything needed to produce the evidence: baselines, metrics, run orchestrator with integrity gate, and the analysis suite.

## Entry conditions

| Condition | State (2026-11-11) |
|---|---|
| `rb-s3-exit` | **Met** (annotated tag on `946f3cb`, pushed); PR #87 (exit report, documentation sync) merged as `c75826f` |
| Baseline Docker environments from the S0.11 spike (`baselines/rcaeval/`, lead-time register L8) | **Met**: both images build and every agreed method imports; B4 PDiagnose needs an adapter (S4.8) |
| Docker memory at least 16 GB (S0.11 L9) | **Met** (owner, during S1; Docker reports 16 GB) |
| Working tree clean of unregistered data | **Met**: only edit-audit lines in `experiments/experiment_log.csv` (committed with this refresh) and the two kept local edits in the demo submodule |
| S2-M9 tracking rows added | **Done with this refresh**: ENG01–ENG11, RES01 (D11 recheck), GATE01, all PLANNED |

## Capacity

13½ days of the breakdown's tasks plus about 2 days of carried-in work (D11 recheck, timing fix, existing-code review), against 10 working days in the January window. With about nine weeks in hand before that window, **time is no longer the constraint**: the "Tier 2 to Stage B first" rule is not triggered by capacity. The Tier-2 items are decided on content instead (below). Order of work, evidence path first because phase E depends on it and the product shell does not:

| Step | Work | Why this order |
|---|---|---|
| 1 | S2-M9-RES01 D11 compute recheck | Carried from S3; sizes the L-pipe budget for E1/E3 and the S5.3 pilot (L5) |
| 2 | S4.9 metrics suite, including the S2-BL-13 timing fix | Everything downstream (orchestrator, analysis, baselines' scores) reads its outputs |
| 3 | S4.11 analysis suite | Depends only on S0.6; long and statistics-heavy, so built early |
| 4 | S4.10 run orchestrator and integrity | Needs S4.9; dry run of the full schedule on fixtures |
| 5 | S4.8 baselines (D5) | Needs a scoring path to check its ranked lists; PDiagnose adapter |
| 6 | S4.1 API → S4.3 compose → S4.2 approval console | Product shell; S4.2 is the RQ4 instrument and waits on IRB only for the study itself, not for the build |
| 7 | Tier 2 (S4.4–S4.7) as decided below | Behind flags; must be in before `build-freeze` or moved |

## Tasks

| Task | Tier | Tracking | Effort | Depends on | Done when |
|---|---|---|---|---|---|
| D11 compute recheck against the measured escalation share | — | S2-M9-RES01 | ½ | S3.1 | Per-variant L-pipe run counts and hours recomputed; D11 design and lead-time register L5 updated; deviation entry only if the run design changes |
| S4.1 API | T1 | S2-M9-ENG01 | 1½ | S2.7 | OpenAPI spec; contract tests |
| S4.2 Approval console (RQ4 instrument) | T1 | S2-M9-ENG02 | 2 | S4.1, S2.8 | Walk-through; timing capture verified |
| S4.3 Compose deployment | T1 | S2-M9-ENG03 | ½ | S4.1 | Fresh install from the compose file alone |
| S4.4 PII redaction | T2 | S2-M9-ENG04 | ½ | — | Behind its flag with tests, or recorded as moved to Stage B |
| S4.5 Shadow / recommendation modes | T2 | S2-M9-ENG05 | ½ | — | Behind its flag with tests, or recorded as moved to Stage B |
| S4.6 FGSV lite | T2 | S2-M9-ENG06 | 1 | — | Behind `fgsv_ks_gate` with tests, or recorded as moved to Stage B |
| S4.7 IOL lite | T2 | S2-M9-ENG07 | ½ | — | Behind `iol_self_telemetry` with tests, or recorded as moved to Stage B |
| S4.8 Baselines from the RCAEval suite (D5) | T1 | S2-M9-ENG08 | 2 | S1.1, S0.10 | Each baseline produces ranked lists on build data; licences recorded |
| S4.9 Metrics suite | T1 | S2-M9-ENG09 | 1½ | S1.9, S2.4, S2.8 | Fixture values match hand computation |
| S4.10 Run orchestrator and integrity | T1 | S2-M9-ENG10 | 1½ | S4.9 | Dry run of the full schedule on fixtures |
| S4.11 Analysis suite | T1 | S2-M9-ENG11 | 2 | S0.6 | Fixture data reproduces hand-computed statistics |

### Existing code each task starts from

Several S4 tasks extend code that earlier sprints built; each starts by reading it, not by rewriting it.

| Task | Starts from |
|---|---|
| S4.9 | `helios/evaluation/scoring.py` (S1.9: HR@k, Avg@5, MRR into `eval_score`), `cost.py` (S1.10 CpR), `rater_agreement.py` (S2.9 κ, H_fact), H_struct rows (S2.4), `helios/consensus/timing.py` (first publication, entry 60). `helios/evaluation/metrics.py` is a May stub (`hr_at_k` only): fold it into the suite or retire it |
| S4.10 | `helios/integrity_gate.py` (per-run schema and hash checks, writes to the exclusion ledger), `bin/log_exclusion.py` (still described as a Stage 1+ stub), `helios/orchestrator/runner.py`, `bin/helios_run.py` |
| S4.11 | `helios/research/analysis_plan.py` (hypothesis tables, Holm ranks, α per rank; fingerprinted by the OSF freeze, so read it, never edit it without an entry) |
| S4.8 | `baselines/rcaeval/` (two pinned images, RCAEval at `2fca61b`), lead-time register §4 (spike findings) |

### Carried-in items that shape the tasks

**S2-M9-RES01 D11 compute recheck** (S3 exit §6). The D11 estimate (about 1,500 L-pipe runs, 30–50 h on the 8B model) assumed the cheap-first router. Measured on build data: OTel escalates every case (63/63), RCAEval 197 of 495 held out (40%). noRouter and LLM-only call the L-pipe on every case regardless. The pool is RCAEval *with* traces, which the router has never seen (S2-BL-01), so its escalation share is unknown: the recheck reports a range (RCAEval-build share up to every case) rather than a point, and the S5.3 pilot measures time per incident on build data. Never read pool data or labels to narrow it. — **Done 2026-11-11** ([s4_d11_compute_recheck.md](s4_d11_compute_recheck.md)). The escalation share does not drive compute: the response cache shares worker calls across variants, and LLM-only and noRouter cover every case. The LLM narrator does drive it, because it runs on every run of a narrated variant. E1 + E3 take about 5–6 h central, 11–14 h conservative, 52–67 h extreme: local compute suffices, the run design is unchanged, and no entry is needed. Found on the way: `p4_cognitive`, `fgsv_ks_gate`, `iol_self_telemetry`, `his_tier` and `sampling_regime_tag` have no consumer, so noCogni and HIS3 are left out of phase E (Tier-2 rule, D11 §4; Stage B work), and noFGSV and noIOL run only if S4.6 and S4.7 are built. **Update 2026-11-14:** S4.6 and S4.7 are built, so phase E includes noFGSV and noIOL; noCogni and HIS3 stay refused ([s4_4_7_tier2_design.md](s4_4_7_tier2_design.md)).

**S4.9 metrics suite**
- **S2-BL-13, timing.** First-publication time excludes graph building; entry 46 counts it in TTT. The scoring path adds graph-build time to TTT, reads the first publication (entry 60) and reports the hardware. The 90 s cutoff can flip the state between reruns: report non-convergence counts beside TTT.
- **S2-BL-18 remainder.** First publication's state is not stored; the scoring path derives it, with a test that both states score.
- **Operational TTCD and detection delay** (entries 71, 72): exploratory columns beside TTCD, never replacing it; TTCD and TTT split by trigger source with the fallback share.
- **`llm_unavailable` covariate** (S3.5): carried into every scored row so the analysis can report with and without affected incidents.
- **A-H5 split by stage and A-H1 split by escalation** (S3.1 design §2, §10): the routed arm per run is a scoring dimension.
- `metric_contract.md` is signed into OSF deposit 1: never edit it. Any metric definition that differs goes to the OSF addendum draft.

**S4.10 run orchestrator**
- Schedule covers 1,920 + 1,200 confirmatory/baseline runs and the exploratory set, including the E-H5 delayed-label subset (S3.3; seeded 25% of each pool corpus, run after confirmatory scoring) and the OTel v4 report (exploratory, not pool).
- The pool stays locked until `build-freeze`: the dry run uses fixtures and build data only.
- The schedule refuses an exploratory variant whose flag has no consumer (noCogni and HIS3; noFGSV and noIOL were refused until S4.6 and S4.7 were built on 2026-11-14), so no duplicate of Full is reported as an ablation (RES01 note).
- Every case starts with a fixed first variant (for example noRouter), whose calls fill the response cache and set the wall times every later variant replays. The run order is recorded, and the determinism rerun bypasses the cache (RES01 note).

**S4.11 analysis suite**
- Refuses to label exploratory data confirmatory; Family E (exploratory) gets BCa intervals without Holm.
- E-H5 as registered compares RRE for Full and noReconcile on different case sets (selection, S3.3 design §6 item 3). The suite implements whichever form the owner's addendum decision fixes; until then, both forms are built and the registered one is the default.

**S4.8 baselines**
- PDiagnose (B4) is a one-case script in RCAEval: faithful adapter with every departure recorded (deviation entry). Alternates CIRCA, then CausalRCA.
- Trace-based baselines (TraceRCA) have no trace data outside the pool in RCAEval: run them on OTel build captures converted to RCAEval format.
- Run with `--network none`; never on pool data before `build-freeze`.

### Tier-2 items: decide on content, not capacity

Capacity no longer forces S4.4–S4.7 out. What decides each is whether it changes the frozen evidence path or the variant hashes.

**Owner decision 2026-11-11:** all four are built in S4. S4.4 and S4.5 are built as option (a), product settings outside the VCL manifest; the variant hashes and `variants.py` are unchanged, so no VCL re-freeze is needed. S4.6 and S4.7 are built behind their existing flags.

| Item | Flag | Consideration | Recommendation (decided as below) |
|---|---|---|---|
| S4.6 FGSV lite | `fgsv_ks_gate` exists, ON in HELIOS-Full | HELIOS-noFGSV (E-H4) exists but behaves exactly like Full until FGSV is built, so E-H4 cannot differ. FGSV validates remediation; it does not change the ranking | **Build in S4** |
| S4.7 IOL lite | `iol_self_telemetry` exists, ON in HELIOS-Full | Same as FGSV: HELIOS-noIOL (E-H6) is a no-op today. Self-telemetry must stay out of the incident graph the pipelines rank (`tenant=self` only), or it changes Full's verdicts | **Build in S4**, with a test that Full's verdicts on build data are byte-identical with the flag ON and OFF |
| S4.4 PII redaction | **None** in the 17-flag registry | A new VCL flag changes every variant hash and `variants.py` (OSF-fingerprinted): deviation entry and re-freeze of the VCL. Redaction before the LLM call also changes L-pipe inputs, so the response cache and frozen prompt inputs no longer match unless redaction is a no-op on the data | Owner decision: (a) product setting outside the VCL manifest, OFF in evidence runs, with a build-data no-op check; or (b) Stage B |
| S4.5 Shadow / recommendation modes | **None** | Product-shell behaviour (never writes to production); does not touch ranking. Same flag question as S4.4 | Owner decision: (a) product setting outside the VCL manifest, recommendation mode for evidence runs; or (b) Stage B |

## Owner items

| Item | Source | Needed by |
|---|---|---|
| Confirm the early start of S4 (as for S1–S3) | This refresh | **Done 2026-11-11** (S4 started early) |
| Decide S4.4 and S4.5 (table above); confirm building S4.6 and S4.7 in S4 | This refresh | **Done 2026-11-11**: S4.4 and S4.5 as product settings outside the manifest (option a); S4.6 and S4.7 built in S4 |
| IRB: status of the RQ4 application (L1 said submission around 2026-11-03). S4.2 is the instrument; the study runs only if approval arrives by early February | S0.11 L1 | Approval by 2027-02-05 |
| Rater 2 and adjudicator (L2, L3; row S2-M5-RES05) | Carried since S0 | 30 Nov 2026 |
| S2.9 rater training to κ ≥ 0.7, rubric freeze, row S2-M7-RES01 | S2 exit | Before S5 |
| E-H5 addendum decision (RRE selection between Full and noReconcile) | S3 exit §6 | Before `build-freeze`; S4.11 builds both forms meanwhile |
| OSF addendum deposit (entries 46–83 and the S4 entries) | S2-BL-05 | Before `build-freeze` |
| Back up `.env`, `.env.labelling`, `data/cache/lpipe_cache.sqlite`, `data/labelling/build`; confirm the key backups (L10 still "partly done") | S2-BL-17, -19; L10 | Now |
| GCP and Azure price-book profiles checked | S1 carry-over | Before `build-freeze` |
| Hook commands use `$CLAUDE_PROJECT_DIR` (approve the `.claude/settings.json` change) | Open since S0 | Any time |
| Chair call (end of November): call-reference doc with an outcomes table; agenda in the S3 exit report §5 | S3 exit | Prepared from about 2026-11-20 |

## Expected deviation entries

PDiagnose adapter and any departure from RCAEval's script (S4.8); a baseline replaced by an alternate (S4.8; logged before phase E); TTT with graph-build time if the scoring path changes what entry 46 measures (S4.9); any new VCL flag (S4.4/S4.5 option (a) avoids this); FGSV and IOL parameters if frozen (S4.6, S4.7); the D11 run design if the recheck changes it (RES01); Tier-2 items moved to Stage B.

## Exit criteria

Tier-1 tasks DONE; RES01 DONE; each Tier-2 task DONE behind its flag or recorded as moved; full gate green on main; CI green on the S4 merges; tag `rb-s4-exit` (pushed); exit report written, with the status of every carried-in item above.

## Risks

| Risk | Mitigation |
|---|---|
| PDiagnose (B4) is a one-case script in RCAEval (S0.11 finding) | Faithful adapter with every departure recorded; alternates CIRCA, then CausalRCA |
| Trace-based baselines first run only now (no trace data outside the pool in RCAEval) | Run on OTel build captures converted to RCAEval format |
| CausalRCA takes 5–7 minutes per case | Used only if needed as an alternate; budget about a day for 240 cases |
| Pool escalation share unknown, so L-pipe compute for E1/E3 may exceed 30–50 h | RES01 reports a range; S5.3 pilot measures time per incident; L5 compute decision by 2027-02-05 |
| IOL or FGSV leaks into the ranked graph and changes HELIOS-Full's verdicts | Byte-identical verdict test on build data, flag ON vs OFF |
| A metric or analysis choice drifts from the signed metric contract or `analysis_plan.py` | Both are read-only; differences go to the addendum draft with a deviation entry |
| IRB approval misses early February | S4.2 is built and verified regardless; E4 is dropped from phase E, not rushed |
