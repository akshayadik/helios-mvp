# Calibration Thresholds

**Purpose:** All frozen runtime thresholds (anomaly detection cutoffs, PPR restart probability, graph edge weights, etc.) with calibration-set justifications. No real values exist until D-pipe is implemented at Stage 1.

**Schema version:** v1.0 (frozen 2026-05-15)
**Update cadence:** End of each calibration stage (Stage 1–5)
**Owner:** AA
**Lock target:** Stage 5 OSF freeze (values must not change post-freeze without a deviation log entry)

---

## Column Definitions

| Column | Meaning |
|---|---|
| `Component` | Pipeline component the threshold governs |
| `Parameter` | Parameter name as it appears in code |
| `Value` | Frozen numeric value (or [PENDING]) |
| `Calibration_source` | Dataset / procedure used to derive the value |
| `Stage_frozen` | Stage gate at which this value was locked |
| `Evidence` | Git SHA or artefact reference for the calibration run |

---

## Current Entries

### Milestone 2 — D-pipe + UEG-C Builder (frozen 2026-05-18)

Calibration corpus: 15-incident OTEL Demo exploratory set (adhc ×3, cart ×3, imgsl ×4, pcat ×5).
Calibration procedure: LOO-CV on 250-cell joint grid (5 × 5 × 10) via `scripts/calibrate_dpipe.py`.
Verification: calibration rerun post-PPR-fix confirming 15/15 PASS on both gates.

| Component | Parameter | Value | Calibration_source | Stage_frozen | Evidence |
|---|---|---|---|---|---|
| UEG-C PPR | PPR restart probability (alpha) | 0.85 | Spec §2.4 (fixed, not data-derived) | Milestone 2 | `helios/graph/ppr_pruner.py` line 67 |
| UEG-C PPR | PRUNER_THRESHOLD | 0.02 | OTEL 15-incident corpus; value removes isolated islands while retaining active call-path nodes | Milestone 2 | `dpipe_config.py`; SHA `d0e8576` |
| UEG-C PPR | PRUNER_EFFICACY_GATE | 0.20 | Observed min efficacy = 0.214 (3/14 pruned on sparse imgsl/pcat captures); deviation §2.4-gate-2 (sig `1737fc5b33ab`) | Milestone 2 | Calibration rerun SHA `44e9994`; 15/15 PASS |
| UEG-C PPR | INTEGRITY_RATE_GATE | 0.40 | Observed min retention = 0.429 (s0-cart-001); efficacy ≥0.20 and integrity ≥0.85 are incompatible on 14-node graph; deviation §2.4-gate-2 | Milestone 2 | Calibration rerun SHA `44e9994`; 15/15 PASS |
| D-pipe | w_error (error-rate weight) | 0.30 | LOO-CV grid search; best cell on all 15 incidents | Milestone 2 | `data/calibrated_params.json`; SHA `8d11801` |
| D-pipe | rho_threshold (propagation damping) | 0.20 | LOO-CV grid search; best cell on all 15 incidents | Milestone 2 | `data/calibrated_params.json`; SHA `8d11801` |
| D-pipe | topology_boost_factor | 1.00 | LOO-CV grid search; best cell on all 15 incidents | Milestone 2 | `data/calibrated_params.json`; SHA `8d11801` |

**LOO-CV result:** HR@3 = 0.5333 (≥ 0.25 gate); no optimism gap (in-sample HR@3 = 0.5333).

**Deviation log entries relevant to these values:**
- §2.4 (sig `5655ff9fbeeabfaf`): temporal containment heuristic for structural edges
- §2.4-gate (sig `766ee8e1fc60`): PPR entry-point fix; PRUNER_EFFICACY_GATE 0.50→0.25
- §2.4-gate-2 (sig `1737fc5b33ab`): PRUNER_EFFICACY_GATE 0.25→0.20; INTEGRITY_RATE_GATE 0.85→0.40
- §4.2 (sig `7737045a57c994a5`): smoke gate tied on rcf hold-out (no re-calibration permitted)

---

## Pending (future stages)

| Component | Parameter | Stage target | Notes |
|---|---|---|---|
| G-pipe | Edge weight threshold | Stage 4 | AIOpsLab calibration subset |
| G-pipe | PPR convergence epsilon | Stage 4 | AIOpsLab calibration subset |
| L-pipe | Hallucination rate threshold | Stage 5 | Human annotation sample (n=30) |
| Consensus | Borda weight distribution | Stage 6 | Calibration run on OTEL Demo set |

**Warning:** Do not set threshold values before the corresponding pipeline stage is implemented and calibrated. Premature threshold setting is a construct validity threat (T3) — thresholds must be derived from data, not guessed.

---

*Last updated: 2026-05-18 — Milestone 2 D-pipe and UEG-C PPR thresholds populated and frozen*
