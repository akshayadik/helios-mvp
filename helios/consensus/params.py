"""MAHC's frozen parameters (S2.5 design §6): prior table, calibrator, floor.

Fitted by bin/mahc_build_run.py on build data only and frozen with a
deviation entry. The provisional file (before the build run) has no priors
(every pipeline weighs 1), no calibrator and no floor: every case is
PROVISIONAL, and a confirmatory run refuses it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from helios.consensus.calibration import Calibrator
from helios.consensus.priors import PriorTable
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.utils import canonical_json

__all__ = [
    "MAHC_PARAMS_PATH",
    "MAHCParams",
    "load_mahc_params",
    "mahc_params_hash",
    "write_mahc_params",
]

HELIOS_ENABLE_MAHC_PARAMS: bool = True

MAHC_PARAMS_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "frozen" / "mahc_params.json"
)
_KEYS = frozenset({"priors", "calibrator", "floor", "provisional"})


@dataclass(frozen=True)
class MAHCParams:
    """Everything MAHC needs beyond the pipelines' verdicts."""

    priors: PriorTable
    calibrator: Calibrator | None
    floor: float | None
    provisional: bool

    def as_dict(self) -> dict[str, Any]:
        cal = self.calibrator
        return {
            "priors": {
                "global": {k: float(v) for k, v in self.priors.global_.items()},
                "by_signal": {
                    s: {k: float(v) for k, v in d.items()}
                    for s, d in self.priors.by_signal.items()
                },
                "counts": self.priors.counts,
            },
            "calibrator": (
                None
                if cal is None
                else {
                    "coef": [float(v) for v in cal.coef],
                    "intercept": float(cal.intercept),
                    "mean": [float(v) for v in cal.mean],
                    "scale": [float(v) for v in cal.scale],
                    "knots": [[float(a), float(b)] for a, b in cal.knots],
                }
            ),
            "floor": None if self.floor is None else float(self.floor),
            "provisional": self.provisional,
        }


def _from_dict(raw: dict[str, Any]) -> MAHCParams:
    if set(raw) != _KEYS:
        raise ValueError(f"MAHC parameter keys must be {sorted(_KEYS)}")
    pri = raw["priors"]
    cal = raw["calibrator"]
    return MAHCParams(
        priors=PriorTable(
            {k: float(v) for k, v in pri["global"].items()},
            {
                s: {k: float(v) for k, v in d.items()}
                for s, d in pri["by_signal"].items()
            },
            {s: {k: int(v) for k, v in d.items()} for s, d in pri["counts"].items()},
        ),
        calibrator=(
            None
            if cal is None
            else Calibrator(
                coef=tuple(float(v) for v in cal["coef"]),
                intercept=float(cal["intercept"]),
                mean=tuple(float(v) for v in cal["mean"]),
                scale=tuple(float(v) for v in cal["scale"]),
                knots=tuple((float(a), float(b)) for a, b in cal["knots"]),
            )
        ),
        floor=None if raw["floor"] is None else float(raw["floor"]),
        provisional=bool(raw["provisional"]),
    )


def load_mahc_params(path: Path = MAHC_PARAMS_PATH) -> MAHCParams:
    """The frozen (or provisional) parameters; a missing file or key is an error."""
    if not path.is_file():
        raise FileNotFoundError(f"MAHC parameters not found: {path}")
    return _from_dict(json.loads(path.read_text(encoding="utf-8")))


def write_mahc_params(params: MAHCParams, path: Path) -> None:
    """Write the parameters as canonical, indented JSON."""
    text = json.dumps(
        json.loads(canonical_json(params.as_dict())), indent=2, sort_keys=True
    )
    path.write_text(text + "\n", encoding="utf-8")


def mahc_params_hash(params: MAHCParams) -> str:
    """SHA-256 over every parameter (stored with the build report)."""
    return hashlib.sha256(canonical_json(params.as_dict()).encode("utf-8")).hexdigest()
