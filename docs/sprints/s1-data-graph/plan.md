# Sprint S1 — Data and graph · plan

**Window:** 16 Nov – 4 Dec 2026 (15 working days) · **Milestone:** S2-M6 · **Exit tag:** `rb-s1-exit` · **Status:** next

Task details: `docs/tracking/helios_task_breakdown.md` § Sprint S1 (authoritative).

## Goal

Every case sealed in the HELIOS recorded format with no label leakage; the typed incident graph (UEG-C) built from all three modalities; scores and costs computed outside the pipelines.

## Entry conditions

- `rb-s0-exit` (met 2026-10-24). Seed register for opaque IDs (S0.8) and the D11 design (S0.3) in place.
- **Early start possible:** S0 closed three weeks before this window. Starting S1 on 26 Oct gives the over-committed sprints (S1, S2, S4) slack. Owner to confirm.

## Capacity

16 days of tasks in 15 working days. If the sprint starts on time, the AIOpsLab spike (S1.3, Tier 2) is the first to slip.

## Tasks

| Task | Tier | Tracking | Effort | Depends on | Done when |
|---|---|---|---|---|---|
| S1.1 RCAEval adapter with sealing and leakage controls | T1 | S2-M6-ENG01 | 3 | S0.8 | 240 pool + 495 build cases sealed; leakage test passes; pool manifest hash recorded |
| S1.2 New OTel Demo captures (~60) | T1 | S2-M6-RES01 | 2 | — | ~80 OTel incidents sealed, all verify |
| S1.3 AIOpsLab recording spike | T2 | S2-M6-RES02 | 2 | — | Go → D11 addendum before the freeze; no-go → Stage B, recorded |
| S1.4 Log templates (Drain3) | T1 | S2-M6-ENG02 | 1 | S1.1 | Templates stable across reruns |
| S1.5 Typed incident graph (UEG-C), four edge kinds | T1 | S2-M6-ENG03 | 3 | S1.1, S1.4 | Cross-domain path test; stable snapshot hash; partial-trace test |
| S1.6 Structural bundle (`ueg_structural`) | T1 | S2-M6-ENG04 | 1 | S1.5 | noStructural changes the snapshot hash |
| S1.7 K-hop pruner (Algorithm 5) | T1 | S2-M6-ENG05 | 1 | S1.5 | 50–200 nodes on build incidents; calibration logged |
| S1.8 Verdict contract (ranked list, μ, σ, cost, latency) | T1 | S2-M6-ENG06 | 1 | S0.7 | Round-trip and stability tests |
| S1.9 Scoring path (post-dispatch, never fed to pipelines) | T1 | S2-M6-ENG07 | 1 | S1.8 | Fixture scores match hand computation |
| S1.10 Price book, token accounting, cost | T1 | S2-M6-ENG08 | 1 | S1.8 | Hand-computed cost matches on a fixture |

Suggested order: S1.1 → S1.4 → S1.5 → S1.6 / S1.7 on the data path; S1.8 → S1.9 / S1.10 in parallel; S1.2 and S1.3 whenever Docker is free.

## Owner items

- Confirm the start date (early start or 16 Nov).
- Raise Docker Desktop memory to at least 16 GB (S0.11 L9) — S1.2 captures and S1.3 (`kind`) need it too.
- Second rater and adjudicator confirmed by 30 Nov (S0.11 L2–L3).

## Documentation carried from S0

- `docs/tracking/ablation_architecture.md` still uses the May flag and variant names: revise to the Chapter 3 names before S1.5 (UEG-C).
- `docs/tracking/validity_tracking.md`: add the S0 threats (case-name leakage F1, concentrated root causes F2, rater blinding for noLLM narratives).
- `data/snapshot_registry.jsonl`, cited in May as the source of `snapshot_hash_registry.md`, is not in the repository: find or rebuild it in S1.1.

## Expected deviation entries

UEG-C schema bump (S1.5); verdict schema bump (S1.8); K and top-n values (S1.7); price-book coefficients (S1.10); AIOpsLab go → D11 addendum (S1.3).

## Exit criteria

S1.1–S1.10 DONE (or S1.3 recorded as moved to Stage B); leakage test passes on every pool and build case; full gate green; tag `rb-s1-exit`; exit report written.

## Risks

| Risk | Mitigation |
|---|---|
| Label leakage through case names, paths or fault strings (S0.1 F1) | Opaque IDs from the register; leakage test over every input, snapshot, prompt and stored text |
| Pool data touched before the freeze | Adapter refuses pool cases before tag `build-freeze`; pool is only sealed, never run |
| Service names differ across modalities (F4, F5) | Per-system normalisation table; metric/log-only services kept as nodes |
| RCAEval download size (~3.4 GB Parquet) | Per-case download outside git, with checksums |
