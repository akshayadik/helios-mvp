**HELIOS Detailed Execution Plan — Authoritative & Actionable**  
**Version:** 1.0 (Combined & Reconciled)  
**Date:** 07 May 2026  
**Binding Sources:** Dissertation Proposal §3.6 + MVP Execution Plan v1.0 (governs Phase 1) + Ablation-Centric Research Principles  

**Core Philosophy**  
- **C1 is the headline novelty** — runtime-enforced ablation discipline (VCL, snapshot hashing, metric integrity gate, exclusion ledger, deviation log, disjointness audit) is built first and never compromised.  
- **MVP-First + Ablation-Centric Parallel Research** — Phase 1 (Months 1–6) delivers the binding MVP on OTEL Demo while producing contemporaneous ablation documentation and OSF protocol.  
- **Spine-and-Body + Additive-Only** — All extensions (AIOpsLab, MAHC, ORAR, etc.) plug into the immutable spine without rework.  
- **Two-Environment Firewall** — OTEL Demo = exploratory calibration; AIOpsLab = confirmatory. `evaluation_phase` column enforces this.  
- **Trackability & Market Readiness** — Weekly status template + essential documents produce a presentable dissertation + marketable product (CLI → API → dashboard) within ~12–15 months.

**Outcome at Month 15**  
- Defensible dissertation (C1 + ablation evidence + Chapter 4/5).  
- Open-source / SaaS-ready HELIOS core (reproducible, modular, observable RCA engine).  
- 1–2 journal submissions + workshop paper path.

---

### Phase 1: MVP + Ablation-Centric Research (Weeks 1–27 / Months 1–6)

**Primary Goal:** Execute binding MVP Plan v1.0 exactly while building ablation-centric research artefacts in parallel (10–15% weekly effort).

#### Milestone 0 – Kickoff & Spine Hardening (Weeks 1–2)
**Objective:** Repo + C1 foundation + OTEL Demo harness proven + first research docs.

**Entry Criteria**  
- Hardware ≥32 GB RAM, Docker + Poetry installed.  
- Advisor sign-off on this plan.

**Step-by-Step Plan**  
1. Create Poetry project, directory structure (`helios/vcl/`, `schemas/`, `telemetry/`, `store/`, `pipelines/`, `eval/`, `tests/`, `docs/`), CI (ruff, mypy, pytest, coverage, disjointness).  
2. Implement VCL core: `config.py` (Pydantic manifest + `variant_config_hash`), `decorators.py` (`@gated_by`), `registry.py` (12 flags with MVP defaults).  
3. Implement deviation log (`eval/deviation_log.py` — append-only JSONL + HMAC-SHA256).  
4. OTEL Demo spike: `docker compose up`, inject 1 fault, capture 5-min telemetry → Parquet (P1/P2/P3).  
5. Draft UEG-C canonical JSON schema (4 typed edge classes declared) + verdict schema (Pydantic).  
6. Start **Ablation Architecture Notebook** (`docs/ablation_architecture.md`) — VCL + spine section.  
7. Draft OSF protocol sketch (hypotheses, variants, metrics, C1 invariants).

**Exit Criteria**  
- VCL test suite: 100% hash-consistency + gate tests passing.  
- 5 OTEL Demo recordings with stable snapshot hashes across 3 replays.  
- Deviation log operational (first entries written).  
- Ablation Notebook: VCL section complete. OSF protocol v0.8 drafted.  
- **Gate:** End-to-end harness success (critical — log deviation if fails).

**Deliverables**  
- Repo skeleton + CI green.  
- VCL foundation.  
- 5 Parquet recordings.  
- Ablation Notebook + OSF draft.

#### Milestone 1 – Telemetry Pipeline + Full C1 Foundations (Weeks 3–6)
**Objective:** Reliable replay + runtime enforcement + schema freezes.

**Entry Criteria**  
- Milestone 0 passed.

**Step-by-Step Plan**  
1. Telemetry recorder + orchestrator CLI (`helios run --variant ... --corpus ...`).  
2. Result store (DuckDB), exclusion ledger (JSONL), metric integrity gate.  
3. Full disjointness audit (static + coverage.py CI).  
4. Record 20 incidents, verify byte-equal replays.  
5. Freeze schemas: UEG-C canonical JSON, verdict model, result row DDL (tagged in Git + CI enforcement).  
6. Update Ablation Notebook: Telemetry + C1 sections + schema freeze memos.  
7. Expand OSF protocol (inclusion/exclusion rules, terminology).

**Exit Criteria**  
- 20 incidents with 100% VCL + snapshot hash + gate compliance.  
- Disjointness CI green.  
- All schemas frozen (CI round-trip tests passing).  
- Ablation Notebook: C1 + Telemetry complete.  
- **Gate (Week 5):** End-to-end result row through full C1 path.

**Deliverables**  
- `vcl/`, `telemetry/`, `store/` complete.  
- Schema freeze artefacts.  
- Updated OSF draft.

#### Milestone 2 – D-pipe + UEG-C Skeleton (Weeks 7–11)
**Objective:** Statistical baseline + content-hashed graph.

**Entry Criteria**  
- Milestone 1 passed.

