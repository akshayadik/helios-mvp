"""Router build fit: arm outcomes, ridge, folds, the R-d rule (S3.1 §5.3-5.4)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from helios.consensus.mahc import Vote
from helios.consensus.params import MAHCParams
from helios.consensus.priors import fit_priors
from helios.consensus.router_features import FEATURE_NAMES
from helios.consensus.router_params import SELECTABLE, Arm
from helios.evaluation.router_calibration import (
    RouterCase,
    arm_outcomes,
    choose_tau,
    cross_fit,
    evaluate,
    fit_all,
    fit_arm,
    folds,
    stage_medians,
    uniform_hit,
)
from helios.telemetry.signal_type import SignalType
from helios.vcl import VCLFlag, get_variant, set_current_manifest  # noqa: F401

if TYPE_CHECKING:
    from collections.abc import Iterator

N = len(FEATURE_NAMES)
MAHC = MAHCParams(fit_priors([]), None, None, provisional=False)
MEDIANS: dict[str, float] = {"dpipe": 200, "gpipe": 900, "lpipe": 15_000}
_IND = FEATURE_NAMES.index("d_margin")


@pytest.fixture(autouse=True)
def _full() -> Iterator[None]:
    set_current_manifest(get_variant("HELIOS-Full"))
    yield


def _x(ind: float) -> tuple[float, ...]:
    x: list[float] = [0] * N
    x[0] = 1
    x[_IND] = ind
    return tuple(x)


def _case(i: int, *, corpus: str, d_right: bool, ind: float) -> RouterCase:
    root = f"svc-{i % 5}"
    d = (root, "svc-x") if d_right else ("svc-x", "svc-y", "svc-z", "svc-w")
    return RouterCase(
        incident_id=f"incident{i:03d}",
        corpus=corpus,
        group=f"g{i % 3}",
        signal=SignalType.LATENCY,
        x_cheap=_x(ind),
        x_dg=None,
        graph=False,
        votes={"dpipe": Vote("dpipe", d, 0.3), "lpipe": Vote("lpipe", (root,), 0.3)},
        latency_ms={"dpipe": 200, "lpipe": 12_000},
        root=root,
    )


def _corpus(name: str, start: int, n: int, *, reliable: bool) -> list[RouterCase]:
    # ind = 1: D-pipe is right; ind = 0: D-pipe misses (unless every D is right).
    return [
        _case(start + i, corpus=name, d_right=reliable or i % 2 == 0, ind=1 - i % 2)
        for i in range(n)
    ]


def test_arm_outcomes_per_selectable_arm() -> None:
    case = _case(1, corpus="c", d_right=False, ind=0)
    out = arm_outcomes(case, MAHC)
    assert out[Arm.D] == 0
    assert out[Arm.D_L] == 1
    # G-pipe gave no list: arms with G are absent.
    assert Arm.D_G not in out
    assert Arm.FULL not in out
    assert uniform_hit(case, MAHC) == 1


def test_fit_arm_is_ridge() -> None:
    model = fit_arm([(_x(0), 1)] * 3, lam=1)
    # Bias only: theta = 3 / (1 + 3), A_inv[0][0] = 1 / 4.
    assert model.theta[0] == pytest.approx(0.75)
    assert model.a_inv[0][0] == pytest.approx(0.25)
    assert model.n == 3


def test_folds_are_corpus_and_group() -> None:
    cases = _corpus("a", 0, 6, reliable=True) + _corpus("b", 6, 6, reliable=True)
    got = folds(cases)
    assert sorted(i for f in got for i in f) == list(range(12))
    for f in got:
        assert len({(cases[i].corpus, cases[i].group) for i in f}) == 1


def test_cross_fit_never_trains_on_the_held_out_fold() -> None:
    cases = _corpus("a", 0, 12, reliable=True)
    outcomes = [arm_outcomes(c, MAHC) for c in cases]
    held = cross_fit(cases, outcomes, lam=1, alpha=0.2, medians=MEDIANS)
    for fold in folds(cases):
        params = held[fold[0]]
        # D arm: one row per training case.
        assert params.arms[Arm.D].n == len(cases) - len(fold)


def test_choose_tau_stops_only_where_dpipe_is_reliable() -> None:
    cases = _corpus("a", 0, 30, reliable=False) + _corpus("b", 30, 30, reliable=False)
    outcomes = [arm_outcomes(c, MAHC) for c in cases]
    held = cross_fit(cases, outcomes, lam=1, alpha=0.05, medians=MEDIANS)
    tau = choose_tau(cases, held, outcomes, MAHC)
    assert tau is not None
    report = evaluate(cases, held, outcomes, MAHC, tau)
    for entry in report["by_corpus"].values():
        assert entry["routed_hr3"] >= entry["uniform_hr3"] - 0.01
        # Half the cases have a reliable D-pipe and stop before the L-pipe.
        assert entry["terminal_arms"]["D"] > 0
        assert entry["lpipe_calls_saved"] == entry["terminal_arms"]["D"]


def test_choose_tau_none_when_no_stop_is_safe() -> None:
    # D-pipe always misses, L-pipe always hits: any stop costs a whole case.
    cases = [_case(i, corpus="a", d_right=False, ind=i % 2) for i in range(30)]
    outcomes = [arm_outcomes(c, MAHC) for c in cases]
    held = cross_fit(cases, outcomes, lam=1, alpha=0, medians=MEDIANS)
    assert choose_tau(cases, held, outcomes, MAHC) is None


def test_fit_all_is_frozen_and_complete() -> None:
    cases = _corpus("a", 0, 12, reliable=True)
    outcomes = [arm_outcomes(c, MAHC) for c in cases]
    params = fit_all(
        cases, outcomes, lam=1, alpha=0.2, tau=0.7, medians=MEDIANS, digest="d" * 64
    )
    assert not params.provisional
    assert set(params.arms) == set(SELECTABLE)
    assert params.tau_acc == 0.7
    assert params.arms[Arm.D].n == 12


def test_report_has_no_incident_ids() -> None:
    cases = _corpus("a", 0, 12, reliable=True)
    outcomes = [arm_outcomes(c, MAHC) for c in cases]
    held = cross_fit(cases, outcomes, lam=1, alpha=0.2, medians=MEDIANS)
    text = json.dumps(evaluate(cases, held, outcomes, MAHC, 0.3))
    assert "incident0" not in text
    assert "svc-" not in text


def test_stage_medians_take_the_larger_corpus_median() -> None:
    a = _corpus("a", 0, 3, reliable=True)
    b = [
        RouterCase(**{**c.__dict__, "corpus": "b", "latency_ms": {"dpipe": 600}})
        for c in _corpus("b", 3, 3, reliable=True)
    ]
    assert stage_medians(a + b) == {"dpipe": 600, "lpipe": 12_000}
