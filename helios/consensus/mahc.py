"""MAHC fusion: sigma-weighted Borda under hierarchical priors (S2.5 design §5.3).

Ch3 Algorithm 3: each pipeline that returned a list votes with weight
w_p prop. to pi_p / (sigma_p^2 + eps) (normalised), pi_p its prior for this incident's signal
type, sigma_p its own uncertainty (None counts as 1: unknown is never certain).
Borda: rank r of n scores (n - r + 1)/n, an unlisted service 0; the fused score
is sum w_p * score_p, ties broken by name. Fused sigma = sqrt(sum w_p sigma_p^2): when all
pipelines agree the ranking cannot depend on sigma, the fused sigma does (M-d).
Out-of-scope services are dropped before fusion, as the scorer drops them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from helios.consensus.calibration import State, features, state
from helios.consensus.timing import CONVERGE_MS, Schedule, schedule
from helios.schemas.verdict import VerdictStatus
from helios.telemetry.scope import in_scope
from helios.vcl import VCLFlag, gated_by

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from helios.consensus.params import MAHCParams
    from helios.schemas.verdict import PipelineVerdict
    from helios.telemetry.signal_type import SignalType

__all__ = [
    "MAHC_EPSILON",
    "FusedVerdict",
    "Fusion",
    "ProvisionalParamsError",
    "Vote",
    "borda",
    "fuse",
    "run_mahc",
    "run_vote_only",
    "votes_from",
]

HELIOS_ENABLE_MAHC: bool = True

MAHC_EPSILON: float = 1e-4
_DIGITS = 6


@dataclass(frozen=True)
class Vote:
    """One pipeline's in-scope ranked list and its sigma."""

    pipeline: str
    ranked: tuple[str, ...]
    sigma: float


@dataclass(frozen=True)
class Fusion:
    """A fused ranking with its weights and fused sigma."""

    ranked: tuple[str, ...]
    scores: dict[str, float]
    weights: dict[str, float]
    fused_sigma: float | None
    contributing: tuple[str, ...]
    top1s_agree: bool


def votes_from(verdicts: Sequence[PipelineVerdict]) -> list[Vote]:
    """Votes of the RANKED verdicts whose in-scope list is not empty."""
    votes = []
    for v in verdicts:
        ranked = tuple(s for s in v.ranked_candidates if in_scope(s))
        if v.status == VerdictStatus.RANKED and ranked:
            votes.append(
                Vote(v.pipeline.value, ranked, 1 if v.sigma is None else v.sigma)
            )
    return votes


def borda(votes: Sequence[Vote], weights: Mapping[str, float]) -> Fusion:
    """Weighted Borda over the votes (weights already normalised)."""
    scores: dict[str, float] = {}
    for vote in votes:
        n = len(vote.ranked)
        for r, service in enumerate(vote.ranked, start=1):
            scores[service] = (
                scores.get(service, 0) + weights[vote.pipeline] * (n - r + 1) / n
            )
    scores = {s: round(v, _DIGITS) for s, v in scores.items()}
    ranked = tuple(sorted(scores, key=lambda s: (-scores[s], s)))
    return Fusion(
        ranked=ranked,
        scores=scores,
        weights=dict(weights),
        fused_sigma=None,
        contributing=tuple(v.pipeline for v in votes),
        top1s_agree=len({v.ranked[0] for v in votes}) <= 1,
    )


def fuse(votes: Sequence[Vote], priors: Mapping[str, float]) -> Fusion:
    """MAHC: weights pi / (sigma^2 + eps), normalised; fused sigma = sqrtsum w sigma^2."""
    if not votes:
        return Fusion((), {}, {}, None, (), True)
    raw = {
        v.pipeline: priors.get(v.pipeline, 1) / (v.sigma**2 + MAHC_EPSILON)
        for v in votes
    }
    total = sum(raw.values())
    weights = {p: w / total for p, w in raw.items()}
    fused = borda(votes, weights)
    sigma = math.sqrt(sum(weights[v.pipeline] * v.sigma**2 for v in votes))
    return Fusion(
        fused.ranked,
        fused.scores,
        {p: round(w, _DIGITS) for p, w in weights.items()},
        round(sigma, _DIGITS),
        fused.contributing,
        fused.top1s_agree,
    )


class ProvisionalParamsError(RuntimeError):
    """A confirmatory run met MAHC parameters that are not frozen."""


@dataclass(frozen=True)
class FusedVerdict:
    """What HELIOS publishes for an incident (S2.5 design §5.4-5.7)."""

    method: str
    ranked: tuple[str, ...]
    scores: dict[str, float]
    confidence: float | None
    fused_sigma: float | None
    state: State
    schedule: Schedule
    first_ranked: tuple[str, ...]
    evidence: dict[str, Any]


def _publish(
    method: str,
    verdicts: Sequence[PipelineVerdict],
    latency_ms: Mapping[str, float],
    combine: Callable[[Sequence[Vote]], Fusion],
    score: Callable[[Fusion], float | None],
    floor: float | None,
    extra: dict[str, Any],
) -> FusedVerdict:
    votes = votes_from(verdicts)
    sched = schedule(latency_ms)
    in_time = [v for v in votes if latency_ms.get(v.pipeline, 0) <= CONVERGE_MS]
    terminal = combine(in_time)
    first = combine([v for v in votes if v.pipeline in sched.first_pipelines])
    confidence = score(terminal) if terminal.ranked else None
    if sched.non_converged:
        published = State.NON_CONVERGED
    elif not terminal.ranked:
        published = State.PROVISIONAL
    elif method == "vote_only":
        published = State.CONFIRMED
    else:
        published = state(confidence, floor, all_in=True)
    top = terminal.ranked[0] if terminal.ranked else None
    return FusedVerdict(
        method=method,
        ranked=terminal.ranked,
        scores=terminal.scores,
        confidence=confidence,
        fused_sigma=terminal.fused_sigma,
        state=published,
        schedule=sched,
        first_ranked=first.ranked,
        evidence={
            **extra,
            "weights": terminal.weights,
            "contributing": list(terminal.contributing),
            "features": list(features(terminal)),
            "disagreeing": sorted(v.pipeline for v in in_time if v.ranked[0] != top),
        },
    )


@gated_by(VCLFlag.MAHC_HIERARCHICAL)
def run_mahc(
    verdicts: Sequence[PipelineVerdict],
    signal: SignalType,
    params: MAHCParams,
    *,
    latency_ms: Mapping[str, float],
    confirmatory: bool,
) -> FusedVerdict:
    """MAHC under the frozen priors, calibrator and floor."""
    if confirmatory and params.provisional:
        raise ProvisionalParamsError(
            "MAHC parameters are provisional; freeze them first"
        )
    looked = {
        p.value: params.priors.lookup(p.value, signal)
        for p in (v.pipeline for v in verdicts)
    }
    priors = {p: value for p, (value, _) in looked.items()}
    cal = params.calibrator

    def score(f: Fusion) -> float | None:
        return None if cal is None else cal.predict(features(f))

    return _publish(
        "mahc",
        verdicts,
        latency_ms,
        lambda votes: fuse(votes, priors),
        score,
        params.floor,
        {"signal": signal.value, "priors": {p: list(v) for p, v in looked.items()}},
    )


def run_vote_only(
    verdicts: Sequence[PipelineVerdict], *, latency_ms: Mapping[str, float]
) -> FusedVerdict:
    """HELIOS-noConsensus: equal-weight Borda, no gate (S2.6)."""
    from helios.consensus.vote_only import vote_only

    return _publish(
        "vote_only", verdicts, latency_ms, vote_only, lambda _f: None, None, {}
    )
