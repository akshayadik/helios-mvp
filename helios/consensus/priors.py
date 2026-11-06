"""Hierarchical priors for MAHC (S2.5 design §5.2; owner decision M-a).

A pipeline's prior for an incident is its top-3 hit rate on build cases with
the same trigger signal type, smoothed toward its global rate with
PRIOR_STRENGTH pseudo-cases, and used only when that signal type has at least
MIN_CASES build cases where the pipeline returned a list; otherwise the global
rate. A pipeline never seen on build data gets prior 1 (neutral weight). No
label enters at run time: the table is fitted on build cases and frozen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from helios.telemetry.signal_type import SignalType

__all__ = ["MIN_CASES", "PRIOR_STRENGTH", "PriorCase", "PriorTable", "fit_priors"]

HELIOS_ENABLE_MAHC_PRIORS: bool = True

PRIOR_STRENGTH: int = 10
MIN_CASES: int = 30
_DIGITS = 6


@dataclass(frozen=True)
class PriorCase:
    """One build case: its signal type and each pipeline's top-3 hit (None: no list)."""

    signal: SignalType
    hits: Mapping[str, int | None]


@dataclass(frozen=True)
class PriorTable:
    """Global and per-signal-type priors, with the counts behind them."""

    global_: dict[str, float]
    by_signal: dict[str, dict[str, float]]
    counts: dict[str, dict[str, int]]

    def lookup(self, pipeline: str, signal: SignalType) -> tuple[float, str]:
        """(prior, level): the signal-type prior if fitted, else global, else 1."""
        per = self.by_signal.get(signal.value, {})
        if pipeline in per:
            return per[pipeline], "signal"
        return self.global_.get(pipeline, 1), "global"


def fit_priors(cases: Sequence[PriorCase]) -> PriorTable:
    """Fit the table on build cases (held-out use is the caller's folds)."""
    pipelines = sorted({p for c in cases for p in c.hits})
    global_: dict[str, float] = {}
    for p in pipelines:
        given = [c.hits[p] for c in cases if c.hits.get(p) is not None]
        if given:
            global_[p] = round(sum(h or 0 for h in given) / len(given), _DIGITS)
    by_signal: dict[str, dict[str, float]] = {}
    counts: dict[str, dict[str, int]] = {}
    for signal in sorted({c.signal.value for c in cases}):
        mine = [c for c in cases if c.signal.value == signal]
        for p in pipelines:
            given = [c.hits[p] for c in mine if c.hits.get(p) is not None]
            counts.setdefault(signal, {})[p] = len(given)
            if len(given) >= MIN_CASES and p in global_:
                smoothed = (
                    sum(h or 0 for h in given) + PRIOR_STRENGTH * global_[p]
                ) / (len(given) + PRIOR_STRENGTH)
                by_signal.setdefault(signal, {})[p] = round(smoothed, _DIGITS)
    return PriorTable(global_, by_signal, counts)
