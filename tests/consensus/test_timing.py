"""Replayed concurrency for PROVISIONAL, CONFIRMED and non-convergence (S2.5 §5.5)."""

from __future__ import annotations

from helios.consensus.timing import CONVERGE_MS, PROVISIONAL_MS, Schedule, schedule
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def test_constants() -> None:
    assert (PROVISIONAL_MS, CONVERGE_MS) == (30_000, 90_000)


def test_all_done_before_30s() -> None:
    s = schedule({"dpipe": 120, "gpipe": 900, "lpipe": 15_400})
    assert s == Schedule(15_400, ("dpipe", "gpipe", "lpipe"), 15_400, False)


def test_slow_lpipe_after_30s() -> None:
    s = schedule({"dpipe": 120, "gpipe": 900, "lpipe": 45_000})
    assert s == Schedule(30_000, ("dpipe", "gpipe"), 45_000, False)


def test_non_convergence_after_90s() -> None:
    s = schedule({"dpipe": 120, "lpipe": 95_000})
    assert s == Schedule(30_000, ("dpipe",), None, True)


def test_no_pipelines() -> None:
    assert schedule({}) == Schedule(0, (), 0, False)


def test_gpipe_finishes_after_dpipe() -> None:
    # Review I4: G-pipe is dispatched only after D-pipe's routing gate.
    from helios.consensus.timing import finish_times

    assert finish_times({"dpipe": 400, "gpipe": 900, "lpipe": 15_000}) == {
        "dpipe": 400,
        "gpipe": 1300,
        "lpipe": 15_000,
    }
    assert finish_times({"dpipe": 400, "lpipe": 15_000}) == {
        "dpipe": 400,
        "lpipe": 15_000,
    }
