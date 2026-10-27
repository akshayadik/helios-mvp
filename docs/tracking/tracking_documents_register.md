# Tracking Documents Register

**Purpose:** Index of the living tracking documents with paths, purposes, owners, and update cadences. Single source of truth for which docs exist and why.

**Update cadence:** On any tracking-doc add/remove/rename
**Owner module:** Researcher (solo)
**Last updated:** 2026-10-27 (S1 exit documentation sync: rows re-checked against the repository; OTel build corpus, validity threats, lead-time L9)

---

## Design Principles

All tracking documents in `docs/tracking/` follow these rules:

1. **Frozen column schema.** Column definitions are set at the document's introduction stage. Adding a column requires a deviation log entry if it has analytic consequence.
2. **Append-only data rows.** Historical rows are never edited or deleted. Corrections are added as new rows with a `Correction_of` reference.
3. **Stage-gated population.** Rows with data from future stages are marked `[PENDING: Stage N — reason]`. Placeholder rows with invented values are forbidden.
4. **Cross-reference links.** Each document notes which other documents it depends on or feeds into.

---

## Document Index

Status key: ✅ current · ⚠️ stale (content predates the October re-baseline; update due as noted) · 🟡 schema only.

| # | Document | Path | Purpose | First active stage | Update trigger | Last updated | Status |
|---|----------|------|---------|-------------------|----------------|--------------|--------|
| 1 | Ablation Architecture | `ablation_architecture.md` | Architectural decision record | Stage 0 | On any pipeline/component architectural change | 2026-10-26 | ✅ Current (v0.12: D2 flag names; UEG-C schema-draft-v0.2, Algorithm 5 pruner, verdict schema-draft-v0.5) |
| 2 | Calibration Thresholds | `calibration_thresholds.md` | Thresholds used by the integrity gate | Stage 1 | After threshold tuning | 2026-05-19 | ⚠️ May values on the OTel corpus; recalibrated on build data in S2–S3. K-hop K and top-n are recorded in `s1_7_khop_pruner.md` and entry 40 (re-checked on the S1.2 corpus at the S1 exit) |
| 3 | Dashboard | `dashboard.md` | Sprint Gantt, architecture, evidence grid, integrity snapshot | Stage 0 | At every sprint exit | 2026-10-27 | ✅ Current (S1 exit) |
| 4 | Data Collection Log | `data_collection_log.md` | Per-incident capture record; imported corpora as summaries | Stage 0 | After every capture or import | 2026-10-27 | ✅ Current (20 OTel captures; RCAEval build 495 and pool 240; OTel build corpus 63, S1.2) |
| 5 | Deviation Log | `deviation_log.md` | Mirror of `deviation_log.jsonl` | Stage 0 | After every `bin/log_deviation.py` append | 2026-10-27 | ✅ Current (45 entries) |
| 6 | Disjointness Audit Log | `disjointness_audit_log.md` | Every DisjointnessAuditor run | Stage 1 | After each audit run | 2026-05-21 | ✅ Current as a history (3 entries, May flag names); next entry at S5.2 certification |
| 7 | Ground Truth Labelling | `ground_truth_labelling.md` | Fault → root-cause labels, OTel corpus | Stage 0 | On corpus expansion or label correction | 2026-10-27 | ✅ Current: 20 May OTel labels listed; RCAEval and OTel build labels are signed files (pointers added at the S1 exit) |
| 8 | Helios MVP Tracking | `helios_mvp_tracking.md` | Task tracker with SHAs and evidence (schema R1–R8) | Stage 0 | Every task start and finish | 2026-10-27 | ✅ Current (Milestone 6 = S1 closed; S2-M5-RES05 open) |
| 9 | Hypothesis–Variant–Metric Mapping | `hypothesis_variant_metric_mapping.md` | Readable view of Families A, B, E | Stage 0 | On analysis-plan change | 2026-10-24 | ✅ Current (generated from `helios/research/analysis_plan.py`) |
| 10 | Price Book | `price_book.md` | Cost coefficients for CpR | Stage 2 | Frozen at `build-freeze` | 2026-10-27 | 🟢 price-book-v2 (S1.10, deviation entries 42-43): AWS primary profile fully verified against AWS price data (S3 Standard checked 2026-10-27); GCP and Azure sensitivity profiles unverified; read by `helios/evaluation/cost.py` |
| 11 | Prompt Version Registry | `prompt_version_registry.md` | Frozen L-pipe prompts with SHA | Stage 3 | Before each prompt change | 2026-05-19 | ✅ Current (rca_v1); new prompts in S2.3 |
| 12 | Replication Verification Log | `replication_verification_log.md` | 10% byte-equality replication | Stage 7 | After replication runs | 2026-05-08 | 🟡 Schema only — S5.4 and phase E |
| 13 | Reproducibility Manifest | `reproducibility_manifest.md` | Environment pins, schema freeze, checklist | Stage 0 | On environment change or schema freeze | 2026-05-19 | ⚠️ Predates the Ed25519 layer, `cryptography`, the baseline images and `drain3==0.9.11` (S1.4); full update at `build-freeze` (S5.6) |
| 14 | Seed Register | `seed_register.md` | Seed registry | Stage 0 | Before any new seed is used | 2026-10-24 | ✅ Current (binding register SEED-SA0-01, entry 34) |
| 15 | Snapshot Hash Registry | `snapshot_hash_registry.md` | Incident → snapshot hash mirror | Stage 0 | After every capture | 2026-05-15 | ✅ Current: its source `data/snapshot_registry.jsonl` was reset on purpose in `b24955c` (May re-capture) and is recreated by runs; checked in S1.1 |
| 16 | Tracking Documents Register | `tracking_documents_register.md` | This index | Stage 0 | On any tracking-doc add/remove/rename and at every sprint exit | 2026-10-27 | ✅ Current |
| 17 | Validity Tracking | `validity_tracking.md` | Threat-to-validity register | Stage 0 | After each new threat | 2026-10-27 | ✅ Current (17 threats; S0 findings and S1 findings T10–T17 added) |
| 18 | VCL Manifest Tracking | `vcl_manifest_tracking.md` | Variant configuration hashes | Stage 0 | After every VCL change or new variant | 2026-10-24 | ✅ Current (15 variants; confirmatory hashes match OSF deposit 1) |
| 19 | E2E Product Plan | `helios_e2e_product_plan_2026-10.md` | Schedule, principles, decisions D1–D12 | Stage A | On a plan change approved by the owner | 2026-10-24 | ✅ Current |
| 20 | Task Breakdown | `helios_task_breakdown.md` | Every task as a module (authoritative steps) | Stage A | When a task is added or changed | 2026-10-26 | ✅ Current (S1.3 no-go and the S2.1 detection trigger recorded) |
| 21 | R1 Traceability Matrix | `r1_traceability_matrix.md` | Approved Ch3 vs the code | Stage A | On a design change against Ch3 | 2026-10-23 | ✅ Current (approved) |
| 22 | Metric Contract | `metric_contract.md` | One definition per metric; strata | Stage A / S0 | Deposited; changes need a deviation entry | 2026-10-24 | ✅ Current (in OSF deposit 1; read with entry 38) |
| 23 | S0.1 Dataset Check | `s0_1_dataset_check.md` | RCAEval / AIOpsLab findings F1–F5 | Stage A / S0 | Fixed record | 2026-10-23 | ✅ Final |
| 24 | S0.3 Corpus and Run Design | `s0_3_d11_corpus_run_design.md` | Approved D11 design | Stage A / S0 | Addendum only (e.g. AIOpsLab) | 2026-10-26 | ✅ Final (approved); S1.3 note: AIOpsLab no-go, no addendum |
| 25 | S0.11 Lead-time Register | `s0_11_lead_time_register.md` | Owner lead-time items L1–L10 | Stage A / S0 | When an item's status changes | 2026-10-27 | ✅ Current (open; L1 IRB in progress, L9 Docker 16 GB done, L10 partly done) |
| 26 | Sprint plans and exit reports | `docs/sprints/` | One folder per sprint: `plan.md` and `exit_report.md` | Stage A | Plan before each sprint; exit report at each exit | 2026-10-27 | ✅ Current (S0 and S1 closed; S2 plan refreshed; S3–S5, E, A, Stage B planned) |

