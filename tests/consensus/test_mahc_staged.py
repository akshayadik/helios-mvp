"""Staged timing and publication for routed runs; R-e (S3.1 design §5.5, §3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from helios.consensus.calibration import Calibrator, State
from helios.consensus.mahc import run_mahc, run_vote_only
from helios.consensus.params import MAHCParams
from helios.consensus.priors import fit_priors
from helios.consensus.timing import (
    CONVERGE_MS,
    schedule,
    staged_finish_times,
    staged_schedule,
)
from helios.schemas.verdict import PipelineName, PipelineVerdict, VerdictStatus
from helios.telemetry.signal_type import SignalType
from helios.vcl import VCLFlag, get_variant, set_current_manifest  # noqa: F401

if TYPE_CHECKING:
    from collections.abc import Iterator


def _verdict(p: PipelineName, ranked: list[str], sigma: float) -> PipelineVerdict:
    return PipelineVerdict(
        run_id="r",
        incident_id="i",
        variant_config_hash="h",
        snapshot_hash="s",
        pipeline=p,
        evaluation_phase="exploratory",
        status=VerdictStatus.RANKED,
        ranked_candidates=ranked,
        sigma=sigma,
        mu=1,
        latency_ms=1,
    )


D = _verdict(PipelineName.DPIPE, ["cart", "ad"], 0.2)
G = _verdict(PipelineName.GPIPE, ["cart", "email"], 0.3)
L = _verdict(PipelineName.LPIPE, ["ad", "cart"], 0.4)


def _confident() -> MAHCParams:
    # Every fusion scores 0.95 against a floor of 0.9: CONFIRMED whenever allowed.
    cal = Calibrator((0,) * 4, 0, (0,) * 4, (1,) * 4, ((-1e9, 0.95),))
    return MAHCParams(fit_priors([]), cal, 0.9, provisional=False)


@pytest.fixture(autouse=True)
def _full() -> Iterator[None]:
    set_current_manifest(get_variant("HELIOS-Full"))
    yield


# --- staged schedule ----------------------------------------------------------


def test_first_publication_at_the_end_of_the_cheap_stage() -> None:
    s = staged_schedule({"dpipe": 200, "gpipe": 900}, None)
    assert s.first_ms == 1_100  # G-pipe starts after the D-pipe
    assert s.first_pipelines == ("dpipe", "gpipe")
    assert s.terminal_ms == 1_100
    assert not s.non_converged


def test_terminal_after_the_lpipe_when_escalated() -> None:
    s = staged_schedule({"dpipe": 200, "gpipe": 900}, 15_000)
    assert s.first_ms == 1_100
    assert s.terminal_ms == 16_100


def test_escalation_past_the_bound_does_not_converge() -> None:
    s = staged_schedule({"dpipe": 200}, CONVERGE_MS)
    assert s.non_converged
    assert s.terminal_ms is None
    assert s.first_ms == 200


def test_staged_finish_times_put_the_lpipe_after_the_cheap_stage() -> None:
    assert staged_finish_times({"dpipe": 200, "gpipe": 900}, 15_000) == {
        "dpipe": 200,
        "gpipe": 1_100,
        "lpipe": 16_100,
    }
    assert staged_finish_times({"dpipe": 200}, None) == {"dpipe": 200}


def test_concurrent_schedule_unchanged() -> None:
    # Uniform runs keep S2.5's rule: first at the earlier of 30 s and all done.
    s = schedule({"dpipe": 200, "gpipe": 1_100, "lpipe": 15_000})
    assert s.first_ms == 15_000


# --- staged publication -------------------------------------------------------


def test_routed_stop_publishes_the_cheap_arm_early() -> None:
    finish = staged_finish_times({"dpipe": 200, "gpipe": 900}, None)
    fused = run_mahc(
        [D, G],
        SignalType.LATENCY,
        _confident(),
        latency_ms=finish,
        confirmatory=False,
        sched=staged_schedule({"dpipe": 200, "gpipe": 900}, None),
    )
    assert fused.schedule.first_ms == 1_100
    assert fused.ranked[0] == "cart"
    assert fused.state == State.CONFIRMED


def test_escalated_run_fuses_all_three_at_the_terminal() -> None:
    stage1 = {"dpipe": 200, "gpipe": 900}
    fused = run_mahc(
        [D, G, L],
        SignalType.LATENCY,
        _confident(),
        latency_ms=staged_finish_times(stage1, 15_000),
        confirmatory=False,
        sched=staged_schedule(stage1, 15_000),
    )
    assert fused.schedule.first_ms == 1_100
    assert fused.schedule.terminal_ms == 16_100
    assert set(fused.first_ranked) == {"cart", "ad", "email"}
    assert set(fused.evidence["contributing"]) == {"dpipe", "gpipe", "lpipe"}


def test_escalation_past_the_bound_publishes_non_converged() -> None:
    stage1 = {"dpipe": 200}
    fused = run_mahc(
        [D, L],
        SignalType.LATENCY,
        _confident(),
        latency_ms=staged_finish_times(stage1, CONVERGE_MS),
        confirmatory=False,
        sched=staged_schedule(stage1, CONVERGE_MS),
    )
    assert fused.state == State.NON_CONVERGED
    # The late L-pipe list is left out of the terminal fusion.
    assert fused.evidence["contributing"] == ["dpipe"]


# --- R-e ------------------------------------------------------------------------


def test_single_pipeline_is_provisional_under_mahc() -> None:
    fused = run_mahc(
        [D],
        SignalType.LATENCY,
        _confident(),
        latency_ms={"dpipe": 200},
        confirmatory=False,
        sched=staged_schedule({"dpipe": 200}, None),
    )
    assert fused.confidence is not None
    assert fused.state == State.PROVISIONAL


def test_single_pipeline_is_provisional_under_vote_only() -> None:
    fused = run_vote_only([D], latency_ms={"dpipe": 200})
    assert fused.state == State.PROVISIONAL


def test_two_pipelines_still_confirm_under_vote_only() -> None:
    fused = run_vote_only([D, G], latency_ms={"dpipe": 200, "gpipe": 1_100})
    assert fused.state == State.CONFIRMED
