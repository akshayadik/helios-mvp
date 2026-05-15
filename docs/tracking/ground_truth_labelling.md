# Ground Truth Labelling

**Purpose:** Hand-curated ground-truth labels distinguishing injection-target service from telemetry-proximate root cause. Justifications per OSF binding decision §2.4. Source for HR@3 computation.

**Schema version:** v1.0 (frozen 2026-05-15)
**Update cadence:** During corpus build (Stage 0–2)
**Owner:** AA
**Labelling protocol:** OSF §2.4 inclusion/exclusion rules; featureflagservice config for OTEL Demo; AIOpsLab published catalogue for confirmatory corpus

---

## Column Definitions

| Column | Meaning |
|---|---|
| `incident_id` | Fault event identifier |
| `environment` | `OTEL Demo` or `AIOpsLab` |
| `fault_injected_service` | Service where fault flag was toggled |
| `root_cause_service` | Ground-truth root cause (used for HR@3 evaluation) |
| `fault_type` | Specific fault flag or scenario name |
| `label_source` | How the label was determined |
| `labelled_at` | UTC date label was assigned |
| `evaluation_phase` | `exploratory` or `confirmatory` |

**Note on fault_injected_service vs root_cause_service:** For OTEL Demo faults driven by `featureflagservice`, the injected service and root cause service are identical by construction — the fault is injected directly at the service level. For AIOpsLab scenarios, these may differ (e.g., a database fault propagates to a dependent service).

---

## Entries

### Stage 0 + Milestone 1 — OTEL Demo Exploratory Labels (20 incidents)

All `evaluation_phase = exploratory`. These labels are NOT used for confirmatory hypothesis testing — they support exploratory calibration only.

| incident_id | environment | fault_injected_service | root_cause_service | fault_type | label_source | labelled_at | evaluation_phase |
|---|---|---|---|---|---|---|---|
| s0-adhc-001 | OTEL Demo | adService | adService | adHighCpu | featureflagservice config (deterministic) | 2026-05-14 | exploratory |
| s0-adhc-002 | OTEL Demo | adService | adService | adHighCpu | featureflagservice config (deterministic) | 2026-05-14 | exploratory |
| s0-adhc-003 | OTEL Demo | adService | adService | adHighCpu | featureflagservice config (deterministic) | 2026-05-14 | exploratory |
| s0-cart-001 | OTEL Demo | cartService | cartService | cartFailure | featureflagservice config (deterministic) | 2026-05-14 | exploratory |
| s0-cart-002 | OTEL Demo | cartService | cartService | cartFailure | featureflagservice config (deterministic) | 2026-05-15 | exploratory |
| s0-cart-003 | OTEL Demo | cartService | cartService | cartFailure | featureflagservice config (deterministic) | 2026-05-15 | exploratory |
| s0-imgsl-001 | OTEL Demo | imageService | imageService | imageSlowLoad | featureflagservice config (deterministic) | 2026-05-14 | exploratory |
| s0-imgsl-002 | OTEL Demo | imageService | imageService | imageSlowLoad | featureflagservice config (deterministic) | 2026-05-15 | exploratory |
| s0-imgsl-003 | OTEL Demo | imageService | imageService | imageSlowLoad | featureflagservice config (deterministic) | 2026-05-15 | exploratory |
| s0-imgsl-004 | OTEL Demo | imageService | imageService | imageSlowLoad | featureflagservice config (deterministic) | 2026-05-15 | exploratory |
| s0-pcat-001 | OTEL Demo | productCatalogService | productCatalogService | productCatalogFailure | featureflagservice config (deterministic) | 2026-05-14 | exploratory |
| s0-pcat-002 | OTEL Demo | productCatalogService | productCatalogService | productCatalogFailure | featureflagservice config (deterministic) | 2026-05-15 | exploratory |
| s0-pcat-003 | OTEL Demo | productCatalogService | productCatalogService | productCatalogFailure | featureflagservice config (deterministic) | 2026-05-15 | exploratory |
| s0-pcat-004 | OTEL Demo | productCatalogService | productCatalogService | productCatalogFailure | featureflagservice config (deterministic) | 2026-05-15 | exploratory |
| s0-pcat-005 | OTEL Demo | productCatalogService | productCatalogService | productCatalogFailure | featureflagservice config (deterministic) | 2026-05-15 | exploratory |
| s0-rcf-001 | OTEL Demo | recommendationService | recommendationService | recommendationCacheFailure | featureflagservice config (deterministic) | 2026-05-14 | exploratory |
| s0-rcf-002 | OTEL Demo | recommendationService | recommendationService | recommendationCacheFailure | featureflagservice config (deterministic) | 2026-05-15 | exploratory |
| s0-rcf-003 | OTEL Demo | recommendationService | recommendationService | recommendationCacheFailure | featureflagservice config (deterministic) | 2026-05-15 | exploratory |
| s0-rcf-004 | OTEL Demo | recommendationService | recommendationService | recommendationCacheFailure | featureflagservice config (deterministic) | 2026-05-15 | exploratory |
| s0-rcf-005 | OTEL Demo | recommendationService | recommendationService | recommendationCacheFailure | featureflagservice config (deterministic) | 2026-05-15 | exploratory |

---

## Future Entries

`[PENDING: Stage 2 — AIOpsLab confirmatory corpus (174 incidents); labels from AIOpsLab published benchmark catalogue; root_cause_service may differ from fault_injected_service; two-labeller agreement check required per OSF §2.4]`

---

*Last updated: 2026-05-15 — 20 exploratory labels from Milestone 1 corpus (OTEL Demo only)*
