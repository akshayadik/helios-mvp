"""OTel fix B (entry 76): the memory-trend channel and its parameter."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np
import pytest

from helios.pipelines.d_pipe.params import (
    DPipeParams,
    dpipe_params_hash,
    load_dpipe_params,
)
from helios.pipelines.d_pipe.stages.a_metrics_parser import ParsedMetrics
from helios.pipelines.d_pipe.stages.b_anomaly_scorer import (
    AnomalyScorer,
    memory_trend,
    theil_sen,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path

_N = 24  # 12 steps before the split, 12 after
_BEFORE = np.arange(_N) < _N // 2
_MEM = "container_memory_usage_total_bytes"
_W_MEMORY = 0.4


def _noise(level: float) -> list[float]:
    return [level + (7 * t % 5) for t in range(_N)]


def _leak(level: float, per_step: float) -> list[float]:
    base = _noise(level)
    return base[: _N // 2] + [
        v + per_step * (k + 1) for k, v in enumerate(base[_N // 2 :])
    ]


def _spike(level: float, height: float) -> list[float]:
    base = _noise(level)
    base[_N // 2 + 3] += height
    return base


def test_theil_sen_is_the_slope_of_a_line() -> None:
    assert theil_sen(np.array([3, 5, 7, 9, 11])) == 2


def test_a_leak_scores_and_a_spike_does_not() -> None:
    # Level 100: the scale floor is 5% of it over a 6-step run, about 0.83.
    leak = memory_trend(_leak(100, 6), _BEFORE)
    spike = memory_trend(_spike(100, 400), _BEFORE)
    assert leak > 3
    assert spike < 1


def test_a_falling_series_scores_zero() -> None:
    assert memory_trend(_leak(100, -6), _BEFORE) == 0


def test_too_few_points_score_zero() -> None:
    before = np.arange(8) < 4  # 4 before: run = 2 < 3
    series: list[float] = [1, 2, 3, 4, 9, 19, 29, 39]
    assert memory_trend(series, before) == 0


def test_a_flat_history_uses_the_level_floor() -> None:
    flat = [float(1000 + 10 * max(k - _N // 2 + 1, 0)) for k in range(_N)]
    # floor = 5% of 1000 over a 6-step run, about 8.3 per step; slope 10.
    assert memory_trend(flat, _BEFORE) == pytest.approx(10 / (50 / 6))


def _parsed() -> ParsedMetrics:
    steps = [float(t) for t in range(_N)]
    flat = [10.0] * _N
    return ParsedMetrics(
        error_deltas={},
        latency_means={"email": flat, "quote": flat},
        steps=steps,
        p1_services=["email", "quote"],
        resource_values={
            # email leaks; quote's memory is noise and its CPU spikes once.
            "email": {
                _MEM: _leak(5e8, 2e7),
                "container_cpu_utilization_ratio": _noise(2),
            },
            "quote": {
                _MEM: _noise(5e8),
                "container_cpu_utilization_ratio": _spike(2, 60),
            },
        },
    )


def test_without_w_memory_memory_stays_in_the_resource_channel() -> None:
    scored = AnomalyScorer(w_error=0, w_resource=1).score_split(_parsed(), split_s=12)
    assert "memory" not in scored.channels["email"]
    assert scored.channels["email"]["resource"] > 3  # the memory level shift


def test_with_w_memory_the_leak_outranks_the_cpu_spike() -> None:
    scorer = AnomalyScorer(w_error=0, w_resource=0.1, w_memory=_W_MEMORY)
    scored = scorer.score_split(_parsed(), split_s=12)
    assert scored.channels["email"]["memory"] > 3
    assert scored.channels["quote"]["memory"] < 1
    assert scored.scores["email"] > scored.scores["quote"]
    assert scored.levels["email"]["memory"]["unit"] == _MEM


def test_with_w_memory_the_resource_channel_drops_memory() -> None:
    only_memory = replace(_parsed(), resource_values={"email": {_MEM: _leak(5e8, 2e7)}})
    scored = AnomalyScorer(w_error=0, w_resource=0.1, w_memory=0).score_split(
        only_memory, split_s=12
    )
    assert scored.channels["email"]["resource"] == 0


def _params_file(tmp_path: Path, **extra: object) -> Path:
    body = {
        "w_error": 0.7,
        "w_resource": 0.1,
        "rho_threshold": 0.2,
        "topology_boost_factor": 1,
        "provisional": False,
        **extra,
    }
    path = tmp_path / "d.json"
    path.write_text(json.dumps(body))
    return path


def test_the_frozen_file_has_no_memory_weight_and_keeps_its_hash() -> None:
    params = load_dpipe_params()
    assert params.w_memory is None
    assert "w_memory" not in params.as_dict()


def test_w_memory_loads_and_changes_the_hash(tmp_path: Path) -> None:
    old = load_dpipe_params(_params_file(tmp_path))
    new = load_dpipe_params(_params_file(tmp_path, w_memory=0.1))
    assert new.w_memory == pytest.approx(0.1)
    assert dpipe_params_hash(new) != dpipe_params_hash(old)
    assert dpipe_params_hash(replace(new, w_memory=0)) != dpipe_params_hash(old)


def test_weights_over_one_are_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="w_memory"):
        load_dpipe_params(_params_file(tmp_path, w_memory=0.3))


def test_unknown_keys_are_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="keys"):
        load_dpipe_params(_params_file(tmp_path, w_cpu=0.1))


def test_dataclass_default_is_the_legacy_channel() -> None:
    assert DPipeParams(0.7, 0.1, 0.2, 1, provisional=False).w_memory is None


def test_the_legacy_channel_never_computes_the_trend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The trend is the costliest statistic; frozen chains without w_memory
    # must not pay for it (it would also move D-pipe's measured latency).
    from helios.pipelines.d_pipe.stages import b_anomaly_scorer

    def boom(*_: object) -> float:
        raise AssertionError("memory_trend called without w_memory")

    monkeypatch.setattr(b_anomaly_scorer, "memory_trend", boom)
    AnomalyScorer(w_error=0, w_resource=1).score_split(_parsed(), split_s=12)
