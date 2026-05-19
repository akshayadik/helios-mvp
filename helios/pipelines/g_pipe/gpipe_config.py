"""G-pipe calibration constants — frozen after LOO-CV calibration rerun.

Do not change DISAGREEMENT_THRESHOLD after calibration without a deviation log entry.
"""

from __future__ import annotations

from helios.vcl import VCLFlag  # noqa: F401 — satisfies flag-guard

DISAGREEMENT_THRESHOLD: float = 0.20

GPIPE_PPR_ALPHA: float = 0.85

DISAGREEMENT_SWEEP: list[float] = [0.20, 0.25, 0.30, 0.35, 0.40]
