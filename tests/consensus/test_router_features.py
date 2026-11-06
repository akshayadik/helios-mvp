"""Router features: label-free, fixed order, defined for every input (S3.1 §5.2)."""

from __future__ import annotations

import inspect

import pytest

from helios.consensus import router_features as rf
from helios.consensus.router_features import FEATURE_NAMES, cheap_features, with_gpipe
from helios.schemas.verdict import PipelineName, PipelineVerdict, VerdictStatus
from helios.telemetry.signal_type import SignalType
from helios.vcl import VCLFlag  # noqa: F401


def _verdict(
    p: PipelineName,
    ranked: list[str],
    *,
    mu: float | None = 0.6,
    sigma: float | None = 0.2,
    status: VerdictStatus | None = None,
) -> PipelineVerdict:
    st = status or (VerdictStatus.RANKED if ranked else VerdictStatus.ABSTAINED)
    ok = st == VerdictStatus.RANKED
    return PipelineVerdict(
        run_id="r",
        incident_id="i",
        variant_config_hash="h",
        snapshot_hash="s",
        pipeline=p,
        evaluation_phase="exploratory",
        status=st,
        ranked_candidates=ranked if ok else [],
        mu=mu if ok else None,
        sigma=sigma if ok else None,
        latency_ms=1,
    )


D = _verdict(PipelineName.DPIPE, ["cart", "ad", "email", "currency"])
SCORES = {"cart": 0.8, "ad": 0.4, "email": 0.2, "currency": 0.1}


def _x(**kw: object) -> dict[str, float]:
    args: dict[str, object] = {
        "gate_value": 0.25,
        "signal": SignalType.LATENCY,
        "traces": True,
    }
    args.update(kw)
    return dict(zip(FEATURE_NAMES, cheap_features(D, SCORES, **args), strict=True))  # type: ignore[arg-type]


def test_fixed_length_and_bias_first() -> None:
    x = cheap_features(
        D, SCORES, gate_value=0.25, signal=SignalType.ERROR, traces=False
    )
    assert len(x) == len(FEATURE_NAMES)
    assert FEATURE_NAMES[0] == "bias"
    assert x[0] == 1


def test_d_block_values() -> None:
    x = _x()
    assert x["d_mu"] == pytest.approx(0.6)
    assert x["d_sigma"] == pytest.approx(0.2)
    assert x["d_top1_share"] == pytest.approx(0.8 / 1.5, abs=1e-6)
    assert x["d_margin"] == pytest.approx((0.8 - 0.4) / 0.8, abs=1e-6)
    assert x["gate_value"] == pytest.approx(0.25)
    assert x["signal_latency"] == 1
    assert x["signal_resource"] == 0
    assert x["signal_error"] == 0
    assert x["traces"] == 1


def test_unclassified_signal_sets_no_indicator() -> None:
    x = _x(signal=SignalType.UNCLASSIFIED)
    assert x["signal_resource"] == x["signal_latency"] == x["signal_error"] == 0


def test_sigma_none_counts_as_unknown() -> None:
    d = _verdict(PipelineName.DPIPE, ["cart"], mu=None, sigma=None)
    x = dict(
        zip(
            FEATURE_NAMES,
            cheap_features(
                d, {"cart": 0.3}, gate_value=None, signal=SignalType.ERROR, traces=False
            ),
            strict=True,
        )
    )
    assert x["d_sigma"] == 1
    assert x["d_mu"] == 0
    assert x["gate_value"] == 0
    # One candidate: the whole score and the full margin.
    assert x["d_top1_share"] == 1
    assert x["d_margin"] == 1


def test_failed_dpipe_gives_zero_block() -> None:
    d = _verdict(PipelineName.DPIPE, [], status=VerdictStatus.FAILED)
    x = dict(
        zip(
            FEATURE_NAMES,
            cheap_features(
                d, {}, gate_value=None, signal=SignalType.ERROR, traces=True
            ),
            strict=True,
        )
    )
    assert x["d_top1_share"] == x["d_margin"] == x["d_mu"] == 0
    assert x["d_sigma"] == 1


def test_out_of_scope_services_are_dropped() -> None:
    d = _verdict(PipelineName.DPIPE, ["prometheus", "cart", "ad"])
    scores = {"prometheus": 5, "cart": 0.8, "ad": 0.4}
    x = dict(
        zip(
            FEATURE_NAMES,
            cheap_features(
                d, scores, gate_value=0.25, signal=SignalType.ERROR, traces=True
            ),
            strict=True,
        )
    )
    assert x["d_top1_share"] == pytest.approx(0.8 / 1.2, abs=1e-6)


def test_g_block_zero_until_gpipe_ran() -> None:
    x = _x()
    assert x["g_ran"] == x["g_mu"] == x["dg_top1_agree"] == x["dg_top3_overlap"] == 0
    assert x["g_sigma"] == 1


def test_with_gpipe_fills_g_block() -> None:
    base = cheap_features(
        D, SCORES, gate_value=0.25, signal=SignalType.LATENCY, traces=True
    )
    g = _verdict(PipelineName.GPIPE, ["cart", "email", "frontend"], mu=0.7, sigma=0.3)
    x = dict(zip(FEATURE_NAMES, with_gpipe(base, g, D), strict=True))
    assert x["g_ran"] == 1
    assert x["g_mu"] == pytest.approx(0.7)
    assert x["g_sigma"] == pytest.approx(0.3)
    assert x["dg_top1_agree"] == 1
    # D top 3 {cart, ad, email}, G top 3 {cart, email, frontend}: two shared.
    assert x["dg_top3_overlap"] == pytest.approx(2 / 3, abs=1e-6)
    # The cheap block is unchanged.
    for name in ("d_mu", "d_sigma", "d_top1_share", "gate_value"):
        assert x[name] == dict(zip(FEATURE_NAMES, base, strict=True))[name]


@pytest.mark.parametrize("status", [VerdictStatus.SKIPPED, VerdictStatus.FAILED])
def test_with_gpipe_ignores_a_gpipe_without_a_list(status: VerdictStatus) -> None:
    base = cheap_features(
        D, SCORES, gate_value=0.25, signal=SignalType.LATENCY, traces=True
    )
    g = _verdict(PipelineName.GPIPE, [], status=status)
    assert with_gpipe(base, g, D) == base


def test_values_are_rounded_for_bitwise_reruns() -> None:
    scores = {"cart": 1 / 3, "ad": 1 / 7, "email": 1 / 11, "currency": 1 / 13}
    x = cheap_features(
        D, scores, gate_value=1 / 9, signal=SignalType.ERROR, traces=True
    )
    assert all(round(v, 6) == v for v in x)


def test_no_parameter_can_carry_a_label() -> None:
    banned = {"label", "root", "root_cause", "fault", "inject_time", "system", "truth"}
    for fn in (cheap_features, with_gpipe):
        params = set(inspect.signature(fn).parameters)
        assert not params & banned, fn.__name__
    assert not hasattr(rf, "ground_truth")
