"""Stage B: anomaly scoring — wm90 winsorised mean + global cross-service normalisation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.stats.mstats

from helios.pipelines.d_pipe.dpipe_config import W_ERROR_DEFAULT
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def wm90(series: np.ndarray) -> float:
    valid = series[~np.isnan(series)]
    if len(valid) == 0:
        return float("nan")
    n = len(valid)
    # 2/n would exceed 1.0 for n < 3; clamp to keep winsorize's limit in [0, 1).
    upper_limit = min(2 / n, 1.0 - 1e-9)
    winsorized = scipy.stats.mstats.winsorize(valid, limits=[0, upper_limit])
    return float(np.mean(winsorized))


@dataclass
class AnomalyScorer:
    w_error: float = W_ERROR_DEFAULT

    def score(
        self,
        error_deltas: dict[str, list[float]],
        latency_means: dict[str, list[float]],
        p1_services: list[str],
    ) -> dict[str, float]:
        score_error_raw = {
            s: wm90(np.array([np.log1p(v) for v in error_deltas.get(s, [0.00])]))
            for s in p1_services
        }
        score_latency_raw = {
            s: wm90(np.array([np.log1p(v) for v in latency_means.get(s, [0.00])]))
            for s in p1_services
        }

        max_e = max(score_error_raw.values(), default=1)
        max_l = max(score_latency_raw.values(), default=1)
        norm_error = {
            s: min(score_error_raw[s] / (max_e + 1e-9), 1.00) for s in p1_services
        }
        norm_latency = {
            s: min(score_latency_raw[s] / (max_l + 1e-9), 1.00) for s in p1_services
        }

        return {
            s: self.w_error * norm_error[s] + (1 - self.w_error) * norm_latency[s]
            for s in p1_services
        }
