# Sprint S2 — backlog to revisit

**Date:** 2026-10-31 · **Owner direction:** review and fix these after the remaining S2 tasks (S2.7 Chain-of-Evidence ledger, S2.8 narrator with grounding verifier, S2.9 rubric) are finished · **Source:** S2.1–S2.5 build runs, design notes §10, fresh reviews, deviation entries 46–63

Each item: what was observed, why it matters, the evidence, and where it is best handled. IDs are stable; close an item by noting the commit, entry or decision that resolved it. A change that alters what a confirmatory test measures needs a deviation entry (and the OSF addendum) **before** confirmatory data exists.

## A. Threats to the confirmatory results (highest priority)

| ID | Item | Why it matters | Evidence | Where |
|---|---|---|---|---|
| S2-BL-01 | **Build → pool shift (T21).** The pool is RCAEval *with* traces; nothing was tuned or checked on that combination: G-pipe never saw RCAEval traces, the L-pipe trace worker is off on the pool (k ≤ 2), MAHC's three-pipeline regime rests on 44 OTel cases | Pool behaviour of G-pipe, L-pipe and MAHC's confidence is unmeasured until the confirmatory run | Entries 57 (L-f), 63; `calibration/mahc_frozen_check.json` | Pre-register an analysis split by G-pipe participation (OSF addendum) before `build-freeze` |
| S2-BL-02 | **Ceiling and power.** On RCAEval build, D-pipe alone 0.945, L-pipe 0.972, MAHC 0.974; A-H4 is near null (ambiguous stratum MAHC vs vote-only: OTel 28 vs 27 of 39; RCAEval 132 vs 133 of 141) | Little room for A-H1 (noLLM) and A-H4 (noConsensus) to show an effect | `calibration/mahc_run3.json`; design S2.5 §10 | Chair call: A-H4 power and the size of the pool's ambiguous stratum |
| S2-BL-03 | **Every build figure is in-sample.** Detector, D-pipe, G-pipe, L-pipe prompts and MAHC were all fixed on the same 63 + 495 build cases | Build HR@3 cannot be read as out-of-sample; only the pool is clean | Entries 52–63 | Chapter 4 wording: build figures exploratory only |
| S2-BL-04 | **Choices made after inspecting build results.** MAHC runs 1–3 (two withdrawn), the L-pipe prompt round (round 1 kept), G-pipe selection amendments (entry 55) | Forking-paths critique from an examiner | Entries 55, 56, 58, 61, 62, 63; withdrawn reports kept | Chapter 4: a decision-log table built from the entries |
| S2-BL-05 | **Pre-registration behind the code.** Entries 46–63 change what several tests measure: TTT read as first publication; H_struct option (b); L-pipe trace skip (k ≤ 2 on the pool); MAHC calibrated-confidence floor replacing Ch3's entropy floor; modality level dropped from the priors | Confirmatory tests must match what was pre-registered | Entries 46, 57, 59, 60–63 | OSF addendum, deposited before any confirmatory data; also `metric_contract.md` §9 correction |

## B. Weak components (product quality)

