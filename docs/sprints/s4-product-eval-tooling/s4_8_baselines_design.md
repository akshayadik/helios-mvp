# S4.8 Baselines from the RCAEval suite: design (draft)

**Row:** S2-M9-ENG08 · **Effort:** 2 days · **Depends on:** S4.10 (campaign, `Executor` protocol), S4.9 (`baseline_publications`, CpR) · **Status:** approved 2026-11-13 (B-a to B-k as recommended); deviation entry to follow

## 1. What is fixed already

- **Entry 36 (chair call):**
  - The five baselines, in Holm order: B1 multi-source BARO (`mmbaro`), B2 TraceRCA (`tracerca`), B3 BARO metrics-only (`baro`), B4 PDiagnose, B5 multi-source RCD (`mmrcd`).
  - Alternates: CIRCA, then CausalRCA. They replace a method that cannot run, logged before the build freeze.
  - CHASE stays 0.60 (0.61 in the sensitivity band).
- **D11 §4:**
  - 5 × 240 = 1,200 baseline runs, paired with HELIOS by case.
  - One registered seed per (case, baseline).
  - Ranking over all services of the system.
  - Baselines are timed the same way, on the same hardware (contract §4, TTCD).
- **Environments (S0.11, `baselines/rcaeval/`):**
  - Two images pinned at RCAEval `2fca61b`: default (Python 3.12) and rcd (Python 3.8).
  - Runs use `--network none`.
  - No baseline runs on pool data before `build-freeze`.
- **S4.9:** a baseline publishes once, at its measured runtime (`baseline_publications`). `eval_score` rows carry the baseline name as `source`.
- **S4.10:**
  - The schedule already holds the baseline slots (`BASELINE-k`).
  - `run` skips the phase until an executor exists.
  - Outcome classes O-c apply.
  - Cells follow the rule decided in O-e.
- **S4.11:** BEST-BASELINE = the baseline with the highest mean HR@3 (ties by name).

## 2. What the spike and this design's checks found

| Finding | Consequence |
|---|---|
| **Every RCAEval method takes the injection time as an input** (`baro`, `mmbaro`, `tracerca`, `mmrcd`, `circa`; the PDiagnose script too). They split normal from anomalous data at it. RCAEval's `main.py` reads `inject_time.txt` | HELIOS never receives it (contract §1, D11 §3). What the baselines get instead is the main decision (B-b) |
| Multi-source methods read RCAEval's **derived time series**: `logts.csv` (log counts per service), `tracets_err.csv` and `tracets_lat.csv` (span errors and latency per operation). These ship with the RE2/RE3 dataset; RCAEval's repo holds no code that derives them | The S1.1 adapter kept the raw streams (P1/P2/P3), not the derived files. The export has to rebuild them (B-a) |
| `mmbaro` uses traces only when the `dataset` argument names an RE2/RE3 OB/TT set (`_mm_has_traces`) | Pass the RCAEval dataset name for pool cases. On OTel build captures, pass a name that turns traces on, recorded |
| `mmbaro` thins metrics with `iloc[::15]`, which assumes 1-second sampling | OTel build captures are not sampled at 1 s, so build results are a pipeline check only, not a fidelity check (B-h) |
| Rankings are metric-level names (`service_metric`); RCAEval maps them to services with `split("_")[0]` | A common output step maps them to canonical service names (B-c) |
| PDiagnose is a 128-line `main()` hard-wired to one Online Boutique case path, and it prints its ranking | Needs a faithful adapter, with every departure recorded (B-d) |
| Build data: OTel v3 has 63 cases with metrics, logs and traces. RCAEval build has 495 cases, all with metrics, 120 with logs and none with traces | All five baselines can run end to end on build data only with OTel v3 (B-h) |
| Docker has 18 CPUs and 15.6 GiB of memory; RCAEval asks for 16 GB and 8 cores | Fixed limits per container (B-e) |

## 3. Decisions for the owner

### B-a. Input: export from the sealed window, not RCAEval's raw files

- **Recommended:** each run exports the sealed HELIOS window into RCAEval's file layout:
  - `data.csv`: wide metrics with `time` and `service_metric` columns, at native sampling;
  - `logs.csv`, `traces.csv`;
  - `logts.csv`, `tracets_err.csv` and `tracets_lat.csv`, derived with HELIOS code that follows RCAEval's published definitions;
  - `inject_time.txt` per B-b.
