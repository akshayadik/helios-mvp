# Confirmatory guard fix · design

**Found by:** the phase A rehearsal on build data, 2026-11-26 · **Code:** `helios/analysis/run.py` `confirmatory_guard` (S4.11 design T-i) · **Status:** go-ahead from the owner, 2026-11-26 · **Data:** build data only (`data/campaigns/s5_cr`); the pool stays locked · **Freeze:** `build-freeze-4`, before E1

## 1. What is wrong

The guard decides whether an analysis run may be labelled confirmatory. It refuses the label if **any** run in the store carries a variant hash outside the **8 confirmatory** variants.

The pool campaign writes one store, `results.duckdb`, for three phases:
- E1: the 8 confirmatory variants;
- E2: 5 baselines, each also at trigger time, so 8 baseline systems with their own executor config hashes;
- E3: the runnable exploratory variants.

So the real store would always fail with "a run's variant hash is not a confirmatory variant". Every Family A and B result would be labelled exploratory, and no Holm decision would read "rejected". The S5.3 pilot did not show this, because build data is labelled exploratory anyway: its corpus is not the pool.

Splitting the store does not help. Family B pairs each baseline with HELIOS-Full, so baseline runs must sit in the same store as Full.

## 2. Cause

The code is stricter than its design. S4.11 T-i says "every variant hash matches the frozen `variant_hashes.json`", which holds all 15 variants. The design is silent on baselines, which carry an executor config hash rather than a variant hash. The guard tests used only HELIOS-Full and HELIOS-D.

## 3. Fix

- A **HELIOS run**, meaning any run whose `state` is not `BASELINE`, must carry one of the **15 frozen variant hashes**: the 8 confirmatory and the 7 exploratory variants. Family E stays exploratory regardless (BCa only, never Holm), and the Family A and B tests read only their registered comparisons.
- A **baseline run** (`state = BASELINE`, S4.8) is not checked against the variant list. Its code and container images are pinned by the freeze record, which the guard already checks through `frozen()`.
- Unchanged:
  - the pool-corpus check, which applies to every row, baselines included;
  - the build-freeze check;
  - the scoring-version and metrics-version checks.
- The reason text becomes "a HELIOS run's variant hash is not a frozen variant".
- The pool-lock messages and `BUILD_FREEZE_TAG` move to `build-freeze-4`. Tests check that `build-freeze`, `build-freeze-2` and `build-freeze-3` stay locked.

## 4. Evidence

**Tests (new):**
- a store with confirmatory, exploratory and baseline runs is accepted;
- an unknown HELIOS hash is still refused, whatever its state;
- baseline rows still need the pool corpus, current versions and the frozen build.

**Rehearsal on build data.** The rows of the `s5_cr` stores are relabelled as pool in memory only, and only the tag check is stubbed.

| Store | Today's guard | Fixed guard | p-values | Decisions |
|---|---|---|---|---|
| `rcaeval_build_1` (165 cases, 21 systems) | exploratory | confirmatory | identical | identical (48 rows) |
| `otel_build_v3` (63 cases, 23 systems) | exploratory | confirmatory | identical | identical (48 rows) |

The only output difference is the key `below_threshold_descriptive` becoming `rejected`, which T-i defines.

## 5. What this is not

- It changes no hypothesis, comparison, metric, test, α, Holm rank, variant hash or frozen parameter.
- It makes the label reachable as the design intended. It does not relax what counts as confirmatory data: the pool corpus, the frozen build and the current versions are still required.

## 6. Other rehearsal findings (no change to the frozen build)

Phase A builds these as scripts outside the frozen folders (`bin/`, `helios/`):
- the Markdown tables per family that T-j promises (only JSON is written today);
- E-H5 from the delayed-label subset (`e_h5_forms` exists but nothing calls it);
- A5 innovation evidence;
- A6 figures and the replication bundle.

E-H4 and E-H6 each need a separate campaign (`--fgsv-perturb`, `--iol-inject`). Phase E does not schedule them, and Stage B (B5) covers their full forms; whether to run reduced forms on the pool is an open owner question.
