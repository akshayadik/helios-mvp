# S4.8 Baselines from the RCAEval suite: design (draft)

**Row:** S2-M9-ENG08 · **Effort:** 2 days · **Depends on:** S4.10 (campaign, `Executor` protocol), S4.9 (`baseline_publications`, CpR) · **Status:** draft 2026-11-13, for owner approval (B-a to B-k)

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