- The export goes to a per-run temporary directory, mounted read-only into the container.
- **Why not RCAEval's raw files:**
  - the raw directories are named by RCAEval case name, which carries the root-cause service and the fault;
  - the raw files are not sealed.
- **Why the export is better:** baselines and HELIOS then read the same sealed bytes, and the content seal is checked before the export (the same integrity gate, the same `capture_seal_invalid` exclusion).
- **Fidelity check:** the derived series are compared with the RCAEval-shipped files on build cases that carry them, and the result is reported. The check does not tune the derivation to match.

### B-b. Anomaly time given to the baselines (main decision)

| Option | What the baselines get | For | Against |
|---|---|---|---|
| (a) | The true injection time, from the sealed ground-truth file, read by the harness at run time (never by HELIOS) | RCAEval's protocol; comparable with published scores (RE2-TT AC@3 0.82, entry 36) and with the CHASE anchor. It gives the baselines information HELIOS lacks, so a HELIOS win is conservative | Contract §1 says injection time is never given to "any pipeline"; this reads that as HELIOS's pipelines, which needs a recorded clarification (the contract itself is not edited) |
| (b) | HELIOS's own detection-trigger time for the case (label-free, recorded in `eval_run`) | Equal information for every system | Departs from RCAEval's protocol; published scores are no longer comparable; a baseline then also inherits HELIOS's trigger errors |
| **(c) recommended** | (a) binding, (b) as a reported sensitivity row for B-H1 to B-H8 | Keeps the published protocol and the conservative direction, and shows how much of any gap comes from the injection time | Doubles the baseline runs (2,400 on the pool; the metric methods take seconds, RCD minutes) |

The pool lock still applies: the harness reads `inject_time` (and nothing else) from the ground truth through one narrow function, which refuses pool cases before `build-freeze`.

### B-c. Common output format