**Step-by-Step Plan**  
1. UEG-C builder (structural + behavioural edges, K-hop PPR pruner, canonical JSON + SHA-256).  
2. D-pipe (Pearson/Spearman + propagation behind flags).  
3. Calibration on held-out set; freeze thresholds.  
4. Update Ablation Notebook: UEG-C + D-pipe sections + edge taxonomy memo.  
5. Smoke ablations (HELIOS-D vs random).

**Exit Criteria**  
- HR@3 ≥ 0.25 on calibration; 0 hash collisions.  
- Canonical round-trip + pruner efficacy tests passing.  
- Ablation Notebook updated.  
- **Gate:** Pruner reduces graph ≥50%; D-pipe deterministic.

#### Milestone 3 – Conditional G-pipe + L-pipe + OSF Full Freeze (Weeks 12–17)
**Objective:** Peer pipelines + protocol locked.

**Entry Criteria**  
- Milestone 2 passed.

**Step-by-Step Plan**  
1. G-pipe entry gate test (PPR disagreement ≥30%).  
2. If passes: Implement G-pipe (PPR traversal).  
3. L-pipe: Ollama + frozen prompt (SHA recorded) + JSON schema + 1 retry.  
4. Model selection spike + lock.  
5. Full OSF freeze (corpus manifest, seeds, prompt SHA, thresholds, variant hashes).  
6. Update Ablation Notebook: Pipelines + consensus + variant matrix.

**Exit Criteria**  
- H_struct ≤ 0.10; OSF full freeze deposited.  
- All 7 variants live in VCL.  
- Ablation Notebook: L0–L3 complete.  
- **Gate:** 10-incident qualitative review.

#### Milestone 4 – Consensus + Main Run + Audits (Weeks 18–22)
**Objective:** Ablation matrix + C1 evidence.

**Entry Criteria**  
- Milestone 3 + OSF freeze.

**Step-by-Step Plan**  
1. Uniform Borda consensus + baselines.  
2. Run 125 events across variants.  
3. Statistical inference (exploratory Wilcoxon).  
4. Final disjointness audit + replication script (10%).  
5. Finalise C1 evidence tables + Ablation Notebook.

**Exit Criteria**  
- ≥80% inclusion; C1 verification ≥99%.  
- Disjointness + replication passing.  

#### Milestone 5 – Chapter 4 + Phase 1 Closure (Weeks 23–27)
**Objective:** Protected writing + submission-ready Chapter 4.

**Entry Criteria**  
- Milestone 4 passed.

**Step-by-Step Plan**  
1. Write Chapter 4 (architecture, C1 evidence, exploratory results, limitations, deviation summary).  
2. Final OSF MVP deposit.  
3. Advisor reviews (writing window inviolate — no new engineering).

**Exit Criteria**  
- Advisor sign-off on Chapter 4.  
- Replication verified on fresh machine.

**Phase 1 Parallel Research (10–15% weekly effort)**  
- Ablation Architecture Notebook updates every milestone.  
- OSF protocol incremental drafting.  
- Weekly C1 verification dashboard.  
- Deviation log discipline.

---

### Phase 2: Full Research Extensions + Product Refinement (Months 7–15)

**Milestone 6 – AIOpsLab Migration & Product Foundation (Months 7–8)**  
- M1 migration (`ingest_mode` + service-name registry).  
- 5 AIOpsLab incidents under same VCL.  
- Product: CLI → simple FastAPI endpoint + basic observability.

**Milestone 7 – Advanced Pipelines (Months 8–10)**  
- Full MAHC, ORAR pre-training, GNN G-pipe, L-pipe M2 migration.  
- Product: Add IOL passive + Docker image packaging + basic dashboard (Streamlit).

**Milestone 8 – Confirmatory Runs + Analysis (Months 10–12)**  
- OSF pre-registration freeze.  
- Full ablation + baseline runs.  
- Statistical analysis + Chapter 5.  
- Product: Usage tracking + API key auth.

**Milestone 9 – Defense + Market Launch Readiness (Months 12–15)**  
- Dissertation submission + defense.  
- Open-source repo + reproducible demos + Helm chart option.  
- Journal submissions.  
- Marketable MVP: CLI + API + dashboard for real-world OTEL/K8s environments.

---

### Weekly Tracking System (Use Every Friday)

Create `docs/weekly_status_YYYY-WW.md` with this template and commit it:

```markdown
# Weekly Status — Week XX (YYYY-MM-DD)

**Engineering**  
Completed:  
Blocked/Next:  

**Research Documentation**  
Ablation Notebook updated:  
OSF progress:  
Deviation log entries:  

**C1 Verification**  
Variant-identity rate:  
Snapshot hash consistency:  
Metric integrity gate pass rate:  
Disjointness status:  

**Risks & Mitigations**  

**Next Week Plan**  
Engineering:  
Research:  
Advisor items:
```

This becomes your audit trail for Chapter 4 and product README.

---

### Essential Documents (All in `docs/` — Build in Parallel)

- `deviation_log.md` (append-only, Day 1).  
- `ablation_architecture.md` (living — update every milestone).  
- `osf_protocol_v1.md` (incremental → full freeze Stage 5).  
- `c1_evidence.md` (tables + rates).  
- Schema freeze memos (tagged in Git).  
- Weekly status files.

---