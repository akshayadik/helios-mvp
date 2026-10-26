# S1.9 — Scoring path · design note

**Task:** S1.9 (tracking S2-M6-ENG07) · **Date:** 2026-10-26 · **Code:** `helios/evaluation/scoring.py`, `eval_score` in `helios/store/schema.sql`, `bin/score_runs.py` · **Deviation:** none (implements the deposited metric contract; see below) · **Flags:** scoring serves every variant and runs after dispatch, outside the run path

## What the contract asks

Metric contract §1–§2 (deposited with OSF deposit 1): accuracy is measured on **the fused ranked list a variant publishes**, per-pipeline lists are kept for diagnostics, and scoring is "computed after dispatch by the evaluation harness, from stored outputs joined to the sealed ground-truth file. Ground truth, case names and injection time are never given to any pipeline (D11 §3)". HR@k for k ∈ {1, 3, 10}; Avg@5 = (1/5) Σ_{j=1..5} HR@j (RCAEval); MRR = 1/rank, **0 if absent**. Missing values are never imputed.

## Design

| Piece | Implementation |
|---|---|
| Metrics | `rank_of`, `hr_at`, `avg_at_k`, `reciprocal_rank`, `score_ranking` → `CaseScore(rank, hr_at_1, hr_at_3, hr_at_10, avg_at_5, mrr)`; position in the stored list is the rank (ties were already broken by the producer) |
| Ground truth | `load_ground_truth(corpus)`: RCAEval build and pool files are HMAC-verified with the ledger key (the importer signed them); their labels are canonical service names, so matching is exact. OTel Demo captures (exploratory) say `adService` where the graph says `ad`, so they match by service stem (`service_key`, shared with `bin/khop_calibrate.py`). Exact matching stays the default because a stem rule would merge RCAEval's distinct `payment` / `paymentservice` |
| Pool lock | The pool's ground truth, and any stored run whose phase is confirmatory, are refused (`PoolLockedError`) until tag `build-freeze` |
| Stored runs | `score_store(store, gt)` scores every `result_row` list (`list_kind = pipeline`) and every `consensus_verdict` list (`list_kind = fused`, source = variant) into `eval_score` |
| Status rules | `skipped` pipelines (gated off, not dispatched) produced no list and are not scored; `abstained` and `failed` pipelines are scored as misses, with `source_status` kept so analysis can filter. Cases without a label are counted, never imputed. Re-scoring replaces rows |
| What is stored | Rank of the ground truth (NULL = absent), the five scores, list length, corpus, **SHA-256 of the ground-truth file**, `scoring_version`. Never the label itself |
| CLI | `bin/score_runs.py --db … --corpus build\|captures\|pool`: counts and per-list means only, never case names, incident IDs or labels |

## Ground truth removed from the pipelines

`run_dpipe` and Stage D (`DVerdict.compute`) took an optional `ground_truth_service` and computed HR@3 and MRR inside the pipeline. The orchestrator never passed it, but three May calibration scripts did. Both the parameter and the in-pipeline scores are removed; `scripts/calibrate_dpipe.py` and `scripts/smoke_ablation.py` now score the returned ranking with `score_ranking` after the call, and `scripts/calibrate_gpipe.py` simply stops passing the label (its LOO scoring was already after dispatch).

One definition changes in those scripts: Stage D gave MRR = 1/(n+1) when the ground truth was absent; the contract (and now the scripts) give 0. HR@3 is unchanged. The frozen D-pipe calibration (`data/calibrated_params.json`, Milestone 2, in the OSF freeze) was produced with the old Stage D and is **not** recomputed; its `loo_cv_mean_mrr` remains a May-definition descriptive value. No deviation entry: nothing a pre-registered test measures changes — the scoring path implements the deposited contract, and the D-pipe parameters stay frozen.

## Leakage tests (`tests/evaluation/test_no_ground_truth_leak.py`)

1. **Signatures:** no run-path entry point (`run_dpipe`, `run_gpipe`, `run_lpipe`, `should_run_gpipe`, Stage D, UEG-C builder, structural bundle, K-hop pruner, `RunOrchestrator.__init__` / `run`) has a parameter whose name contains ground, truth, label, root_cause or inject.
2. **Source scan:** no module under `helios/pipelines`, `graph`, `orchestrator`, `consensus`, `telemetry` or `schemas` uses `ground_truth`, `root_cause_service`, `inject_time` or imports `helios.evaluation` in code (identifiers, parameters, keywords, imports, non-docstring strings); a self-test proves the scan catches a leaky function.
3. **Runtime trap:** an orchestrator run with a ground-truth file next to the captures, and `open` / `Path.read_text` / `Path.read_bytes` instrumented, never opens it.

## Done-when

Fixture scores match hand-computed values: `tests/evaluation/test_scoring.py` (seven ranked lists worked by hand — first, second, fourth, seventh and eleventh of twelve, absent, empty — for every metric; a stored-run fixture with fused, ranked, failed, skipped and unlabelled rows). Coverage of `scoring.py` 99%.

## Open points

- **OSF addendum (with the next deposit):** `metric_contract.md` §9 says MRR lives in `PipelineVerdict.mrr`; since S1.8/S1.9 it is computed by the scoring path into `eval_score.mrr`. The file is in the deposit-1 digest and is not edited.
- The orchestrator does not fuse yet; fused lists come from `consensus_verdict` (written by `scripts/fuse_verdicts.py` today, by MAHC / vote-only in S2). The scoring path already scores them.
- `scripts/analyse_results.py` still computes HR@3 itself from the May database; it moves to `eval_score` with the analysis pipeline (phase A).
- Strata (ambiguous-incident stratum for A-H4, fault type) are joined from the ground-truth covariates at analysis time; they are not copied into `eval_score`.
