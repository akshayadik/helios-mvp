# S2.2 — G-pipe culprit-versus-victim ranker · design

**Task:** S2.2 (tracking S2-M7-ENG02) · **Date:** 2026-10-29 · **Status:** approved by the owner 2026-10-29 · **Depends on:** S2.1 (frozen trigger and D-pipe, deviation entries 52–53), S1.7 K-hop pruner, S1.5 UEG-C builder, S1.2 OTel build corpus · **Owner decisions:** the points marked *owner* below (2026-10-29)

## 1. Intent

D-pipe scores every service on its own shift. In a cascade, a caller that times out because its dependency is broken looks as anomalous as the dependency itself, so D-pipe treats one failure as several equal local failures. **G-pipe's job is culprit versus victim** *(owner)*: use the trace graph to push the true root above the services that only suffer from it, and hand over the facts that justify the ranking, before L-pipe writes any narrative.

An examiner should be able to see, for a top suspect, *why* it outranks its callers: "checkout spent 94% of its time waiting on payment", "payment degraded one bucket before checkout", "new call path X → Y after the trigger". Those facts are the G-pipe evidence L-pipe cites (IN1) and the RQ4 study can check.

Today's G-pipe (`helios/pipelines/g_pipe/pipeline.py`, 165 lines) runs plain personalised PageRank over the whole incident graph, seeded by D-pipe's scores, only when D-pipe's third score is at least 0.2 of its top score; it reports no σ.

## 2. Decisions already made

