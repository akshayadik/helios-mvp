"""Vote-only fusion for HELIOS-noConsensus (S2.6; S2.5 design §5.6).

The same per-pipeline lists MAHC fuses, by plain Borda with equal weights: no
priors, no sigma, no confidence. A-H4 compares it with MAHC on identical inputs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from helios.consensus.mahc import Fusion, borda
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Sequence

    from helios.consensus.mahc import Vote

__all__ = ["vote_only"]

HELIOS_ENABLE_VOTE_ONLY: bool = True


def vote_only(votes: Sequence[Vote]) -> Fusion:
    """Equal-weight Borda; fused sigma None (vote-only has no uncertainty)."""
    return borda(votes, {v.pipeline: 1 for v in votes})
