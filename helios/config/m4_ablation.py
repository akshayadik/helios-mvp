"""Frozen M4 ablation constants — single source of truth.

Any change to NUM_INCIDENTS, NUM_PIPELINES, or HR_AT_3_FLOOR requires
a deviation log entry (analytic consequence).
"""

from __future__ import annotations

from helios.vcl import (
    VCLFlag,  # noqa: F401 — flag-guard compliance
    get_all_variants,
)

HELIOS_ENABLE_M4_ABLATION: bool = True

NUM_INCIDENTS: int = 20
NUM_PIPELINES: int = 3
NUM_VARIANTS: int = len(get_all_variants())
EXPECTED_PIPELINE_ROW_COUNT: int = NUM_INCIDENTS * NUM_VARIANTS * NUM_PIPELINES
HR_AT_3_FLOOR: float = 0.05
# Minimum paired-incident count for exact Wilcoxon; pairs below this floor are
# skipped and reported as insufficient_sample rather than zero_variance.
MIN_WILCOXON_PAIRS: int = 10