| # | Decision | Who |
|---|---|---|
| G-a | G-pipe is the **graph** pipeline (L2). Log and stack-trace reading, hypotheses in prose, RAG over change events and runbooks belong to L-pipe (S2.3), the narratives (IN1) or Stage B | owner, 2026-10-29 |
| G-b | **Stage A features:** (1) anomaly leads at metric-bucket resolution, (2) self time versus wait time, (4) ghost edges. **Stage B:** (3) cross-layer convergence onto shared infrastructure (no infrastructure layer exists in either corpus) and (5) retry and cycle inflation (cycles are rare; (2) absorbs most retry wait) | owner, 2026-10-29 |
| G-c | **Three candidates, simplest wins unless beaten:** a low-parameter learned ranker; feature-weighted PPR with constants fixed before the run; plain PPR (today's G-pipe). Complexity must earn its place; a tie or a margin short of the bar goes to the simpler candidate. Freezing a learned ranker that fails its held-out test is ruled out | owner, 2026-10-29 |
| G-d | **Wait time is the union of the child spans' time intervals**, never the sum of their durations (concurrent calls overlap; a sum can push self time below zero) | owner, 2026-10-29 |
| G-e | **The ghost-edge baseline is fixed by definition:** the part of the window before the frozen trigger, the same split D-pipe uses. No lookback parameter | owner, 2026-10-29 (60-minute lookback replaced: v3 windows have 8–15 minutes before the fault) |
| G-f | **The 20 earlier OTel captures** (`data/captures/`, OSF deposit 1, exploratory) join the 63 v3 cases as build data for G-pipe (D11 allows it) | owner, 2026-10-29 |
| G-g | Whichever candidate is frozen, G-pipe exports its per-suspect evidence for L-pipe | owner, 2026-10-29 |
| G-h | **`ueg_structural` OFF (HELIOS-noStructural, A-H8):** G-pipe drops back to plain PPR on the flattened graph, so A-H8 measures typed structure and everything built on it (call edges, leads, wait share, ghost edges); E-H10 attributes the difference across these sub-mechanisms. If plain PPR wins the selection, the two arms coincide for G-pipe. Recorded in the pre-run deviation entry, since it fixes what a confirmatory hypothesis measures | owner, 2026-10-29 |

## 3. Goals, non-goals, anti-goals

**Goals**
1. Three Stage A graph features per service, computed from the sealed window and the frozen trigger only, the same way on OTel and on RCAEval trace data.
2. The three candidate rankers, one selection run on build data under a rule fixed before the run, and the winner frozen in `data/frozen/gpipe_params.json` with a hash.
3. G-pipe σ (for S2.5 consensus) and a per-suspect evidence record stored with the verdict.
4. Bitwise rerun equality across processes, as for the trigger and D-pipe.
5. A build report: HR@3 of every candidate, with D-pipe and plain PPR alongside, per held-out fault; plus the gated view (how many cases the current routing gate sends to G-pipe, and HR@3 on those).

**Non-goals**
- Stage B features (3) and (5); any LLM or text reading (G-a).
- Recalibrating the routing gate: S3.1 replaces it with the cheap-first router (IN3). S2.2 leaves `DISAGREEMENT_THRESHOLD` unchanged.
- Log-template novelty. The task breakdown lists it among G-pipe features, but the 20 earlier captures have unattributed logs (deviation entry 50) and log reading belongs with L-pipe; it is left out of Stage A G-pipe. *(My call — §8.)*
- The narrower "services with metrics" idea for D-pipe propagation (S2.1 finding): G-pipe's wait-share edges do this job directly; it is not revisited here.

**Anti-goals**
- Any service identity in the features or the model (F3): no names, no one-hot, no per-service constants. A feature-audit test fails training if one appears.
- Any path for the injection time, the fault or a label into features, ranking or evidence. Labels are used only to score build runs.
- Tuning anything on the confirmatory pool or looking at pool outcomes before `build-freeze`.
- Feature-weighted PPR constants chosen by looking at results (a grid search in disguise).
- Editing `research/osf/*`, `docs/tracking/metric_contract.md`, `helios/vcl/variants.py` or the seed register.

## 4. Constraints

- **Build data (G-f):** the 63 `otel_build_v3` cases plus the earlier captures in `data/captures/`. Their `imageSlowLoad` cases (4) are left out: that fault was excluded from the campaign because its root cause is not a single service (S1.2 labelling rule, deviation entry 44). That leaves **79 cases over the 9 v3 fault types**. The earlier captures differ: 5 users, the fault at the exact middle of the window (T19), histograms rather than span metrics, unattributed logs. G-pipe's features use traces and the trigger, so the logs do not matter; the T19 cue matters only if a feature reads position, and none may. *(My call — §8.)*
- **No trace-bearing RCAEval build data exists.** The pool (RE2/RE3 Online Boutique and Train-Ticket) has traces in the same P2 columns (`helios/adapters/rcaeval.py` writes `trace_id`, `span_id`, `parent_span_id`, `service_name`, `start_time_us`, `duration_us`, `status_code`). The OTel demo descends from Online Boutique; Train-Ticket is a much larger graph, and the pool's faults (CPU, memory, disk, delay, loss, socket, code-level) differ from the demo's feature flags. That shift is why the learned ranker stays small and why selection holds whole faults out.
- Trace check on OTel v3 (one case): every child span's parent is in the capture; 12,455 of 38,948 child spans cross a service boundary. Self and wait time are computable; RCAEval pool traces are not inspected before `build-freeze`.
- Trigger and D-pipe come from their frozen files; G-pipe's seeds are D-pipe's in-scope scores, as today.
- Out-of-scope services (D-f) take part in the graph but are never ranked.
- G-pipe stays under `VCLFlag.GPIPE`; the graph under `VCLFlag.L2B_GRAPH`. The choice of candidate is a frozen parameter, not a new flag: the 17-flag registry and every variant hash are fingerprinted by OSF deposit 1.
- Python 3.11; networkx (already used); any new dependency pinned and justified. The learned ranker needs no new library if it is a regularised linear model fitted by a deterministic solver (numpy / scipy).

## 5. Design

### 5.1 Features (per service, per window)

All from the incident graph the runner builds (`incident_graph`), the P2 spans, the frozen trigger time `t` and D-pipe's verdict. No feature may read the window's start or end, the position of `t` in the window, or a service name.

1. **Leads (feature 1).** For each call edge A → B (A calls B), whether B's anomaly onset is at least one bucket earlier than A's. A service's onset is the first bucket **at or after the trigger bucket** in which its causal score from the frozen detector (60 s buckets, `service_scores`) reaches the frozen threshold; crossings before the trigger are noise and ignored. A service that never crosses has no onset, and a callee with an onset leads a caller without one (in a cascade the victim often stays under the threshold). Per service: number of callers it leads, number of callees that lead it. Ordinal, bucket resolution only *(owner: "earlier by at least one bucket")*.
2. **Self and wait time (feature 2).** For each server span of a service: wait = the length of the union of the time intervals of its child spans in *other* services; self = duration − wait (never below zero by construction, G-d). Per service, after `t` against before `t`: shift of the median self time (robust scale as the detector). Per call edge A → B: A's **wait share on B after `t`** (wait on B ÷ A's total span duration, over A's spans after `t`) and its rise against before `t`.
3. **Ghost edges (feature 4).** A call edge (caller service → callee service) present after `t` and absent before `t` (G-e). Per service: number of ghost edges it is the callee of and the caller of. An edge seen before `t` only is not a ghost.
4. **Context features** (already computed or cheap): D-pipe's normalised score; plain PPR score (rounded with the `canonical_json` rule); call-graph in-degree and out-degree (the task breakdown's "graph centrality"); error share of its own spans after `t` against before.

