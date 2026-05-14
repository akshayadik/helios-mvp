# Fault Catalogue (v0) — HELIOS Milestone 0

This document serves as the binding record of the fault-injection mechanism used for exploratory calibration (OTEL Demo). Research integrity requires that every fault-injection event is reproducible and correctly categorized according to the OSF protocol §5.4.

---

## 1. Injection Infrastructure

- **Controller:** OTEL Demo Feature Flag Service (flagd)
- **Flagd Endpoint:** `http://localhost:32768` (gRPC/HTTP)
- **Management UI:** `http://localhost:8080/feature`
- **Mechanism:** Faults are toggled via the Web UI by switching the relevant flag to **ON**. Changes are propagated via flagd to the target microservices in real-time.

---

## 2. Research Category Mapping (§5.4)

HELIOS research logic categorizes all faults into one of six classes. Below is the mapping for the OTEL Demo subset:

| Research Category | Description | Candidate OTEL Demo Flags |
|-------------------|-------------|---------------------------|
| **Resource**      | CPU, Memory, Disk, Thread exhaustion | `adHighCpu`, `emailMemoryLeak`, `adManualGc` |
| **Network**       | Latency, Packet Loss, Bandwidth | `imageSlowLoad`, `paymentUnreachable` |
| **Dependency**    | Downstream service/DB failure | `cartFailure`, `recommendationCacheFailure`, `paymentFailure` |
| **Config**        | Environment or Runtime parameter errors | `failedReadinessProbe` |
| **Code**          | Logic errors, Exceptions, LLM hallucinations | `productCatalogFailure`, `llmInaccurateResponse` |
| **External**      | Third-party API rate limits, Kafka lag | `llmRateLimitError`, `kafkaQueueProblems`, `loadGeneratorFloodHomepage` |

---

## 3. Selected Fault Scenarios (Milestone 0)

The following 5 scenarios are selected for the initial 5 Parquet recordings. They span **4 distinct research classes** and **5 different service tiers**.

| # | `incident_id` | Flag Name | Affected Service | Research Class | Verification Method (Prometheus/UI) |
|---|---------------|-----------|------------------|----------------|-------------------------------------|
| 1 | `s0-adhc-001` | `adHighCpu` | `adservice` | **Resource** | `process_cpu_usage` spike in Prometheus for `adservice` |
| 2 | `s0-cart-001` | `cartFailure` | `cartservice` | **Dependency** | `rpc.grpc.status_code` != 0 for Cart service calls |
| 3 | `s0-imgsl-001` | `imageSlowLoad` | `frontend` | **Network** | Increase in `http.server.duration` for image assets |
| 4 | `s0-pcat-001` | `productCatalogFailure` | `productcatalog` | **Code** | 500 Errors on `GetProduct` requests for specific IDs |
| 5 | `s0-rcf-001` | `recommendationCacheFailure` | `recommendationservice` | **Dependency** | Cache miss rate spike / increased latency to Redis |

---

## 4. `incident_id` Naming Convention

`TelemetryWindow.incident_id` is the sole identifier linking a Parquet recording to its fault scenario. The schema carries no `fault_class` or `active_flag` field (frozen at schema-draft-v0.1), so the `incident_id` must encode fault identity unambiguously.

**Format:** `{stage}-{flag_short}-{seq:03d}`

| Token | Meaning | Example |
|-------|---------|---------|
| `{stage}` | Execution plan stage (`s0`, `s1`, …) | `s0` |
| `{flag_short}` | Abbreviated flag name (see table below) | `adhc` |
| `{seq:03d}` | Zero-padded sequence within stage + flag | `001` |

**Flag abbreviation registry (Stage 0):**

| Flag Name | Abbreviation |
|-----------|-------------|
| `adHighCpu` | `adhc` |
| `cartFailure` | `cart` |
| `imageSlowLoad` | `imgsl` |
| `productCatalogFailure` | `pcat` |
| `recommendationCacheFailure` | `rcf` |

**Parquet file layout for each incident:**

```
data/captures/{incident_id}/p1_metrics.parquet
data/captures/{incident_id}/p2_traces.parquet
data/captures/{incident_id}/p3_logs.parquet
```

P4 and P5 streams are `None` in Stage 0 (Docker Compose environment; no K8s events or profiling).

---

## 5. Operational Protocol

1. **Pre-Check:** Ensure `docker compose` is healthy and the Feature Flag UI is reachable.
2. **Activation:** Toggle the flag to **ON** at `http://localhost:8080/feature`.
3. **Stabilization:** Wait 60 seconds for the fault to propagate and manifest in the telemetry stream.
4. **Recording:** Execute `helios/telemetry/capture.py --incident-id {incident_id}` for a 5-minute window.
5. **Deactivation:** Toggle the flag back to **OFF** and wait for the system to return to baseline before the next recording.