| ID | Item | Why it matters | Evidence | Where |
|---|---|---|---|---|
| S2-BL-06 | **Routing gate costs G-pipe cases.** G-pipe runs on 44 of 63 OTel cases; ungated it scored 50/63 (S2.2), above the fused 49. Threshold 0.20 dates from May | Lost accuracy on exactly the cases G-pipe is for | S2.2 selection report; `mahc_run3.json` | S3.1 router (a change to the frozen gate needs an entry) |
| S2-BL-07 | **L-pipe is the weakest pipeline on OTel** (44/63, below D 48 and G): log digest often empty after the trigger; metric worker alone beat the merged list on held-out OTel (23 vs 22 of 31); on RCAEval close to a single metric reader | Weak LLM contribution to the fused result | `calibration/lpipe_round3.json`; design S2.3 §10 | Stage B (8B model is the ceiling); digest coverage review |
| S2-BL-08 | **MAHC confidence discriminates modestly.** OTel 0.85 confirmed vs 0.72 provisional; RCAEval 0.99 vs 0.95, so 38% of easy RCAEval cases go to a human; 6 distinct confidence levels; held-out confidence runs low | Operations cost (needless escalations); IN2 claim must be modest | `mahc_run3.json`, `mahc_frozen_check.json` | Stage B calibration work; Chapter 4 reporting |
| S2-BL-09 | **Signal type unclassified on 54% of OTel cases** (34/63; RCAEval 31/495); log-driven triggers are typed from the suspect's strongest metric series | Priors fall back to global; error-level logs not used | Entry 60; design S2.5 §5.1, §10 | Revisit signal-type rules (new entry before any refit) |
| S2-BL-10 | **G-pipe learned ranker adds 2 cases over D-pipe;** ghost-edge weights never exercised on held-out folds; same mean-loss L2 convention that over-regularised MAHC (harmless for ranking) | Small lift; untested features | Entry 56; `helios/pipelines/g_pipe/rankers.py` | S2 exit note; Stage B |
| S2-BL-11 | **Two faults missed by every method:** emailMemoryLeak (slow leak) and recommendationCacheFailure (silent at the root) | Known blind spots | T14; S2.2 and S2.3 reports | Chapter 4 limitations; Stage B fault coverage |
| S2-BL-12 | **Detector and D-pipe:** fallback trigger time uses the window peak (non-causal); D-pipe propagation inert on build data; D-pipe propagation raises scipy ConstantInputWarning on some real windows (silenced only in tests) | TTCD/TTT on fallback triggers look ahead; dead mechanism; hidden warning | Entries 52, 53; `tests/test_runner_lpipe.py` | S2 exit gate |

## C. Measurement details

| ID | Item | Why it matters | Evidence | Where |
|---|---|---|---|---|
| S2-BL-13 | **Timing:** first-publication time excludes graph building (entry 46 counts it in TTT); the 90 s cutoff can flip the state between reruns; timing is specific to the M5 Pro; replay assumes G-pipe starts after D-pipe | TTT and non-convergence comparability | Entries 46, 60; `helios/consensus/timing.py` | Scoring path (S4) must add graph-build time; report hardware |
| S2-BL-14 | **H_struct option (b):** counts invented services and evidence IDs as well as malformed answers; noLLM is a structural zero; rows only for stored runs | A-H7 reading | Entry 59 | Chapter 4 definition; chair call |
| S2-BL-15 | **Narrative (IN1) not built yet;** noLLM, D and G need a model-free narrator because S2.9 rates noLLM narratives | Otherwise "noLLM" contains an LLM | Design S2.3 §5.5 | S2.8 design |

## D. Engineering and process debt

| ID | Item | Why it matters | Evidence | Where |
|---|---|---|---|---|
| S2-BL-16 | **63+ local commits never run by CI** (S2.3 PR 2, S2.4, S2.5/S2.6, validator fix), held back for the GitHub Actions quota | Environment differences surface all at once in one large push | `git status`: main ahead of origin/main | Push and open one PR as soon as minutes allow |
| S2-BL-17 | **L-pipe cache must be preserved:** cache-only reruns need `data/cache/lpipe_cache.sqlite` (gitignored), the same llama3.1:8b digest (`46e0c10c039e…`) and a local Ollama; real-model determinism checked on 10 cases | Losing the cache means new model calls and new timings | Entries 57, 58 | Back up the cache with `.env`; extend the determinism check |
| S2-BL-18 | **Deferred minor items:** vote-only scores on a different scale from MAHC's; first publication's state not stored; one runner test accepts either state; a pipeline unseen on build data gets prior 1 (labelled "global"); `BuildCase` does not enforce non-empty votes; masking edge cases (`cartservice2` → `svc-032`, short names over-mask ordinary words, names only in message text such as `redis` not aliased) | Polish and edge cases | S2.3, S2.4, S2.5 review ledgers | When convenient; tests first |
| S2-BL-19 | **Owner items:** IRB; rater 2 by 30 Nov; back up `.env`; chair call covering S2-BL-02, 05, 06, A-H4, the TTT reading and the pool's two-worker L-pipe | Blocking for S2.9 and confirmatory runs | `plan.md` owner items | Owner; call-reference doc with an outcomes table before the call |
