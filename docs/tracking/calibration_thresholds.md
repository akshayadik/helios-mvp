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

No thresholds are frozen yet. D-pipe (the first pipeline with real computation) is targeted for Stage 1 / Milestone 2.

---

## Anticipated Structure

When populated, this table will contain entries of the form:

| Component | Parameter | Value | Calibration_source | Stage_frozen | Evidence |
|---|---|---|---|---|---|
| D-pipe | Pearson correlation threshold | [PENDING: Stage 1] | OTEL Demo 20-incident exploratory set | Stage 1 | calibration_run_SHA |
| D-pipe | PPR restart probability (alpha) | [PENDING: Stage 1] | OTEL Demo 20-incident exploratory set | Stage 1 | calibration_run_SHA |
| D-pipe | Anomaly z-score cutoff | [PENDING: Stage 1] | OTEL Demo 20-incident exploratory set | Stage 1 | calibration_run_SHA |
| G-pipe | Edge weight threshold | [PENDING: Stage 4] | AIOpsLab calibration subset | Stage 4 | calibration_run_SHA |
| G-pipe | PPR convergence epsilon | [PENDING: Stage 4] | AIOpsLab calibration subset | Stage 4 | calibration_run_SHA |
| L-pipe | Hallucination rate threshold | [PENDING: Stage 5] | Human annotation sample (n=30) | Stage 5 | annotation_SHA |
| Consensus | Borda weight distribution | [PENDING: Stage 6] | Calibration run on OTEL Demo set | Stage 6 | calibration_run_SHA |

**Warning:** Do not set threshold values before the corresponding pipeline stage is implemented and calibrated. Premature threshold setting is a construct validity threat (T3) — thresholds must be derived from data, not guessed.

---

`[PENDING: Stage 1 — D-pipe implementation required before any thresholds can be calibrated. First thresholds expected at Milestone 2.]`

---

*Last updated: 2026-05-15 — structure defined; no values yet (D-pipe not implemented)*
