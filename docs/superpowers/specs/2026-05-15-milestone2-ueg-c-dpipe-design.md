# Milestone 2 — UEG-C Builder + D-pipe Design Spec

> **Status:** Approved
> **Date:** 2026-05-15
> **Branch:** feature/stage1_telemetry_c1_foundation

---

## 1. Architecture

UEG-C (Universal Edge Graph — Calibrated) is shared infrastructure: built **once per incident** before orchestrator dispatch, then passed read-only to all three pipelines (D-pipe, G-pipe, L-pipe). The orchestrator calls `build_ueg_c(traces)` before invoking any pipeline.

**Feature flags (Milestone 2 scope):**

| Flag | Gates |
|---|---|
| `HELIOS_ENABLE_GRAPH` | UEG-C construction (shared infra) |
| `HELIOS_ENABLE_DPIPE` | All D-pipe logic (Stages A–D) |

Both flags must be enabled for HELIOS-Full. Disabling `HELIOS_ENABLE_GRAPH` ablates the structural graph entirely; the D-pipe still runs but receives no topology boost.

---

## 2. UEG-C Builder

### 2.1 Edge Taxonomy (Milestone 2 Scope)

| EdgeType | Source | Weight | Milestone |
|---|---|---|---|
| STRUCTURAL | Span containment heuristic | Unity (integer 1) | 2 |
| CALL | Trace co-occurrence frequency | `len(traces_with_pair) / total_unique_traces` | 2 |
| METRIC | D-pipe correlation | TBD | 3+ |
| LOG | Log-event co-occurrence | TBD | 3+ |

### 2.2 Span Containment Heuristic

For each trace, infer structural (parent → child) service relationships via temporal containment:

1. Sort all spans in the trace by start time ascending
2. For each span S, scan backward through the sorted list to find the most-recent span P from a **different** service satisfying `P.start ≤ S.start AND P.end ≥ S.end`
3. Backward scan does **not** short-circuit on same-service spans — continues until a qualifying enclosing span from a different service is found, or the list is exhausted
4. The first qualifying P found is S's structural parent; emit `STRUCTURAL` edge: `P.service_name → S.service_name`

**Deviation log entry required** before merge: span-containment is a simplification relative to OpenTelemetry `parent_span_id` linkage; the analytic consequence is potential misattribution of structural edges in deeply nested same-service call stacks.

### 2.3 CALL Edge Construction

For each directed pair `(caller_service, callee_service)` observed across all traces:

```
call_weight = |{trace_id : (caller, callee) observed in trace}| / |all_unique_trace_ids|
```

Emit one CALL edge per unique directed pair with `weight = call_weight`. Multiple trace observations accumulate into the frequency fraction.

### 2.4 K-Hop PPR Pruner

- **Entry points:** services with structural in-degree = 0 (no incoming STRUCTURAL edge)
- **Algorithm:** Personalized PageRank seeded from entry points; restart probability α = 0.15
- **Threshold:** retain nodes with PPR score ≥ `pruner_threshold` (calibrated; starting default 0.01)
- **Return type:** `PruneResult(nodes_before, nodes_after, edges_before, edges_after, integrity_rate)` — no assert; caller enforces gate
- **Integrity gate (label-free):** `integrity_rate = |nodes_after| / |nodes_before| ≥ 0.85` — structural reachability only; no ground-truth labels used
- **Exit gate:** pruner must achieve ≥ 50% node reduction on the 15-incident calibration set

### 2.5 Canonical JSON and Content Hash

- `canonical_json(obj)`: recursively pre-normalise all floats to 6 decimal places, then `json.dumps(obj, sort_keys=True, separators=(',', ':'))`
  - Pre-normalisation is required because `json.dumps` handles `float` natively and never invokes the `default` hook; a `default`-only approach silently produces un-rounded output
- `UEGCSnapshot.compute_snapshot_hash()`: SHA-256 of `canonical_json(self.model_dump())`
- **Exit gate:** zero hash collisions verified on the 15-incident calibration set

---

## 3. D-pipe

### 3.1 Stage A — Telemetry Parser

**Input:** `data/captures/s0-adhc-001/p1_metrics.parquet`
Columns: `(timestamp: float64, metric_name: str, value: float64, labels: str[JSON])`

**Metric schemas present in this dataset:**

| Schema | `metric_name` | Key label keys |
|---|---|---|
| HTTP | `http_server_duration_milliseconds_bucket` | `http_request_method`, `http_response_status_code`, `le` |
| gRPC | `rpc_server_duration_milliseconds_bucket` | `rpc_grpc_status_code`, `le` |

**Error code classification:**

