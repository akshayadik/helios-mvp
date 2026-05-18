# HELIOS MVP — Live Dashboard

_Auto-refresh target (Stage 1+): `weekly_dashboard.yml` GitHub Action will
regenerate the dynamic sections (cell-completion grid, deviation count) every
Friday EOD. Until then, sections marked **(manual)** are kept current by hand._

## Stage Progress (manual)

```mermaid
gantt
    title HELIOS MVP — Stage Progress
    dateFormat YYYY-MM-DD
    axisFormat %b %d

    section Tracking
    Stage 0 — Repo + VCL skeleton + Harness   :active, s0, 2026-05-08, 14d
    Stage 1 — Telemetry + VCL Foundation      :s1, after s0, 28d
    Stage 2 — D-pipe                          :s2, after s1, 14d
    Stage 3 — G-pipe                          :s3, after s2, 14d
    Stage 4 — L-pipe + Consensus              :s4, after s3, 21d
    Stage 5 — OSF Freeze                      :crit, s5, after s4, 7d
    Stage 6 — Confirmatory runs               :s6, after s5, 21d
    Stage 7 — Replication verification        :s7, after s6, 14d
    Stage 8 — Chapter 4 + OSF deposit         :crit, s8, after s7, 28d
```

## Architecture flow (manual; updated when ablation_architecture.md changes)

```mermaid
flowchart LR
    OTEL[OTEL telemetry] --> UEG[UEG-C snapshot]
    UEG -->|snapshot_hash| D[D-pipe]
    UEG -->|snapshot_hash| G[G-pipe]
    UEG -->|snapshot_hash| L[L-pipe]
    D --> C[MAHC consensus]
    G --> C
    L --> C
    C --> R[Ranked root cause]
    VCL[Variant Control Layer] -.gates.-> D
    VCL -.gates.-> G
    VCL -.gates.-> L
    VCL -.gates.-> C
    MIG[Metric Integrity Gate] -.audits.-> R
    MIG -.signs.-> EL[(exclusion_ledger.jsonl)]
    DL[(deviation_log.jsonl)] -.HMAC chain.-> VCL
```

## Cell-completion grid (manual until weekly_dashboard.yml lands)

| Variant            | AIOpsLab | Train-Ticket | DeathStar | PetShop | OpsEval |
|--------------------|----------|--------------|-----------|---------|---------|
| HELIOS-Full        | ⏳ 0/N   | ⏳ 0/N       | ⏳ 0/N    | ⏳ 0/N  | ⏳ 0/N  |
| HELIOS-noLLM       | ⏳ 0/N   | ⏳ 0/N       | ⏳ 0/N    | ⏳ 0/N  | ⏳ 0/N  |
| HELIOS-noConsensus | ⏳ 0/N   | ⏳ 0/N       | ⏳ 0/N    | ⏳ 0/N  | ⏳ 0/N  |

Legend: ✅ ≥80% complete · 🟡 partial · ⏳ not yet started · ❌ blocked

## C1 Invariants snapshot (manual)

*Last updated: 2026-05-18 (Milestone 2 exit + PPR fix)*

| Invariant | Status | Evidence link |
|---|---|---|
| Variant manifest hashing | ✅ | `helios/vcl/` — 8 confirmatory variants, unique hashes, frozen Stage 0 |
| Snapshot hash registry | ✅ | `helios/vcl/snapshot_registry.py` + `data/snapshot_registry.jsonl` (20 entries) |
| Metric integrity gate | ✅ | `helios/integrity_gate.py` — frozen Milestone 1 |
| Exclusion ledger (signed) | 🟡 partial | `bin/log_exclusion.py` — schema defined; CLI stub; auto-populated via `AppendOnlyLedger` protocol |
| Deviation log (signed, chained) | ✅ | `bin/log_deviation.py` — 10 entries, chain verified (M2 adds 5 entries) |
| Reconciliation ledger | ✅ | `helios/orchestrator/ledger.py` — 25 entries, HMAC chain verified |
| DisjointnessAuditor | ✅ | `helios/vcl/disjointness.py` — static + dynamic PASSED at Milestone 1 |
| UEG-C Builder | ✅ | `helios/graph/ueg_c_builder.py` + `ppr_pruner.py` — frozen Milestone 2; 15/15 gate PASS |
| D-pipe calibration | ✅ | LOO-CV HR@3=0.5333; params frozen in `dpipe_config.py`; SHA `8d11801` |

## Latest deviation log entries (manual)

*Source: `deviation_log.jsonl` — 10 entries total; 5 most recent shown*

| # | Date | Stage | Clause | Change (truncated) | sig[:12] |
|---|---|---|---|---|---|
| 6 | 2026-05-16 | Stage 1 | §2.2 Span Containment Heuristic | Temporal containment backward-scan instead of parent_span_id | 5655ff9fbeeabfaf |
| 7 | 2026-05-16 | Stage 1 | §4.2 Smoke Ablation | Smoke gate tied: HELIOS-D HR@3=0.00, Random HR@3=0.00 on rcf hold-out | 7737045a57c994a5 |
| 8 | 2026-05-16 | Stage 1 | §2.4 K-Hop PPR Pruner — Pruner Efficacy Exit Gate | Pruner achieves 0% node reduction; gate requires ≥50% reduction | 629886ca14cd7468 |
| 9 | 2026-05-18 | Stage 1 / M2-fix | §2.4-gate | PPR entry-point fix; PRUNER_EFFICACY_GATE 0.50→0.25; PRUNER_THRESHOLD 0.01→0.02 | 766ee8e1fc60 |
| 10 | 2026-05-18 | Stage 1 / M2-fix | §2.4-gate-2 | PRUNER_EFFICACY_GATE 0.25→0.20; INTEGRITY_RATE_GATE 0.85→0.40 | 1737fc5b33ab |
