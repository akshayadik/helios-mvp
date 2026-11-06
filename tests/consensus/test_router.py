"""Router policy: G decision, escalation, feasibility (S3.1 design §5.1, §5.4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from helios.consensus.router import decide_escalation, decide_g, feasible
from helios.consensus.router_features import FEATURE_NAMES
from helios.consensus.router_params import (
    SELECTABLE,
    Arm,
    ArmModel,
    RouterParams,
    provisional_router_params,
)
from helios.vcl import (
    GatedComponentInactiveError,
    VCLFlag,  # noqa: F401
    get_variant,
    set_current_manifest,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

N = len(FEATURE_NAMES)
X = (1,) + (0,) * (N - 1)  # bias only: p equals the arm's theta[0]
FAST: dict[str, float] = {"dpipe": 200, "gpipe": 900, "lpipe": 15_000}


def _model(p: float) -> ArmModel:
    tiny = tuple(tuple(1e-6 if i == j else 0 for j in range(N)) for i in range(N))
    return ArmModel(a_inv=tiny, theta=(p,) + (0,) * (N - 1), n=60)


def _params(
    p: dict[Arm, float], *, tau: float | None = 0.8, medians: Mapping[str, float] = FAST
) -> RouterParams:
    return RouterParams(
        feature_names=FEATURE_NAMES,
        arms={a: _model(p[a]) for a in SELECTABLE},
        lam=1,
        alpha=1,
        tau_acc=tau,
        stage_median_ms=medians,
        price_book_digest="d" * 64,
        provisional=False,
    )


HIGH = {Arm.D: 0.9, Arm.D_G: 0.92, Arm.D_L: 0.93, Arm.FULL: 0.95}
D_LOW = {Arm.D: 0.6, Arm.D_G: 0.9, Arm.D_L: 0.9, Arm.FULL: 0.95}
ALL_LOW = {Arm.D: 0.6, Arm.D_G: 0.65, Arm.D_L: 0.7, Arm.FULL: 0.75}
CHEAP_LOW = {Arm.D: 0.6, Arm.D_G: 0.7, Arm.D_L: 0.9, Arm.FULL: 0.95}


@pytest.fixture(autouse=True)
def _full() -> Iterator[None]:
    set_current_manifest(get_variant("HELIOS-Full"))
    yield


# --- feasibility -------------------------------------------------------------


def test_feasible_needs_lower_bound_at_tau() -> None:
    ok = feasible(Arm.D, X, _params(HIGH))
    assert ok.feasible
    assert ok.p == pytest.approx(0.9)
    assert not feasible(Arm.D, X, _params(D_LOW)).feasible


def test_no_tau_means_nothing_is_feasible() -> None:
    assert not feasible(Arm.D, X, _params(HIGH, tau=None)).feasible


def test_latency_bound_excludes_slow_arms() -> None:
    slow: dict[str, float] = {"dpipe": 200, "gpipe": 900, "lpipe": 95_000}
    params = _params(HIGH, medians=slow)
    assert feasible(Arm.D_G, X, params).feasible
    assert not feasible(Arm.D_L, X, params).feasible
    assert not feasible(Arm.FULL, X, params).feasible


# --- G decision ---------------------------------------------------------------


def test_no_graph_never_runs_g() -> None:
    g = decide_g(X, _params(D_LOW), graph=False)
    assert not g.run_g
    assert g.reason == "no_graph"


def test_feasible_d_stops_before_g() -> None:
    g = decide_g(X, _params(HIGH), graph=True)
    assert not g.run_g
    assert g.reason == "d_feasible"


def test_infeasible_d_runs_g() -> None:
    g = decide_g(X, _params(D_LOW), graph=True)
    assert g.run_g
    assert g.reason == "d_infeasible"
    assert g.estimates["D"][0] == pytest.approx(0.6)


# --- escalation ---------------------------------------------------------------


def test_disagreement_escalates_even_when_confident() -> None:
    e = decide_escalation(
        X, _params(HIGH), g_ran=True, d_top="cart", g_top="ad", llm_on=True
    )
    assert e.escalate
    assert e.reason == "disagreement"
    assert e.stage1_arm == Arm.D_G
    assert e.terminal_arm == Arm.FULL


def test_agreeing_confident_cheap_arm_stops() -> None:
    e = decide_escalation(
        X, _params(D_LOW), g_ran=True, d_top="cart", g_top="cart", llm_on=True
    )
    assert not e.escalate
    assert e.reason == "none"
    assert e.stage1_arm == e.terminal_arm == Arm.D_G


def test_d_only_stop_when_d_is_feasible() -> None:
    e = decide_escalation(
        X, _params(HIGH), g_ran=False, d_top="cart", g_top=None, llm_on=True
    )
    assert not e.escalate
    assert e.terminal_arm == Arm.D


def test_low_confidence_escalates_to_d_plus_l_without_g() -> None:
    e = decide_escalation(
        X, _params(CHEAP_LOW), g_ran=False, d_top="cart", g_top=None, llm_on=True
    )
    assert e.escalate
    assert e.reason == "low_confidence"
    assert e.stage1_arm == Arm.D
    assert e.terminal_arm == Arm.D_L


def test_low_confidence_escalates_to_full_after_g() -> None:
    e = decide_escalation(
        X, _params(CHEAP_LOW), g_ran=True, d_top="cart", g_top="cart", llm_on=True
    )
    assert e.escalate
    assert e.reason == "low_confidence"
    assert e.terminal_arm == Arm.FULL


def test_no_feasible_arm_is_constraint_empty_and_runs_full() -> None:
    e = decide_escalation(
        X, _params(ALL_LOW), g_ran=True, d_top="cart", g_top="cart", llm_on=True
    )
    assert e.escalate
    assert e.reason == "constraint_empty"
    assert e.terminal_arm == Arm.FULL


def test_llm_off_never_escalates_and_says_why() -> None:
    e = decide_escalation(
        X, _params(CHEAP_LOW), g_ran=True, d_top="cart", g_top="ad", llm_on=False
    )
    assert not e.escalate
    assert e.reason == "llm_off"
    assert e.wanted == "disagreement"
    assert e.terminal_arm == Arm.D_G


def test_provisional_parameters_route_everything_to_full() -> None:
    params = provisional_router_params(stage_median_ms=FAST)
    assert decide_g(X, params, graph=True).run_g
    e = decide_escalation(
        X, params, g_ran=True, d_top="cart", g_top="cart", llm_on=True
    )
    assert e.escalate
    assert e.terminal_arm == Arm.FULL


def test_decisions_are_deterministic() -> None:
    params = _params(CHEAP_LOW)
    a = decide_escalation(
        X, params, g_ran=True, d_top="cart", g_top="cart", llm_on=True
    )
    b = decide_escalation(
        X, params, g_ran=True, d_top="cart", g_top="cart", llm_on=True
    )
    assert a == b


def test_router_is_gated_by_cbr_routing() -> None:
    set_current_manifest(get_variant("HELIOS-noRouter"))
    with pytest.raises(GatedComponentInactiveError):
        decide_g(X, _params(HIGH), graph=True)
    with pytest.raises(GatedComponentInactiveError):
        decide_escalation(
            X, _params(HIGH), g_ran=False, d_top="cart", g_top=None, llm_on=True
        )
