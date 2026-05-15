# Tracking Documents Register

**Purpose:** Index of all 18 living tracking documents with paths, purposes, owners, and update cadences. Single source of truth for which docs exist and why.

**Update cadence:** On any tracking-doc add/remove/rename
**Owner module:** Researcher (solo)
**Last updated:** 2026-05-15 (Milestone 1 exit)

---

## Design Principles

All tracking documents in `docs/tracking/` follow these rules:

1. **Frozen column schema.** Column definitions are set at the document's introduction stage. Adding a column requires a deviation log entry if it has analytic consequence.
2. **Append-only data rows.** Historical rows are never edited or deleted. Corrections are added as new rows with a `Correction_of` reference.
3. **Stage-gated population.** Rows with data from future stages are marked `[PENDING: Stage N — reason]`. Placeholder rows with invented values are forbidden.
4. **Cross-reference links.** Each document notes which other documents it depends on or feeds into.

---

## Document Index

| # | Document | Path | Purpose | First active stage | Update trigger | Last updated | Status |
|---|----------|------|---------|-------------------|----------------|--------------|--------|
| 1 | Ablation Architecture | `ablation_architecture.md` | Architectural decision record — design choices with justification and ablation variant mapping | Stage 0 | On any pipeline/component architectural change | 2026-05-15 | ✅ Current |
| 2 | Calibration Thresholds | `calibration_thresholds.md` | Per-metric thresholds used in MetricIntegrityGate; frozen before confirmatory runs | Stage 1 | After D-pipe/G-pipe/L-pipe threshold tuning | 2026-05-15 | 🟡 Schema only — values pending Stage 2+ |
| 3 | Dashboard | `dashboard.md` | Live experiment dashboard — Gantt, architecture flow, cell-completion grid, C1 invariants | Stage 0 | Weekly (manual until weekly_dashboard.yml CI lands) | 2026-05-15 | ✅ Current |
| 4 | Data Collection Log | `data_collection_log.md` | Per-incident capture record — window times, row counts, anomalies | Stage 0 | After every telemetry capture session | 2026-05-15 | ✅ Current (20 captures) |
| 5 | Deviation Log | `deviation_log.md` | Human-readable mirror of `deviation_log.jsonl` — 5 most recent HMAC-signed deviation entries | Stage 0 | After every `bin/log_deviation.py` append | 2026-05-15 | ✅ Current (5 entries) |
| 6 | Disjointness Audit Log | `disjointness_audit_log.md` | Record of every DisjointnessAuditor run — static and dynamic results per commit | Stage 1 | After each CI disjointness workflow run | 2026-05-15 | ✅ Current (1 entry) |
| 7 | Ground Truth Labelling | `ground_truth_labelling.md` | Deterministic fault→root-cause labels for all 20 OTEL Demo incidents | Stage 0 | On corpus expansion or label correction | 2026-05-15 | ✅ Current (20 entries) |
| 8 | Helios MVP Tracking | `helios_mvp_tracking.md` | Daily task tracker — all engineering, research, evaluation, and gate rows with SHAs and evidence | Stage 0 | After every completed task (DONE transition) | 2026-05-15 | ✅ Current (S0 + M1 rows) |
| 9 | Hypothesis–Variant–Metric Mapping | `hypothesis_variant_metric_mapping.md` | Maps A-H1..8 hypotheses to variants, primary/secondary metrics, statistical tests, and α | Stage 0 | On hypothesis revision (requires deviation log entry) | 2026-05-15 | ✅ Current (8 hypotheses) |
| 10 | Price Book | `price_book.md` | Per-token and per-compute-second cost coefficients for CpR metric computation | Stage 2 | Stage 5 freeze (post-freeze changes are external-validity threats) | — | 🟡 Schema only — Stage 2+ |
| 11 | Prompt Version Registry | `prompt_version_registry.md` | Frozen L-pipe prompt templates with prompt_sha — binds H_struct measurement to prompt revisions | Stage 3 | Before each L-pipe prompt update | — | 🟡 Schema only — Stage 3+ |
| 12 | Replication Verification Log | `replication_verification_log.md` | Results of the 10% byte-equality replication matrix (bin/replicate.sh) for OSF deposit | Stage 7 | After replication verification runs | — | 🟡 Schema only — Stage 7+ |
| 13 | Reproducibility Manifest | `reproducibility_manifest.md` | Environment pin list, schema freeze record, software versions, and Stage 5 pre-registration checklist | Stage 0 | On environment change or schema freeze | 2026-05-15 | ✅ Current |
| 14 | Seed Register | `seed_register.md` | Integer seed registry — maps Seed_ID to value, stage, variant, benchmark, and algorithm context | Stage 0 | Before any new experiment seed is used | 2026-05-15 | ✅ Stage 0 seed registered; confirmatory block pending Stage 5 |
| 15 | Snapshot Hash Registry | `snapshot_hash_registry.md` | Append-only JSONL-mirror — maps incident_id to snapshot_hash and variant_config_hash | Stage 0 | After every telemetry capture (automated via SnapshotRegistry) | 2026-05-15 | ✅ Current (20 entries) |
| 16 | Tracking Documents Register | `tracking_documents_register.md` | This document — master index of all tracking docs | Stage 0 | On any tracking-doc add/remove/rename | 2026-05-15 | ✅ Current |
| 17 | Validity Tracking | `validity_tracking.md` | Threat-to-validity register — internal, construct, and external threats with mitigations | Stage 0 | After each new validity threat identified | 2026-05-15 | ✅ Current (8 threats) |
| 18 | VCL Manifest Tracking | `vcl_manifest_tracking.md` | Master register of VCL variant configurations and their variant_config_hash values | Stage 0 | After every VCL config change or new variant | 2026-05-14 | ✅ Current (8 confirmatory variants) |

---

## Ownership and Responsibility

All 18 documents are maintained by the researcher (Akshay Adik, solo). There is no delegation.

Document updates must be committed in the **same PR** as the code change they track. A PR that adds a new capture must also update `data_collection_log.md` and `snapshot_hash_registry.md`. A PR that adds a variant must also update `vcl_manifest_tracking.md`.

---

## Excluded from this Register

- `HELIOS_MVP_Execution_plan_v0.6.md` — project planning document, not a research tracking artefact; not covered by the schema rules
- `.claude/docs/pdf/research_proposal_akshayadik.pdf` — source research proposal; read-only reference
- `.claude/docs/pdf/project_plan.md` — execution plan reference; read-only

---

## Cross-Reference Map

```
deviation_log.jsonl (source of truth)
    └─ deviation_log.md (human-readable mirror; top 5 entries)

helios/vcl/variants.py (source of truth)
    └─ vcl_manifest_tracking.md (hash registry)

data/snapshot_registry.jsonl (source of truth)
    └─ snapshot_hash_registry.md (human-readable mirror)

data/captures/<incident>/ (source of truth)
    └─ data_collection_log.md (per-capture statistics)

ground_truth_labelling.md + vcl_manifest_tracking.md + seed_register.md
    └─ reproducibility_manifest.md (environment + corpus summary)

hypothesis_variant_metric_mapping.md
    └─ calibration_thresholds.md (threshold per metric per hypothesis)
    └─ validity_tracking.md (threat per metric/test choice)

disjointness_audit_log.md
    └─ helios_mvp_tracking.md (GATE rows reference audit entries)
```
