# S1.2 — OTel Demo build captures · design note

**Task:** S1.2 (tracking S2-M6-RES01) · **Date:** 2026-10-26 · **Code:** `helios/adapters/otel_campaign.py` (`HELIOS_ENABLE_OTEL_CAMPAIGN`), `bin/capture_campaign.py`, `SlicedFetcher` / `build_campaign_capture` in `helios/telemetry/otel_demo_capture.py` · **Deviation:** entry 44 (OTel build corpus and protocol) · **Data:** `data/otel/build/` (captures), `data/otel/ground_truth_build.json` (signed labels), `data/otel/build_manifest.json` (label-free corpus manifest)

## Why

The RCAEval build corpus has no traces (S1.5), so trace-derived graph edges, the K-hop pruner's K on topology (S1.7), the label-free detector (S2.1) and the graph ranker (S2.2) need trace-bearing build data. Goal: about 60 new OTel Demo incidents (63 planned), about 80 with the 20 exploratory captures.

## Where the data lives

`data/captures/` (the 20 May captures) is part of OSF deposit 1: `verify_osf_freeze.py` rebuilds the exploratory corpus manifest from every directory there, so new captures in it would break the freeze check. The new corpus therefore has its own tree, `data/otel/`, as `data/rcaeval/build` does. It is build data (D11): never confirmatory, and labels allowed for calibration and training.

## Protocol per case (about 13 minutes)

| Step | Duration | What happens |
|---|---|---|
| Recovery | 60 s | the previous fault's flag is off (and `email` restarted after a memory leak) |
| Normal period | 300 s | no fault |
| Onset | — | the flag is set in `src/flagd/demo.flagd.json`, written in place, which flagd watches through the bind mount. The run waits until flagd's OFREP endpoint serves the new variant; that moment is the injection time |
| Fault period | 300 s | fault active |
| Off | — | flag off, confirmed through OFREP |
| Ingest lag | 60 s | exporters and Prometheus scrapes catch up |
| Capture | ~1 min | window = injection − 300 s … injection + 300 s; metrics at 15 s steps; traces and logs fetched in 60 s slices (`SlicedFetcher`) |
| Seal and label | — | snapshot hash, content seal (ledger key), signed ground-truth entry |

**What changes from the May protocol:**
- The window now holds the onset (5 minutes normal, then 5 minutes faulty), as RCAEval windows do. The May captures were 5 minutes, all faulty.
- Traces and logs are fetched in slices. Jaeger returns at most 1,000 traces per service per query and OpenSearch 10,000 hits, so one 10-minute query would drop part of the window.
- **Spans carry their own service** (found in the S1.3 spike, deviation entry 45). `JaegerTracesFetcher` labelled every span of a returned trace with the service it had queried. Every OTel capture, the May ones included, therefore holds each span several times, mostly under the wrong service. The fetcher now uses the trace's processes table and keeps each span once. The May captures stay as deposited.
- **Resource metrics are captured** (found in the first pilot). The May metric list asks for `up`, `process_cpu_seconds_total` and `process_resident_memory_bytes`, none of which OTel Demo 2.2.0 exports. So the May captures, all 20 of them, hold only the HTTP and RPC latency histograms, and resource faults (high CPU, GC, memory leak) leave no metric trace in them. The campaign adds the collector's per-container `container_cpu_utilization_ratio` and `container_memory_usage_total_bytes`, limited to the demo's 28 containers. Other projects' containers on the same Docker host are dropped. A `service_name` label is added at query time (`label_replace`; raw labels kept). The first pilot's capture was discarded and recorded again.

## Faults and labels

| Flag | Variants (rotated by repetition) | Root-cause service | Fault type |
|---|---|---|---|
| adHighCpu | on | ad | resource |
| adManualGc | on | ad | resource |
| adFailure | on | ad | code |
| cartFailure | on | cart | code |
| paymentFailure | 90%, 75%, 50% | payment | code |
| paymentUnreachable | on | checkout (it dials a bad payment address) | dependency |
| productCatalogFailure | on | product-catalog | code |
| recommendationCacheFailure | on | recommendation | dependency |
| emailMemoryLeak | 10x | email (restarted after each case) | resource |

The label is the service whose code reads the flag. Names are the Jaeger service names, which are the UEG-C node names, so scoring matches exactly. Excluded flags:

| Flag | Why excluded |
|---|---|
| kafkaQueueProblems | the fault is split between checkout and fraud-detection |
| imageSlowLoad | implemented in browser-side frontend code |
| llmRateLimitError, llmInaccurateResponse | simulated in the caller |
| loadGeneratorFloodHomepage | load, not a fault |
| failedReadinessProbe | Kubernetes only |

**Schedule.** 7 repetitions × 9 faults = 63 cases, run rep-major (every fault once, then again), so a campaign stopped early stays balanced. The root-cause services are unbalanced (ad has 3 of the 9 faults); this is reported, not corrected.

## Leakage and identity

- **Opaque IDs.** Incident IDs are 32 hex digits, derived from the registered OTel opaque-ID seed slot (`otel_exploratory`) and a case name prefixed `otel_build/`. No new seed slot was added, because the seed register is in OSF deposit 1.
- **What stays out of the window.** The fault, variant, injection time and window bounds are in the signed ground truth only.
- **No fault order in the manifest.** The corpus manifest lists IDs sorted, since the capture order would reveal the fault rotation.
- **Location.** The campaign module sits in `helios/adapters/`, outside the run path, so the S1.9 leakage scan (`test_no_ground_truth_leak.py`) still holds.

## Running it

