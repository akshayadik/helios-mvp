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

## Risks

| Risk | Mitigation |
|---|---|
| B1 overlaps phases E and A (15 Feb – 31 Mar), competing for the same time | Phases E and A take priority until results are ready on 31 March |
| Stage B work alters the frozen build | Separate flags; VCL blocks divergence from the freeze manifest in confirmatory runs |
