"""MAHC build calibration (S2.5 design §5.2-5.4; owner decisions M-a, M-c, M-e).

Build labels only; the confirmatory pool is never loaded here. Inputs are the
frozen pipelines' stored verdicts on the build cases (HELIOS-Full), so MAHC is
fitted on exactly what it will fuse.

- Outer folds are groups: OTel cases by root service, RCAEval cases by system,
  so no case is scored by priors or a calibrator fitted on its own group.
- Nested cross-fitting: within an outer training set, each case's fusion
  features come from priors fitted on the other inner groups; the calibrator is
  fitted on those; the held-out group is fused with priors fitted on the whole
  training set and scored by that calibrator.
- The floor: per corpus, the lowest held-out confidence with HR@3 >= 0.8 among
  the cases at or above it; the stricter corpus wins; None if a corpus cannot
  reach it (the tool then stops, M-e).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from helios.consensus.calibration import (
    Calibrator,
    State,
    choose_floor,
    features,
    state,
)
from helios.consensus.mahc import Fusion, Vote, fuse
from helios.consensus.priors import PriorCase, PriorTable, fit_priors
from helios.consensus.vote_only import vote_only
from helios.evaluation.scoring import score_ranking
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Sequence

    from helios.consensus.params import MAHCParams
    from helios.telemetry.signal_type import SignalType

__all__ = [
    "CURVE_BINS",
    "BuildCase",
    "CrossFit",
    "PriorCase",
    "PriorTable",
    "cross_fit",
    "evaluate",
    "fit_priors",
    "frozen_check",
    "inner_calibrator",
    "outer_folds",
    "prior_case",
]

CURVE_BINS: int = 10
_DIGITS = 4


@dataclass(frozen=True)
class BuildCase:
    """One build case: its votes, signal type, label and fold group."""

    incident_id: str
    corpus: str
    group: str
    signal: SignalType
    votes: tuple[Vote, ...]
    root: str


@dataclass(frozen=True)
class CrossFit:
    """Held-out confidence and fused top-3 hit per case (case order)."""

    conf: list[float]
    hit: list[int]


def _hit(ranked: Sequence[str], root: str) -> int:
    return score_ranking(list(ranked), root).hr_at_3 if ranked else 0


def prior_case(case: BuildCase) -> PriorCase:
    """Each pipeline's top-3 hit on this case (pipelines without a list absent)."""
    return PriorCase(
        case.signal, {v.pipeline: _hit(v.ranked, case.root) for v in case.votes}
    )


def _fused(case: BuildCase, table: PriorTable) -> Fusion:
    priors = {v.pipeline: table.lookup(v.pipeline, case.signal)[0] for v in case.votes}
    return fuse(case.votes, priors)


def outer_folds(cases: Sequence[BuildCase]) -> list[list[int]]:
    """One fold per (corpus, group), in sorted order."""
    keys = sorted({(c.corpus, c.group) for c in cases})
    return [[i for i, c in enumerate(cases) if (c.corpus, c.group) == k] for k in keys]


def _group_held_out(
    cases: Sequence[BuildCase], idx: Sequence[int]
) -> dict[int, Fusion]:
    """Each case in idx fused with priors fitted on idx minus its own group."""
    out: dict[int, Fusion] = {}
    sub = [cases[i] for i in idx]
    for fold in outer_folds(sub):
        held = {idx[j] for j in fold}
        table = fit_priors([prior_case(cases[i]) for i in idx if i not in held])
        for i in held:
            out[i] = _fused(cases[i], table)
    return out


def inner_calibrator(cases: Sequence[BuildCase], idx: Sequence[int]) -> Calibrator:
    """Calibrator fitted on idx, each case's features from priors without its group."""
    fused = _group_held_out(cases, idx)
    xs = [features(fused[i]) for i in idx]
    ys = [_hit(fused[i].ranked, cases[i].root) for i in idx]
    return Calibrator.fit(xs, ys)


def cross_fit(cases: Sequence[BuildCase]) -> CrossFit:
    """Nested cross-fitted confidence and fused hit for every case."""
    conf = [float(0)] * len(cases)
    hit = [0] * len(cases)
    for fold in outer_folds(cases):
        held = set(fold)
        train = [i for i in range(len(cases)) if i not in held]
        cal = inner_calibrator(cases, train)
        table = fit_priors([prior_case(cases[i]) for i in train])
        for i in fold:
            f = _fused(cases[i], table)
            conf[i] = cal.predict(features(f))
            hit[i] = _hit(f.ranked, cases[i].root)
    return CrossFit(conf, hit)


def _rate(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), _DIGITS) if values else None


def _curve(conf: Sequence[float], hit: Sequence[int]) -> list[dict[str, Any]]:
    bins: list[dict[str, Any]] = []
    for b in range(CURVE_BINS):
        lo, hi = b / CURVE_BINS, (b + 1) / CURVE_BINS
        members = [
            (c, h)
            for c, h in zip(conf, hit, strict=True)
            if lo <= c < hi or (b == CURVE_BINS - 1 and c == hi)
        ]
        bins.append(
            {
                "bin": [round(lo, 2), round(hi, 2)],
                "cases": len(members),
                "mean_confidence": _rate([c for c, _ in members]),
                "hr3": _rate([h for _, h in members]),
            }
        )
    return bins


