# Stage B — Completing the full product · plan

**Window:** 15 Feb – end of July 2027 · **Milestones:** S3-M13 … S3-M17 · **Exit tags:** `rb-b1-exit` … `rb-b5-exit` (proposed) · **Status:** planned

Task details: `docs/tracking/helios_task_breakdown.md` § Stage B (authoritative); full feature definitions: first draft of the e2e plan (commit `c0fe406`) and `docs/tracking/r1_traceability_matrix.md`.

## Goal

Build every remaining part of the product, so that nothing in the approved scope is cut. **Full product complete at the end of July.**

## Rules

- Built on `main` after tag `build-freeze`, behind feature flags (`VCLFlag`), through the same gate.
- Never touches the frozen evidence build.
- Each Stage B evaluation is pre-registered separately and is exploratory relative to the Stage A results.
- Each module is broken into tasks (goal, steps, done when, tracking) when it starts; its own folder (`b1-…/` to `b5-…/`) then gets a `plan.md` and, at exit, an `exit_report.md`.

## Modules

| Module | Tracking | Window | Contents |
|---|---|---|---|
| B1 Ingest and deployment | S3-M13 | 15 Feb – 31 Mar | Live OTLP ingest; P4 cognitive telemetry (MCP spans, goal drift, loop depth); P5 business telemetry; Helm production deployment; multi-tenant administration |
| B2 Privacy and robustness | S3-M14 | Apr | Full Privacy Gateway with per-tenant differential privacy; Adversarial Robustness Monitor with attestation; eBPF tiered adaptive sampling |
| B3 Safe action | S3-M15 | May | Full digital twin with traffic mirroring; ASRE (structural, WAL-replay, sketch); remediation templates; automatic-action stage; Monitor Agent; live MTTR measurement (D10) |
| B4 Self-healing and learning | S3-M16 | Jun | Full Cognitive Sentinels and Deterministic Fallback Agent; full IOL; HIS tiers; learning loops in production mode; 1,200-incident synthetic pre-training testbed |
| B5 Stage B evaluation | S3-M17 | Jul | E-H1 (Tier-4 cognitive faults), full E-H4, E-H6, E-H9, H4b scaling, 70B and Qwen contrast, FAE at scale. **Full product complete** |

Plus every Tier-2 item recorded as moved to Stage B during S1–S5.

## Carried in from Stage A

| Item | From | Module |
|---|---|---|
| AIOpsLab exploratory corpus: conversion into the sealed format works (one HotelReservation window, S1.3); pin its images and charts, record a set of problems, and evaluate exploratorily | S1.3 (no-go for the pool) | B5, recorded during B1 |
| Longer fault period for `emailMemoryLeak` (near-silent within 5 minutes in the S1.2 corpus) | S1.2 | B5 (OTel exploratory runs) |
| **Router go-live in shadow mode** (owner 2026-11-06): on a new system or tenant, run uniform routing (`cbr_routing` OFF) in production while recording what the frozen router would have chosen (the CoE R step already holds every decision). Turn routing on for that system once its stop decisions match uniform's answers within the S3.1 tolerance (one percentage point of HR@3) on that system's own incidents; monitor escalation share and per-arm HR@3 after. Answers the build-to-production transfer question (S2-BL-01) with the system's own data, and pairs with the B4 learning loops for drift | S3.1 design (R-b, R-c) | B1 (deployment), B4 (learning loops) |
| **Knowledge Cortex (S3.4)**, moved from Stage A (entry 82; owner 2026-11-08, no index built in Stage A, 2026-11-09). Conditions fixed now: (1) built only from the Stage A build corpora plus captures made after `build-freeze`; never from the confirmatory pool; (2) a pool-exclusion hash test (no pool incident ID or window hash in the index) is part of done; (3) evaluated on non-pool data only (AIOpsLab, new OTel captures); (4) design, content source (real runbooks, incident memory or both) and evaluation are pre-registered in the Stage B pre-registration before any build. Any use by the L-pipe changes its frozen prompts, so it is a Stage B variant, never HELIOS-Full's Stage A build. First check: does SOP retrieval help the log worker when the log digest is empty (S2-BL-07) | S3 plan; row S2-M8-ENG04 | B4 |
| **ACP follow-ups (S3.2, entries 82–83).** Ch3's schema change and data mutation classes and the log WAL-replay estimate need incidents with realised remediations and services with a write-ahead log. Retrain the ACP on those; refit the router with the ACP block as features; evaluate E-H8 (HELIOS-noACP, latency-constraint satisfaction) exploratorily. Starting point: the frozen Stage A fit (`data/frozen/acp_params.json`, `dd7b63d3`; code-level faults 10/30 cross-fitted) | S3.2 design §3 P-a, P-f, §6 | B3 (WAL, remediation records), B4 (retraining, router refit) |
| **Accuracy guard for learning loops.** In the S3.3 replay, online reward learning under the frozen τ_acc taught the router to stop more often and fell 1.16 points of HR@3 below uniform, beyond the one-point tolerance. Production learning loops need a guard that checks per-arm HR@3 against that tolerance and reverts or freezes when it is crossed | S3.3 design §6 | B4 |
| **OTel fix C:** errors confined to one caller's calls (`recommendationCacheFailure`). Fixes A and B tied the frozen chain on held-out v4 and were not adopted (entry 81); their candidate chain is kept in `data/candidate/otel_fix/` as the exploratory record | S3 OTel fix design | B5 (OTel exploratory runs) |
| **FGSV beyond the lite version (S4.6, entry 89).** On HELIOS-Full's own top-1, the lite replay (ASRE structural mode) passes wrong and correct targets alike (12 of 17 each among gated proposals); the KS gate does almost all of FGSV's work and marks 52% of clean OTel targets STALE. The full twin with traffic mirroring and the WAL-replay and sketch modes should be judged on whether they separate near-miss targets (upstream callers) from the root cause | S4.6 design §7.3 | B3 |
| **IOL beyond the shared detector (S4.7, entry 89).** The frozen trigger rule sees control-plane slowdowns of ×5 and more within 3 runs but never ×2 or ×3, because per-run timings vary about 40% between incidents. Full IOL (live self-instrumentation) needs a per-component baseline that accounts for incident size, without giving up the same-apparatus claim lightly | S4.7 design §7.4 | B4 |
| **Privacy Gateway beyond patterns (S4.4).** Pattern redaction changes no build-data prompt, because the digests template raw values. NER for names in free text, redaction of stored evidence and per-tenant differential privacy remain | S4.4 design T-b | B2 |

## Risks

| Risk | Mitigation |
|---|---|
| B1 overlaps phases E and A (15 Feb – 31 Mar), competing for the same time | Phases E and A take priority until results are ready on 31 March |
| Stage B work alters the frozen build | Separate flags; VCL blocks divergence from the freeze manifest in confirmatory runs |
