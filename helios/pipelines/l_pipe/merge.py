"""Deterministic merge of the valid workers (S2.3 design §5.4; owner L-b, L-c, L-d).

No model adjudicates. Each valid worker weighs 1/k: rank r (1 to MAX_RANKED)
scores (MAX_RANKED + 1 - r) / MAX_RANKED, an unlisted service 0, and the
merged score is the mean. Ties break by service name.

- mu = the top-1 share of the merged scores (``top1_share``).
- sigma = 1 - agreement * gap, the shape D-pipe and G-pipe use: gap =
  (s1 - s2) / s1; agreement = (workers whose top-1 is the merged top-1,
  minus one, floored at 0) / (k - 1), and 0 for k = 1, so a lone worker
  has sigma 1 and sigma stays in [0, 1].
- k = 0: no ranking, mu and sigma None (the verdict contract's ABSTAINED).

The model's own stated confidence is never used.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from helios.pipelines.l_pipe.lpipe_config import MAX_RANKED
from helios.schemas.verdict import MU_DIGITS, top1_share
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Sequence

    from helios.pipelines.l_pipe.workers import WorkerResult

__all__ = ["MergeResult", "merge"]

HELIOS_ENABLE_LPIPE_MERGE: bool = True


@dataclass(frozen=True)
class MergeResult:
    """L-pipe's ranking and its (mu, sigma) from k valid workers."""

    scores: dict[str, float]
    ranked: tuple[str, ...]
    mu: float | None
    sigma: float | None
    k: int


def merge(results: Sequence[WorkerResult]) -> MergeResult:
    """Equal-weight Borda over the valid workers."""
    valid = [r for r in results if r.valid and r.ranked]
    k = len(valid)
    if k == 0:
        return MergeResult({}, (), None, None, 0)
    totals: dict[str, float] = {}
    for r in valid:
        for rank, service in enumerate(r.ranked, start=1):
            totals[service] = (
                totals.get(service, 0) + (MAX_RANKED + 1 - rank) / MAX_RANKED
            )
    scores = {s: round(v / k, MU_DIGITS) for s, v in totals.items()}
    ranked = tuple(sorted(scores, key=lambda s: (-scores[s], s)))
    s1 = scores[ranked[0]]
    s2 = scores[ranked[1]] if len(ranked) > 1 else 0
    gap = (s1 - s2) / s1
    agreeing = sum(r.ranked[0] == ranked[0] for r in valid)
    # No worker may top the merge (e.g. a, c and b, c merge to c): agreement 0.
    agreement = max(agreeing - 1, 0) / (k - 1) if k > 1 else 0
    sigma = round(1 - agreement * gap, MU_DIGITS)
    return MergeResult(scores, ranked, top1_share(scores), sigma, k)
