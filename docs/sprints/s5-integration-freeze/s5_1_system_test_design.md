# S5.1 System test of every variant · design

**Row:** S2-M10-EVAL01 · **Status:** approved by the owner 2026-11-15 (S-a to S-g as written) · **Plan:** [plan.md](plan.md) step 2 · **Carries:** S5.2 design D-e (the per-variant dynamic check)

## 1. What the test has to show

Done-when (breakdown): "15 variants run end to end on build data". In Stage A that means:

- the 13 runnable variants complete through the phase E campaign machinery, unchanged, on build data;
- noCogni and HIS3 are refused, with the recorded reason;
- every switched-off `VCLFlag` leaves its visible mark on every run (S5.2 D-e), and does nothing else that the certificate does not declare.

It is a **system test**, not an evaluation. No hypothesis is tested, and no metric is read as a result. Scoring, cost and timing belong to the S5.3 pilot, which reuses these runs (§4, S-f).

## 2. Starting point

- `bin/helios_campaign.py` (S4.10): plan, run, resume, cells, compare.
  - The schedule runs noRouter first in each case, then Table 17 order.
  - Each campaign directory has its own anchored ledgers.
  - The schedule refuses noCogni and HIS3 (S5.2 `NO_CONSUMER`).
- The S4.10 build dry run (2026-11-13) ran 504 confirmatory and 189 exploratory specs on OTel v3 with a cache-only client and no exclusions. noFGSV and noIOL were not yet built, and RCAEval build and the May captures were never run as a campaign.
- Model server: `llama3.1:8b`, digest matching entry 58 (`bin/check_model.py`, 2026-11-15).

## 3. Decisions (S-a to S-g)

**S-a Corpora.** Three build corpora, each in its own campaign directory under `data/campaigns/s5_1/`. That path is not ignored by git today, so a `.gitignore` line is added with the code: the stores are too large for git. Their digests go in the report, and the directories go into the owner's backup set with the cache.

| Corpus | Cases | Why |
|---|---|---|
| OTel build v3 (`otel_build_v3`) | 63 | All modalities and traces; the only corpus with structure (FGSV, structural edges) |
| RCAEval build (`build`) | 495 | Same benchmark family as the pool; no structure, so the variants without a graph path get exercised |
| May captures (`captures`) | 20 | Older demo version: a robustness check that the frozen chain survives a different capture vintage |

**Not used:**
- **the pool**, which stays locked until `build-freeze`;
- **OTel held-out v4**, which entry 76 limits to one read, already spent.

*Alternative:* OTel v3 only, which takes about 30 minutes. It would leave the corpus closest to the pool untested end to end. I don't recommend it.

**S-b Protocol.** The phase E campaign as it stands:
- `plan`, then `run --phase confirmatory` and `run --phase exploratory`;
- 8 confirmatory and 5 exploratory variants (noACP, noReconcile, noFGSV, noIOL, noExpl);
- the live model, with the response cache in front of it.

These phases are not run here:
- **Baselines:** S5.3 needs them for cost and timing, so it runs them in the same directories.
- **Rerun:** that is S5.5.
- **The perturbed E-H4 and E-H6 variants:** these are exploratory runs with their own planning options.

Nothing in the code or the frozen files changes for the test. No hypothesis-bearing number is read before S5.3 scores the stores.

**S-c Checks, in a new checker.** Code: `helios/evaluation/system_test.py`, with the CLI `bin/system_test.py --dir <campaign>`. It reads the store, the CoE files, the schedule and the ledgers, and never ground truth.

1. **Completion.** Every scheduled spec is either passed, or excluded with a ledger entry and a reason. The checker reports zero `GatedComponentInactiveError`, zero run errors, zero retries left pending, and gate exclusions counted per reason.
2. **Refusal.** `schedule.json` refuses exactly noCogni and HIS3, and its reason names their no-consumer flags.
3. **Flag signatures (S5.2 D-e).** For every run and every boolean flag, the checker verifies the visible mark of the flag's state. The exact field names are fixed during implementation from the CoE and verdict schemas.

   | Flag | OFF leaves | ON leaves |
   |---|---|---|
   | `dpipe` | D-pipe verdict skipped | D-pipe verdict ranked or failed with a reason |
   | `gpipe` | G-pipe skipped; routing reason `gpipe_off` | G-pipe decided by router or uniform rule |
   | `l2b_graph` | No graph built; G-pipe skipped | Graph snapshot hash recorded |
   | `ueg_structural` | No structural edges in the snapshot | Structural edges where the corpus has topology (OTel) |
   | `dpipe_propagation` | No propagation evidence in the D-pipe output | Propagation evidence when a graph exists |
   | `l2c_llm` | L-pipe skipped; template narrator | L-pipe asked when routed or uniform; LLM narrator |
   | `mahc_hierarchical` | Uniform Borda fusion | MAHC fusion record |
   | `cbr_routing` | Routing mode `uniform` | Routing mode `routed` |
   | `acp_stateful` | ACP block with the uniform prior | ACP block with the frozen ACP hash |
   | `coe_narrative` | No step N | Step N present |
   | `fgsv_ks_gate` | Step A `UNVALIDATED` / `fgsv_off` | Step A with PASS, FAIL or STALE, or a recorded reason |
   | `iol_self_telemetry` | No step S | Step S present |
   | `reconcile_terminal` | No in-run mark (the E-H5 replay reads it after scoring) | Same; checked by the replay check below |

