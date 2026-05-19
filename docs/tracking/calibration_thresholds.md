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

### Milestone 3 — G-pipe Conditional PPR Traversal (frozen 2026-05-19)

Calibration corpus: 20-incident OTEL Demo exploratory set (same set as M2).
Calibration procedure: LOO-CV sweep over 5 thresholds via `scripts/calibrate_gpipe.py` (`DISAGREEMENT_SWEEP = [0.20, 0.25, 0.30, 0.35, 0.40]`).
Finding: All 20 incidents triggered G-pipe at every threshold — corpus too uniform for discrimination. Threshold frozen at lowest sweep value; real calibration deferred to AIOpsLab confirmatory phase.

| Component | Parameter | Value | Calibration_source | Stage_frozen | Evidence |
|---|---|---|---|---|---|
| G-pipe | GPIPE_PPR_ALPHA | 0.85 | Fixed (matched D-pipe alpha; not data-derived) | Milestone 3 | `helios/pipelines/g_pipe/gpipe_config.py` |
| G-pipe | DISAGREEMENT_THRESHOLD | 0.20 | LOO-CV sweep on 20-incident OTEL corpus; all thresholds 0.20–0.40 triggered identically; lowest value selected | Milestone 3 | `gpipe_config.DISAGREEMENT_THRESHOLD`; SHA `8759d6f` |

**LOO-CV result (held-out):** G-pipe HR@3 = 0.60 (≥ 0.40 held-out gate); D-pipe HR@3 = 0.40 on same held-out set.

**A-H6 sentinel filter mandatory:** `WHERE narrative != 'gpipe-gated-or-skipped'` — all 20 OTEL incidents trigger at threshold 0.20; sentinel prevents phantom G-pipe signal in analysis.

**Deviation log entries relevant to these values:**
- §4.2 A-H6 / §3.6.7 G-pipe threshold (sig `05a602955403f9cb`): DISAGREEMENT_THRESHOLD 0.30→0.20; ppr_scores added to run_dpipe return dict

**Note on thresholds.json:** `research/osf/thresholds.json` field `gpipe.disagreement_threshold` erroneously contains `PRUNER_THRESHOLD` (0.02) instead of `DISAGREEMENT_THRESHOLD` (0.20). The authoritative source is `gpipe_config.DISAGREEMENT_THRESHOLD`. This discrepancy is a known artefact generation bug; correct value is 0.20.

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

*Last updated: 2026-05-19 — Milestone 3 G-pipe conditional PPR thresholds added and frozen*
