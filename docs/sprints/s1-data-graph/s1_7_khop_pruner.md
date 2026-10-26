# S1.7 — K-hop pruner (Algorithm 5) · design and calibration

**Task:** S1.7 (tracking S2-M6-ENG05) · **Date:** 2026-10-26 · **Code:** `helios/graph/khop_pruner.py` (`khop_prune`), `bin/khop_calibrate.py` · **Deviation:** entry 40 (K, top-n, seeds, causal expansion, floor) · **Flags:** the pruner serves every variant; the typed graph it reads is gated by `VCLFlag.UEG_STRUCTURAL` (structural bundle, S1.6, applied before pruning)

## Chapter 3

Algorithm 5 (p. 48): given the UEG-C, seed nodes, a hop limit K, a Pearson threshold (pre-registered r = 0.7) and an edge budget of 10,000, expand the seeds by K-hop traversal over structural and behavioural edges, keep the top-n nodes by personalized PageRank, drop causal and behavioural edges below the threshold, and content-hash the result. p. 39: "a subgraph of 50 to 200 nodes". Chapter 3 does not say where the seeds come from, nor the values of K and top-n.

## Design

| Step | Implementation | Source |
|---|---|---|
| Seeds | The three services with the highest peak anomaly intensity in the window (new service-node metadata `anomaly_peak`, from the S1.5 metric + log intensity); else call-graph entry points; else every service. Label-free. The D-pipe trigger (S2.1) may pass its own seeds. | Design choice; three = the HR@3 horizon |
| Expansion | K hops, undirected, over structural, behavioural and untyped edges **and causal edges with \|r\| ≥ 0.7** | Ch3 + extension (below) |
| Selection | Seeds first, then the K-hop neighbourhood, each ordered by personalized PageRank from the seeds (restart 0.15, scores rounded to 12 digits, ties by name); filled up to **50 services** from the rest of the graph when the neighbourhood is smaller; at most top-n | Ch3 (50–200 range) + floor (below) |
| Kept with services | KPI nodes of kept services; tenant-`self` nodes (reasoning steps) | S1.5 |
| Edge cut | Causal and behavioural edges with \|r\| < 0.7 dropped; edges without a correlation (structural, call edges without latency evidence, agent-step edges) stay | Ch3 |
| Budget | At most 10,000 edges, strongest first | Ch3 |
| Hash | `KHopResult.snapshot_hash` of the pruned snapshot | Ch3 |

Floor and top-n count production service nodes (the root-cause candidates); KPI and reasoning-step nodes come along with them.

**Two extensions beyond Chapter 3, both forced by the data:**

1. *Causal edges in the expansion.* The RCAEval build corpus has no traces (S1.5), so its graphs have no structural or behavioural edges and a topology-only expansion never leaves the seeds. Strong causal edges (anomaly propagation, \|r\| ≥ 0.7 — the same threshold) let trace-less services be reached.
2. *A 50-service floor.* Pure Algorithm 5 loses the root cause too often (calibration below: 76% kept at best). Reading Chapter 3's "50 to 200 nodes" as a lower bound as well as an upper bound, a graph is never cut below 50 services; graphs with 50 or fewer services keep every service and only lose weak edges.

**Changes to graph construction made here.** Service nodes gain `anomaly_peak` metadata (six decimals); log lines with no service name no longer become a service node with an empty name (a fake candidate found in the S1.5 OTel graphs — one per graph). Both change S1.5 snapshot hashes: OTel captures digest `dc092f39ff6d` → `945df66330a0` (services per graph 16 → 15, causal edges median 3 → 2); build digest `c76898d9d40f` → `3176badc5996` (metadata only: services and edge counts unchanged; rebuilds identical 495/495).

## Calibration

**Data:** the 495 build windows (labels allowed — build data); the 20 OTel captures as a check. The pool is refused by the tool. Command: `poetry run python bin/khop_calibrate.py --corpus build|captures` (counts only; two runs gave identical output).

**Selection rule.** The grid K ∈ {0, 1, 2, 3} × top-n ∈ {50, 120, 200} runs Algorithm 5 *without* the floor, so it measures how far from the seeds the root cause lies. Highest root-cause retention wins; ties go to the smaller K, then the smaller top-n. *The rule was first stated with the floor on; a dry run on the OTel captures showed every setting ties at full retention there (15-service graphs are below the floor), which would pick K = 0. It was changed to the floor-off form before the build run.*

**Build results (495 graphs, 13–64 services, median 15; 125 graphs have 64 services):**

| K | Root cause in the pruned graph (no floor) | Services kept, median (max) | Edges cut by r, max |
|---|---|---|---|
| 0 (seeds only) | 251 / 495 | 3 (3) | 4 |
| 1 | 327 / 495 | 7 (41) | 107 |
| 2 | 362 / 495 | 8 (50 at top-n 50) | 198 |
| **3** | **376 / 495** | 8 (50 at top-n 50) | 198 |

top-n changes nothing in retention at any K (no neighbourhood exceeds 60 services), so the tie-break gives **top-n = 50**. **Selected: K = 3, top-n = 50.**

**As the orchestrator runs it (K = 3, top-n = 50, floor 50):** root cause kept in **492 / 495** build graphs; services kept 13–50 (median 15). The 125 graphs with 64 services are cut to exactly 50; all others keep every service. The three losses are a ceiling on HR@k for those build cases. The 10,000-edge budget never binds (at most 861 edges kept).

**OTel captures:** 16 of 20 labels are service nodes (the other four name `imageService`, which is not a service in the OTel graph); the root cause is within one hop of the seeds in 16/16, and the floor keeps every service (15 per graph).

**Done-when.** "50–200 nodes on build incidents": met for every build graph with more than 50 services (125/125 cut to 50); graphs with fewer services cannot reach 50 and are kept whole. Calibration logged here and in deviation entry 40.

**By-product (exploratory, build data):** the anomaly-peak seeds alone contain the root cause in 251/495 build cases — a label-free top-3 reference point for the pipelines (random top-3 among the median 15 services is about 3/15).

## Open points

- The S1.2 captures (traces, about 60 incidents) should re-check K with topology edges present; RCAEval pool windows have traces, build windows do not. Any change is a new deviation entry before build-freeze.
- `prune_graph` (`helios/graph/ppr_pruner.py`) and the frozen `PRUNER_THRESHOLD` stay unchanged for the Milestone 2 evidence; the orchestrator no longer calls it.
