"""Sanity checks for dpipe_config typed constants."""

from __future__ import annotations

from helios.pipelines.d_pipe.dpipe_config import (
    INF_MIDPOINT,
    K_INF_MIDPOINT,
    LE_BOUNDARIES,
    PRUNER_EFFICACY_GATE,
    RANDOM_BASELINE_SEED,
    RHO_THRESHOLD_DEFAULT,
    RHO_THRESHOLD_GRID,
    TOPOLOGY_BOOST_DEFAULT,
    TOPOLOGY_BOOST_GRID,
    W_ERROR_GRID,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance for test module


def test_le_boundaries_nonempty_sorted_positive() -> None:
    assert len(LE_BOUNDARIES) >= 14
    assert sorted(LE_BOUNDARIES) == LE_BOUNDARIES
    assert all(b > 0 for b in LE_BOUNDARIES)


def test_inf_midpoint_matches_k() -> None:
    assert INF_MIDPOINT == K_INF_MIDPOINT * 10000


def test_grids_nonempty() -> None:
    assert len(W_ERROR_GRID) == 5
    assert len(RHO_THRESHOLD_GRID) == 5
    assert len(TOPOLOGY_BOOST_GRID) == 10


def test_topology_boost_grid_all_ge_one() -> None:
    assert all(v >= 1 for v in TOPOLOGY_BOOST_GRID)


def test_pruner_efficacy_gate_in_open_interval() -> None:
    assert 0 < PRUNER_EFFICACY_GATE < 1


def test_random_baseline_seed_is_int() -> None:
    assert isinstance(RANDOM_BASELINE_SEED, int)


def test_rho_threshold_default_in_grid() -> None:
    assert RHO_THRESHOLD_DEFAULT in RHO_THRESHOLD_GRID


def test_topology_boost_default_in_grid() -> None:
    assert TOPOLOGY_BOOST_DEFAULT in TOPOLOGY_BOOST_GRID
