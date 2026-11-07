# S3.3 — Two-stage reward and delayed labels (design)

Tracking row S2-M8-ENG03 · Tier 2 · depends on S3.1 · 2026-11-07 · Hypothesis E-H5 (exploratory)

**Owner decisions, 2026-11-07:**
- W-a: build now.
- W-c: r¹ is MAHC's calibrated confidence.
- W-f: start from a two-way cross-fit.

The remaining decisions are carried in the pre-run entry for approval.

## 1. What Chapter 3 asks for

- **Algorithm 1, ORAR (p.44):** after actuation the router emits a provisional reward r¹ at T + Δ₁ ≈ 1–5 min. It is built from three things: the HITL-acceptance indicator, verdict self-consistency and realised CpR. When the post-mortem label arrives (hours to days later), a terminal correction Δr is computed from its correctness and applied as an idempotent compensating update. RRE is logged per incident.
- **Delayed labels (p.12):** recorded corpora have no natural delay, so delays are injected on a pre-registered 25% subset, drawn log-normal with μ_log = 8.7 s and σ_log = 1.4 (median about 1.7 h, 95th percentile about 19 h). LinUCB is thawed on that subset only.
- **RRE (metric contract):** per case on the delayed-label subset, 1 if the provisional and terminal rewards have different signs, else 0. E-H5 compares HELIOS-noReconcile with Full on it; it is exploratory, reported with BCa intervals and outside the Holm family.
- **Static policy (p.44, design §1):** the confirmatory router is frozen. Nothing in S3.3 may change `data/frozen/router_params.json` or the run path.

## 2. Shape

S3.3 is an **offline replay**, not a change to the runner:
- It reuses the S3.1 full-information build data: per case, the router features, every pipeline's list and latency, and therefore every arm's fused outcome.
- It plays the cases as an incident stream through a *thawed copy* of the router, using the same `decide_g` and `decide_escalation` policy.
- Rewards arrive on the injected clock. Each provisional and terminal reward is written to a signed reward ledger.
- It reports RRE and the learning behaviour.

No pipeline runs, no frozen file is written, and the confirmatory path is untouched.

New code:

| File | Role |
|---|---|
| `helios/evaluation/reward_replay.py` | event clock, thawed LinUCB state, reward functions, RRE |
| `helios/orchestrator/reward_ledger.py` | `RewardLedger`, HMAC-chained with an Ed25519-signed anchor, like the CoE |
| `bin/reward_replay.py` | the tool; writes `docs/sprints/s3-routing/calibration/reward_run<N>.json` (aggregates only) |

## 3. Decisions

**W-a. Build now, as exploratory machinery.**
- It touches no frozen artefact and no confirmatory path.
- S3 is about eight weeks ahead of its January slot, so building it now does not crowd Tier 1.
- *Alternative:* move it to Stage B. That costs nothing in the evidence, but E-H5 would then wait for July.

**W-b. Data: build cases now, and a pre-registered pool subset later.**
- **Now:** the 558 build cases (63 OTel, 495 RCAEval).
- **Phase E, after the confirmatory runs are scored:** the same replay on a seeded 25% subset of each pool corpus. Its selection rule goes into the OSF addendum before `build-freeze`.
- **Corpora:** Ch3 names AIOpsLab and Train-Ticket. Our corpora are RCAEval RE2 and OTel (D11), so this goes in the entry.
- **No leakage into confirmatory results:** the pool replay reads ground truth only after scoring and never feeds a confirmatory number.

**W-c. Rewards.**

| Reward | Definition |
|---|---|
| Terminal r² | the HR@3 hit (0 or 1) of the published arm's fused list; the same reward the frozen router was fitted on |
| Provisional r¹ | MAHC's frozen calibrated confidence for that same fused list (verdict self-consistency, no ground truth) |

- **Why the other two Ch3 ingredients are left out:**
  - *HITL acceptance* does not exist on recorded data; it arrives with S4.2 and live use.
  - *Realised CpR* is already handled by the router's fixed cost order (S3.1 §5.4: only accuracy is learned).
  - Both are recorded as Stage B extensions, and the entry says so.
