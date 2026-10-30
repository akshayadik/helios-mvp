"""Frozen G-pipe parameters (S2.2): which candidate ranks, and its model.

The runner loads ``data/frozen/gpipe_params.json``; a missing file or key is
an error, never a code default. ``provisional`` parameters are refused in
confirmatory runs until the S2.2 selection run freezes them.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from helios.pipelines.g_pipe.features import FEATURE_COLUMNS
from helios.pipelines.g_pipe.rankers import LinearRanker
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.utils import canonical_json

__all__ = [
    "GPIPE_PARAMS_PATH",
    "RANKERS",
    "GPipeParams",
    "gpipe_params_hash",
    "load_gpipe_params",
]

GPIPE_PARAMS_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "frozen" / "gpipe_params.json"
)
RANKERS = ("learned", "weighted_ppr", "ppr")
Ranker = Literal["learned", "weighted_ppr", "ppr"]
_KEYS = frozenset({"ranker", "weights", "mean", "scale", "provisional"})
_MODEL_KEYS = ("weights", "mean", "scale")


@dataclass(frozen=True)
class GPipeParams:
    """The frozen candidate; ``model`` only for the learned ranker."""

    ranker: Ranker
    model: LinearRanker | None
    provisional: bool

    def as_dict(self) -> dict[str, Any]:
        model = self.model
        return {
            "ranker": self.ranker,
            "weights": list(model.weights) if model else None,
            "mean": list(model.mean) if model else None,
            "scale": list(model.scale) if model else None,
            "provisional": self.provisional,
        }


def load_gpipe_params(path: Path = GPIPE_PARAMS_PATH) -> GPipeParams:
    """The frozen parameters; a missing file, key or model is an error."""
    if not path.is_file():
        raise FileNotFoundError(f"G-pipe parameters not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if set(raw) != _KEYS:
        raise ValueError(f"G-pipe parameter keys must be {sorted(_KEYS)}")
    if raw["ranker"] not in RANKERS:
        raise ValueError(f"ranker must be one of {RANKERS}")
    model = None
    if raw["ranker"] == "learned":
        values = [raw[k] for k in _MODEL_KEYS]
        if any(
            not isinstance(v, list) or len(v) != len(FEATURE_COLUMNS) for v in values
        ):
            raise ValueError(
                "the learned ranker needs weights, mean and scale per feature"
            )
        model = LinearRanker(*(tuple(float(x) for x in v) for v in values))
    elif any(raw[k] is not None for k in _MODEL_KEYS):
        raise ValueError(f"ranker {raw['ranker']!r} takes no model values")
    return GPipeParams(
        ranker=cast("Ranker", raw["ranker"]),
        model=model,
        provisional=bool(raw["provisional"]),
    )


def gpipe_params_hash(params: GPipeParams) -> str:
    """SHA-256 over every parameter (stored with the selection report)."""
    return hashlib.sha256(canonical_json(params.as_dict()).encode("utf-8")).hexdigest()
