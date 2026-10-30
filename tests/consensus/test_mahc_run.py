"""MAHC and vote-only entry points, frozen parameters (S2.5 §5.4-5.7)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from helios.consensus.calibration import Calibrator, State
from helios.consensus.mahc import ProvisionalParamsError, run_mahc, run_vote_only
from helios.consensus.params import (
    MAHCParams,
    load_mahc_params,
    mahc_params_hash,
    write_mahc_params,
)
from helios.consensus.priors import fit_priors
from helios.schemas.verdict import PipelineName, PipelineVerdict, VerdictStatus
from helios.telemetry.signal_type import SignalType
from helios.vcl import (
    GatedComponentInactiveError,
    VCLFlag,  # noqa: F401
    get_variant,
    set_current_manifest,
)

if TYPE_CHECKING:
    from pathlib import Path

RES = SignalType.RESOURCE


def _verdict(
    p: PipelineName, ranked: list[str], sigma: float | None
) -> PipelineVerdict:
    status = VerdictStatus.RANKED if ranked else VerdictStatus.ABSTAINED
    return PipelineVerdict(
        run_id="r",
        incident_id="i",
        variant_config_hash="h",
        snapshot_hash="s",
        pipeline=p,
        evaluation_phase="exploratory",
        status=status,
        ranked_candidates=ranked,
        sigma=sigma if ranked else None,
        mu=1 if ranked else None,
        latency_ms=1,
    )


D = _verdict(PipelineName.DPIPE, ["cart", "ad"], 0.2)
G = _verdict(PipelineName.GPIPE, ["ad", "cart"], 0.3)
L = _verdict(PipelineName.LPIPE, ["cart"], 0.4)
FAST = {"dpipe": 100, "gpipe": 200, "lpipe": 9_000}
PROVISIONAL = MAHCParams(fit_priors([]), None, None, provisional=True)


def _calibrated(value: float, floor: float) -> MAHCParams:
    cal = Calibrator((0,) * 4, 0, (0,) * 4, (1,) * 4, ((-1e9, value),))
    return MAHCParams(fit_priors([]), cal, floor, provisional=False)


@pytest.fixture(autouse=True)
def _full() -> None:
    set_current_manifest(get_variant("HELIOS-Full"))


def test_provisional_params_refused_in_confirmatory() -> None:
    with pytest.raises(ProvisionalParamsError):
        run_mahc([D], RES, PROVISIONAL, latency_ms=FAST, confirmatory=True)


def test_provisional_params_have_neutral_priors_and_no_floor() -> None:
    p = PROVISIONAL
    assert p.provisional and p.calibrator is None and p.floor is None
    assert p.priors.lookup("dpipe", RES) == (1, "global")


def test_params_round_trip(tmp_path: Path) -> None:
    p = _calibrated(0.9, 0.8)
    write_mahc_params(p, tmp_path / "p.json")
    q = load_mahc_params(tmp_path / "p.json")
    assert q == p and mahc_params_hash(q) == mahc_params_hash(p)


def test_no_votes_gives_empty_provisional() -> None:
    empty = _verdict(PipelineName.DPIPE, [], None)
    out = run_mahc(
        [empty], RES, _calibrated(0.9, 0.8), latency_ms={"dpipe": 5}, confirmatory=False
    )
    assert (
        out.ranked == () and out.state == State.PROVISIONAL and out.confidence is None
    )


def test_state_uses_calibrator_and_floor() -> None:
    ok = run_mahc(
        [D, G, L], RES, _calibrated(0.9, 0.8), latency_ms=FAST, confirmatory=False
    )
    assert ok.state == State.CONFIRMED and ok.confidence == 0.9
    low = run_mahc(
        [D, G, L], RES, _calibrated(0.9, 0.95), latency_ms=FAST, confirmatory=False
    )
    assert low.state == State.PROVISIONAL
    assert ok.ranked[0] == "cart"
    assert ok.evidence["disagreeing"] == ["gpipe"]
    assert ok.evidence["priors"]["dpipe"] == [1, "global"]


def test_first_publication_fuses_only_early_pipelines() -> None:
    slow = {"dpipe": 100, "gpipe": 200, "lpipe": 45_000}
    out = run_mahc(
        [D, G, L], RES, _calibrated(0.9, 0.8), latency_ms=slow, confirmatory=False
    )
    assert out.schedule.first_pipelines == ("dpipe", "gpipe")
    assert set(out.first_ranked) == {"cart", "ad"}
    assert out.state == State.CONFIRMED


def test_non_convergence_drops_the_late_pipeline() -> None:
    late = {"dpipe": 100, "gpipe": 200, "lpipe": 95_000}
    out = run_mahc(
        [D, G, L], RES, _calibrated(0.9, 0.8), latency_ms=late, confirmatory=False
    )
    assert out.state == State.NON_CONVERGED
    assert out.evidence["contributing"] == ["dpipe", "gpipe"]


def test_vote_only_confirmed_unless_non_converged_or_empty() -> None:
    assert run_vote_only([D, G, L], latency_ms=FAST).state == State.CONFIRMED
    late = {"dpipe": 100, "lpipe": 95_000}
    assert run_vote_only([D, L], latency_ms=late).state == State.NON_CONVERGED
    empty = _verdict(PipelineName.DPIPE, [], None)
    assert run_vote_only([empty], latency_ms={"dpipe": 5}).state == State.PROVISIONAL


def test_gated_off_raises_inactive() -> None:
    set_current_manifest(get_variant("HELIOS-noConsensus"))
    with pytest.raises(GatedComponentInactiveError):
        run_mahc([D], RES, PROVISIONAL, latency_ms=FAST, confirmatory=False)