def evaluate(cases: Sequence[BuildCase]) -> dict[str, Any]:
    """The build report: per corpus HR@3, the floor, the confirmed share, the curve."""
    cf = cross_fit(cases)
    corpora = [c.corpus for c in cases]
    floor = choose_floor(cf.conf, cf.hit, corpora)
    by_corpus: dict[str, Any] = {}
    for name in sorted(set(corpora)):
        idx = [i for i, c in enumerate(cases) if c.corpus == name]
        pipelines = sorted({v.pipeline for i in idx for v in cases[i].votes})
        confirmed = [i for i in idx if floor is not None and cf.conf[i] >= floor]
        ambiguous = [i for i in idx if len({v.ranked[0] for v in cases[i].votes}) > 1]
        plain = {i: _hit(vote_only(cases[i].votes).ranked, cases[i].root) for i in idx}
        by_corpus[name] = {
            "cases": len(idx),
            "mahc_hr3": _rate([cf.hit[i] for i in idx]),
            "vote_only_hr3": _rate([plain[i] for i in idx]),
            "ambiguous": len(ambiguous),
            "mahc_hr3_ambiguous": _rate([cf.hit[i] for i in ambiguous]),
            "vote_only_hr3_ambiguous": _rate([plain[i] for i in ambiguous]),
            "pipelines_hr3": {
                p: _rate(
                    [
                        _hit(v.ranked, cases[i].root)
                        for i in idx
                        for v in cases[i].votes
                        if v.pipeline == p
                    ]
                )
                for p in pipelines
            },
            "pipelines_with_list": {
                p: sum(1 for i in idx for v in cases[i].votes if v.pipeline == p)
                for p in pipelines
            },
            "confirmed": len(confirmed),
            "hr3_confirmed": _rate([cf.hit[i] for i in confirmed]),
            "signal_types": {
                s: sum(1 for i in idx if cases[i].signal.value == s)
                for s in sorted({cases[i].signal.value for i in idx})
            },
        }
    return {
        "floor": floor,
        "by_corpus": by_corpus,
        "calibration_curve": _curve(cf.conf, cf.hit),
    }


def _frozen(
    case: BuildCase, params: MAHCParams, votes: Sequence[Vote]
) -> tuple[float | None, State, int]:
    priors = {
        v.pipeline: params.priors.lookup(v.pipeline, case.signal)[0] for v in votes
    }
    f = fuse(votes, priors)
    cal = params.calibrator
    conf = cal.predict(features(f)) if cal is not None and f.ranked else None
    return conf, state(conf, params.floor, all_in=True), _hit(f.ranked, case.root)


def frozen_check(cases: Sequence[BuildCase], params: MAHCParams) -> dict[str, Any]:
    """The frozen parameters applied to the build cases (in-sample, PR 2 review).

    Per corpus: confirmed and provisional counts and their HR@3 under the refit
    calibrator (the floor was chosen on cross-fitted confidences). And, on cases
    where G-pipe voted, the same with and without G-pipe's vote: how a third
    pipeline moves confidence and state through agreement and fused sigma.
    """
    by_corpus: dict[str, Any] = {}
    gpipe: dict[str, Any] = {}
    for name in sorted({c.corpus for c in cases}):
        mine = [c for c in cases if c.corpus == name]
        runs = [_frozen(c, params, c.votes) for c in mine]
        confirmed = [h for _, s, h in runs if s == State.CONFIRMED]
        provisional = [h for _, s, h in runs if s != State.CONFIRMED]
        by_corpus[name] = {
            "cases": len(mine),
            "confirmed": len(confirmed),
            "provisional": len(provisional),
            "hr3_confirmed": _rate(confirmed),
            "hr3_provisional": _rate(provisional),
        }
        with_g = [c for c in mine if any(v.pipeline == "gpipe" for v in c.votes)]
        if not with_g:
            continue
        both = [
            (
                _frozen(c, params, c.votes),
                _frozen(c, params, [v for v in c.votes if v.pipeline != "gpipe"]),
            )
            for c in with_g
        ]
        gpipe[name] = {
            "cases_with_gpipe": len(with_g),
            "confirmed_with": sum(a[1] == State.CONFIRMED for a, _ in both),
            "confirmed_without": sum(b[1] == State.CONFIRMED for _, b in both),
            "flips_confirmed_to_provisional": sum(
                a[1] != State.CONFIRMED and b[1] == State.CONFIRMED for a, b in both
            ),
            "flips_provisional_to_confirmed": sum(
                a[1] == State.CONFIRMED and b[1] != State.CONFIRMED for a, b in both
            ),
            "mean_confidence_with": _rate([a[0] or 0 for a, _ in both]),
            "mean_confidence_without": _rate([b[0] or 0 for _, b in both]),
            "hr3_with": _rate([a[2] for a, _ in both]),
            "hr3_without": _rate([b[2] for _, b in both]),
        }
    return {"by_corpus": by_corpus, "gpipe_effect": gpipe}
