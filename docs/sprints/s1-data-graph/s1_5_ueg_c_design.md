# S1.5 — Typed incident graph (UEG-C) · design

**Task:** S1.5 (tracking S2-M6-ENG03) · **Date:** 2026-10-25 · **Schema:** UEG-C `schema-draft-v0.1` → `schema-draft-v0.2` (deviation entry before merge) · **Flags:** graph construction gated by `VCLFlag.L2B_GRAPH`; structural edges by `VCLFlag.UEG_STRUCTURAL`

## Why a redesign

Chapter 3 (C2, §1.4.3, §3.6) asks for one graph with four typed edge classes — structural, behavioural, causal, economic — "formal composition rules" so that cross-domain path queries (causal composed with economic, behavioural composed with structural) are first-class, Agent-Reasoning-Step (ARS) and Transaction-or-KPI nodes, and nodes for every service seen in any modality. It does not define the composition rules.

The May builder (`schema-draft-v0.1`) had two edge kinds from traces only. Its "four classes" were a relabelling of sub-types (log edges counted as *economic*, metric edges as *causal*), and nothing produced the metric or log edges. Its snapshot hash was not stable: `captured_at_iso` was the wall-clock time of the build.

## Schema v0.2 (`helios/schemas/ueg_c.py`)

**Nodes** (`UEGCNode`): `node_id`, `node_type`, `service_name`, `tenant`, `metadata`.

| Node type | Meaning | Source |
|---|---|---|
| `service` | Root-cause candidate | traces, metrics or logs — any modality (metadata `modalities`) |
| `operation`, `pod`, `database`, `external` | Kept from v0.1 | not built for RCAEval |
| `transaction_kpi` *(new)* | User-facing transaction / KPI of an entry service | derived from traces (see economic edges) |
| `agent_reasoning_step` *(new)* | One step of an agent's reasoning (P4) | supplied by the caller; tenant `self` |

`tenant` (*new*, default `prod`) is the C5 partition: HELIOS's own telemetry and ARS nodes are written under `self` into the same graph. Only `service` nodes in tenant `prod` are root-cause candidates (`UEGCSnapshot.candidate_ids()`); pipelines rank nothing else.

**Edges** (`UEGCEdge`): `source`, `target`, `edge_type` (the relation), `weight` in [0, 1], and two optional evidence fields: `correlation` (Pearson r in [−1, 1]) and `lag_seconds`. `edge_class` is derived from `edge_type`, never stored separately, so it cannot disagree with it.

| Class | Relation (`edge_type`) | Built from | Direction | Weight | Evidence |
|---|---|---|---|---|---|
| structural | `structural` | parent → child span, different services | caller → callee | 1 (topology) | — |
| structural | `precedes` | ARS order | step → next step | 1 | — |
| behavioural | `call` | the same calls, observed traffic | caller → callee | share of traces with the call | `correlation`: caller vs callee latency per bucket |
| behavioural | `invokes` | ARS tool call on a service | step → service | 1 | — |
| causal | `anomaly_leads` | anomaly intensity (metrics + log templates) of A leads B | A → B | \|r\| at the best lag | `correlation`, `lag_seconds` > 0 |
| causal | `anomaly_co_moves` | same, best lag 0 | both ways | \|r\| | `correlation`, `lag_seconds` = 0 |
| economic | `serves_kpi` | service → KPI node of an entry service | service → KPI | share of the entry's traces that pass through the service | — |

`metric` and `log` from v0.1 are removed (never built).

## How each class is built

- **Calls (structural, behavioural).** Parent and child spans are linked by `parent_span_id` within a trace; temporal containment remains only as the warned fallback for trace files without that column. Behavioural `correlation` is the Pearson r between the caller's and callee's mean span duration per bucket, when both have enough buckets.
- **Anomaly intensity per service** (input to causal edges). Metrics: every series of the service (`service_name` label, else the last part of `job`) is put on buckets aligned to the window start; counters (`_total`, `_count`, `_sum`, `_bucket`) are differenced; each series is turned into a robust z-score (median, MAD) over the whole window; intensity = max \|z\| over the service's series per bucket. Logs: the per-bucket line count of the service from S1.4 templates, plus the lines of templates new to that service in that bucket, z-scored the same way. Service intensity = max of the two. Everything comes from the window itself: no injection time, no labels, no other case.
- **Causal edges.** For every ordered pair of services with intensity series, the Pearson r at lags 0 … `MAX_LAG_BUCKETS`; an edge is kept when the best \|r\| ≥ `CAUSAL_MIN_R`. Positive best lag → `anomaly_leads` A → B; lag 0 → `anomaly_co_moves` both ways. This is how metric-only and log-only services get edges.
- **Economic edges and KPI nodes.** Entry services are the services owning root spans. Each gets one `transaction_kpi` node (`kpi:<service>`); every service on the entry's traces gets `serves_kpi` with the share of those traces it appears in. RCAEval has no business telemetry (P5), so the KPI is the user-facing transaction itself; revenue or SLO-penalty weights replace the traffic share where P5 exists (Stage B).
- **ARS nodes.** `build_ueg_c(..., reasoning_steps=...)` adds them (tenant `self`), with `precedes` and `invokes` edges. Nothing produces reasoning steps before the L-pipe rebuild (S2); the schema and builder are ready and tested on a fixture.

## Composition rules (`helios/graph/composition.py`)

Order the classes structural < behavioural < causal < economic. Composing two adjacent edges gives the larger class, except that nothing may follow an economic edge (KPI nodes are sinks):

    compose(a, b) = undefined   if a is economic
                  = max(a, b)   otherwise
    undefined composed with anything is undefined

A path's class is the composition of its edge classes; its weight is the product of edge weights (stays in [0, 1], never grows along a path). The rule is associative (tested over every triple), so a path's class does not depend on how it is grouped, and it gives Chapter 3's examples: behavioural ∘ structural = behavioural; causal ∘ economic = economic ("which KPI does this anomaly reach, and how strongly"). `typed_paths(snapshot, source, target, max_hops)` returns every simple path with its class and weight — the cross-domain query.

## Determinism

`captured_at_iso` is the window end, not the build time; nodes and edges are sorted; floats are rounded by `canonical_json`. The same window and parameters always give the same snapshot hash (tested on build cases).

## Parameters (calibration, recorded in the deviation entry)

`BUCKET_SECONDS` 30 (same as S1.4), `MAX_LAG_BUCKETS` 4 (two minutes), `CAUSAL_MIN_R` 0.6, `MIN_POINTS` 8 buckets for any correlation. Chosen a priori; checked on build cases only (edge counts per class, nodes per graph). S1.7 calibrates K and top-n.

## Effect on existing code

- D-pipe propagation reads `call` edges (unchanged relation name).
- The May pruner computes PageRank over structural and behavioural edges only and keeps trace-less service nodes and the KPI nodes of kept services; S1.7 replaces it with Algorithm 5.
- G-pipe ranks only candidate nodes.
- The M4 OTel results (exploratory, May) are not re-created; their graphs were built with v0.1.

## Not in S1.5

The `ueg_structural` OFF behaviour (one untyped class, full-graph training, ARS as flat text) is S1.6; until then OFF drops structural edges as before. Subgraph-aware training is S2. The pool is not built or inspected (pool lock).
