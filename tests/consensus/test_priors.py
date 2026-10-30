"""Hierarchical priors: signal type, backing off to global (S2.5 §5.2, M-a)."""

from __future__ import annotations

import pytest

from helios.consensus.priors import MIN_CASES, PRIOR_STRENGTH, PriorCase, fit_priors
from helios.telemetry.signal_type import SignalType
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

RES, LAT = SignalType.RESOURCE, SignalType.LATENCY


def _cases(signal: SignalType, pipeline: str, hits: int, n: int) -> list[PriorCase]:
    return [PriorCase(signal, {pipeline: 1 if i < hits else 0}) for i in range(n)]


def test_constants() -> None:
    assert (PRIOR_STRENGTH, MIN_CASES) == (10, 30)


def test_global_is_mean_of_given_lists() -> None:
    cases = [*_cases(RES, "dpipe", 3, 4), PriorCase(LAT, {"dpipe": None})]
    assert fit_priors(cases).global_["dpipe"] == pytest.approx(3 / 4)


def test_signal_prior_smoothed_exact() -> None:
    # 40 resource cases with 30 hits; 60 latency cases with 30 hits -> global 0.6
    table = fit_priors(_cases(RES, "dpipe", 30, 40) + _cases(LAT, "dpipe", 30, 60))
    assert table.global_["dpipe"] == pytest.approx(0.6)
    value, level = table.lookup("dpipe", RES)
    assert level == "signal"
    assert value == pytest.approx((30 + 6) / 50)


def test_backs_off_below_30() -> None:
    table = fit_priors(_cases(RES, "dpipe", 20, 29) + _cases(LAT, "dpipe", 30, 60))
    value, level = table.lookup("dpipe", RES)
    assert level == "global" and value == pytest.approx(table.global_["dpipe"])
    assert table.counts[RES.value]["dpipe"] == 29


def test_missing_lists_excluded_from_counts() -> None:
    cases = [*_cases(RES, "gpipe", 31, 31), *[PriorCase(RES, {"gpipe": None})] * 5]
    assert fit_priors(cases).counts[RES.value]["gpipe"] == 31


def test_unseen_pipeline_prior_one() -> None:
    table = fit_priors(_cases(RES, "dpipe", 1, 2))
    assert table.lookup("lpipe", RES) == (1, "global")
    assert fit_priors([PriorCase(RES, {"lpipe": None})]).lookup("lpipe", RES) == (
        1,
        "global",
    )