Historical, not maintained: `stage0_gap_analysis.md` (May Stage 0 gap analysis), `HELIOS_MVP_Execution_plan_v0.6.md` (May plan).

---

## OSF Artefacts

Generated by `bin/verify_osf_freeze.py --generate` and verified on every push by the `osf-freeze-verify` CI job and by the pre-push gate. Deposited in OSF deposit 1 (DOI 10.17605/OSF.IO/KMR3D, commit `524b621`, tag `osf-deposit-1`). **Never regenerate after a deposit**: keep the JSON bytes as deposited and recompute only `manifest_sig.txt` when a covered text file changes.

| Path | Type | Purpose |
|---|---|---|
| `research/osf/seeds.json` | Generated | Seed registry and binding register layout |
| `research/osf/prompt_sha.json` | Generated | Prompt version and SHA-256 |
| `research/osf/thresholds.json` | Generated | Calibrated thresholds |
| `research/osf/variant_hashes.json` | Generated | 8 confirmatory variant hashes and flag matrix |
| `research/osf/analysis_plan.json` | Generated | Families A, B, E with baselines, α by rank and tests |
| `research/osf/corpus_manifest.json` | Generated | Corpus manifest with per-file SHA-256 |
| `research/osf/manifest_sig.txt` | Generated | SHA-256 over the JSON artefacts, `preregistration.md` and `metric_contract.md` |
| `research/osf/preregistration.md` | Human-authored | Pre-registration text (deposited) |
| `research/ablation_notebook.ipynb` | Notebook | Ablation matrix notebook; executed in CI and in the pre-push gate |

---

## Ownership and Responsibility

All documents are maintained by the researcher (Akshay Adik, solo). There is no delegation.

Document updates must be committed in the **same PR** as the code change they track. A PR that adds a new capture must also update `data_collection_log.md` and `snapshot_hash_registry.md`. A PR that adds a variant must also update `vcl_manifest_tracking.md`.

---

## Excluded from this Register

- `HELIOS_MVP_Execution_plan_v0.6.md` — project planning document, not a research tracking artefact; not covered by the schema rules
- `docs/research/research_proposal_akshayadik.pdf` — source research proposal; read-only reference
- `docs/research/project_plan.md` — original 15-month plan, kept for history; read-only

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

helios_e2e_product_plan_2026-10.md + helios_task_breakdown.md
    └─ docs/sprints/<sprint>/plan.md (sprint view)
    └─ helios_mvp_tracking.md (one row per task)
        └─ docs/sprints/<sprint>/exit_report.md (written at the exit gate)

helios/vcl/variants.py
    └─ research/osf/variant_hashes.json (deposited)
```