- **Single-pipeline arm:** a stop on D alone gets no provisional reward. MAHC confidence was never calibrated on one pipeline (R-e). Its terminal reward applies whole, and it is left out of RRE (counted and reported).
- **Signs are centred on the frozen τ_acc** (0.812574): RRE = 1 when the confidence is ≥ τ_acc but the arm missed, or < τ_acc but it hit.

**W-d. Clock.** Each replay stream has:

| Element | Distribution |
|---|---|
| case order | a random permutation |
| arrivals | Poisson, mean inter-arrival 60 min |
| r¹ delay | uniform on 1–5 min |
| r² delay | log-normal (μ_log 8.7, σ_log 1.4) seconds, as Ch3 |

- **Sensitivity:** mean inter-arrival of 15 min and 4 h.
- **Streams:** 8. Each is seeded with `training_seed("orar_prewarm_order", r)` for r = 0–7.
  - The seed register layout is frozen in deposit 1 (`seeds.json`), so no new block can be added without breaking the freeze.
  - The ORAR stream order is what this slot was registered for.
  - Full and noReconcile share each stream's draws, so they are paired.

**W-e. Update rule.** Ridge LinUCB per arm, as the S3.1 fit (λ = 1). An arm is updated when its fused verdict was published: the stage-1 arm and, if escalated, the terminal arm, each on its own features.

| When | Update |
|---|---|
| on r¹ | A ← A + xxᵀ, b ← b + r¹x |
| on r² (Full) | b ← b + (r² − r¹)x, the compensating update; or A ← A + xxᵀ, b ← b + r²x when there was no r¹ |

- **Idempotent:** the ledger refuses a second record for the same (stream, case, arm, stage), and the state is updated only through a ledger append.
- **Invariant (tested):** once every terminal reward has arrived, Full's state equals the batch ridge fit on terminal rewards.
- **noReconcile (`reconcile_terminal` OFF):** no terminal update and no terminal record. The learner keeps provisional rewards only, and the D-only terminal-only cases are never learned. RRE is still measured for both variants by the evaluator from ground truth, outside the ledger.

**W-f. Starting state: two-way cross-fit.**
- The build cases are split into two halves by MAHC's (corpus, group) folds. Within each corpus, groups are taken largest first, ties broken by name, and each goes to the smaller half, so the halves are as even as whole groups allow.
- The router is pre-warmed by a batch fit on one half and streamed over the other; then the halves swap.
- So no streamed case was seen by its starting state. Starting from the frozen refit instead would make every streamed case in-sample.
- τ_acc stays at the frozen value: the replay learns the arm models, not the threshold.

**W-g. Ledger naming.** Ch3 calls the provisional–terminal record the reconciliation ledger. The repo's `reconciliation_ledger` already records run outcomes (passed / excluded / skipped) and stays as it is. The reward records go to a separate `RewardLedger` (`LOG_KIND = "reward"`).
- **One file per replay,** with an Ed25519-signed anchor.
- **Verified by** `bin/verify_ledgers.py --reward`. Every terminal record has at most one earlier provisional record for the same (stream, case, arm), no record is duplicated, and a noReconcile ledger has no terminal records.

**W-h. Report (exploratory, per corpus, mean across streams with the range):**
- RRE rate, and the share of cases without r¹;
- the learning curve: rolling HR@3 of the routed decisions, and the escalation (LLM) share by stream position;
- Full minus noReconcile on both;
- the BCa interval for E-H5 is left to the analysis notebook, using the frozen `bca_seed("E-H5")`.

## 4. Pre-run entry

As in S3.1 (entry 69), one deviation entry is signed before any replay. It covers:
- W-b to W-g (corpora, reward definitions, centring, clock, seeds, update rule, starting state);
- that the frozen router and confirmatory path are unchanged.

The pool-subset rule and the RRE reporting go into the OSF addendum draft.

## 5. Done when

- **Pairs verify:** `verify_ledgers.py --reward` passes on a replay ledger and fails on each tampering case (duplicate, terminal before provisional, terminal record in a noReconcile ledger).
- **Off writes none:** a `reconcile_terminal=OFF` replay writes no terminal records.
- **Invariant:** the batch-equals-online test passes.
- **Tool and report:** the replay tool reproduces its report byte for byte from the same seeds.
- **Frozen artefacts:** the frozen router file and its hash are unchanged.
