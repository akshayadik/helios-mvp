# S5.1 System test of every variant · report

**Row:** S2-M10-EVAL01 · **Design:** [s5_1_system_test_design.md](s5_1_system_test_design.md) (approved 2026-11-15; changes in execution in its §6) · **Date:** 2026-11-15 · **Label:** exploratory build data. No hypothesis is tested here and no number below is a result.

**Outcome: PASS.** All 13 runnable variants completed end to end on both build corpora: 7,254 runs, with no exclusions and no run errors. noCogni and HIS3 were refused with the recorded reason. Every switched-off flag left its visible mark on every run, and no flag did anything the S5.2 certificate does not declare.

## 1. What ran

- **Code:** `s5/system-test` at 8a8648f. The checker has since moved to `bin/` (§5); no runtime code changed.
- **Model:** `llama3.1:8b`, the entry 58 digest, live, with the response cache in front of it.
- **Protocol (S-b):** `bin/helios_campaign.py plan`, then `run --phase confirmatory` and `run --phase exploratory`. Baselines, reruns and the perturbed E-H4/E-H6 variants were not run here; they belong to S5.3 and S5.5.

| Campaign directory (`data/campaigns/s5_1/`) | Cases | Schedule digest | Confirmatory runs | Wall time | Exploratory runs | Wall time |
|---|---|---|---|---|---|---|
| `otel_build_v3` | 63 | 7c45822bc145 | 504 | 1,812 s | 315 | 760 s |
| `rcaeval_build_1` (cases 1–165) | 165 | d3c725c2e88a | 1,320 | 2,040 s | 825 | 991 s |
| `rcaeval_build_2` (cases 166–330) | 165 | 77d48153812b | 1,320 | 2,022 s | 825 | 940 s |
| `rcaeval_build_3` (cases 331–495) | 165 | 24c07f80eeeb | 1,320 | 1,743 s | 825 | 832 s |
| **Total** | 558 | | 4,464 | 7,617 s | 2,790 | 3,523 s |

The whole system test took about 3 h 6 min of compute, far below the design's 6–12 h estimate for RCAEval. The worker cache covered most model calls.

**Two changes from the design** (§6, recorded 2026-11-15):
- **May captures dropped.** This was your decision: their ground-truth file was never signed, and it is OSF deposit 1 data, so it stays untouched.
- **RCAEval split into three campaigns.** The seed register has 7,200 slots and a 495-case schedule needs more, so the corpus runs as three parts of 165 cases.

## 2. Checks (S-c)

Each corpus has a JSON report from `bin/system_test.py` in [system_test/](system_test/).

| Check | OTel v3 | RCAEval 1 | RCAEval 2 | RCAEval 3 |
|---|---|---|---|---|
| **1 Completion:** every spec passed or ledgered; no `GatedComponentInactiveError`, run errors, open runs or gate exclusions | pass (819/819) | pass (2,145/2,145) | pass (2,145/2,145) | pass (2,145/2,145) |
| **2 Refusal:** exactly noCogni (`p4_cognitive`) and HIS3 (`his_tier`) | pass | pass | pass | pass |
| **3 Flag marks:** every run, every boolean flag, OFF and ON marks plus the variant config hash | pass: 0 problems in 819 runs | pass: 0 in 2,145 | pass: 0 in 2,145 | pass: 0 in 2,145 |
| **4 Unchanged verdicts:** noACP, noFGSV, noIOL, noReconcile and noExpl have pipeline and fused decisions identical to Full | pass: 0 of 63 cases differ, all five | pass: 0 of 165 | pass: 0 of 165 | pass: 0 of 165 |
| **5a Ledgers** (`verify_ledgers.py --campaign`) | pass | pass | pass | pass |
| **5b Capture seals:** a bad seal is a gate exclusion | pass (no gate exclusions) | pass | pass | pass |
| **5c Parameter hashes:** detector, dpipe, gpipe, mahc, router, narrator, acp and fgsv equal `data/frozen/` | pass | pass | pass | pass |

**ON marks that need the corpus to show them** (corpus level):

| Mark | OTel v3 | RCAEval (3 parts) | Reading |
|---|---|---|---|
| `ueg_structural` features in the G-pipe output | pass: 582 of 582 possible runs | not exercised: 0 possible | RCAEval has no traces, so no graph is built |
| `l2c_llm` L-pipe ranked | pass: 582 of 630 runs | pass: 1,932 of 4,950 runs | The router asks the L-pipe only when it is worth it |
| `dpipe_propagation` evidence | reported: 245 of 576 | not exercised: 0 possible | Evidence appears only where propagation changes a score. It is reported and never fails (design §6, S2.1 finding) |

OTel v3 is therefore the corpus that exercises the structural and propagation paths. RCAEval exercises the paths without a graph, as S-a intended.

## 3. Fused top-1 differences from Full

This is a count of cases, not a check and not a metric (S-c 4). It shows that each variant does something different where it should, and nothing where it should not.

| Variant | OTel v3 (63) | RCAEval (495) |
|---|---|---|
| HELIOS-D | 25 | 65 |
| HELIOS-G | 21 | 65 |
| HELIOS-LLM-only | 17 | 77 |
| HELIOS-noLLM | 19 | 65 |
| HELIOS-noConsensus | 4 | 3 |
| HELIOS-noRouter | 0 | 42 |
| HELIOS-noStructural | 7 | 0 |
| noACP, noFGSV, noIOL, noReconcile, noExpl | 0 | 0 |

**Readings:**
- noStructural differs only on OTel, the one corpus with topology.
- D and G give the same count on RCAEval. Without traces, G-pipe is skipped in every HELIOS-G run, and the two variants' fused rankings are identical on all 495 cases (checked on the CoE files).
- noRouter differs on RCAEval but not on OTel. Uniform routing asks every pipeline, and on RCAEval the L-pipe then moves some fused rankings.

## 4. Digests

| Directory | `schedule.json` | `campaign_log.jsonl` |
|---|---|---|
| `otel_build_v3` | 61ce7ca2dd45 | 85a4c16ec21e |
| `rcaeval_build_1` | 98d980f24261 | 2cc7973f0ea7 |
| `rcaeval_build_2` | b5f09988c0df | 2691b777bf5b |
| `rcaeval_build_3` | 51eb29bc911e | da06740a37f8 |

Every `exclusion_ledger.jsonl` is empty (e3b0c44298fc). The full SHA-256 values are in the JSON reports. The directories are gitignored, which is too large for git, and go into your backup set with the response cache.

## 5. Findings and hand-over

- **Defects:** none in the system. No check failed on any run, so no corpus was rerun, and no deviation entry is needed (S-e).
- **Checker defect (fixed):** the checker was first committed in `helios/evaluation/`, where the S5.2 scanner counted its flag reads as runtime code. It now lives in `bin/system_test_checks.py` (design §6). The certificate is unchanged, and the moved checker reproduces the OTel v3 report byte for byte.
- **Seed register (for S5.3):** 7,200 slots cover the 240-case pool schedule but not a larger one. A phase E campaign over more than the pool's cases would stop at `plan`. The pilot report records this and proposes whether to widen the register before the freeze, which would need a deviation entry.
- **S5.2 dynamic result:** the per-variant output checks (design D-e) pass. The audit-log row is updated to cite this report.
- **S5.3 (S-f):** the four directories are the pilot's runs. The pilot adds the baseline phase, scores the stores, joins `determinism.json` from S5.5 and reports cost and timing.
