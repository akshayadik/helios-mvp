"""TDD for Stage C PropagationEngine."""

from __future__ import annotations

import pytest

from helios.pipelines.d_pipe.stages.c_propagation_engine import PropagationEngine
from helios.schemas.ueg_c import EdgeType, UEGCEdge
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def _call_edge(src: str, tgt: str, weight: float = 0.80) -> UEGCEdge:
    return UEGCEdge(source=src, target=tgt, edge_type=EdgeType.CALL, weight=weight)


def test_p1_to_p1_boost_applied_when_rho_above_threshold() -> None:
    # Perfectly correlated error series → rho=1 → boost applied
    series = list(range(1, 21))
    engine = PropagationEngine(rho_threshold=0.4, topology_boost_factor=1.2)
    scores = {"caller": 0.8, "callee": 0.2}
    error_deltas = {
        "caller": [float(x) for x in series],
        "callee": [float(x) for x in series],
    }
    result = engine.propagate(
        scores,
        error_deltas,
        [_call_edge("caller", "callee")],
        p1_services=["caller", "callee"],
    )
    assert result["callee"] > scores["callee"]


def test_p1_to_p1_no_boost_when_rho_below_threshold() -> None:
    corr_a = [float(i) for i in range(20)]
    anti_b = [float(20 - i) for i in range(20)]
    engine = PropagationEngine(rho_threshold=0.4, topology_boost_factor=1.2)
    scores = {"a": 0.8, "b": 0.2}
    error_deltas = {"a": corr_a, "b": anti_b}
    result = engine.propagate(
        scores, error_deltas, [_call_edge("a", "b")], p1_services=["a", "b"]
    )
    # anti-correlated → rho negative → no boost
    assert result.get("b", 0.00) == pytest.approx(scores["b"], abs=1e-6)


def test_p1_to_nonp1_uses_max_not_additive() -> None:
    engine = PropagationEngine(rho_threshold=0.4, topology_boost_factor=2.0)
    scores = {"caller1": 0.6, "caller2": 0.3, "leaf": 0.00}
    error_deltas: dict[str, list[float]] = {}
    edges = [_call_edge("caller1", "leaf"), _call_edge("caller2", "leaf")]
    result = engine.propagate(
        scores, error_deltas, edges, p1_services=["caller1", "caller2"]
    )
    # max(2.0*0.6, 2.0*0.3) = max(1.2, 0.6) = 1.2 → result["leaf"] = 0.00 + 1.2 = 1.2
    assert result["leaf"] == pytest.approx(2.0 * scores["caller1"])


def test_final_score_equals_base_plus_boost() -> None:
    engine = PropagationEngine(rho_threshold=0.4, topology_boost_factor=1.5)
    scores = {"p1": 0.8, "nonp1": 0.00}
    error_deltas: dict[str, list[float]] = {}
    result = engine.propagate(
        scores, error_deltas, [_call_edge("p1", "nonp1")], p1_services=["p1"]
    )
    expected_nonp1 = 0.00 + 1.5 * 0.8
    assert result["nonp1"] == pytest.approx(expected_nonp1)
    assert result["p1"] == pytest.approx(0.8)
