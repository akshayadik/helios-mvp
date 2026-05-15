# Validity Tracking

**Purpose:** Internal, construct, and external validity threats and mitigations (proposal §3.9.1–3.9.3). Includes ground-truth labelling protocol boundaries and examiner-facing threat analysis.

**Schema version:** v1.0 (frozen 2026-05-15)
**Update cadence:** At each major stage gate
**Owner:** AA
**Reference:** Proposal §3.9.1 (internal), §3.9.2 (construct), §3.9.3 (external)

---

## Column Definitions

| Column | Meaning |
|---|---|
| `Category` | `internal` / `construct` / `external` |
| `Threat_ID` | Sequential threat identifier |
| `Description` | What the threat is |
| `Mitigation` | How HELIOS addresses it |
| `Artefact_evidence` | Code / doc that implements the mitigation |
| `Status` | `Mitigated` / `Partial` / `Pending` |

---

## Entries

### Internal Validity

| Category | Threat_ID | Description | Mitigation | Artefact_evidence | Status |
|---|---|---|---|---|---|
| Internal | T1 | History effect — external events during data collection alter results | Fixed 5-minute capture windows; OTEL Demo is an isolated Docker Compose environment with no external network access | `TelemetryWindow.window_start_iso / window_end_iso`; `helios/telemetry/otel_demo_capture.py` | Mitigated for exploratory phase |
| Internal | T2 | Instrumentation — measurement tool changes observed system behaviour | Passive telemetry only (Prometheus scrape, Jaeger sampling, OpenSearch collect); no active probes or synthetic traffic injected | `helios/telemetry/otel_demo_capture.py` — read-only backend queries | Mitigated |
| Internal | T8 | Ablation confounding — disabling one flag inadvertently affects multiple code paths | DisjointnessAuditor (static `__gated_by__` scan + dynamic coverage.py diff) enforces that each VCL flag gates exactly one pipeline function | `helios/vcl/disjointness.py` — CI PASSED at Milestone 1; `disjointness_audit_log.md` | Mitigated |

### Construct Validity

| Category | Threat_ID | Description | Mitigation | Artefact_evidence | Status |
|---|---|---|---|---|---|
| Construct | T3 | Construct under-representation — HR@3 alone misses latency and cost dimensions | Secondary metrics CpR, latency_ms, and token_count captured per verdict in every pipeline run | `helios/schemas/verdict.py` — all secondary metrics required fields | Partial — no confirmatory data yet |
| Construct | T4 | Mono-operation bias — single RCA task definition may not generalise | Three peer pipelines over three distinct modalities; 8 ablation variants isolate each component's contribution | VCL + 8 confirmatory variants in `helios/vcl/variants.py` | Mitigated by design |
| Construct | T5 | Hypothesis guessing — user study subjects infer research intent | Double-blind protocol in E-H7 user study; counterbalanced variant presentation order | `[PENDING: Stage 5 — IRB approval required for n=24 SRE user study]` | Pending IRB |

### External Validity

| Category | Threat_ID | Description | Mitigation | Artefact_evidence | Status |
|---|---|---|---|---|---|
| External | T6 | Population validity — OTEL Demo is not representative of production microservices | AIOpsLab confirmatory corpus uses 5 production-representative benchmarks (174 incidents); OTEL Demo data is permanently excluded from confirmatory analysis | Two-environment firewall enforced by `EvaluationPhase` enum in `TelemetryWindow`; `MetricIntegrityGate` blocks exploratory rows from `result_row` | Partially mitigated — AIOpsLab corpus pending Stage 2 |
| External | T7 | Ecological validity — lab fault scenarios differ from production incidents | AIOpsLab uses published fault scenarios derived from real-world post-mortems; incident selection is pre-registered in OSF protocol §2 | `docs/osf_protocol_v0.md §2.4` — inclusion/exclusion criteria; corpus locked at Stage 5 | Partially mitigated — confirmatory corpus pending |

---

## Future Entries

`[PENDING: Stage 5 — additional construct validity threats for L-pipe prompt design sensitivity, CoE narrative quality inter-rater reliability; external validity threats for multi-cloud generalisation beyond AIOpsLab benchmarks]`

---

*Last updated: 2026-05-15 — 8 threats catalogued; T3/T5/T6/T7 partial pending Stage 2+ data*
