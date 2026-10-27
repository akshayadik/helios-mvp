# S2.1 Shared Detection Trigger and D-pipe Completion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One label-free, frozen detector gives every system the same trigger (time + suspects); D-pipe works on both corpora, splits each window at the trigger and reports σ; both are calibrated on build data under the owner's 5% false-trigger limit.

**Architecture:** A new run-path module `helios/telemetry/trigger.py` scores each service's metric and log series against its own past (causal robust z) and fires at the first sustained crossing. The runner computes the trigger before graph pruning, stores it, seeds the K-hop pruner with in-scope suspects, hands it to D-pipe, and filters out-of-scope services (`helios/telemetry/scope.py`) from every ranking. Calibration and trigger classification live in `helios/evaluation/` (outside the leakage-scanned run path) and use build labels only.

**Tech Stack:** Python 3.11, numpy, pandas, pyarrow, pydantic v2, duckdb (result store), pytest.

**Spec:** `docs/sprints/s2-reasoning/s2_1_dpipe_trigger_design.md` (approved by the owner 2026-10-27; decisions D-a … D-f, calls 1–12).

## Global Constraints

- Python `>=3.11,<3.12`; no new dependency.
- New non-VCL modules declare a module flag constant (`HELIOS_ENABLE_TRIGGER: bool = True`, pattern of `HELIOS_ENABLE_ORCHESTRATOR`) and import from `helios.vcl` so `flag-guard` passes. The trigger itself gets **no** `VCLFlag` (design §4, call 6); D-pipe changes stay under `VCLFlag.DPIPE`.
- Never edit `research/osf/*`, `docs/tracking/metric_contract.md`, `helios/vcl/variants.py`, or the seed register.
- Labels (ground truth, injection time) are read only under `helios/evaluation/` or `helios/adapters/`; `tests/evaluation/test_no_ground_truth_leak.py` must pass with the new run-path modules.
- The pool is never read: calibration tools refuse `--corpus pool`; tool output is counts and aggregates only.
- Every stored float is rounded with the `canonical_json` rule (6 digits); every iteration over services or series is sorted.
- Out-of-scope services (D-f), frozen: `load-generator`, `flagd`, `flagd-ui`, `prometheus`, `jaeger`, `opensearch`, `grafana`, `otel-collector`. One global list; none of these names occurs among the 96 RCAEval build services (checked 2026-10-27).
- Detector uses metrics and logs only, never traces (call 7). Warm-up is fixed before calibration (design §5.3): `WARMUP_BUCKETS = 4` with 30 s buckets, i.e. two minutes, below a fifth of the shortest usable build windows. *(Bucket size is a calibration candidate; warm-up is always 4 buckets, never tuned.)*
- False-trigger limit: at most 5% on each build corpus separately (D-e, call 2); if no setting meets it, stop and report to the owner.
- Tracking: each row IN_PROGRESS in its own commit, DONE in its own commit; deviation entries via the CLI only, after the code they describe is committed (`commit_sha` = HEAD).
- Full pre-push gate (root `CLAUDE.md`) before every PR.

## Review Focus

1. **A window with no metrics and no logs** (or only out-of-scope services): `detect` must return a FALLBACK record at the window start with no suspects, never raise. Test in Task 3.
2. **A constant series that suddenly moves** (an error counter flat at zero, then one error; a gauge flat at its level, then a 1% move): the scale floors give a small z (Poisson floor for counts, relative floor for gauges), never a cap, so one event cannot set off the trigger; a gauge flat at zero gives no evidence until it varies. Tests in Task 3 (owner review 2026-10-27).
3. **Suspects absent from the trace graph** (metric-only services) or **a trigger set off only next to out-of-scope anomalies**: missing suspects are dropped before `khop_prune(seeds=...)`, the pruner then picks its own in-scope seeds (`seeds_from_trigger = false`, counted in the calibration), never a `ValueError`; out-of-scope anomalies are kept as `context`, never as suspects. Tests in Tasks 3 and 6.
4. **A ground-truth label on the out-of-scope list** reaching scoring: scoring raises, not silently scores. Test in Task 2.
5. **Provisional (uncalibrated) parameter files in a confirmatory run**: the runner refuses to start, as it refuses an external trigger. Test in Task 6.

---

## PR 1 — rows S2-M7-ENG01 and S2-M7-RES02 (branch `s2/trigger`)

### Task 1: Open the rows; commit the design; TTCD/TTT deviation entry