4. **Verdicts that must not move.** Four variants differ from Full only in recorded steps, never in the ranking: noACP (entries 82–83), noFGSV, noIOL (entry 89) and noReconcile (in-run). Their fused verdicts must be byte-identical to Full's on every case. noExpl must have identical fused verdicts and differ only by having no step N. For the confirmatory variants, the report gives the number of cases whose fused top-1 differs from Full. That is a count, not a check.
5. **Integrity.**
   - `verify_ledgers.py --campaign` passes on every directory;
   - every capture's seal checks;
   - every run's variant config hash matches the frozen variant table;
   - parameter hashes in every run equal the `data/frozen/` hashes.

**S-d In the main test job (S5.2 D-e).** `tests/test_system_test.py` runs the checker on a small campaign built in the test from the existing runner fixtures: each of the 13 runnable variants on two fixture cases, with a stub model client. Every signature row is asserted, and a planted wrong mark (a step S in a noIOL run) must fail. This is the per-variant dynamic check CI runs on every PR; the build-data campaigns are the one-off certification.

**S-e Defects.** A failed check is a defect. It is fixed in its own commit before the freeze, and the affected corpus is rerun from scratch, in a new directory; the old directory is kept as a record. If a fix changes a frozen parameter, a variant, or what a pre-registered test measures, it gets a deviation entry first, with your approval of the text. A check that turns out to be wrong is corrected in the checker and reported as such, never by editing a run.

**S-f Hand-over to S5.3.** The three campaign directories are the pilot's runs. S5.3 adds the baseline phase, scores them with `bin/score_runs.py --metrics`, joins `determinism.json` (S5.5), and writes the pilot report: metrics, cost and timing, labelled exploratory. This avoids running the same 7,500 runs twice.

**S-g Report.** `docs/sprints/s5-integration-freeze/s5_1_system_test.md`, with a JSON beside it:
- per corpus and variant: scheduled, passed, excluded (by reason), wall time;
- every check with its result;
- campaign directory digests;
- the fused top-1 difference counts.

It is labelled exploratory build data. The S5.2 audit-log row gets its dynamic result from it.

## 4. Compute and order

| Step | Runs | Estimate |
|---|---|---|
| OTel v3 | 63 × 13 = 819 | Under an hour (S4.10: 693 runs in about 12 minutes cache-only; narrator and step-S calls add some) |
| May captures | 20 × 13 = 260 | Under an hour |
| RCAEval build | 495 × 13 = 6,435 | The long one. The worker cache covers the router and validation runs (entries 69–81), but narrator calls for RCAEval are partly uncached. Estimate 6–12 h on the 8B model, run overnight with resume |

Order: OTel v3 first, because it is quickest and exercises every flag. Then the captures, then RCAEval. Checks run after each corpus, so a defect stops the next corpus.

## 5. Done-when, files, deviation entry

- **Done when:** all three corpora are complete; every S-c check passes (or a defect is fixed and its corpus rerun); the report is written; the S-d test is in the main suite; the full gate is green.
- **Files:**
  - new: `bin/system_test_checks.py` (first `helios/evaluation/system_test.py`, see §6), `bin/system_test.py`, `tests/test_system_test.py`, the report and its JSON;
  - updated: the S5.2 audit-log row (dynamic result).
- **Deviation entry:** none expected; one only if a defect fix needs it (S-e).
- **Effort:** about 2 days of work, plus overnight compute, within the plan's 2.

## 6. Changes in execution (2026-11-15)

- **May captures dropped (owner decision 2026-11-15).** `bin/helios_campaign.py plan` reads each case's benchmark system from a signed ground-truth file, and the May file `data/ground_truth.json` was never signed. It is OSF deposit 1 data, so it stays untouched, and the tool is not changed for it. OTel v3 and RCAEval build already exercise every flag mark. S5.1 therefore runs two corpora, not three.
- **RCAEval build split into three campaigns of 165 cases.** The seed register (`helios/research/seeds.py`, 7,200 run slots) is sized for the 240-case pool, and a 495-case schedule runs past it. The split keeps every case, in manifest order, with no code change. Each part gets its own campaign directory, and its manifest (`rcaeval_build_{1,2,3}_manifest.json`, cases 1–165, 166–330, 331–495) sits beside it. Seeds repeat across the three parts, which is harmless on build data, where nothing is tested. The finding goes into the S5.3 pilot, because a phase E campaign larger than the pool would hit the same limit.
- **Checker moved to `bin/system_test_checks.py` (checker defect, fixed under S-e).** As first committed in `helios/evaluation/`, the checker reads manifest flags to verify run outputs, and the S5.2 scanner (entry 90: every runtime location in `helios/`) counted it as a runtime consumer. It reported two undeclared combinations, and it would have kept a flag "covered" even if the flag lost its real consumer. Under S5.2 D-b, `bin/` tools are reported separately and are never runtime readers, so the checker now lives there. The scanner and the certificate are unchanged (13 covered, 3 no-consumer, 9 declared rows, 0 violations), and so are the runs: the schedule's refusal does not depend on these reads. The moved checker reproduces the committed OTel v3 report byte for byte.
