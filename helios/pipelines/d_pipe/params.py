"""Frozen D-pipe parameters (S2.1, S2-M7-ENG09).

The runner loads them from ``data/frozen/dpipe_params.json`` and passes them to
``run_dpipe``; a missing file or key is an error, never a code default (before
S2.1 every run silently used the defaults in dpipe_config). ``provisional``
parameters are refused in confirmatory runs until calibration freezes them
(S2-M7-EVAL01).

``w_memory`` (OTel fix B, entry 76) is the one optional key: without it memory
stays in the resource channel, as in every freeze before the fix, and the
hash leaves it out, so those freezes keep their hashes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.utils import canonical_json

__all__ = ["DPIPE_PARAMS_PATH", "DPipeParams", "dpipe_params_hash", "load_dpipe_params"]

HELIOS_ENABLE_DPIPE_PARAMS: bool = True

DPIPE_PARAMS_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "frozen" / "dpipe_params.json"
)
_KEYS = frozenset(
    {"w_error", "w_resource", "rho_threshold", "topology_boost_factor", "provisional"}
)
_OPTIONAL_KEYS = frozenset({"w_memory"})


@dataclass(frozen=True)
class DPipeParams:
    """Stage B weights and Stage C propagation parameters."""

    w_error: float
    w_resource: float
    rho_threshold: float
    topology_boost_factor: float
    provisional: bool
    w_memory: float | None = None

    def as_dict(self) -> dict[str, float | bool]:
        """Every parameter; ``w_memory`` only when set (hash stability)."""
        out: dict[str, float | bool] = {
            k: v for k, v in asdict(self).items() if k != "w_memory"
        }
        if self.w_memory is not None:
            out["w_memory"] = self.w_memory
        return out


def load_dpipe_params(path: Path = DPIPE_PARAMS_PATH) -> DPipeParams:
    """The frozen parameters; a missing file or key is an error."""
    if not path.is_file():
        raise FileNotFoundError(f"D-pipe parameters not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not _KEYS <= set(raw) <= _KEYS | _OPTIONAL_KEYS:
        raise ValueError(
            f"D-pipe parameter keys must be {sorted(_KEYS)}, optionally "
            f"{sorted(_OPTIONAL_KEYS)}"
        )
    params = DPipeParams(
        w_error=float(raw["w_error"]),
        w_resource=float(raw["w_resource"]),
        rho_threshold=float(raw["rho_threshold"]),
        topology_boost_factor=float(raw["topology_boost_factor"]),
        provisional=bool(raw["provisional"]),
        w_memory=None if raw.get("w_memory") is None else float(raw["w_memory"]),
    )
    weights = (params.w_error, params.w_resource, params.w_memory or 0)
    if min(weights) < 0 or sum(weights) > 1:
        raise ValueError(
            "weights must be >= 0 with w_error + w_resource + w_memory <= 1"
        )
    return params


def dpipe_params_hash(params: DPipeParams) -> str:
    """SHA-256 over the parameters (stored with calibration results)."""
    return hashlib.sha256(canonical_json(params.as_dict()).encode("utf-8")).hexdigest()