**Files:**
- Modify: `docs/tracking/helios_mvp_tracking.md` (add S2-M7-ENG01 and S2-M7-RES02 as IN_PROGRESS — two rows, one commit; immutable columns from the breakdown for ENG01; RES02 description "S2.1 protocol records: TTCD and TTT start at the detection trigger (deviation), validity threats, chair-call item")
- Add: `docs/sprints/s2-reasoning/s2_1_dpipe_trigger_design.md`, this plan
- Modify: `docs/sprints/README.md` (S2 status "In progress (started early, 2026-10-27)"), `docs/sprints/s2-reasoning/plan.md` (status line; S2.1 row notes the four tracking rows)
- Deviation: `deviation_log.jsonl` + `.anchor.json` via `bin/log_deviation.py`

- [ ] **Step 1:** Commit the tracking rows alone (`tracking(m7): add S2-M7-ENG01 and S2-M7-RES02 as IN_PROGRESS`). Run `python3 scripts/validate_tracking.py`; expected: clean.
- [ ] **Step 2:** Commit design, plan and sprint-status docs.
- [ ] **Step 3:** Append the TTCD/TTT entry:
  - `--stage "Stage A / S2"`
  - `--clause "Metric contract §4 (TTCD, B-H6; TTT, E-H2); D11 §7"`
  - `--change "TTCD and TTT are measured from the shared detection trigger: the clock starts when a system is handed the trigger record and stops at the first published verdict whose top-1 is the ground truth (TTCD) or the first PROVISIONAL verdict (TTT). Data loading and pipeline start-up are outside the measured time. Censoring at 1,800 s unchanged."`
  - `--reason "Owner decision 2026-10-27: every system receives the same trigger, so starting at the trigger isolates algorithmic speed; starting at invocation mixes in loading and start-up overhead. Matches the D11 design wording; the deposited contract said invocation."`
  - `--analytic-consequence "B-H6 and E-H2 compare compute time after a shared anchor; values are not comparable with invocation-based timings. To be noted in the next OSF deposit addendum and raised on the mid-November chair call. No confirmatory data exists yet."`
- [ ] **Step 4:** `poetry run python bin/log_deviation.py verify && poetry run python bin/log_deviation.py verify-public && poetry run pytest tests/test_deviation_log.py -q`; expected: all pass, 46 entries. Commit `deviation_log.jsonl` with its anchor; add mirror row 46 to `docs/tracking/deviation_log.md` in the same commit.

### Task 2: Out-of-scope service list and scoring guard

**Files:**
- Create: `helios/telemetry/scope.py`
- Modify: `helios/evaluation/scoring.py` (`score_ranking` and `_ranked` path)
- Test: `tests/telemetry/test_scope.py`, `tests/evaluation/test_scoring.py`

**Interfaces — Produces:**
- `OUT_OF_SCOPE_SERVICES: frozenset[str]` (the eight names in Global Constraints)
- `in_scope(service: str) -> bool` (compares `service_key(service)`-style normalised names: lower-case, stripped)
- `filter_in_scope(ranked: Sequence[str]) -> list[str]` (order kept)
- `scope_digest() -> str` (sha256 of the sorted list, canonical JSON)
- `OutOfScopeLabelError(ValueError)` raised by scoring

- [ ] **Step 1: Failing tests**

```python
def test_out_of_scope_list_is_the_frozen_eight():
    assert OUT_OF_SCOPE_SERVICES == frozenset({"load-generator", "flagd", "flagd-ui", "prometheus",
        "jaeger", "opensearch", "grafana", "otel-collector"})

def test_filter_keeps_order_and_drops_harness_and_observability():
    assert filter_in_scope(["prometheus", "cart", "load-generator", "ad"]) == ["cart", "ad"]

def test_app_dependencies_stay_in_scope():
    assert all(in_scope(s) for s in ("kafka", "valkey-cart", "postgresql"))

def test_scope_digest_is_stable():
    assert scope_digest() == scope_digest() and len(scope_digest()) == 64

# tests/evaluation/test_scoring.py
def test_scoring_drops_out_of_scope_candidates_before_ranking():
    case = score_ranking(["jaeger", "cart", "ad"], "cart")
    assert case.rank == 1

def test_scoring_refuses_an_out_of_scope_label():
    with pytest.raises(OutOfScopeLabelError):
        score_ranking(["cart"], "otel-collector")
```

- [ ] **Step 2:** `poetry run pytest tests/telemetry/test_scope.py tests/evaluation/test_scoring.py -q`; expected: FAIL (import errors).
- [ ] **Step 3:** Implement `scope.py`; in `scoring.py`, `score_ranking` filters `ranked` with `filter_in_scope` and raises `OutOfScopeLabelError` when `not in_scope(truth)`. Bump `SCORING_VERSION` (scores of OTel lists change).
- [ ] **Step 4:** Same command; expected: PASS. Run the whole `tests/evaluation/` folder; expected: PASS.
- [ ] **Step 5:** Commit (`feat(s2.1): out-of-scope service list (D-f); scoring drops and refuses out-of-scope names`).