**Which services.** Features and ranking cover the services of the K-hop-pruned incident graph the runner passes to G-pipe (the deployed behaviour); the spans are read for those services, split at `t`. Every candidate ranks the same service set, so a root pruned away is a miss for all three alike.

**No usable split.** A window without traces gets no graph and G-pipe abstains, as today. A window with traces but without spans on both sides of `t` gets no Stage A features: the feature-weighted and learned candidates then **fall back to plain PPR** for that window, so every candidate ranks all 79 cases and the selection denominator stays 79 (an abstention is never silently dropped). The number of fallback windows is reported.

### 5.2 The three candidates

1. **Learned ranker.** A linear score over the features of §5.1 (at most about ten weights), fitted as a pairwise ranking objective (the true root above each other candidate in the same window), L2-regularised, by a deterministic solver; the regularisation strength is fixed before the run. Registered seed for anything stochastic (none expected). Weights hashed into `gpipe_params.json`.
2. **Feature-weighted PPR.** The walk runs over call edges only, caller → callee, with edge weight = the caller's wait share on that callee after `t`, plus a self-loop with weight = the service's self share; ghost edges join the graph with the weight their spans give them. Restart (personalisation) vector = D-pipe's scores, doubled for a service that leads at least one of its callers. α = 0.85 (today's `GPIPE_PPR_ALPHA`). These constants are set here, before the run, and never tuned. Mass flows from victims (high wait share) to the callees they wait on and pools where self time is high.
3. **Plain PPR.** Today's G-pipe unchanged: all UEG-C edges, D-pipe seeds, α 0.85.

### 5.3 Selection rule (fixed before the run; owner G-c)