```python
HTTP_ERROR_CODES = {"500", "503"}
GRPC_ERROR_CODES = {"12", "13", "14"}  # 14 = UNAVAILABLE; present in s0-adhc-001
```

**Aggregate-before-difference protocol:**

1. For each `(timestamp, service, metric_name)` group, **sum `value` across all label combinations** (all status codes, all `le` buckets, all HTTP methods)
2. Sort the aggregated series by `timestamp` ascending
3. Difference: `delta[t] = agg[t] − agg[t−1]`; if `delta[t] < 0` (counter reset), set `delta[t] = NaN` for that single interval only and continue

Rationale: 21 per-combination counter resets in s0-adhc-001 collapse to zero resets in the aggregated series (verified empirically). NaN propagation is bounded to the single affected step.

**Error count extraction:** for each step, sum `value` over rows matching an error status code at `le = +Inf` (the cumulative bucket), then apply the difference protocol above.

**Latency mean from histogram buckets:**

```python
K_INF_MIDPOINT: int = 3
INF_MIDPOINT: float = K_INF_MIDPOINT * 10000   # 30 000 ms

def histogram_mean_ms(
    bucket_counts: list[float],
    le_boundaries: list[float],  # finite upper bounds in ms; defined in dpipe_config.py
) -> float:
    """Weighted mean latency derived from Prometheus cumulative histogram buckets."""
    total = bucket_counts[-1]    # le=+Inf is the cumulative total
    if total == 0:
        return float("nan")
    weighted_sum: float = 0
    prev: float = 0
    for i, le in enumerate(le_boundaries):
        count_in_bin = bucket_counts[i] - prev
        midpoint = (prev + le) / 2
        weighted_sum += count_in_bin * midpoint
        prev = le
    inf_count = total - bucket_counts[len(le_boundaries) - 1]
    weighted_sum += inf_count * INF_MIDPOINT
    return weighted_sum / total
```

`le_boundaries` is defined as a typed constant in `dpipe_config.py`: the Prometheus latency histogram bucket boundaries present in the s0-adhc-001 capture, from 0 ms to 10 000 ms (14 finite buckets). No magic numbers in pipeline source files.

### 3.2 Stage B — Anomaly Scoring

**Winsorized mean (wm90):**

```python
import scipy.stats.mstats

def wm90(series: np.ndarray) -> float:
    valid = series[~np.isnan(series)]
    if len(valid) == 0:
        return float("nan")
    n = len(valid)
    winsorized = scipy.stats.mstats.winsorize(valid, limits=[0, 2 / n])
    return float(np.mean(winsorized))
```

Clamps the top `2/n` fraction (at most 2 values for n = 20 steps). Outlier-robust: a single corrupt spike is clamped to the third-highest value. Burst-sensitive: anomalies spanning ≥ 2 consecutive steps are preserved. A 1-step burst is acknowledged to be partially clamped; this is an acceptable MVP limitation.

**Anomaly scores (P1 services only):**

```python
score_error_raw = {
    s: wm90(np.array([np.log1p(delta_error(s, t)) for t in steps]))
    for s in P1_SERVICES
}
score_latency_raw = {
    s: wm90(np.array([np.log1p(latency_mean_ms(s, t)) for t in steps]))
    for s in P1_SERVICES
}

# Global cross-service normalisation — computed once across P1, not per-timestamp
max_e = max(score_error_raw.values(), default=1)
max_l = max(score_latency_raw.values(), default=1)
norm_error   = {s: min(score_error_raw[s]   / (max_e + 1e-9), 1) for s in P1_SERVICES}
norm_latency = {s: min(score_latency_raw[s] / (max_l + 1e-9), 1) for s in P1_SERVICES}

score = {
    s: W_ERROR * norm_error[s] + (1 - W_ERROR) * norm_latency[s]
    for s in P1_SERVICES
}
```

`np.log1p` preserves zero-count steps (`log1p(0) = 0`) and handles large bursts without overflow.

**Non-P1 and stale services:** `score[s] = 0` — not a statistical fallback. Assignment to zero prevents non-P1 services from ranking above P1 services; nanmedian is explicitly excluded.

**Calibrated parameter:** `W_ERROR ∈ [0.3, 0.9]` — exact grid in §4.1.

### 3.3 Stage C — Directional Propagation

Direction: **caller → callee** (following CALL edges from UEG-C).

**P1 → P1 propagation (Spearman correlation):**

- Compute Spearman ρ on raw `error_rate` time series (not anomaly scores) between each directed P1 caller–callee pair
- If `ρ ≥ RHO_THRESHOLD`: `boost[callee] += ρ × score[caller]`
- Additive: the same callee can accumulate boosts from multiple P1 callers

**P1 → non-P1 propagation (topology boost):**