### Task 3: Causal series scoring and the detector

**Files:**
- Modify: `helios/graph/anomaly_intensity.py` (extract raw-series helpers; outputs of `metric_intensity`/`log_intensity` unchanged)
- Create: `helios/telemetry/trigger.py`, `data/frozen/trigger_detector.json`
- Test: `tests/telemetry/test_trigger.py`, existing `tests/graph/test_ueg_c_v02.py` (must stay green: UEG-C unchanged)

**Interfaces — Produces:**
- In `anomaly_intensity.py`: `metric_series(metrics, window_start_iso, n_buckets, bucket_seconds) -> dict[str, list[np.ndarray]]` (per service, raw bucket means, counters differenced, sorted) and `log_series(features, window_start_iso, n_buckets, bucket_seconds) -> dict[str, list[np.ndarray]]` (line count, novel lines). `metric_intensity`/`log_intensity` become `robust_z` over these.
- In `trigger.py`:
  - `HELIOS_ENABLE_TRIGGER: bool = True`; `DETECTOR_VERSION = "trigger-v1"`; `WARMUP_BUCKETS = 4`; `REL_FLOOR = 0.05`; `Z_CAP = 50` (numeric guard only, never a substitute for a scale); `SUSPECT_COUNT = SEED_COUNT` (from `khop_pruner`)
  - `class TriggerSource(StrEnum)`: `THRESHOLD`, `FALLBACK`, `EXTERNAL`
  - `@dataclass(frozen=True) class DetectorParams`: `bucket_seconds: int`, `threshold: float`, `persistence: int`, `provisional: bool`
  - `class TriggerRecord(BaseModel)` (frozen, `extra="forbid"`): `incident_id: str`, `trigger_time_s: float`, `suspects: tuple[str, ...]`, `context: tuple[str, ...]` (out-of-scope services over the threshold at the trigger bucket: evidence for narratives, never suspects or seeds), `source: TriggerSource`, `detector_hash: str`
  - `causal_z(values: np.ndarray, *, count_series: bool, warmup: int = WARMUP_BUCKETS) -> np.ndarray`
  - Count series (Poisson floor) = differenced counters (`COUNTER_SUFFIXES`), RCAEval `error`, log line and novel-line counts; every other series is a gauge. `metric_series`/`log_series` return each series with its kind.
  - `service_scores(window: TelemetryWindow, bucket_seconds: int, *, root: Path | None = None, crop_start_s: float = 0) -> tuple[list[str], np.ndarray, float]` → sorted in-scope services, a services × buckets matrix of max causal |z|, and the window start in seconds
  - `detect(window: TelemetryWindow, params: DetectorParams, *, root: Path | None = None, crop_start_s: float = 0) -> TriggerRecord`
  - `detector_hash(params: DetectorParams) -> str` (sha256 of canonical JSON of params, `DETECTOR_VERSION`, `WARMUP_BUCKETS`, `Z_CAP`, `scope_digest()`)
  - `load_detector_params(path: Path = DETECTOR_PARAMS_PATH) -> DetectorParams` (missing file or key → `FileNotFoundError`/`ValueError`; never a default)

Algorithm the signatures do not fix:

```text
causal_z, per bucket i:
  history = finite values in [0, i)
  if len(history) < warmup or values[i] is NaN: NaN
  centre = median(history)
  spread = 1.4826 * MAD(history); if spread == 0: spread = std(history)
  floor  = max(REL_FLOOR * |centre|, sqrt(max(centre, 1)) if count_series else 0)
  scale  = max(spread, floor)
  if scale == 0: NaN          # a gauge that has never varied and sits at zero: no evidence yet
  else: z = min(|values[i] - centre| / scale, Z_CAP)
  # A flat count series moving 0 -> 1 gives z = 1 (one event is Poisson noise), not a cap;
  # a flat gauge moving by 1% of its level gives z = 0.2.
detect:
  M = service_scores(...) over in-scope services; a bucket b "crosses" if max_s M[s, b] >= threshold
  fire at the first b with buckets b .. b+persistence-1 all crossing  -> THRESHOLD
  suspects = in-scope services with M[s, b] >= threshold, by (-M[s, b], name), first SUSPECT_COUNT
  context  = out-of-scope services whose own max causal |z| at b >= threshold, sorted
  none fires -> b = argmax over buckets of max_s M[s, b] (earliest on ties; NaN ignored) -> FALLBACK,
                 suspects = top SUSPECT_COUNT in-scope services at b with M > 0; context as above
  no data at all -> FALLBACK at the window start, suspects (), context ()
  trigger_time_s = round(window_start_s + b * bucket_seconds, 6)
crop_start_s (calibration audit only): buckets that start before window_start_s + crop_start_s are set to NaN before causal_z
```

