"""Frozen router parameters (S3.1 design §5.3, §5.6).

Ch3 Algorithm 1 keeps LinUCB parameters (A_a, b_a) per arm. This file keeps,
per selectable arm, A_a⁻¹ and θ_a = A_a⁻¹ b_a (computed once at the freeze, so
every run uses the same numbers), plus the ridge λ, the bound coefficient alpha,
τ_acc, the build-median latency of each pipeline (for τ_lat) and the price
book's digest. The hash of the whole file is checked at run start.

Arms (R-c): the seven Ch3 arms are recorded; only D, D+G, D+L and Full are
selectable, because D-pipe runs first in every routed run and G-pipe takes the
D-pipe's scores as its seeds.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from helios.consensus.router_features import FEATURE_NAMES
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.utils import canonical_json

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "ARM_PIPELINES",
    "ROUTER_PARAMS_PATH",
    "SELECTABLE",
    "Arm",
    "ArmModel",
    "RouterParams",
    "load_router_params",
    "provisional_router_params",
    "router_params_hash",
    "write_router_params",
]

HELIOS_ENABLE_ROUTER_PARAMS: bool = True

ROUTER_PARAMS_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "frozen" / "router_params.json"
)
_DIGITS = 6
_KEYS = frozenset(
    {
        "feature_names",
        "arms",
        "lam",
        "alpha",
        "tau_acc",
        "stage_median_ms",
        "price_book_digest",
        "provisional",
    }
)


class Arm(StrEnum):
    """Ch3 Algorithm 1's action set."""

    D = "D"
    G = "G"
    L = "L"
    D_G = "D+G"
    D_L = "D+L"
    G_L = "G+L"
    FULL = "Full"


ARM_PIPELINES: dict[Arm, tuple[str, ...]] = {
    Arm.D: ("dpipe",),
    Arm.G: ("gpipe",),
    Arm.L: ("lpipe",),
    Arm.D_G: ("dpipe", "gpipe"),
    Arm.D_L: ("dpipe", "lpipe"),
    Arm.G_L: ("gpipe", "lpipe"),
    Arm.FULL: ("dpipe", "gpipe", "lpipe"),
}

#: Selectable arms in their fixed cost order (design §5.4).
SELECTABLE: tuple[Arm, ...] = (Arm.D, Arm.D_G, Arm.D_L, Arm.FULL)


@dataclass(frozen=True)
class ArmModel:
    """One arm's frozen ridge model: A⁻¹, θ and the number of fitted cases."""

    a_inv: tuple[tuple[float, ...], ...]
    theta: tuple[float, ...]
    n: int

    def __post_init__(self) -> None:
        d = len(self.theta)
        if len(self.a_inv) != d or any(len(row) != d for row in self.a_inv):
            raise ValueError(f"A_inv shape must be {d}x{d} to match theta")

    def estimate(self, x: Sequence[float], *, alpha: float) -> tuple[float, float]:
        """(p, lower bound) = (theta.x, theta.x - alpha * sqrt(x A_inv x)), rounded."""
        if len(x) != len(self.theta):
            raise ValueError("feature vector length does not match the model")
        p = sum(t * v for t, v in zip(self.theta, x, strict=True))
        quad = sum(
            x[i] * sum(row[j] * x[j] for j in range(len(x)))
            for i, row in enumerate(self.a_inv)
        )
        lcb = p - alpha * math.sqrt(max(quad, 0))
        return round(p, _DIGITS), round(lcb, _DIGITS)


@dataclass(frozen=True)
class RouterParams:
    """Everything the router needs beyond the incident's features."""

    feature_names: tuple[str, ...]
    arms: Mapping[Arm, ArmModel]
    lam: float
    alpha: float
    tau_acc: float | None
    stage_median_ms: Mapping[str, float]
    price_book_digest: str
    provisional: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "feature_names": list(self.feature_names),
            "arms": {
                a.value: {
                    "a_inv": [[float(v) for v in row] for row in m.a_inv],
                    "theta": [float(v) for v in m.theta],
                    "n": int(m.n),
                }
                for a, m in sorted(self.arms.items(), key=lambda kv: kv[0].value)
            },
            "lam": float(self.lam),
            "alpha": float(self.alpha),
            "tau_acc": None if self.tau_acc is None else float(self.tau_acc),
            "stage_median_ms": {
                k: float(v) for k, v in sorted(self.stage_median_ms.items())
            },
            "price_book_digest": self.price_book_digest,
            "provisional": self.provisional,
        }


def _from_dict(raw: dict[str, Any]) -> RouterParams:
    if set(raw) != _KEYS:
        raise ValueError(f"router parameter keys must be {sorted(_KEYS)}")
    names = tuple(str(n) for n in raw["feature_names"])
    if names != FEATURE_NAMES:
        raise ValueError("router feature names do not match FEATURE_NAMES")
    if set(raw["arms"]) != {a.value for a in SELECTABLE}:
        raise ValueError(f"router arms must be {[a.value for a in SELECTABLE]}")
    arms = {
        Arm(name): ArmModel(
            a_inv=tuple(tuple(float(v) for v in row) for row in m["a_inv"]),
            theta=tuple(float(v) for v in m["theta"]),
            n=int(m["n"]),
        )
        for name, m in raw["arms"].items()
    }
    return RouterParams(
        feature_names=names,
        arms=arms,
        lam=float(raw["lam"]),
        alpha=float(raw["alpha"]),
        tau_acc=None if raw["tau_acc"] is None else float(raw["tau_acc"]),
        stage_median_ms={k: float(v) for k, v in raw["stage_median_ms"].items()},
        price_book_digest=str(raw["price_book_digest"]),
        provisional=bool(raw["provisional"]),
    )


def provisional_router_params(
    *,
    stage_median_ms: Mapping[str, float],
    price_book_digest: str = "",
    lam: float = 1,
    alpha: float = 1,
) -> RouterParams:
    """Unfitted parameters: A = λI, b = 0, no τ_acc, so every arm is
    infeasible and every routed run escalates to Full until the freeze."""
    d = len(FEATURE_NAMES)
    a_inv = tuple(tuple((1 / lam) if i == j else 0 for j in range(d)) for i in range(d))
    model = ArmModel(a_inv=a_inv, theta=(0,) * d, n=0)
    return RouterParams(
        feature_names=FEATURE_NAMES,
        arms=dict.fromkeys(SELECTABLE, model),
        lam=lam,
        alpha=alpha,
        tau_acc=None,
        stage_median_ms=dict(stage_median_ms),
        price_book_digest=price_book_digest,
        provisional=True,
    )


def load_router_params(path: Path = ROUTER_PARAMS_PATH) -> RouterParams:
    """The frozen (or provisional) parameters; a missing file or key is an error."""
    if not path.is_file():
        raise FileNotFoundError(f"router parameters not found: {path}")
    return _from_dict(json.loads(path.read_text(encoding="utf-8")))


def write_router_params(params: RouterParams, path: Path) -> None:
    """Write the parameters as canonical, indented JSON."""
    text = json.dumps(
        json.loads(canonical_json(params.as_dict())), indent=2, sort_keys=True
    )
    path.write_text(text + "\n", encoding="utf-8")


def router_params_hash(params: RouterParams) -> str:
    """SHA-256 over every parameter (CoE parameter hashes; checked at run start)."""
    return hashlib.sha256(canonical_json(params.as_dict()).encode("utf-8")).hexdigest()
