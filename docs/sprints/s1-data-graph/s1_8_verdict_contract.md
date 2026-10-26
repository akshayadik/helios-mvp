# S1.8 — Verdict contract · design note

**Task:** S1.8 (tracking S2-M6-ENG06) · **Date:** 2026-10-26 · **Code:** `helios/schemas/verdict.py` (`PipelineVerdict`, schema-draft-v0.5), `helios/orchestrator/runner.py`, `helios/store/schema.sql` · **Deviation:** entry 41 (schema bump, full D-pipe ranking, failed verdicts) · **Flags:** the contract serves every variant; a pipeline gated off by its flag gives a `skipped` verdict

## Chapter 3

p. 110 (layer L2): the three peer pipelines each consume the same content-hashed UEG-C snapshot and emit "a typed verdict of the form (ranked_RCA_list, μ, σ, cost, latency)". Algorithm 3 (MAHC, pp. 115–116) weights each pipeline's vote by a hierarchical prior "and apply[s] an uncertainty adjustment that reduces the effective weight as σ_p grows"; the fused variance is a weighted sum of squared σ_p. The C4 counterexample (p. 124: three agents agreeing at σ = 0.1 versus σ = 0.8) needs σ carried separately from the vote. Chapter 3 does not define μ's scale or the units of cost.

## The contract (schema-draft-v0.5)

| Field | Meaning |
|---|---|
| `status` | `ranked` (a ranking), `abstained` (ran, nothing to rank), `skipped` (gated off or not dispatched), `failed` (ran and errored). Only `ranked` carries candidates, μ or σ |
| `ranked_candidates` | The pipeline's **full** ranking, no repeats |
| `candidate_scores` | The pipeline's own score per ranked candidate (was `ppr_scores`) |
| `mu` | Confidence, in [0, 1], that the top-1 is the root cause; `None` = no estimator yet |
| `sigma` | Standard deviation of μ, ≥ 0; `None` = unknown. Consensus must treat `None` as unknown, never as certain |
| `cost` | `prompt_tokens`, `completion_tokens`, `cpu_ms`, `gpu_ms` — resource usage, not money |
| `latency_ms` | Wall clock |
| `narrative`, `prompt_version` | As before |

Removed: `hr_at_3`, `mrr`, `token_count`, `ppr_scores`.

**Decisions and why**

1. *Scores leave the verdict.* `hr_at_3` and `mrr` need ground truth; a pipeline must never see it. In every orchestrator run they were zero (the runner never passes ground truth), so the columns stored nothing true. HR@k, Avg@5 and MRR are computed after dispatch by the scoring path (S1.9) into their own table. The D-pipe keeps `ground_truth_service` for its calibration scripts until S1.9 removes it.
2. *Cost as usage, priced later.* A verdict records tokens and CPU/GPU time; the price book (S1.10, frozen before build-freeze) turns usage into CpR. A verdict therefore never changes when a price changes, and the five CpR components can be recomputed from stored rows.
3. *One clock for every pipeline.* The orchestrator measures wall-clock latency and process CPU time around each pipeline call (`_dispatch`); a pipeline's own timer is ignored. Before S1.8 the D-pipe reported zero latency, the G-pipe and L-pipe timed different spans.
4. *Status instead of placeholder candidates.* The L-pipe used to rank a fake service (`l-pipe-connectivity-error`, `l-pipe-fallback`) when the model was unreachable or every answer failed validation; those strings entered consensus as candidates. They are now `failed` verdicts with an empty ranking. Skipped pipelines are told apart by `status`, not by a narrative string.
5. *Full D-pipe ranking.* Stage D used to keep the top 3. HR@10, Avg@5 and MRR need the full list (R1 matrix: "D-pipe stores top-3 only"), and consensus fuses over the union of lists. This changes fused rankings and is part of deviation entry 41.
6. *μ now, σ later.* D-pipe and G-pipe report a label-free provisional μ: the top-1 share of their non-negative scores, rounded to six digits (`top1_share`). σ comes with the estimators planned in S2 (D-pipe σ from score spread, S2.1; graph ranker, S2.2; L-pipe workers each emitting (μ, σ), S2.3); MAHC calibration (IN2) uses the calibration split only. The single-prompt L-pipe has neither; its self-reported `confidence` is not used as μ (verbalised confidence is uncalibrated).
7. *Decision hash.* `compute_decision_hash()` hashes everything except `run_id`, latency and CPU/GPU time (floats rounded by `canonical_json`), so S2.1's "bitwise rerun equality" can be checked per verdict; it is stored in `result_row.decision_hash`. `compute_verdict_hash()` still identifies the whole row.
8. *Every pipeline emits it.* `PipelineVerdict.from_output` is the one conversion from a pipeline's output dict; the runner refuses an output that names another pipeline. A variant that turns the D-pipe off (HELIOS-LLM-only) used to abort the run with `GatedComponentInactiveError`; it now gives a `skipped` D-pipe verdict.

## Result store

`result_row` mirrors the contract (`status`, `candidate_scores`, `mu`, `sigma`, `prompt_tokens`, `completion_tokens`, `cpu_ms`, `gpu_ms`, `prompt_version`, `decision_hash`). A database created before v0.5 keeps its rows, untouched, in `result_row_v04`; the store refuses to start if that archive already exists, rather than overwrite it.

## Done-when

Round-trip and stability tests updated: `tests/test_schema_stability.py` (`TestVerdictContract`: field ranges, status rules, decision hash invariance and coverage, `top1_share`), `tests/test_schema_roundtrip.py`, `tests/test_result_store.py` (contract columns, archive migration), `tests/test_orchestrator_runner.py` (contract rows for all three pipelines, runner-measured latency, skipped D-pipe under HELIOS-LLM-only, mismatched output refused), pipeline tests (each pipeline's output converts to a valid verdict).

## Open points

- `docs/tracking/metric_contract.md` §9 still names `PipelineVerdict.mrr` as the home of MRR. The file is inside the OSF deposit-1 digest, so it is not edited here; the correction (MRR is computed by the scoring path) goes into the next deposit's addendum with S1.9.
- Token accounting across L-pipe retries (tokens of answers that fail validation are not yet counted) is S1.10 (LLM gateway counts tokens per episode).
- GPU time is recorded as zero until S1.10 measures it.
- Analysis scripts from the May milestones (`scripts/fuse_verdicts.py`, `scripts/replicate.py`) read their own databases and filter sentinels by narrative; they are rewired with the scoring path (S1.9) and MAHC (S2).