Out-of-scope services are scored (for `context`) but never decide whether or when the trigger fires (D-f). Known blind spot, recorded in validity threat T18: a telemetry gap (series that stop) is not a signal in `trigger-v1`; a broken collector shows only through its own metrics, as `context`.

Initial `data/frozen/trigger_detector.json`: `{"bucket_seconds": 30, "threshold": 6, "persistence": 2, "provisional": true}` (provisional until Task 12).

- [ ] **Step 1: Failing tests** (fixtures build small P1/P3 parquet windows in `tmp_path`, as `tests/graph/test_ueg_c_v02.py` does)

```python
def test_causal_z_uses_only_the_past():
    v = np.array([1, 1, 2, 1, 1, 9, 1], dtype=float)
    z = causal_z(v, warmup=4)
    assert np.isnan(z[:4]).all() and z[5] > z[4]
    assert causal_z(v[:6], warmup=4)[5] == z[5]          # the future never changes a past score

def test_one_event_on_a_flat_count_series_is_noise_not_a_cap():
    z = causal_z(np.array([0, 0, 0, 0, 0, 1], dtype=float), count_series=True, warmup=4)
    assert z[5] == 1 and z[4] == 0

def test_flat_gauge_small_move_scores_against_its_level():
    z = causal_z(np.array([200, 200, 200, 200, 200, 202], dtype=float), count_series=False, warmup=4)
    assert z[5] < 1

def test_flat_zero_gauge_gives_no_evidence_until_it_varies():
    z = causal_z(np.array([0, 0, 0, 0, 0, 3, 3], dtype=float), count_series=False, warmup=4)
    assert np.isnan(z[5]) and np.isfinite(z[6])

def test_single_bucket_blip_never_fires_with_persistence_two(tmp_path): ...
    # fixture: one service jumps for exactly one bucket; params persistence=2 -> FALLBACK

def test_out_of_scope_anomaly_is_recorded_as_context(tmp_path): ...
    # fixture: "cart" latency and "otel-collector" CPU jump in the same bucket
    # assert rec.suspects == ("cart",) and rec.context == ("otel-collector",)

def test_detector_fires_at_first_sustained_crossing_and_names_the_service(tmp_path): ...
    # fixture: service "cart" latency steps up at bucket 10 for 4 buckets
    # assert rec.source == TriggerSource.THRESHOLD and rec.suspects[0] == "cart"
    # assert rec.trigger_time_s == start_s + 10 * 30

def test_out_of_scope_services_never_trigger_or_appear(tmp_path): ...
    # fixture: only "load-generator" CPU jumps; assert rec.source == TriggerSource.FALLBACK
    # and "load-generator" not in rec.suspects

def test_no_data_gives_fallback_at_window_start(tmp_path): ...

def test_detector_hash_changes_with_any_parameter(): ...

def test_provisional_flag_round_trips_from_the_frozen_file(): ...

def test_moving_window_start_does_not_move_the_trigger(tmp_path): ...
    # same fixture with crop_start_s = 60: identical trigger_time_s and suspects
```

- [ ] **Step 2:** `poetry run pytest tests/telemetry/test_trigger.py -q`; expected: FAIL.
- [ ] **Step 3:** Implement the helpers in `anomaly_intensity.py` (refactor only), then `trigger.py`.
- [ ] **Step 4:** `poetry run pytest tests/telemetry/test_trigger.py tests/graph -q`; expected: PASS, UEG-C tests unchanged. Then `poetry run python bin/ueg_c_check.py --corpus captures`; expected: the digest recorded in S1.5/S1.7 docs is unchanged.
- [ ] **Step 5:** Commit (`feat(s2.1): label-free causal detector and trigger record (provisional parameters)`).

### Task 4: Trigger and timing storage

**Files:**
- Modify: `helios/store/result_store.py`
- Test: `tests/test_result_store.py`

