"""ACP parameters: a multinomial logistic model, frozen and hashed (S3.2 P-d).

The frozen file is ``data/frozen/acp_params.json``, written once by
``bin/acp_fit.py --freeze``. Features are standardised with the fit's mean
and scale (the bias column is left as is), then each class scores
``w_k . z``; probabilities are the softmax. Values are rounded to six digits
so the hash is stable across machines.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from helios.acp.features import ACP_FEATURE_NAMES
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.utils import canonical_json

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "ACP_CLASSES",
    "ACP_PARAMS_PATH",
    "ACPParams",
    "acp_params_from_dict",
    "acp_params_hash",
    "load_acp_params",
    "write_acp_params",
]

HELIOS_ENABLE_ACP_PARAMS: bool = True

ACP_PARAMS_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "frozen" / "acp_params.json"
)
# Remediation families the build data can label (design P-a, entry 82).
ACP_CLASSES: tuple[str, ...] = ("resource", "network", "config", "code")
_DIGITS = 6


@dataclass(frozen=True)
class ACPParams:
    """Standardisation and per-class weights over ``feature_names``."""

    feature_names: tuple[str, ...]
    classes: tuple[str, ...]
    mean: tuple[float, ...]
    scale: tuple[float, ...]
    weights: tuple[tuple[float, ...], ...]
    lam: float
    n_cases: int

    def __post_init__(self) -> None:
        d = len(self.feature_names)
        if self.feature_names != ACP_FEATURE_NAMES:
            raise ValueError("ACP feature names differ from ACP_FEATURE_NAMES")
        if self.classes != ACP_CLASSES:
            raise ValueError("ACP classes differ from ACP_CLASSES")
        if len(self.mean) != d or len(self.scale) != d:
            raise ValueError("ACP mean/scale length differs from the features")
        if len(self.weights) != len(self.classes) or any(
            len(w) != d for w in self.weights
        ):
            raise ValueError("ACP weights do not match classes x features")
        if any(s <= 0 for s in self.scale):
            raise ValueError("ACP scale must be positive")

    def standardise(self, x: Sequence[float]) -> list[float]:
        if len(x) != len(self.feature_names):
            raise ValueError("feature vector length differs from the parameters")
        return [(v - m) / s for v, m, s in zip(x, self.mean, self.scale, strict=True)]

    def probabilities(self, x: Sequence[float]) -> dict[str, float]:
        """Softmax over the classes, rounded."""
        z = self.standardise(x)
        logits = [
            sum(w * v for w, v in zip(row, z, strict=True)) for row in self.weights
        ]
        top = max(logits)
        exps = [math.exp(v - top) for v in logits]
        total = sum(exps)
        return {
            c: round(e / total, _DIGITS)
            for c, e in zip(self.classes, exps, strict=True)
        }

    def as_dict(self) -> dict[str, Any]:
        """Floats throughout, so the hash does not depend on int or float input."""

        def r(v: float) -> float:
            return round(float(v), _DIGITS)

        return {
            "feature_names": list(self.feature_names),
            "classes": list(self.classes),
            "mean": [r(v) for v in self.mean],
            "scale": [r(v) for v in self.scale],
            "weights": [[r(v) for v in row] for row in self.weights],
            "lam": r(self.lam),
            "n_cases": int(self.n_cases),
        }


def acp_params_from_dict(raw: dict[str, Any]) -> ACPParams:
    expected = {
        "feature_names",
        "classes",
        "mean",
        "scale",
        "weights",
        "lam",
        "n_cases",
    }
    if set(raw) != expected:
        raise ValueError(f"ACP parameter keys {sorted(raw)} != {sorted(expected)}")
    return ACPParams(
        feature_names=tuple(str(v) for v in raw["feature_names"]),
        classes=tuple(str(v) for v in raw["classes"]),
        mean=tuple(float(v) for v in raw["mean"]),
        scale=tuple(float(v) for v in raw["scale"]),
        weights=tuple(tuple(float(v) for v in row) for row in raw["weights"]),
        lam=float(raw["lam"]),
        n_cases=int(raw["n_cases"]),
    )


def load_acp_params(path: Path = ACP_PARAMS_PATH) -> ACPParams:
    return acp_params_from_dict(json.loads(path.read_text(encoding="utf-8")))


def write_acp_params(params: ACPParams, path: Path) -> None:
    text = json.dumps(
        json.loads(canonical_json(params.as_dict())), indent=2, sort_keys=True
    )
    path.write_text(text + "\n", encoding="utf-8")


def acp_params_hash(params: ACPParams) -> str:
    """SHA-256 over every parameter (CoE parameter hashes)."""
    return hashlib.sha256(canonical_json(params.as_dict()).encode("utf-8")).hexdigest()
