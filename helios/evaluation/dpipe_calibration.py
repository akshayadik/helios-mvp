"""D-pipe recalibration on build data (S2.1 Task 13, row S2-M7-EVAL01).

Build labels only; the confirmatory pool is refused. Fixed before the run:

- Grid: the ``dpipe_config`` grid for ``w_error``, ``rho_threshold`` and
  ``topology_boost_factor``, crossed with ``W_RESOURCE_GRID``, keeping
  ``w_error + w_resource < 1``.
- Trigger: the frozen detector (``data/frozen/trigger_detector.json``), never
  the injection time.
- Objective: the mean of the per-corpus HR@3 (RCAEval build, OTel build).
  Ties go to the smallest summed absolute change from the May values
  (``MAY_PARAMS``), then to the lexicographically smallest parameters, so the
  result never depends on the order the grid was evaluated in.
"""

from __future__ import annotations

import statistics
from itertools import product
from typing import TYPE_CHECKING

from helios.pipelines.d_pipe.dpipe_config import (
    RHO_THRESHOLD_GRID,
    TOPOLOGY_BOOST_GRID,
    W_ERROR_GRID,
)
from helios.pipelines.d_pipe.params import DPipeParams
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "MAY_PARAMS",
    "W_RESOURCE_GRID",
    "change_from_may",
    "dpipe_grid",
    "select_dpipe",
]

W_RESOURCE_GRID: tuple[float, ...] = (0, 0.1, 0.2, 0.3)
# The May values (w_error, rho, boost) and the provisional resource weight.
MAY_PARAMS = DPipeParams(
    w_error=0.3,
    w_resource=0.2,
    rho_threshold=0.2,
    topology_boost_factor=1,
    provisional=False,
)
_DIGITS = 6


def dpipe_grid() -> list[DPipeParams]:
    """Every candidate setting, in a fixed order."""
    return [
        DPipeParams(
            w_error=w_error,
            w_resource=w_resource,
            rho_threshold=rho,
            topology_boost_factor=boost,
            provisional=False,
        )
        for w_error, w_resource, rho, boost in product(
            W_ERROR_GRID, W_RESOURCE_GRID, RHO_THRESHOLD_GRID, TOPOLOGY_BOOST_GRID
        )
        if round(w_error + w_resource, _DIGITS) < 1
    ]


def change_from_may(params: DPipeParams) -> float:
    """Summed absolute change of the four parameters from ``MAY_PARAMS``."""
    return round(
        abs(params.w_error - MAY_PARAMS.w_error)
        + abs(params.w_resource - MAY_PARAMS.w_resource)
        + abs(params.rho_threshold - MAY_PARAMS.rho_threshold)
        + abs(params.topology_boost_factor - MAY_PARAMS.topology_boost_factor),
        _DIGITS,
    )


def select_dpipe(hr3: Mapping[DPipeParams, Mapping[str, float]]) -> DPipeParams:
    """The best mean per-corpus HR@3; ties as in the module docstring."""
    if not hr3:
        raise ValueError("no calibration results")

    def key(params: DPipeParams) -> tuple[float, float, tuple[float, ...]]:
        mean = round(statistics.mean(hr3[params].values()), _DIGITS)
        return (
            -mean,
            change_from_may(params),
            (
                params.w_error,
                params.w_resource,
                params.rho_threshold,
                params.topology_boost_factor,
            ),
        )

    return min(hr3, key=key)