**Interfaces — Produces:**
- Table `trigger_row(run_id PK, incident_id, variant_config_hash, trigger_time_s DOUBLE, suspects JSON, context JSON, source, detector_hash, seeds_from_trigger BOOLEAN, handover_unix DOUBLE)`
- Table `timing_row(run_id, pipeline, started_unix DOUBLE, published_unix DOUBLE, PRIMARY KEY(run_id, pipeline))`
- `ResultStore.insert_trigger(record: TriggerRecord, *, run_id: str, variant_config_hash: str, seeds_from_trigger: bool, handover_unix: float) -> None`
- `ResultStore.fetch_trigger(incident_id: str, variant_config_hash: str) -> TriggerRecord | None` (latest run)
- `ResultStore.insert_timing(run_id: str, pipeline: PipelineName, started_unix: float, published_unix: float) -> None`
- `ResultStore.fetch_timings(run_id: str) -> list[dict[str, object]]`

- [ ] **Step 1: Failing tests:** `test_trigger_round_trips_exactly` (insert then fetch equals the record, suspects order kept); `test_timing_rows_one_per_pipeline` (duplicate `(run_id, pipeline)` raises); `test_existing_store_gains_the_new_tables` (open a store created by the current schema; tables appear, old rows untouched).
- [ ] **Step 2:** Run `poetry run pytest tests/test_result_store.py -q`; expected: FAIL.
- [ ] **Step 3:** Implement (create-if-not-exists in `_init_schema`; JSON with `sort_keys` only for dicts — suspects stay ordered).
- [ ] **Step 4:** Same command; expected: PASS.
- [ ] **Step 5:** Commit (`feat(s2.1): result store keeps the trigger record and per-pipeline timings`).

### Task 5: D-f deviation entry

- [ ] **Step 1:** After Task 2–4 commits, append:
  - `--clause "Metric contract §2 (ranking over all services); §3.6.4 K-hop seeds; S1.7"`
  - `--change "Out-of-scope services (test harness: load-generator, flagd, flagd-ui; observability stack: prometheus, jaeger, opensearch, grafana, otel-collector) are excluded from trigger decisions, suspects, pruner seeds and every system's ranking (HELIOS pipelines, MAHC, baselines' output before scoring). Their telemetry stays in the graph and in pipeline inputs. Scoring refuses a label on the list. List digest <scope_digest()>."`
  - `--reason "Owner decision 2026-10-27 (D-f): harness anomalies are testbed noise; faults are never injected into the observability stack, so naming it would be scored as a false positive for every system; its telemetry remains as context."`
  - `--analytic-consequence "Rankings and HR@k/MRR on OTel corpora are over application services only (exploratory). RCAEval corpora unaffected: none of the 96 build service names is on the list; the pool's names are checked at build-freeze. Same rule for HELIOS and baselines."`
- [ ] **Step 2:** Verify as Task 1 Step 4 (47 entries); commit with mirror row 47.

### Task 6: Runner — trigger first, seeds, scope filter, hand-over, refusals

**Files:**
- Modify: `helios/orchestrator/runner.py`, `helios/graph/khop_pruner.py` (`seed_nodes`/`khop_prune` gain `exclude: Collection[str] = ()`), `helios/pipelines/d_pipe/pipeline.py` (accepts `trigger: TriggerRecord | None = None`, unused until Task 9)
- Test: `tests/test_orchestrator_runner.py`, `tests/graph/test_khop_pruner.py`

**Interfaces — Consumes:** `detect`, `load_detector_params`, `TriggerRecord` (Task 3); `insert_trigger`, `insert_timing` (Task 4); `filter_in_scope`, `OUT_OF_SCOPE_SERVICES` (Task 2).
**Produces:**
- `RunOrchestrator(..., detector_params: DetectorParams | None = None, external_triggers: Path | None = None)`; `None` params → `load_detector_params()`
- `ExternalTriggerRefusedError(RuntimeError)`, `ProvisionalParametersError(RuntimeError)`
- `load_external_triggers(path: Path) -> dict[str, TriggerRecord]` (JSON lines; every record must have `source == EXTERNAL`)

Behaviour:
1. After the seal checks: if the window is confirmatory and (`external_triggers` is set, or `detector_params.provisional`) → raise the matching error before anything runs.
2. `trigger = external[incident_id] if external_triggers else detect(window, params)`; `handover = time.time()`; `insert_trigger(...)`.
3. `khop_prune(ueg_c, seeds=[s for s in trigger.suspects if s in ueg_c.candidate_ids()] or None, exclude=OUT_OF_SCOPE_SERVICES)`; `seeds_from_trigger` = whether that list was non-empty, stored with the trigger. (Suspects are already in-scope, so the fallback happens only when the suspects are missing from the trace graph, e.g. metric-only services, or the trigger has no suspects; its rate is reported in the calibration.) `context` services are kept by the pruner as context nodes when present in the graph, never as seeds.
4. `run_dpipe(..., trigger=trigger)`.
5. In `_dispatch`, record `started_unix`/`published_unix` and `insert_timing` for every non-skipped pipeline.
6. Before `_build_verdict`, filter `ranked_candidates` and `candidate_scores` with `filter_in_scope`; recompute `mu` with `top1_share` when scores are present.