- Metric: HR@3 over the 79 build cases, scored against the signed ground truth (stem matching for the earlier captures' `adService`-style labels, as today).
- The learned ranker is scored **leaving one fault type out**: 9 folds, each trained on the other 8 faults and scored on the held-out one. Feature-weighted and plain PPR have nothing to fit and are scored once.
- A candidate beats the next simpler one only if it has **at least 3 more top-3 hits** (of 79) **and** is better on more held-out faults than it is worse. Otherwise the simpler one is selected. Order: learned vs feature-weighted PPR, then the survivor vs plain PPR. Ties always go to the simpler candidate.
- If the learned ranker wins, it is refitted on all 79 cases with the same settings and that fit is frozen.
- The report gives every candidate's HR@3 overall and per fault, D-pipe's HR@3 on the same cases (the lift from graph reasoning), and the gated view. A negative result is reported in full.

### 5.4 σ and evidence

- **σ = 1 − gap × strength**, as D-pipe: gap = (top score − second score) ÷ top score; strength = the share of the three Stage A evidence kinds that support the top suspect: (i) at least one caller's wait share on it **rose** after `t` against before; (ii) it leads at least one caller; (iii) it is the callee of a ghost edge. Always in [0, 1]. *(My call — §8.)*
- **Evidence record** stored with the G-pipe verdict, for each of the top three suspects: wait share pooled from each caller, lead relations (who it leads, by how many buckets), ghost edges it is part of, self-time shift. Numbers rounded with the `canonical_json` rule, service names as in the graph. No label, no injection time.

### 5.5 Routing

The gate (`should_run_gpipe`, disagreement ≥ 0.2) is unchanged in the runner. The selection run scores G-pipe on **all** build cases, ignoring the gate, so the comparison is not limited to the cases the May threshold lets through; the gated view is reported beside it as the starting point for S3.1. *(My call — §8.)*

### 5.6 Determinism

PageRank with fixed iteration limit and tolerance; sorted node and edge order; ties broken by service name only *after* scoring (never as a feature). Two separate processes on the same window give byte-identical verdicts and evidence (`bin/trigger_check.py --with-dpipe` gains a G-pipe line, or a sibling check).

## 6. Protocol records

- **Before the run:** deviation entry for the selection rule (§5.3), the feature definitions (§5.1), the feature-weighted PPR constants (§5.2), the build data (G-f, imageSlowLoad excluded), σ (§5.4) and the noStructural behaviour (G-h, A-H8).
- **After the run:** deviation entry for the frozen candidate and its parameters (hash), the build HR@3 of all candidates, and any negative result.
- Validity tracking: T19 (the earlier captures' mid-window onset; no feature reads position), the OTel-to-pool shift (a new or extended threat), and the feature audit (F3).
- Carry-over from S2 plan: add the OTel corpora (v3 and the earlier captures) to `bin/khop_calibrate.py` and re-check K = 3 / top-n 50 on 79 cases. This lands in PR 1, **before** the selection run, so G-pipe is selected on the graph it will run on; a change of K is its own deviation entry.
- The earlier captures were not in the S2.1 calibration; the frozen trigger is applied to them as it is (no retuning), and its outcome on them (threshold vs fallback) is reported.

## 6a. Size and tracking

Row S2-M7-ENG02 (planned, effort 3). About 3–4 days: features and evidence (1½), candidates and selection tool (1), σ, runner wiring, determinism and K-hop carry-over (1), report and entries (½). Two PRs: (1) features, candidates, selection tool and the rule's deviation entry; (2) the run, the freeze and the result entry.

## 7. Done when

- Feature-audit test, interval-union test (concurrent children), ghost-edge test (edge before `t` only is not a ghost), leakage scan passing with G-pipe on the run path.
- Selection run on the 79 build cases per §5.3; report committed; the winner frozen with its hash; the frozen file tied to the report by a test.
- σ and evidence in every ranked G-pipe verdict; cross-process byte equality.
- Two deviation entries; tracking row DONE; full gate; fresh review; PRs merged by the owner.

## 8. Calls I made (owner to check)

1. Log-template novelty left out of Stage A G-pipe (unattributed logs in the earlier captures; log reading belongs to L-pipe).
2. imageSlowLoad cases excluded from the earlier captures (79 cases, 9 fault types, not 83 and 10 as first said in conversation).
3. σ strength = share of the three evidence kinds supporting the top suspect.
4. Selection scores G-pipe on all cases, ignoring the routing gate; the gated view is reported.
5. Feature-weighted PPR constants: weights = wait share and self share, restart doubled for a leader, α 0.85.
6. Learned ranker = L2-regularised pairwise linear model; regularisation strength fixed before the run.
7. Onset is searched from the trigger bucket on; a callee with an onset leads a caller without one.
8. Every candidate ranks the K-hop-pruned service set the runner passes; the K-hop re-check lands before the selection run.
9. Without spans on both sides of `t`, the feature candidates fall back to plain PPR for that window (denominator stays 79).
10. "Graph centrality" from the task breakdown = call-graph in- and out-degree among the learned features.

## 8b. PR 1 review amendments (owner, 2026-10-30) — before the selection run

A fresh review of PR 1 found two defects that change the rule signed in deviation entry 54; no selection had run. Owner decision G-i, recorded in deviation entry 55:

1. **Build data = the 63 `otel_build_v3` cases** (9 fault types, 7 root services — entry 55 says 6; corrected in entry 56). The 20 earlier captures are dropped: in their P2 files 88–90% of span IDs appear under several services (up to 9), because the May capture stamped every span of a returned trace with the queried service, so wait shares, call edges and ghost edges are invented there (v3: 0%). This replaces G-f. P2 files with a span under more than one service are now refused.
2. **The learned ranker is scored leaving one root service out** (one fold per root, 7 folds), not one fault type: `ad` is the root of three faults, so a fault-type fold still trained on the held-out service.
3. **No degree features; D-pipe and PPR scores divided by the window's largest.** In a fixed topology degree is a per-service constant (an identity proxy, F3), and raw scores scale with the window and graph size. Ten features remain.
4. The 3-hit margin and the order of comparisons are unchanged (now of 63).

Code fixes from the same review (no rule change): only in-scope services are ranked, so σ and the evidence describe the verdict's suspects; status codes `2`, `ERROR`, `STATUS_CODE_ERROR` count as errors (RCAEval writes `2`); every G-pipe run stores its ranker and whether features were used. Wording made exact in entry 55: the evidence kind (i) is a rise of the **pooled** wait share; the walk gives a service with no requests after `t` a self-loop of one and drops zero-share edges; the learned ranker's scores pass through an order-preserving softmax for μ, and its standardisation uses the training fold only.

Consequence outside S2.2: May results built on the 20 earlier captures (exploratory runs, the May G-pipe threshold) used the same span attribution; recorded as a validity threat, not redone here.

## 9. Left to the builder

Module layout; the exact pairwise objective and solver; how evidence is attached to the verdict (field and schema version); rounding details within the `canonical_json` rule; report layout.

## 10. Results

### K-hop re-check (S2 plan carry-over, 2026-10-29) — before the selection run

`bin/khop_calibrate.py` (HELIOS-Full graphs; root-cause retention per (K, top-n); then the frozen setting with the 50-node floor, and seeded by the frozen trigger's suspects with the out-of-scope services excluded, as the runner prunes):

| Corpus | Graphs | Root is a service node | K = 3, top-n 50, no floor | With the floor | Seeded by the frozen trigger | Services kept (with floor) |
|---|---|---|---|---|---|---|
| OTel build v3 | 63 | 63 | 63/63 | 63/63 | **63/63** | 29 (every graph) |
| Earlier captures | 20 | 16 (the 4 imageSlowLoad cases have no service root) | 16/16 | 16/16 | **16/16** | 15 (every graph) |

The frozen K = 3 / top-n 50 (deviation entry 40) keeps the root in all 79 G-pipe build cases; no change. On the earlier captures every K in the grid keeps all 16 roots, so the S1.7 tie rule prints K = 1; that is a tie on a 16-case corpus, not a reason to move K. OTel graphs are smaller than the 50-node floor, so on OTel the pruner keeps every service: G-pipe ranks over the whole service graph there. The trigger's suspects contain the root in 22 of 63 v3 cases (6 of 16 earlier).

### G-pipe selection run 1 (2026-10-30) — learned ranker frozen

`bin/gpipe_select.py` on the 63 `otel_build_v3` cases under the rule of deviation entries 54–55 (HELIOS-Full graphs, frozen trigger and D-pipe; routing gate ignored; the learned ranker scored leaving one root service out — **7 folds**: the labels have 7 root services (paymentUnreachable's root is `checkout` under the S1.2 labelling rule, entry 44), not the 6 entry 55 states; one fold per root is what the rule intends). Top-3 hits:

| Fault (7 cases each) | Learned | Feature-weighted PPR | Plain PPR | D-pipe alone |
|---|---|---|---|---|
| adFailure | 4 | 4 | 3 | 4 |
| adHighCpu | 7 | 7 | 5 | 7 |
| adManualGc | 7 | 7 | 7 | 7 |
| cartFailure | 7 | 7 | 7 | 7 |
| emailMemoryLeak | 5 | 5 | 5 | 5 |
| paymentFailure | 6 | 2 | 2 | 4 |
| paymentUnreachable | 7 | 4 | 5 | 7 |
| productCatalogFailure | 6 | 6 | 4 | 6 |
| recommendationCacheFailure | 1 | 1 | 1 | 1 |
| **Total (of 63)** | **50** | 43 | 39 | 48 |

Rule: learned vs feature-weighted PPR +7 hits, better on 2 faults, worse on none → learned; learned vs plain PPR +11 → **learned selected**. Feature fallbacks 0; no case without a graph. Gated view: the current routing gate sends 44 of 63 cases to G-pipe; HR@3 on them learned 32, weighted 25, plain 21.

What it means: the lift of G-pipe over D-pipe alone is **2 cases**, both paymentFailure (root payment brought into the top three); elsewhere G-pipe matches D-pipe. "Never trained on" holds for the G-pipe weights only: the detector and D-pipe were frozen on these same 63 cases (entries 52, 53), and D-pipe's and PPR's scores are among the largest weights, so the held-out 50 is not a clean out-of-sample figure — the D-pipe baseline (48) is in-sample in the same way, so the selection itself is not biased. The refit's largest weights are the error-share shift (0.215), D-pipe's score (0.172), PPR (0.164), ghost-edge out-degree (0.115) and the rise of pooled wait (0.092): part of what it learned is to agree with D-pipe. **The ghost-edge weights are untested by the held-out evaluation:** outside the 21 ad-rooted cases no root differs from the other services on the ghost columns, so in every held-out ranking those columns are constant (and the fold holding out ad fits them to zero); their weight is learned from three ad faults only and enters the pool untested (T21). The graph-only walks do worse than D-pipe (43 and 39 against 48): on this testbed the graph helps only together with anomaly evidence. recommendationCacheFailure is missed by every method (silent within five minutes, T14). Pool HR@3 is measured after tag build-freeze, on another system (OTel-to-pool shift, T21).

Frozen in `data/frozen/gpipe_params.json` (`ranker: learned`, ten weights, `provisional: false`, `gpipe_params_hash` `3ab65983cba8…`); `tests/pipelines/g_pipe/test_pipeline_s22.py::test_frozen_gpipe_params_are_the_selection` ties the file to the report and to the frozen detector and D-pipe. `bin/trigger_check.py --corpus otel_build_v3 --with-gpipe` twice in separate processes: G-pipe digest `a67bc8a98ff173a561add7a9e31aabf6f5bff8b6c36cad167b49e19157432a20` both times (trigger digest unchanged, `3ca9a4678e9b…`).