- **Mapping metric names to services:** each RCAEval metric-level rank is mapped to its service by RCAEval's own rule (`split("_")[0]`), then by the S1.1 canonical-name map. The service list keeps first occurrences in rank order.
- **Services the method never ranks** stay absent, so a case whose true root cause is absent is a miss (the contract's MRR rule).
- **Ties:** the method's own order is kept. The PDiagnose adapter breaks ties by name (B-d).
- **Rows written:**
  - one `eval_score` row (`list_kind` fused, `source` = the baseline name, no variant hash);
  - one `eval_run` row (runtime, `run_seed`, image digest, method version);
  - one transaction per run (O-c).

### B-d. PDiagnose adapter

- **Recommended:** a faithful port of `RCAEval/e2e/pdiagnose.py` to RCAEval's function interface, `pdiagnose(data, inject_time, dataset, **kw) -> {"ranks": [...]}`. It runs in the default image, mounted from `baselines/rcaeval/adapters/`.
- **Kept:** ALPHA = 5; the 3σ rules on metrics and on span durations; the error and fail log counts; the unit conversions as in the script (seconds to µs for logs and spans).
- **Departures, each recorded in the deviation entry:**
  - inputs come from the data dictionary instead of hard-coded paths;
  - the ranking is returned instead of printed;
  - ties are broken by name (the script uses dict order);
  - a service that appears in no modality is not ranked.
- **Fidelity check:** the port reproduces the script's ranking byte for byte on RCAEval's bundled sample case, run inside the container.

### B-e. Timing, resources and CpR

- **Timing:** measured inside the container around the method call, including reading the exported inputs. This is the analogue of HELIOS's graph build from Parquet. It excludes container start and the export.
- **Resources:** the containers are pinned to 8 CPUs and 12 GiB (`--cpus 8 --memory 12g`). `--network none` and the limits are recorded per run.
- **CpR components:**
  - infrastructure = runtime × 8 vCPU × the price-book vCPU-hour price;
  - tokens = zero (recorded as such);
  - storage = window bytes, as for HELIOS;
  - opportunity = TTCD (runtime if top-1 is correct, else censored at 1,800 s; S4.9).
- **Human time:** a baseline publishes a ranking with no verdict state, so nothing can confirm automatically.
  - **Recommended (a):** every baseline run carries the price-book review time (15 min). That is how a team would use the ranking, and how HELIOS's PROVISIONAL-with-HITL verdicts are already costed. A sensitivity row for B-H7 drops human time from both sides.
  - (b) Baselines carry no human time.
- Under (a), the review time (15 min, about 16 at the price-book rate) dominates a baseline's CpR. B-H7 then mostly measures how often HELIOS confirms automatically, which is the claim Ch3 makes.

### B-f. Failures

- **Outcome classes:** O-c applies unchanged.
  - Docker daemon errors and OOM kills are infrastructure errors (at most 2 retries, then excluded).
  - Image or digest mismatch, and a missing adapter, are configuration refusals that stop the campaign.
- **When the method itself fails** (it raises, or runs past a hard limit of 1,800 s):
  - **Recommended (b):** excluded with reason `baseline_error` or `baseline_timeout`, like HELIOS's `run_error`. The failure share is reported per method, and the cell rule and MCAR/IPW cover it.
    - This is symmetric with HELIOS.
    - It is conservative for B-H1 to B-H5: dropping a case where the baseline fails can only remove pairs HELIOS would likely win.
  - (a) Count the run as an empty ranking (a miss, TTCD censored). It is reported as a sensitivity row under either choice.

### B-g. Seeds and determinism

- **Seeding:** the registered `run_seed` is passed into the container. The wrapper seeds `random`, `numpy` and `torch` (when present) and passes `seed=` where the method takes it (`mmrcd`). BARO, TraceRCA and PDiagnose are deterministic and ignore it.
- **Determinism rerun:**
  - **Recommended:** add the baselines to the stride rerun subset (every 10th case per app, O-g).
    - On the pool this is 24 × 5 = 120 extra runs, mostly seconds each.
    - RCD (and CausalRCA as an alternate) is stochastic, so the rerun is the evidence that the registered seed fixes its output.
    - This changes the schedule to `schedule-v2` (a new digest); the build campaign is replanned.
  - (b) Leave the rerun to the 8 model-calling variants.

### B-h. Build runs (done-when) and a published-score check

- **All five baselines on OTel build v3 (63 cases):** the only build data with traces. This proves the pipeline end to end (export, container, mapping, scoring, cells, Family B in the analysis report). The numbers are not a fidelity measure, because the sampling differs (§2).
- **`baro` and the metric and log parts of `mmbaro` and `mmrcd` on RCAEval build cases (RE1, RE2-SS, RE3-SS):** native RCAEval sampling. AC@1 and AC@3 are compared with RCAEval's published figures for the same datasets, as a check that the export reproduces the published protocol.
  - The comparison is reported, not tuned to.
  - A large gap stops S4.8 and is investigated before the freeze.

### B-i. Executor and integration

- **`BaselineExecutor`** (`helios/orchestrator/baselines.py`) implements the S4.10 `Executor` protocol:
  - `config_hash` = SHA-256 of (image digest, method, adapter version, parameters, limits);
  - `prepare()` checks the image digest and the adapter's hash;
  - `run_incident()` exports, runs the container, maps, writes rows;
  - `discard_run()` deletes rows.
- **Campaign wiring:** `bin/helios_campaign.py` maps `BASELINE-k` to it. `run` then executes the baseline phase, and nothing else in the campaign changes.

### B-j. Licences

- RCAEval is MIT; each bundled method carries its own licence in `LICENSES/`.
- A register goes into `baselines/rcaeval/LICENCES.md`. For each method used it records the licence, the source path at `2fca61b`, the image digest, and whether it was modified (PDiagnose adapter only).

### B-k. CHASE anchor

- **No run:** CHASE is the published-score anchor.
- **In the analysis report:** the Family B section prints 0.60 (and 0.61 in the sensitivity band) beside each baseline's HR@3 and the prior-only floor. Nothing in S4.11's tests changes.

## 4. Deviation entry expected

- B-b: the injection time is given to baselines, with the clarification of contract §1, plus the sensitivity row.
- B-d: the PDiagnose departures.
- B-e: the human-time rule for baselines.
- B-f: failure handling.
- B-g: `schedule-v2`, if chosen.

No hypothesis, comparator, metric, alpha or Holm rank changes.

## 5. Tests and dry runs

- **Unit tests (no Docker):**
  - export round trip on a fixture window;
  - the derived `logts`/`tracets` against hand-computed values;
  - name mapping;
  - CpR for a baseline row worked out by hand;
  - failure classes with a stub container runner;
  - the pool-lock refusal for `inject_time`.
- **Container tests (marked, run locally):** the PDiagnose port against the script on the sample case; each method once on one OTel build case.
- **Dry runs:** B-h; the OTel v3 build campaign replanned with the baseline phase executed; `cells` and `analyse` showing Family B testable on build data.

## 7. Implementation and build runs (2026-11-13)

### What was built

- **Code:**
  - `helios/baselines/`:
    - `export.py`: the B-a export, `rcaeval-export-v1`;
    - `container.py`: the pinned images, the offline `docker run` with fixed limits, and the outcome classes;
    - `executor.py`: the S4.10 `Executor`; B-b anomaly time; B-c mapping.
  - `baselines/rcaeval/adapters/`:
    - `run_method.py`: the in-container wrapper, following `main.py`'s data preparation;
    - `pdiagnose_adapter.py`: the B-d port.
  - `baselines/rcaeval/LICENCES.md`: B-j.
- **Store and scoring:**
  - a `baseline_row` table (`baseline-v1`);
  - `score_store` and `score_run_metrics` score baseline rows: one fused list under the baseline's name, and an `eval_run` row with state `BASELINE`.
- **Schedule:** `schedule-v2` adds the `baseline_trigger` phase (B-b sensitivity, same seed) and the baselines in the rerun (B-g).
- **Analysis:** `family_b_sensitivity` reports the CHASE anchor (B-k) and three reruns of Family B:
  - trigger time (B-b);
  - no human time (B-e);
  - failures as misses (B-f).

### Departures from the approved design, found while building

1. **CPU time (B-e).**
   - Infrastructure cost uses the CPU time measured inside the container (`time.process_time()`, the same measure HELIOS records), not runtime × 8 vCPU.
   - This is closer to "timed the same way" (contract §4).
   - The limits stay `--cpus 8 --memory 12g`.
2. **Published-score check replaced by a stronger one (B-h).**
   - RCAEval's repository holds no published figures for the build datasets: its CI and README reproduce only RE2-TT and Online Boutique, both pool or pool-like.
   - Instead, BARO was run on RCAEval's **native** build files and on HELIOS's **export** of the same sealed cases, in the same pinned image (results below).
3. **Derived series are rebuilt for the pool too.** The Hugging Face copy of RCAEval, from which the pool was imported, carries no `logts.csv` or `tracets_*.csv`, so the B-a rebuild applies to every case, not only to OTel. The definitions are in `export.py`.
4. **Two departures from `main.py`, both inside the wrapper.**
   - `main.py` derives `sli` from the case folder name, which carries the root-cause service. `sli` is passed as None; none of the five methods reads it (checked at 2fca61b).
   - `main.py` hands TraceRCA the metric table. The wrapper passes the trace table and the anomaly time in µs, following TraceRCA's own commented conversion.
5. **RCAEval dataset argument.**
   - `re2-<system>` for every case, so a method never learns RE2 vs RE3 from it.
   - OTel uses `re2-ob`, which turns on mmbaro's trace use.
6. **The pinned default image has no Parquet reader.**
   - This doesn't affect runs: the export writes CSV.
   - The native side of the fidelity check was converted to CSV on the host with `pandas.read_parquet`, the call RCAEval's `read_metrics` makes.

### Export fidelity (RCAEval build, 495 cases, BARO)

| Dataset | n | AC@1 native / export | AC@3 native / export | Same top-1 | Same full list |
|---|---|---|---|---|---|
| RE1-OB | 125 | 0.728 / 0.728 | 0.912 / 0.912 | 123 (2 cases fail identically on both sides) | 119 |
| RE1-SS | 125 | 0.848 / 0.848 | 0.992 / 0.992 | 125 | 125 |
| RE1-TT | 125 | 0.560 / 0.560 | 0.808 / 0.808 | 125 | 119 |
| RE2-SS | 90 | 0.067 / 0.067 | 0.956 / 0.956 | 90 | 90 |
| RE3-SS | 30 | 0 / 0 | 0.967 / 0.967 | 30 | 30 |
| **All** | **495** | **0.552 / 0.552** | **0.917 / 0.917** | **493 of 493 that run** | 483 |

- **What it shows:** the export reproduces BARO's input exactly as far as accuracy goes. The 12 full-list differences are in the tail order only.
- **What it can't check:** the log and trace derived series, because no native derived files exist to compare against.

### PDiagnose port (B-d)

- The port reproduces RCAEval's own script exactly on a synthetic case inside the script's working domain, run in the pinned image (`tests/baselines/test_containers.py`, run locally with `HELIOS_DOCKER_TESTS=1`).
- A hand-computed fixture checks every departure (`tests/baselines/test_baselines.py`).

### OTel build v3 campaign (schedule-v2, digest `ff89b57c75f6`)

- **Runs:**
  - 504 confirmatory runs (cache-only), all passed;
  - 315 baseline runs: 265 passed, 50 excluded;
  - 315 trigger-time runs: 265 passed, 50 excluded.
- **Exclusions:**
  - TraceRCA: 50 binding and 37 trigger-time;
  - Multi-source BARO: 13, trigger time only.
- **Scores:** 1,034 runs. HR@3:
  - Multi-source BARO 0.540
  - PDiagnose 0.381
  - BARO metrics-only 0.302
  - TraceRCA 0.231 (13 runs)
  - Multi-source RCD 0.159
  - HELIOS-Full, for comparison: Family A as before
- **Family B (exploratory label):**

| | Comparison | n | p |
|---|---|---|---|
| B-H1 | Full vs Multi-source BARO, HR@3 McNemar | 63 | 2.4e-4 |
| B-H2 | Full vs TraceRCA | — | untestable (cell rule: 13 of 63) |
| B-H3 | Full vs BARO metrics-only | 63 | 9.7e-9 |
| B-H4 | Full vs PDiagnose | 63 | 7.0e-7 |
| B-H5 | Full vs Multi-source RCD | 63 | 5.0e-12 |
| B-H7 | log-CpR, best baseline (Multi-source BARO) vs Full | 63 | 0.13 |
| B-H6 | log-TTCD | 63 | 0.073 |
| B-H8 | Avg@5 | 63 | 0.0019 |

- **Sensitivity rows:**
  - **Trigger time:** B-H3 to B-H5 hold. B-H1 and B-H6 to B-H8 are untestable, because Multi-source BARO's trigger-time cell has 50 of 63 runs (below 4/5).
  - **No human time:** B-H7 p = 0.65. Human time does not decide B-H7 on this data: most HELIOS verdicts here are PROVISIONAL, so both sides carry it, and the censored opportunity cost dominates.
  - **Failures as misses:** 50 cases filled. B-H2 p = 3.6e-15; the other hypotheses are unchanged.
- **CHASE anchor:** 0.60 is printed beside the baselines' HR@3.

### Findings for the owner

1. **TraceRCA fails on 50 of 63 OTel build cases (79%).**
   - All failures are RCAEval's own `KeyError` in `tracerca.py`: an operation seen only after the anomaly time has no normal-period reference (`normal_slo[op]`).
   - Under B-f (b) these runs are exclusions, so B-H2 is untestable on this data.
   - Whether the pool behaves the same can't be checked before the freeze. RCAEval's authors built RE2/RE3 for TraceRCA, but OTel's sparse operations (feature-flag calls) are what trigger the failure.
   - Options:
     - (a) keep it faithful and accept that B-H2 may be untestable;
     - (b) a recorded robustness departure: skip operations without a normal-period reference, the same as PDiagnose port departure 6;
     - (c) replace TraceRCA with the first alternate, CIRCA, per entry 36. CIRCA is metrics-only, so trace-based coverage in Family B would be lost.
   - **Recommended: (b)**, logged as a departure. It changes no scoring rule, it is the minimal change that lets the method run on the data it was written for, and failures-as-misses (B-f) stays a sensitivity row.
2. **Multi-source BARO fails at trigger time on 13 cases** (`IndexError`) when HELIOS's trigger falls near the edge of the window, leaving one side empty. It affects only the B-b sensitivity row, and is reported there.
3. **Multi-source RCD returns two services per case.** RCD returns a partial candidate set by design, which explains its low HR@3; RCAEval's own `--report-decomposition` notes this. No change.