- [ ] **Step 1: Failing tests:**
  - `test_trigger_runs_before_pruning_and_seeds_it` (spy on `khop_prune`; `seeds` equals the in-scope suspects present in the graph)
  - `test_suspects_missing_from_graph_fall_back_to_pruner_seeds` (no `ValueError`; seeds `None`)
  - `test_pruner_never_seeds_out_of_scope_services` (khop test: highest peak on `prometheus` → not in seeds)
  - `test_rankings_exclude_out_of_scope_services_for_every_pipeline`
  - `test_trigger_time_identical_for_helios_and_a_baseline_reader` (the record passed to `run_dpipe` equals `ResultStore.fetch_trigger(...)`, which is what the S4.8 baseline harness reads)
  - `test_confirmatory_run_refuses_external_triggers` and `test_confirmatory_run_refuses_provisional_parameters` (confirmatory fixture with an injected unlocked `pool_lock`)
  - `test_timing_rows_written_for_each_dispatched_pipeline`
- [ ] **Step 2:** `poetry run pytest tests/test_orchestrator_runner.py tests/graph/test_khop_pruner.py -q`; expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Same command, then full `poetry run pytest`; expected: PASS, coverage ≥ 90%.
- [ ] **Step 5:** Commit (`feat(s2.1): runner computes the shared trigger first, seeds the pruner, filters out-of-scope services, records timings`).

### Task 7: Cross-process rerun equality; check CLI; close the rows

**Files:**
- Create: `bin/trigger_check.py` (`--corpus captures|otel_build|rcaeval_build` or `--window DIR`; prints counts per source and the sha256 of the canonical JSON of all records; `--json` prints the records; refuses `pool`)
- Test: `tests/test_trigger_check_cli.py`

