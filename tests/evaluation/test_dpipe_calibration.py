"""D-pipe recalibration on build data (S2.1 Task 13, row S2-M7-EVAL01)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from helios.evaluation.dpipe_calibration import (
    MAY_PARAMS,
    W_RESOURCE_GRID,
    change_from_may,
    dpipe_grid,
    select_dpipe,
)
from helios.pipelines.d_pipe.dpipe_config import (
    RHO_THRESHOLD_GRID,
    TOPOLOGY_BOOST_GRID,
    W_ERROR_GRID,
)
from helios.pipelines.d_pipe.params import DPipeParams, dpipe_params_hash
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def _p(w_error: float, w_resource: float, rho: float, boost: float) -> DPipeParams:
    return DPipeParams(w_error, w_resource, rho, boost, provisional=False)


def test_grid_crosses_the_config_grid_with_resource_weights_below_one() -> None:
    grid = dpipe_grid()
    assert W_RESOURCE_GRID == (0, 0.1, 0.2, 0.3)
    assert all(round(p.w_error + p.w_resource, 6) < 1 for p in grid)
    assert {p.w_error for p in grid} == set(W_ERROR_GRID)
    assert {p.rho_threshold for p in grid} == set(RHO_THRESHOLD_GRID)
    assert {p.topology_boost_factor for p in grid} == set(TOPOLOGY_BOOST_GRID)
    pairs = {
        (w, r) for w in W_ERROR_GRID for r in W_RESOURCE_GRID if round(w + r, 6) < 1
    }
    assert len(grid) == len(pairs) * len(RHO_THRESHOLD_GRID) * len(TOPOLOGY_BOOST_GRID)
    assert len(set(grid)) == len(grid)
    assert not any(p.provisional for p in grid)


def test_may_values_are_the_tie_anchor() -> None:
    assert (
        MAY_PARAMS.w_error,
        MAY_PARAMS.w_resource,
        MAY_PARAMS.rho_threshold,
        MAY_PARAMS.topology_boost_factor,
    ) == (0.3, 0.2, 0.2, 1)
    assert change_from_may(MAY_PARAMS) == 0
    assert change_from_may(_p(0.6, 0.1, 0.4, 1.2)) == pytest.approx(0.8)


def test_select_maximises_the_mean_of_per_corpus_hr3() -> None:
    a, b = _p(0.3, 0.2, 0.2, 1), _p(0.9, 0, 0.8, 2.8)
    hr3 = {
        a: {"rcaeval_build": 0.6, "otel_build_v3": 0.2},  # mean 0.4
        b: {"rcaeval_build": 0.3, "otel_build_v3": 0.7},  # mean wins
    }
    assert select_dpipe(hr3) == b


def test_select_ties_go_to_the_smallest_change_from_may() -> None:
    near, far = _p(0.3, 0.2, 0.2, 1.2), _p(0.9, 0, 0.8, 2.8)
    hr3 = {
        far: {"rcaeval_build": 0.6, "otel_build_v3": 0.4},
        near: {"rcaeval_build": 0.4, "otel_build_v3": 0.6},
    }
    assert select_dpipe(hr3) == near


def test_select_is_independent_of_result_order() -> None:
    x, y = _p(0.3, 0.1, 0.2, 1), _p(0.3, 0.3, 0.2, 1)  # same change from May
    scores = {"rcaeval_build": 0.6, "otel_build_v3": 0.6}
    assert select_dpipe({x: scores, y: scores}) == select_dpipe({y: scores, x: scores})


def test_params_hash_is_stable_and_covers_every_parameter() -> None:
    base = dpipe_params_hash(MAY_PARAMS)
    assert dpipe_params_hash(replace(MAY_PARAMS)) == base
    for changed in (
        replace(MAY_PARAMS, w_error=0.6),
        replace(MAY_PARAMS, w_resource=0.1),
        replace(MAY_PARAMS, rho_threshold=0.4),
        replace(MAY_PARAMS, topology_boost_factor=1.2),
        replace(MAY_PARAMS, provisional=True),
    ):
        assert dpipe_params_hash(changed) != base


def test_frozen_dpipe_params_are_the_calibration_selection() -> None:
    # S2-M7-EVAL01 (owner 2026-10-29): D-pipe calibration run 2 selected
    # (0.7, 0.1, 0.2, 1); the frozen file must match the committed report.
    import json
    from pathlib import Path

    from helios.pipelines.d_pipe.params import load_dpipe_params
    from helios.telemetry.trigger import detector_hash, load_detector_params

    report_path = Path(__file__).resolve().parents[2] / (
        "docs/sprints/s2-reasoning/s2_1_dpipe_calibration.json"
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    selected = report["selected"]
    params = load_dpipe_params()
    assert not params.provisional
    assert report["detector_hash"] == detector_hash(load_detector_params())
    assert (
        params.w_error,
        params.w_resource,
        params.rho_threshold,
        params.topology_boost_factor,
    ) == (
        selected["w_error"],
        selected["w_resource"],
        selected["rho_threshold"],
        selected["topology_boost_factor"],
    )
    assert dpipe_params_hash(params) == selected["dpipe_params_hash"]
