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

---

## Imported corpora — RCAEval (S1.1, 2026-10-24/25)

Recorded by the RCAEval authors, not captured here; imported with `bin/import_rcaeval.py` from the Hugging Face copy at pinned revision `afeacb11bcc94dadfd1c8f483ee4377b2b8b614e` (every file checked against its published hash). **No per-case rows in this log:** the per-case columns above (fault service, fault type) are labels, and for the confirmatory pool they must not sit beside opaque incident IDs outside the signed ground-truth file. Per-case details: `data/rcaeval/ground_truth_<corpus>.json` (signed); label-free case order and seal hashes: `data/rcaeval/<corpus>_manifest.json`.

| Corpus | Datasets | Cases | Phase | Streams | Manifest digest | Notes |
|---|---|---|---|---|---|---|
| Build | RE1-OB/SS/TT, RE2-SS, RE3-SS | 495 | exploratory | P1 all; P3 in 120; no traces | `158e108859e50fbdf1cb708ce0c27237f47e4330145b79b9d49921f923e2f7e9` | 375 logs_missing are RE1 (metrics only); one injection-signature hit is a false positive (`javax.inject`); one Sock Shop case holds sparse Online Boutique series |
| Pool (confirmatory) | RE2-OB, RE2-TT, RE3-OB, RE3-TT | 240 | confirmatory | P1, P2 all; P3 in 239 | `8f68dfd9b50de365549b9889b181e43a8f89b7155c7a81ac16c908f56c7286b1` | Trace times in microseconds; 1 logs_missing (known RE2-TT case); 0 injection-tool strings; Online Boutique cases hold 4 sparse Sock Shop metric columns, kept as distinct services. **Locked for runs until tag `build-freeze`** |

Sealed windows live in `data/rcaeval/{build,pool}/` (git-ignored, 0.5 GB and 5.7 GB). The seals bind these exact bytes: **back up `data/rcaeval/pool/`** — re-converting with different library versions may produce different bytes and therefore different seals.