```bash
docker compose -f external/otel-demo-pinned/docker-compose.yml --project-directory external/otel-demo-pinned up -d
set -a; source .env; set +a
poetry run python bin/capture_campaign.py preflight
nohup poetry run python bin/capture_campaign.py run > data/otel/campaign.log 2>&1 &
poetry run python bin/capture_campaign.py status      # any time
poetry run python bin/capture_campaign.py verify      # after the run
poetry run python bin/capture_campaign.py finalize    # writes the label-free corpus manifest
```

`run` resumes: labelled cases are skipped, and an interrupted capture is recorded again. The OTel Demo checkout is the pinned commit `b74a7bc` (tag 2.2.0, `external/otel-demo-commit.txt`), with `DEMO_VERSION=${IMAGE_VERSION}` as in Stage 0. `bin/pin-otel-demo.sh` uses GNU `sed -i` and fails on macOS, so on the Mac it was cloned and pinned by hand (same two steps).

## Done-when

About 80 OTel incidents sealed (20 exploratory + the build cases), all verifying: `bin/verify_captures.py` for the 20, `bin/capture_campaign.py verify` for the build corpus. Results go in the *Results* section once the campaign has run.

## Results

**Run.** 2026-10-26 22:55 IST to 2026-10-27 11:36 IST (first window start 17:26 UTC, last window end 06:05 UTC), one uninterrupted run under `caffeinate`, with no other workload on the Docker host. All 63 cases were captured and labelled with no retries or redone cases. The run log is `data/otel/campaign.log` (counts and positions only). The only non-progress lines are the 7 planned `email` restarts, one after each `emailMemoryLeak` case. All flags were off at the end.

**Pilots (all discarded, logs kept).** Three pilots ran before the campaign. Each found a defect, and its captures were deleted before the full run.

| Log | Defect found | Fix |
|---|---|---|
| `pilot1_metrics_gap.log` | the May metric names do not exist in demo 2.2.0, so there were no resource metrics | per-container CPU and memory queries (commit e60c5fb) |
| `pilot2_builder_not_wired.log` | the new queries were not passed to the campaign builder | wired, with a test on the fetcher's queries |
| `pilot3_span_labels.log` | spans labelled with the queried service (found in S1.3) | fetcher fix, deviation entry 45 (commit 805c1eb) |

**Integrity.**
- `bin/capture_campaign.py verify`: the ground-truth signature is OK, 63 labelled cases, and all 63 are intact (window hash and content seal).
- `finalize` wrote `data/otel/build_manifest.json` with 63 sorted IDs.

**Corpus.**

| | Value |
|---|---|
| Cases | 63: 7 per fault; root causes ad 21, cart 7, checkout 7, email 7, payment 7, product-catalog 7, recommendation 7 |
| paymentFailure variants | 90% ×3, 75% ×2, 50% ×2 |
| Size | 22 MB (`p1_metrics`, `p2_traces`, `p3_logs` per case) |
| Rows per case (median) | metrics 11,480, spans 3,966, log lines 3,303 |
| Rows in total | metrics 704,104, spans 247,743, log lines 207,851 |
| Empty streams | none |

**Span check (fix confirmed on live data).** Across all 63 cases:
- No span appears twice.
- Of 230,910 parent→child span links, 73,170 (32%) cross a service boundary. Under the old fetcher every span of a trace carried one service, so no link could cross.
- About 17 services appear in each case's traces, and every case's root-cause service is among them.

**Fault visibility at the root-cause service** (medians over the 7 cases; normal period → fault period). Exploratory build data, reported to show what each fault leaves in the telemetry:

| Fault | Error-span share | Median span latency | Container CPU |
|---|---|---|---|
| adFailure | none → 0.04 | ×10.1 | ×0.84 |
| adHighCpu | none → none | ×1.49 | ×2,180 |
| adManualGc | none → none | ×20.0 | ×13.2 |
| cartFailure | none → 0.03 | ×1.12 | ×1.80 |
| emailMemoryLeak | none → none | ×1.12 | ×1.19 |
| paymentFailure | none → 0.38 | ×1.33 | ×0.96 |
| paymentUnreachable (label checkout) | none → 0.20 | ×0.87 | ×1.44 |
| productCatalogFailure | none → 0.04 | ×0.93 | ×0.89 |
| recommendationCacheFailure | none → 0.38 | ×0.66 | ×0.97 |

Eight of the nine faults show a clear signal in at least one modality at the labelled service. **`emailMemoryLeak` is near-silent within the 5-minute fault period:** email memory rises only 1–2 MiB (47 → 48 MiB in 6 of 7 cases) and latency ×1.12. The leak grows per order, and the load generator's order rate is too low for it to build up in 5 minutes. These cases are kept as hard cases and reported per fault (validity T14); a longer fault period for this flag is a Stage B option, not a protocol change here.

**Warm-up in repetition 1.** 8 of the 9 first-repetition cases hold fewer latency-histogram rows (7,544–11,016 rows against 11,480). The demo had just been started, and a histogram series exists only once its endpoint has received traffic. Container CPU and memory are complete in every case. This is recorded, not corrected; detectors trained on the corpus must not assume a fixed series set.

**Done-when.**
- 63 build cases plus the 20 exploratory captures make 83 sealed OTel incidents, against a target of about 80.
- The 20 exploratory captures verify with `bin/verify_captures.py`, and the 63 build cases with `bin/capture_campaign.py verify`.
- The trace-dependent checks that S1.7 had to void (deviation entry 45) can now run on this corpus. That rerun is S2 work, listed in the S1 exit report.
