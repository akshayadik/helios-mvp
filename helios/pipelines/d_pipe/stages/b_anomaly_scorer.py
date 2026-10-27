"""Stage B: anomaly scoring — wm90 winsorised mean + global cross-service normalisation.

With the shared trigger (S2.1), ``score_split`` scores each channel's shift
after the trigger against the part before it (robust scale shared with the
trigger), keeps each service's largest raw shift as evidence for sigma, and
adds a resource channel. ``score`` is the whole-window form, used without a
trigger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import scipy.stats.mstats

from helios.pipelines.d_pipe.dpipe_config import W_ERROR_DEFAULT
from helios.telemetry.scope import in_scope
from helios.telemetry.trigger import robust_scale
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from helios.pipelines.d_pipe.stages.a_metrics_parser import ParsedMetrics

_NORM_EPS = 1e-9


def wm90(series: np.ndarray) -> float:
    valid = series[~np.isnan(series)]
    if len(valid) == 0:
        return float("nan")
    n = len(valid)
    # 2/n would exceed 1.0 for n < 3; clamp to keep winsorize's limit in [0, 1).
    upper_limit = min(2 / n, 1.0 - 1e-9)
    winsorized = scipy.stats.mstats.winsorize(valid, limits=[0, upper_limit])
    return float(np.mean(winsorized))


@dataclass(frozen=True)
class ScoredServices:
    """Normalised scores, and each service's largest raw shift (robust-z units)."""

    scores: dict[str, float]
    evidence: dict[str, float] = field(default_factory=dict)


def _shift(series: list[float], before: np.ndarray, *, count_series: bool) -> float:
    """Robust shift of the part after the split over the part before it (>= 0)."""
    values = np.asarray(series, dtype="float64")
    ref = values[before][np.isfinite(values[before])]
    inc = values[~before][np.isfinite(values[~before])]
    if ref.size < 2 or inc.size == 0:
        return 0
    scale = robust_scale(ref, count_series=count_series)
    if scale <= 0:
        return 0
    return max(0, (wm90(inc) - float(np.median(ref))) / scale)


def _normalised(raw: dict[str, float]) -> dict[str, float]:
    """Divide by the largest in-scope value: out-of-scope services (D-f) keep
    their raw shift as evidence but never set the scale for the others."""
    top = max((v for s, v in raw.items() if in_scope(s)), default=0)
    return {s: min(v / (top + _NORM_EPS), 1) for s, v in raw.items()}


@dataclass
class AnomalyScorer:
    w_error: float = W_ERROR_DEFAULT
    w_resource: float = 0

    def score_split(self, parsed: ParsedMetrics, *, split_s: float) -> ScoredServices:
        """Scores from the shift after ``split_s`` (the trigger) per channel."""
        before = np.asarray(parsed.steps, dtype="float64") < split_s
        err, lat, res = {}, {}, {}
        for s in parsed.p1_services:
            err[s] = (
                _shift(parsed.error_deltas[s], before, count_series=True)
                if s in parsed.error_deltas
                else 0
            )
            lat[s] = (
                _shift(parsed.latency_means[s], before, count_series=False)
                if s in parsed.latency_means
                else 0
            )
            res[s] = max(
                (
                    _shift(v, before, count_series=False)
                    for _m, v in sorted(parsed.resource_values.get(s, {}).items())
                ),
                default=0,
            )
        n_err, n_lat, n_res = _normalised(err), _normalised(lat), _normalised(res)
        w_lat = 1 - self.w_error - self.w_resource
        scores = {
            s: self.w_error * n_err[s] + self.w_resource * n_res[s] + w_lat * n_lat[s]
            for s in parsed.p1_services
        }
        evidence = {s: max(err[s], lat[s], res[s]) for s in parsed.p1_services}
        return ScoredServices(scores=scores, evidence=evidence)

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
