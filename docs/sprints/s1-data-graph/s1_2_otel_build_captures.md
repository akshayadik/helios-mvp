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

*(filled in after the campaign)*
