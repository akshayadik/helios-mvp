# Sprint S3 — Routing and learning · plan

**Window:** 4–15 Jan 2027 (10 working days) · **Milestone:** S2-M8 · **Exit tag:** `rb-s3-exit` · **Status:** planned

Task details: `docs/tracking/helios_task_breakdown.md` § Sprint S3 (authoritative).

## Goal

The cheap-first router (IN3) sends statistical and graph evidence first and calls the LLM only on disagreement or low confidence, with frozen, hashed parameters. Tier-2 learning parts (ACP, two-stage reward, Knowledge Cortex, LLM fallback) are built behind their flags (`VCLFlag`: `cbr_routing`, `acp_stateful`, `reconcile_terminal`) or recorded as moved to Stage B.

## Entry conditions

`rb-s2-exit`: MAHC (S2.5) and cost accounting (S1.10) for the router; L-pipe (S2.3) for the Knowledge Cortex.

## Capacity

9 days of tasks in 10 working days. Only S3.1 is Tier 1.

## Tasks

| Task | Tier | Tracking | Effort | Depends on | Done when |
|---|---|---|---|---|---|
| S3.1 Router with cheap-first gate (IN3) | T1 | S2-M8-ENG01 | 3 | S2.5, S1.10 | Routed arm recorded per run; VCL verifies frozen parameters at start |
| S3.2 Action-Class Predictor | T2 | S2-M8-ENG02 | 2 | S1.5 | Gated; parameters hashed |
| S3.3 Two-stage reward and delayed labels | T2 | S2-M8-ENG03 | 2 | S3.1 | Provisional/terminal pairs verify; `reconcile_terminal=OFF` writes none |
| S3.4 Knowledge Cortex (SOP retrieval, build data only) | T2 | S2-M8-ENG04 | 1½ | S2.3 | Retrieval tests; pool-exclusion test |
| S3.5 LLM-unavailable fallback | T2 | S2-M8-ENG05 | ½ | S3.1 | Route to D+G on LLM failure; covariate recorded |

## Owner items

Finish S2.9 rater training if it ran over (target: κ ≥ 0.7 by end of January).

## Expected deviation entries

Router initialisation and thresholds (S3.1); ACP and reward parameters if built (S3.2, S3.3); Tier-2 items moved to Stage B.

## Exit criteria

S3.1 DONE; each Tier-2 task DONE behind its flag or recorded as moved to Stage B; full gate green; tag `rb-s3-exit`; exit report written.

## Risks

| Risk | Mitigation |
|---|---|
| Router tuned on data that overlaps the pool | Initialised on build data only; parameters frozen and hashed |
| Cheap-first gate hides LLM value from A-H1/A-H2 | Routed arm recorded per run; noRouter (uniform) is a confirmatory variant |