- [ ] **Step 1: Failing test** `test_two_processes_give_identical_bytes`: run `[sys.executable, "bin/trigger_check.py", "--window", <fixture>, "--json"]` twice with `subprocess.run`; assert both stdouts are equal and non-empty. Also `test_cli_refuses_pool`.
- [ ] **Step 2–4:** Fail, implement, pass.
- [ ] **Step 5:** Run `poetry run python bin/trigger_check.py --corpus otel_build` and `--corpus rcaeval_build` twice each; expected: same digest both times (record the digests and source counts in the design note's results section — provisional parameters).
- [ ] **Step 6:** RES02 items: add validity threats T18 (shared trigger quality) and T19 (injection at the window midpoint) to `docs/tracking/validity_tracking.md`; add the TTCD-anchor and false-trigger items to the chair-call list in `docs/sprints/s2-reasoning/plan.md`; note the two RCAEval build cases with the injection outside the window in `docs/tracking/data_collection_log.md`. Commit.
- [ ] **Step 7:** Close S2-M7-ENG01 and S2-M7-RES02 (DONE, separate commit), full gate, push, open PR 1.

---

## PR 2 — row S2-M7-ENG09 (branch `s2/dpipe-complete`, from main after PR 1)

### Task 8: Format-neutral Stage A with a resource channel

**Files:**
- Modify: `helios/pipelines/d_pipe/stages/a_metrics_parser.py`, `helios/pipelines/d_pipe/dpipe_config.py`
- Test: `tests/pipelines/d_pipe/test_a_metrics_parser.py`

**Interfaces — Produces:** `ParsedMetrics` gains `resource_values: dict[str, list[float]]`. Fixed tables in `dpipe_config.py`:
- `RCAEVAL_LATENCY_NAMES = ("latency-90", "latency-50", "latency")` (first present wins)
- `RCAEVAL_ERROR_NAMES = ("error",)` (per-step values, not cumulative)
- `RCAEVAL_RESOURCE_NAMES = ("cpu", "mem", "diskio", "socket", "load", "workload")`
- `OTEL_RESOURCE_NAMES = ("container_cpu_utilization_ratio", "container_memory_usage_total_bytes")`

Service = `service_of(labels)` (shared with `anomaly_intensity`). OTel histogram handling is unchanged.

- [ ] **Step 1: Failing tests:** `test_rcaeval_metrics_give_services` (fixture with `service_name` labels and the plain names: services found; latency from `latency-90`); `test_latency_falls_back_to_median_then_plain`; `test_otel_container_metrics_fill_resource_channel`; `test_otel_histogram_parsing_unchanged` (existing fixture outputs equal).
- [ ] **Step 2–4:** Fail, implement, pass.
- [ ] **Step 5:** Commit.

### Task 9: Trigger split scoring, σ, frozen parameter file

**Files:**
- Modify: `helios/pipelines/d_pipe/stages/b_anomaly_scorer.py`, `helios/pipelines/d_pipe/pipeline.py`, `helios/schemas/verdict.py` (add `sigma_from_scores` next to `top1_share`), `helios/orchestrator/runner.py` (load and pass D-pipe params)
- Create: `data/frozen/dpipe_params.json` — `{"w_error": 0.3, "w_resource": 0.2, "rho_threshold": 0.2, "topology_boost_factor": 1, "provisional": true}` (May frozen values plus the new resource weight; latency weight = remainder)
- Test: `tests/pipelines/d_pipe/test_b_anomaly_scorer.py`, `tests/pipelines/d_pipe/test_pipeline.py`, `tests/test_schema_stability.py`

**Interfaces — Produces:**
- `AnomalyScorer(w_error: float, w_resource: float).score(parsed: ParsedMetrics, *, split_s: float | None) -> ScoredServices`, where `ScoredServices` has `scores: dict[str, float]` (as before) and `evidence: dict[str, float]` (each service's largest raw shift across channels, in robust-z units, before max-normalisation). Per channel and service, `shift = max(0, (wm90(incident part) - median(reference part)) / scale(reference part))` with the scale rule of `causal_z` (spread, floors); `split_s is None` → previous whole-window behaviour. Channels max-normalised across services as now; `score = w_error*err + w_resource*res + (1 - w_error - w_resource)*lat`.
- `sigma_from_scores(scores: Mapping[str, float], evidence: Mapping[str, float], *, evidence_ref: float) -> float | None`:
  - no scores or `s1 <= 0` → `None`;
  - `gap = (s1 - s2) / s1` (`s2 = 0` with one candidate), from the normalised scores sorted descending;
  - `strength = min(1, evidence[top] / evidence_ref)`, with `evidence_ref` = the frozen detector threshold;
  - `σ = 1 - gap * strength`, rounded to `MU_DIGITS`.
  - Why: max-normalisation always produces a "winner", so the relative gap alone says nothing when every raw shift is tiny. Weak evidence drives σ towards 1 (unsure) whatever the gap, so σ is stable for small scores.
- `DPipeParams` dataclass + `load_dpipe_params(path: Path = DPIPE_PARAMS_PATH) -> DPipeParams` (missing → error, never defaults); the runner passes them to `run_dpipe` and refuses `provisional` in confirmatory runs (same error as Task 6).

- [ ] **Step 1: Failing tests:** `test_split_scores_only_the_shift_after_the_trigger` (a service high in both halves scores lower than one that rises after the split); `test_sigma_is_high_for_close_scores_and_low_for_a_clear_winner`; `test_sigma_near_one_when_raw_evidence_is_tiny` (normalised gap large, `evidence[top]` a hundredth of `evidence_ref` → σ ≥ 0.99); `test_sigma_bounded_and_finite_for_tiny_positive_scores` (s1 = 1e-9); `test_sigma_counterexample_ch3_p157` (two verdicts with equal top-1 and different spreads give different σ); `test_sigma_none_without_scores`; `test_runner_uses_frozen_dpipe_params_not_defaults` (spy: `w_error == 0.3`); `test_dpipe_ranks_on_rcaeval_window` (not ABSTAINED).
- [ ] **Step 2–4:** Fail, implement, pass; full `poetry run pytest`.
- [ ] **Step 5:** Cross-process equality for the D-pipe verdict: extend `bin/trigger_check.py --window DIR --json` with `--with-dpipe` and add `test_dpipe_verdict_identical_across_processes`.
- [ ] **Step 6:** Commit; close S2-M7-ENG09; gate; PR 2.

---

## PR 3 — row S2-M7-EVAL01 (branch `s2/trigger-calibration`, from main after PR 2)

### Task 10: Trigger classification

**Files:**
- Create: `helios/evaluation/trigger_eval.py`
- Test: `tests/evaluation/test_trigger_eval.py`

**Interfaces — Produces:**
- `class TriggerLabel(StrEnum)`: `TRUE`, `FALSE`, `NO_TRIGGER`
- `classify_trigger(record: TriggerRecord, inject_time_s: float) -> TriggerLabel` (FALLBACK → NO_TRIGGER; threshold before injection → FALSE; else TRUE)
- `trigger_delay_s(record, inject_time_s) -> float | None` (TRUE only)
- `injection_inside_window(window, inject_time_s) -> bool`

- [ ] Steps 1–5: tests for each label, the delay, and the outside-window check (the injection exactly at the trigger is TRUE); implement; commit.

### Task 11: Calibration grid and invariance audit

**Files:**
- Create: `helios/evaluation/trigger_calibration.py`, `bin/trigger_calibrate.py`
- Test: `tests/evaluation/test_trigger_calibration.py`

**Interfaces — Produces:**
- `GRID = {"bucket_seconds": (15, 30, 60), "threshold": (3, 4, 5, 6, 8, 10, 12), "persistence": (1, 2, 3)}` (fixed before the run)
- `CROP_FRACTIONS = (0.25, 0.4, 0.6)` of each window's **slack**, fixed before the run: `slack = pre-injection span - (WARMUP_BUCKETS + max persistence in GRID + 1) * bucket_seconds`. The crop never eats into the warm-up the detector needs before the injection, so a valid setting cannot fail the audit just because cropping left it still warming up at the injection. Cases with `slack <= 0` for a bucket size are skipped for that crop and counted. (Build pre-injection spans are at least 300 s: the OTel slack with 30 s buckets is 60 s, so the OTel audit is weak; this is reported, and RCAEval build spans are mostly far longer.)
- `evaluate(params, cases) -> CorpusResult` (counts: true, false, no-trigger, excluded; false rate; median delay; root cause among suspects; root cause within K-hop reach of suspects; false rate per fault on OTel)
- `select(results_by_corpus) -> DetectorParams | None` — design §5.3 rule: false rate ≤ 5% on **each** corpus; then smallest median delay (mean of the two corpora's medians); ties → fewer no-triggers, then higher threshold, then higher persistence; `None` if nothing qualifies
- `audit(params, cases) -> AuditResult` — every crop keeps false rate ≤ 5% and median delay within one bucket of the uncropped run, over the cases with enough slack; `AuditResult` also counts skipped cases per crop
- calibration report also gives: share of triggers with `seeds_from_trigger = false`, and cases where only out-of-scope services crossed (context-only)
- CLI: `bin/trigger_calibrate.py --corpora rcaeval_build otel_build` writes `docs/sprints/s2-reasoning/s2_1_trigger_calibration.json` (aggregates only) and prints counts; refuses the pool; exits non-zero when `select` returns `None` or the audit fails.

- [ ] Steps 1–5: unit tests on synthetic cases for `select` (the 5% rule per corpus; tie order; `None`), `audit` (a parameter set that only works uncropped fails); implement; commit.
- [ ] **Step 6:** Run the calibration on both build corpora. If no setting qualifies or the audit fails: stop and report to the owner (D-e); do not widen the grid silently.

### Task 12: Freeze the detector; deviation entry

- [ ] **Step 1:** Write the selected parameters to `data/frozen/trigger_detector.json` with `"provisional": false`; rerun `bin/trigger_check.py` on both build corpora twice (digest equal); commit with the calibration JSON and a results section in the design note.
- [ ] **Step 2:** Deviation entry (clause "D11 §1–§3; metric contract §1 (no injection time); S2.1 detection trigger"; change: detector `trigger-v1`, metrics and logs only, causal robust z, warm-up 4 buckets, Z_CAP, selected bucket/threshold/persistence, `detector_hash`; reason: owner decisions D-a … D-e; consequence: every system's trigger and TTCD/TTT anchor; build false/no-trigger rates per corpus; pool rates reported after build-freeze). Mirror row; commit.

### Task 13: Recalibrate D-pipe; deviation entry; close

**Files:**
- Create: `bin/dpipe_calibrate.py` (or extend `scripts/calibrate_dpipe.py`; keep one tool), using `helios/evaluation/scoring.py`
- Modify: `data/frozen/dpipe_params.json`

- [ ] **Step 1:** Grid = `dpipe_config.py` grid for `w_error`, `rho_threshold`, `topology_boost_factor` plus `w_resource ∈ (0, 0.1, 0.2, 0.3)` with `w_error + w_resource < 1`; trigger = frozen detector (never the injection time). Objective: mean of per-corpus HR@3 (RCAEval build, OTel build); ties → smallest summed absolute change from the May values (0.3, 0.2, 1) and `w_resource` 0.2. Unit-test the selection function on synthetic scores first.
- [ ] **Step 2:** Run it; write the winner with `"provisional": false`; report per-corpus HR@3 (exploratory) in the design note.
- [ ] **Step 3:** Deviation entry (D-pipe formats, resource channel, trigger split, σ formula, new parameter file and values; replaces the runtime use of code defaults). Mirror row; commit.
- [ ] **Step 4:** Close S2-M7-EVAL01; full gate; PR 3. Update `docs/tracking/tracking_documents_register.md` (deviation log count, validity tracking, calibration thresholds row now pointing at `data/frozen/`).
