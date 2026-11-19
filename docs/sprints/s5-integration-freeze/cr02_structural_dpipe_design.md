# CR-02 Structural bundle and the D-pipe's call edges · design

**Backlog item:** CR-02 (component review backlog, S5 folder) · **Flag:** `VCLFlag.UEG_STRUCTURAL` (finding sits in `VCLFlag.DPIPE_PROPAGATION`) · **Status:** draft for the owner, 2026-11-19 · **Data:** OTel build only (`otel_build_v3`, 63 cases); RCAEval has no traces and is unaffected

## 1. What is wrong

On OTel build (S5.1 store), HELIOS-noStructural beats HELIOS-Full: top-1 34 against 31, top-3 51 against 50. A-H8 predicts the opposite.

## 2. Cause

Splitting the fused result into its pipelines (S5.1 store, own-list hits out of 63):

| Pipeline | Full top-1 / top-3 | noStructural top-1 / top-3 |
|---|---|---|
| D-pipe | 20 / 48 | **29 / 51** |
| G-pipe (57 cases it ran) | **30 / 44** | 21 / 37 |
| L-pipe (57) | 25 / 38 | 25 / 38 (identical on every case) |
| Fused | 31 / 50 | 34 / 51 |

The structural bundle does help where it is meant to: G-pipe's learned ranker, which needs the typed graph, gains 9 top-1 hits over plain PPR. The loss is in the **D-pipe**, which should not depend on typing at all.

The mechanism, found by replaying HELIOS-noLLM's D-pipe on the 63 cases with one change at a time:

- Algorithm 5 (k-hop pruner, S1.7, Chapter 3 p. 48) drops **behavioural edges whose latency correlation |r| is below 0.7**. `call` edges are behavioural and carry a latency Pearson value, so on the typed graph every weakly correlated call edge is cut.
- The D-pipe's propagation (Stage C) follows `call` edges only, so it propagates over the **strong-correlation call edges alone**.
- Under noStructural, `flatten` turns every edge into an `untyped` edge **without** a correlation value. Algorithm 5's cut then cannot apply, every call edge survives, and the D-pipe propagates over all of them.

| D-pipe replay (typed graph unless stated) | D top-1 | D top-3 |
|---|---|---|
| As frozen (strong call edges only) | 20 | 48 |
| Plus span (structural) edges | 20 | 51 |
| Plus anomaly-lead edges | 20 | 49 |
| Plus anomaly-lead and co-move edges | 20 | 49 |
| **Weak call edges kept** | **30** | **51** |
| Weak call edges kept, plus anomaly edges | 29 | 51 |
| Flattened graph (as noStructural) | 29 | 51 |

So the A-H8 contrast currently measures something other than typing: noStructural escapes Algorithm 5's correlation cut, Full does not. A call that exists but whose latencies do not co-move is still a path along which a failure propagates; latency correlation is a reasonable filter for the graph G-pipe ranks on, but a poor one for the D-pipe's call topology.

## 3. Proposed fix and replay

**Fix (C2-a).** The D-pipe's propagation uses every observed `call` edge between the pruned subgraph's candidate services, taken from the graph **before** Algorithm 5's correlation cut. The pruned subgraph itself, what G-pipe ranks on, its content hash, and Algorithm 5 are unchanged. Under noStructural nothing changes (its edges carry no correlation already).

**Replay, all pipelines, OTel build, L-pipe answers from the response cache** (no miss):

| Run | Fused top-1 / top-3 | D-pipe | G-pipe | L-pipe ran |
|---|---|---|---|---|
| Full, as frozen | 31 / 50 | 20 / 48 | 30 / 44 | 57 |
| **Full, C2-a** | **34 / 52** | 30 / 51 | 36 / 46 | 57 |
| noRouter, C2-a | 34 / 52 | 30 / 51 | 42 / 52 | 63 |
| noStructural, as frozen | 34 / 51 | 29 / 51 | 21 / 37 | 57 |

The as-frozen rows (Full, noRouter 31 / 50, noStructural) reproduce the S5.1 store exactly, so the replay path is the campaign's path.

- Full gains 3 top-1 and 2 top-3 hits; G-pipe gains too, because it is seeded by the D-pipe's scores.
- Full and noStructural become level on top-1 and Full leads by one on top-3. A-H8's contrast then measures the bundle itself.
- The same fix applied to the pruned graph (keeping weak call edges for every consumer) gives the same Full figures, but it changes Algorithm 5, which is pre-registered; C2-a does not.

## 4. Latency (not a ranking change)

The 0.9 s that Full spends over noStructural is the G-pipe's learned ranker computing its trace features (median G-pipe latency 970 ms against under 1 ms for plain PPR). It is the price of the ranker that gives G its 9 extra top-1 hits. It is reported, and profiled separately if time allows; no change is proposed here.

## 5. Decisions for the owner

| # | Decision | Proposal | Alternatives |
|---|---|---|---|
| C2-a | D-pipe call edges | **All observed call edges between the pruned candidates, before the correlation cut** | Keep as frozen and report the confound; change Algorithm 5 for every consumer |
| C2-b | D-pipe parameters | **Not refitted** (ρ threshold and topology boost stay as frozen); the replay above is with the frozen values | Refit the D-pipe on build data |
| C2-c | Order with CR-01 | **CR-02 first.** The router reads D-pipe features (margin, share, μ, σ), so it is refitted after the D-pipe change | — |
| C2-d | Deviation entry | **One entry** for C2-a to C2-c, text to the owner first, appended before the code change merges | — |
| C2-e | A-H8 reading | Addendum note: the S5.1 figures were measured with the confound; after C2-a the bundle's contrast is typing, the learned ranker and reasoning-step structure only | — |

## 6. Steps after approval

1. Deviation entry (text to the owner first).
2. Code: `incident_graph` also returns the pre-cut call edges among the kept candidates; the runner passes them to `run_dpipe`; D-pipe calibration reads the same path, so build and runs agree. Tests: a weak call edge reaches Stage C under Full; nothing changes under noStructural; the pruned snapshot's hash is unchanged.
3. The D-pipe parameter hash is unchanged; the decision hashes of OTel runs change.
4. CR-01 refit on top of this (its design note, step 3).
5. The reruns listed in the CR-01 note cover this change too (one rerun of the routed and graph-using variants on build data).

## 7. What this changes and what it does not

- **Changes:** D-pipe rankings on trace-bearing cases (OTel) for every variant with the graph, D-pipe propagation and the typed graph on: Full, noLLM, noConsensus, noRouter and the seven exploratory variants; router features on those cases. HELIOS-D (graph off), HELIOS-G (propagation off) and LLM-only are unaffected.
- **Does not change:** RCAEval (no traces, no graph); noStructural; Algorithm 5 and the pruned subgraph; any hypothesis, metric, test, alpha or Holm rank.
