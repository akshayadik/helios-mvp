"""Router parameter file: arms, per-arm LinUCB models, load/write/hash (S3.1 §5.3)."""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING

import pytest

from helios.consensus.router_features import FEATURE_NAMES
from helios.consensus.router_params import (
    ARM_PIPELINES,
    ROUTER_PARAMS_PATH,
    SELECTABLE,
    Arm,
    ArmModel,
    RouterParams,
    load_router_params,
    provisional_router_params,
    router_params_hash,
    write_router_params,
)
from helios.vcl import VCLFlag  # noqa: F401

if TYPE_CHECKING:
    from pathlib import Path

N = len(FEATURE_NAMES)


def _identity(scale: float) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(scale if i == j else 0 for j in range(N)) for i in range(N))


def _params(**kw: object) -> RouterParams:
    model = ArmModel(a_inv=_identity(0.25), theta=(0.75,) + (0,) * (N - 1), n=40)
    base: dict[str, object] = {
        "feature_names": FEATURE_NAMES,
        "arms": dict.fromkeys(SELECTABLE, model),
        "lam": 1,
        "alpha": 0.2,
        "tau_acc": 0.6,
        "stage_median_ms": {"dpipe": 210, "gpipe": 860, "lpipe": 15_240},
        "price_book_digest": "d" * 64,
        "provisional": False,
    }
    base.update(kw)
    return RouterParams(**base)  # type: ignore[arg-type]


def test_arm_set_follows_ch3_and_r_c() -> None:
    assert [a.value for a in Arm] == ["D", "G", "L", "D+G", "D+L", "G+L", "Full"]
    assert SELECTABLE == (Arm.D, Arm.D_G, Arm.D_L, Arm.FULL)
    assert ARM_PIPELINES[Arm.FULL] == ("dpipe", "gpipe", "lpipe")
    assert ARM_PIPELINES[Arm.D_L] == ("dpipe", "lpipe")


def test_estimate_and_lower_bound() -> None:
    model = ArmModel(a_inv=_identity(0.25), theta=(0.75,) + (0,) * (N - 1), n=40)
    x = (1,) + (0,) * (N - 1)
    p, lcb = model.estimate(x, alpha=0.2)
    # p = theta . x; the bound subtracts alpha times sqrt(x' A^-1 x), a half here.
    assert p == pytest.approx(0.75)
    assert lcb == pytest.approx(0.65)


def test_estimate_is_rounded() -> None:
    model = ArmModel(a_inv=_identity(1 / 3), theta=(1 / 7,) + (0,) * (N - 1), n=1)
    p, lcb = model.estimate((1,) + (0,) * (N - 1), alpha=1 / 9)
    assert round(p, 6) == p
    assert round(lcb, 6) == lcb


def test_round_trip_and_hash_stable(tmp_path: Path) -> None:
    params = _params()
    path = tmp_path / "router.json"
    write_router_params(params, path)
    loaded = load_router_params(path)
    assert loaded == params
    assert router_params_hash(loaded) == router_params_hash(params)
    write_router_params(loaded, path)
    assert router_params_hash(load_router_params(path)) == router_params_hash(params)


def test_hash_changes_with_any_parameter() -> None:
    base = router_params_hash(_params())
    assert router_params_hash(_params(tau_acc=0.61)) != base
    assert router_params_hash(_params(alpha=0.3)) != base
    assert router_params_hash(_params(price_book_digest="e" * 64)) != base


def test_feature_name_mismatch_refused(tmp_path: Path) -> None:
    path = tmp_path / "router.json"
    write_router_params(_params(), path)
    raw = json.loads(path.read_text())
    raw["feature_names"] = list(reversed(raw["feature_names"]))
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="feature"):
        load_router_params(path)


def test_arm_set_mismatch_refused(tmp_path: Path) -> None:
    path = tmp_path / "router.json"
    write_router_params(_params(), path)
    raw = json.loads(path.read_text())
    raw["arms"]["G"] = raw["arms"]["D"]
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="arms"):
        load_router_params(path)


def test_model_shape_refused() -> None:
    with pytest.raises(ValueError, match="shape"):
        ArmModel(a_inv=_identity(1)[:-1], theta=(0,) * N, n=0)


def test_provisional_escalates_everything() -> None:
    params = provisional_router_params(stage_median_ms={"dpipe": 1, "lpipe": 2})
    assert params.provisional
    assert params.tau_acc is None
    for model in params.arms.values():
        p, lcb = model.estimate((1,) + (0,) * (N - 1), alpha=params.alpha)
        assert p == 0
        assert lcb < 0


def test_committed_file_loads() -> None:
    params = load_router_params(ROUTER_PARAMS_PATH)
    assert params.feature_names == FEATURE_NAMES
    assert set(params.arms) == set(SELECTABLE)
    assert math.isfinite(params.alpha)
