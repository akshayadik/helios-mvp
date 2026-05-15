# Data Collection Log

**Purpose:** Record of all telemetry captures, fault injections, and stream row counts (proposal §3.7). Construct-validity boundary documentation — proves what was captured, when, under what fault, and with what observable data volume.

**Schema version:** v1.0 (frozen 2026-05-15)
**Update cadence:** After every recording session
**Owner:** AA
**Environment:** OTEL Demo v2.2.0 (tag b74a7bc, pinned in `external/otel-demo-pinned`)
**Fault injection mechanism:** `featureflagservice` — toggles application-level fault flags

---

## Column Definitions

| Column | Meaning |
|---|---|
| `incident_id` | Fault event identifier |
| `fault_class` | Category: Resource / Dependency / Network / Code |
| `fault_service` | Microservice where fault was injected |
| `fault_type` | Specific fault flag name in featureflagservice |
| `window_mins` | Capture window duration (minutes) |
| `evaluation_phase` | `exploratory` (OTEL Demo) or `confirmatory` (AIOpsLab) |
| `p1_rows` | Prometheus metrics Parquet row count |
| `p2_rows` | Jaeger traces Parquet row count (spans) |
| `p3_rows` | OpenSearch logs Parquet row count |
| `recorded_at` | UTC date of capture |
| `notes` | Any anomalies or recording conditions |

**Fault class taxonomy:**
- `Resource` — CPU/memory saturation (adHighCpu)
- `Dependency` — upstream service failure (cartFailure, recommendationCacheFailure)
- `Network` — latency/packet-loss injection (imageSlowLoad)
- `Code` — application-level error flag (productCatalogFailure)

---

## Entries

### Stage 0 + Milestone 1 — OTEL Demo Exploratory Captures (20 incidents)

All incidents use `evaluation_phase = exploratory` and are permanently excluded from confirmatory analysis.

| incident_id | fault_class | fault_service | fault_type | window_mins | evaluation_phase | p1_rows | p2_rows | p3_rows | recorded_at | notes |
|---|---|---|---|---|---|---|---|---|---|---|
| s0-adhc-001 | Resource | adService | adHighCpu | 5 | exploratory | 4032 | 9043 | 1745 | 2026-05-14 | First capture; Stage 0 corpus seed |
| s0-adhc-002 | Resource | adService | adHighCpu | 5 | exploratory | 3824 | 7175 | 1656 | 2026-05-14 | — |
| s0-adhc-003 | Resource | adService | adHighCpu | 5 | exploratory | 3856 | 7892 | 1699 | 2026-05-14 | — |
| s0-cart-001 | Dependency | cartService | cartFailure | 5 | exploratory | 4368 | 4369 | 1462 | 2026-05-14 | First dependency-class capture |
| s0-cart-002 | Dependency | cartService | cartFailure | 5 | exploratory | 3856 | 8103 | 1714 | 2026-05-15 | — |
| s0-cart-003 | Dependency | cartService | cartFailure | 5 | exploratory | 3856 | 8413 | 1731 | 2026-05-15 | — |
| s0-imgsl-001 | Network | imageService | imageSlowLoad | 5 | exploratory | 4368 | 6566 | 1630 | 2026-05-14 | First network-class capture |
| s0-imgsl-002 | Network | imageService | imageSlowLoad | 5 | exploratory | 3856 | 8482 | 1730 | 2026-05-15 | — |
| s0-imgsl-003 | Network | imageService | imageSlowLoad | 5 | exploratory | 3856 | 8336 | 1716 | 2026-05-15 | — |
| s0-imgsl-004 | Network | imageService | imageSlowLoad | 5 | exploratory | 3856 | 8406 | 1716 | 2026-05-15 | — |
| s0-pcat-001 | Code | productCatalogService | productCatalogFailure | 5 | exploratory | 5376 | 6957 | 1631 | 2026-05-14 | First code-class capture |
| s0-pcat-002 | Code | productCatalogService | productCatalogFailure | 5 | exploratory | 3856 | 8468 | 1723 | 2026-05-15 | — |
| s0-pcat-003 | Code | productCatalogService | productCatalogFailure | 5 | exploratory | 3872 | 8449 | 1720 | 2026-05-15 | — |
| s0-pcat-004 | Code | productCatalogService | productCatalogFailure | 5 | exploratory | 3872 | 8451 | 1725 | 2026-05-15 | — |
| s0-pcat-005 | Code | productCatalogService | productCatalogFailure | 5 | exploratory | 3872 | 8376 | 1715 | 2026-05-15 | — |
| s0-rcf-001 | Dependency | recommendationService | recommendationCacheFailure | 5 | exploratory | 5712 | 5741 | 1540 | 2026-05-14 | — |
| s0-rcf-002 | Dependency | recommendationService | recommendationCacheFailure | 5 | exploratory | 3872 | 8393 | 1706 | 2026-05-15 | — |
| s0-rcf-003 | Dependency | recommendationService | recommendationCacheFailure | 5 | exploratory | 3872 | 8397 | 1710 | 2026-05-15 | — |
| s0-rcf-004 | Dependency | recommendationService | recommendationCacheFailure | 5 | exploratory | 3872 | 8362 | 1711 | 2026-05-15 | — |
| s0-rcf-005 | Dependency | recommendationService | recommendationCacheFailure | 5 | exploratory | 3872 | 8359 | 1711 | 2026-05-15 | — |

**Recording notes:**
- Backend port drift occurred between Stage 0 and Milestone 1 capture sessions. After Docker container restart: Jaeger reassigned to port 32770, OpenSearch to port 32781. Fixed in `helios/telemetry/otel_demo_capture.py` at commit `f11c529`.
- Row counts from `bin/verify_captures.py` output at Milestone 1 exit. All 20 hashes verified OK.

---

## Future Entries

`[PENDING: Stage 2 — AIOpsLab confirmatory corpus; evaluation_phase=confirmatory; 174 incidents across 5 benchmarks (AIOpsLab, Train-Ticket, DeathStar, PetShop, OpsEval); fault injection via AIOpsLab fault-injection framework rather than featureflagservice]`

---

*Last updated: 2026-05-15 — 20 entries from Milestone 1 corpus*