- `boost[callee] = max(boost.get(callee, 0), TOPOLOGY_BOOST_FACTOR × score[caller])`
- `max()`, not `+=`: prevents multi-hop accumulation beyond the direct P1 caller
- **Hard constraint:** `TOPOLOGY_BOOST_FACTOR ≥ 1` enforced at calibration — ensures a non-P1 callee is never ranked below its P1 caller due to rounding

**Final score:** `score_final[s] = score.get(s, 0) + boost.get(s, 0)`

### 3.4 Stage D — Verdict

```python
ranked = sorted(services, key=lambda s: (-score_final[s], s))  # deterministic alphabetic tiebreak
ground_truth_rank = ranked.index(ground_truth_service) + 1     # 1-indexed position
hr_at_3 = int(ground_truth_service in ranked[:3])
cpr = 1 / ground_truth_rank                                    # integer 1; not a float literal
```

Return `PipelineVerdict(hr_at_3=hr_at_3, cpr=cpr, ranked_candidates=ranked[:3], narrative=None)`.

---

## 4. Calibration, Smoke Ablation, and Exit Gate

### 4.1 Calibration Protocol

**Dataset:** 15 labeled calibration incidents (disjoint from the 5-incident smoke ablation hold-out).

**Method:** Leave-one-out cross-validation (LOO-CV) — 15 folds; fold k trains on 14 incidents and validates on incident k. LOO-CV is chosen over k-fold because it extracts maximum resolution from N = 15 (threshold step granularity 1/15 vs. 1/5 for 3-fold).

**Joint grid (250 cells = 5 × 5 × 10) — all three parameters swept simultaneously:**

| Parameter | Candidate values |
|---|---|
| `W_ERROR` | 0.3, 0.50, 0.6, 0.7, 0.9 |
| `RHO_THRESHOLD` | 0.2, 0.4, 0.6, 0.7, 0.8 |
| `TOPOLOGY_BOOST_FACTOR` | 1.00, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8 |

No sequential greedy optimisation — all 250 cells evaluated in a single pass to avoid multi-stage optimisation traps.

**Tiebreaker (5-level, evaluated in priority order):**

1. HR@3 across all 15 LOO folds (maximise)
2. Mean CpR across all 15 LOO folds (maximise)
3. std(HR@3) across folds (minimise — prefer stability)
4. min(CpR) across folds (maximise — protect worst-case)
5. `TOPOLOGY_BOOST_FACTOR` (minimise — prefer lower boost when all other criteria tie)

**Post-hoc audit (anti-deflation gate):** all 15 incidents count in the denominator regardless of whether the PPR pruner severs them. Incidents severed by the pruner contribute HR@3 of 0 and CpR of 0 to the aggregate. If more than 1/15 of calibration incidents are severed, a deviation log entry is required before freezing thresholds.

**All-stale gate:** if more than 1/15 calibration incidents produce all-zero P1 scores (all P1 services stale), a deviation log entry is required.

### 4.2 Smoke Ablation

**Hold-out:** 5 labeled incidents (disjoint from the 15-incident calibration set).

**Baselines:**

| Baseline | Description |
|---|---|
| Random | Uniform random ranking over all services; seeded from `HELIOSConfig.seed` |
| In-degree | Rank services by structural in-degree descending |

**Smoke gate:** HELIOS-D HR@3 must exceed the random baseline HR@3 on the 5-incident hold-out.

### 4.3 Exit Gate Summary

| Gate | Criterion | Enforced by |
|---|---|---|
| Hash collisions | Zero on 15-incident calibration set | Test suite |
| Canonical round-trip | `compute_snapshot_hash()` stable across re-serialisation | Test suite |
| Pruner efficacy | ≥ 50% node reduction on calibration set | Calibration script |
| Structural integrity | `integrity_rate ≥ 0.85` per incident | Pruner return value |
| D-pipe determinism | Identical output on repeated runs with identical manifest | Test suite |
| HR@3 calibration | HR@3 ≥ 0.25 on 15-incident LOO-CV | Calibration script |
| Smoke gate | HELIOS-D HR@3 > random baseline on hold-out | Smoke script |

---

## 5. Open Items and Pre-Implementation Requirements

1. **Deviation log entry — span containment heuristic** (see §2.2): log before merging any UEG-C commit
2. **`dpipe_config.py`**: must define `LE_BOUNDARIES`, `K_INF_MIDPOINT`, and the calibration grid ranges as typed constants; no magic numbers in pipeline source files
3. **Tracking rows**: Milestone 2 ENG/RES/EVAL/GATE task rows must be appended to `docs/tracking/helios_mvp_tracking.md` before implementation begins; use two-step state transitions (PLANNED → IN_PROGRESS → DONE)
