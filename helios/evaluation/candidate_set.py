"""Candidate parameter sets for a chain refit (OTel fix, entries 76 and 78).

A refit writes each stage's parameters to ``data/candidate/<name>/`` instead
of ``data/frozen/``, so the current chain stays the one every run and test
uses until the adoption decision. A stage whose file is absent from the
candidate directory uses its frozen file. Build tools pass the loaded set to
the orchestrator; nothing here writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from helios.consensus.params import MAHCParams, load_mahc_params, mahc_params_hash
from helios.pipelines.d_pipe.params import (
    DPipeParams,
    dpipe_params_hash,
    load_dpipe_params,
)
from helios.pipelines.g_pipe.params import (
    GPipeParams,
    gpipe_params_hash,
    load_gpipe_params,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

__all__ = ["CANDIDATE_ROOT", "ChainParams", "load_chain"]

CANDIDATE_ROOT = Path(__file__).resolve().parents[2] / "data" / "candidate"
_FILES = {
    "dpipe": "dpipe_params.json",
    "gpipe": "gpipe_params.json",
    "mahc": "mahc_params.json",
}


@dataclass(frozen=True)
class ChainParams:
    """D-pipe, G-pipe and MAHC parameters, and where each came from."""

    dpipe: DPipeParams
    gpipe: GPipeParams
    mahc: MAHCParams
    sources: dict[str, str]

    def hashes(self) -> dict[str, str]:
        """Each stage's parameter hash (recorded in build reports)."""
        return {
            "dpipe": dpipe_params_hash(self.dpipe),
            "gpipe": gpipe_params_hash(self.gpipe),
            "mahc": mahc_params_hash(self.mahc),
        }


def load_chain(candidate: Path | None = None) -> ChainParams:
    """The frozen chain, with each stage the candidate directory holds replaced.

    ``candidate`` must be an existing directory when given (a typo must not
    silently fall back to the frozen chain).
    """
    if candidate is not None and not candidate.is_dir():
        raise FileNotFoundError(f"candidate directory not found: {candidate}")

    def pick(stage: str) -> Path | None:
        if candidate is None:
            return None
        path = candidate / _FILES[stage]
        return path if path.is_file() else None

    d, g, m = pick("dpipe"), pick("gpipe"), pick("mahc")
    return ChainParams(
        dpipe=load_dpipe_params(d) if d else load_dpipe_params(),
        gpipe=load_gpipe_params(g) if g else load_gpipe_params(),
        mahc=load_mahc_params(m) if m else load_mahc_params(),
        sources={
            stage: "candidate" if path else "frozen"
            for stage, path in (("dpipe", d), ("gpipe", g), ("mahc", m))
        },
    )
