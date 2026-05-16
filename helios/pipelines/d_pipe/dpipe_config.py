"""D-pipe typed constants — single source of truth for all calibration parameters."""

from __future__ import annotations

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

# Latency histogram bucket finite upper bounds in ms.
# Derived from: poetry run python - (Step 1 of Task 1). Do not edit by hand.
# 0.0 boundary omitted: schema artifact — zero rows with le=0.0 in capture data,
# no analytic signal. Positive-only boundaries are required for latency scoring.
LE_BOUNDARIES: list[float] = [
    5.0,
    10.0,
    25.0,
    50.0,
    75.0,
    100.0,
    250.0,
    500.0,
    750.0,
    1000.0,
    2500.0,
    5000.0,
    7500.0,
    10000.0,
]

K_INF_MIDPOINT: int = 3
INF_MIDPOINT: float = K_INF_MIDPOINT * 10000  # 30_000 ms representative cap

# Stage B error weight (calibrated; default before grid search)
W_ERROR_DEFAULT: float = 0.50

# Default thresholds (used before calibration)
RHO_THRESHOLD_DEFAULT: float = 0.4
TOPOLOGY_BOOST_DEFAULT: float = 1.4

# Joint calibration grid: 5 x 5 x 10 = 250 cells
W_ERROR_GRID: list[float] = [0.3, 0.50, 0.6, 0.7, 0.9]
RHO_THRESHOLD_GRID: list[float] = [0.2, 0.4, 0.6, 0.7, 0.8]
TOPOLOGY_BOOST_GRID: list[float] = [
    1.00,
    1.2,
    1.4,
    1.6,
    1.8,
    2.0,
    2.2,
    2.4,
    2.6,
    2.8,
]

# Exit gates (label-free)
PRUNER_EFFICACY_GATE: float = 0.50  # >= 50% node reduction required on calibration set
INTEGRITY_RATE_GATE: float = 0.85  # structural reachability lower bound

# Smoke ablation baseline
RANDOM_BASELINE_SEED: int = 0
