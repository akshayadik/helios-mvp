"""Fit and evaluate the cheap-first router on build data (S3.1 design §5.3-5.4).

Full information: the build run is HELIOS-noRouter (every pipeline, G-pipe
ungated), so each case gives the outcome of every selectable arm, not one
sampled arm. An arm's outcome is the HR@3 hit of the frozen MAHC's fusion of
that arm's lists. Per-arm ridge models (LinUCB's A, b) are cross-fitted on
MAHC's folds; the held-out policy is simulated with the runtime decision
functions themselves (``decide_g``, ``decide_escalation``), so the build
figures and the runs use one policy.

τ_acc (R-d): the lowest held-out lower bound at which the routed policy's
held-out HR@3 is within the tolerance of uniform routing in every corpus and
at least one case stops before the L-pipe. A τ under which every case
escalates meets the tolerance trivially and does not qualify: no qualifying
value means the router cannot stop any case safely, and the build tool stops
for the owner.
"""

from __future__ import annotations

import dataclasses
import statistics
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from helios.consensus.mahc import Vote, fuse
from helios.consensus.router import decide_escalation, decide_g
from helios.consensus.router_features import FEATURE_NAMES
from helios.consensus.router_params import (
    ARM_PIPELINES,
    SELECTABLE,
    Arm,
    ArmModel,
    RouterParams,
)
from helios.evaluation.scoring import score_ranking
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from helios.consensus.params import MAHCParams
    from helios.telemetry.signal_type import SignalType

__all__ = [
    "RouterCase",
    "Simulated",
    "arm_outcomes",
    "choose_tau",
    "cross_fit",
    "evaluate",
    "fit_all",
    "fit_arm",
    "folds",
    "simulate",
    "stage_medians",
]

HELIOS_ENABLE_ROUTER_CALIBRATION: bool = True

TOLERANCE = 0.01  # R-d: one percentage point of HR@3, per corpus
_DIGITS = 4


@dataclass(frozen=True)
class RouterCase:
    """One build case as the router and the scorer see it.

    ``x_cheap`` are the features after the D-pipe, ``x_dg`` after G-pipe (None
    when G-pipe produced no list); ``graph`` is whether G-pipe could run.
    """

    incident_id: str
    corpus: str
    group: str
    signal: SignalType
    x_cheap: tuple[float, ...]
    x_dg: tuple[float, ...] | None
    graph: bool
    votes: Mapping[str, Vote]
    latency_ms: Mapping[str, float]
    root: str


@dataclass(frozen=True)
class Simulated:
    """The routed policy's decision on one case and its outcome."""

    stage1_arm: Arm
    terminal_arm: Arm
    reason: str
    g_ran: bool
    hit: int
    first_ms: float


def _hit(ranked: Sequence[str], root: str) -> int:
    return score_ranking(list(ranked), root).hr_at_3 if ranked else 0


def _fused_hit(case: RouterCase, pipelines: Sequence[str], mahc: MAHCParams) -> int:
    votes = [case.votes[p] for p in pipelines if p in case.votes]
    if not votes:
        return 0
    priors = {v.pipeline: mahc.priors.lookup(v.pipeline, case.signal)[0] for v in votes}
    return _hit(fuse(votes, priors).ranked, case.root)


def arm_outcomes(case: RouterCase, mahc: MAHCParams) -> dict[Arm, int]:
    """HR@3 hit of each selectable arm whose pipelines all produced a list."""
    out = {}
    for arm in SELECTABLE:
        names = ARM_PIPELINES[arm]
        if all(n in case.votes for n in names):
            out[arm] = _fused_hit(case, names, mahc)
    return out


def uniform_hit(case: RouterCase, mahc: MAHCParams) -> int:
    """noRouter's outcome: the fusion of every list the case has."""
    return _fused_hit(case, sorted(case.votes), mahc)


def _x(case: RouterCase, arm: Arm) -> tuple[float, ...] | None:
    """The features the runtime policy evaluates the arm on (design §5.1)."""
    if arm in (Arm.D, Arm.D_L):
        return case.x_cheap
    return case.x_dg


def fit_arm(rows: Sequence[tuple[tuple[float, ...], int]], lam: float) -> ArmModel:
    """Ridge: A = λI + Σ x xᵀ, b = Σ r x, θ = A⁻¹ b."""
    d = len(FEATURE_NAMES)
    a = lam * np.eye(d)
    b = np.zeros(d)
    for x, r in rows:
        v = np.asarray(x, dtype=float)
        a += np.outer(v, v)
        b += r * v
    a_inv = np.linalg.inv(a)
    theta = a_inv @ b
    return ArmModel(
        a_inv=tuple(tuple(float(v) for v in row) for row in a_inv),
        theta=tuple(float(v) for v in theta),
        n=len(rows),
    )


def _rows(
    cases: Sequence[RouterCase], idx: Sequence[int], outcomes: Sequence[dict[Arm, int]]
) -> dict[Arm, list[tuple[tuple[float, ...], int]]]:
    rows: dict[Arm, list[tuple[tuple[float, ...], int]]] = {a: [] for a in SELECTABLE}
    for i in idx:
        for arm, r in outcomes[i].items():
            x = _x(cases[i], arm)
            if x is not None:
                rows[arm].append((x, r))
    return rows


def folds(cases: Sequence[RouterCase]) -> list[list[int]]:
    """One fold per (corpus, group), MAHC's scheme (S2.5 §8 call 7)."""
    keys = sorted({(c.corpus, c.group) for c in cases})
    return [[i for i, c in enumerate(cases) if (c.corpus, c.group) == k] for k in keys]


def _params(
    models: Mapping[Arm, ArmModel],
    *,
    lam: float,
    alpha: float,
    tau: float | None,
    medians: Mapping[str, float],
    digest: str,
    provisional: bool,
) -> RouterParams:
    return RouterParams(
        feature_names=FEATURE_NAMES,
        arms=dict(models),
        lam=lam,
        alpha=alpha,
        tau_acc=tau,
        stage_median_ms=dict(medians),
        price_book_digest=digest,
        provisional=provisional,
    )


def cross_fit(
    cases: Sequence[RouterCase],
    outcomes: Sequence[dict[Arm, int]],
    *,
    lam: float,
    alpha: float,
    medians: Mapping[str, float],
) -> dict[int, RouterParams]:
    """Per case, parameters fitted on every fold but its own (τ unset)."""
    out: dict[int, RouterParams] = {}
    every = range(len(cases))
    for fold in folds(cases):
        held = set(fold)
        rows = _rows(cases, [i for i in every if i not in held], outcomes)
        models = {a: fit_arm(rows[a], lam) for a in SELECTABLE}
        params = _params(
            models,
            lam=lam,
            alpha=alpha,
            tau=None,
            medians=medians,
            digest="",
            provisional=True,
        )
        for i in fold:
            out[i] = params
    return out


def _top(vote: Vote | None) -> str | None:
    return vote.ranked[0] if vote is not None and vote.ranked else None


def simulate(
    case: RouterCase,
    params: RouterParams,
    outcomes: Mapping[Arm, int],
    mahc: MAHCParams,
) -> Simulated:
    """The runtime policy on one case (callers set a routed manifest)."""
    g = decide_g(case.x_cheap, params, graph=case.graph)
    g_ran = g.run_g and case.x_dg is not None
    x = case.x_dg if g_ran and case.x_dg is not None else case.x_cheap
    esc = decide_escalation(
        x,
        params,
        g_ran=g_ran,
        d_top=_top(case.votes.get("dpipe")),
        g_top=_top(case.votes.get("gpipe")) if g_ran else None,
        llm_on=True,
    )
    terminal = esc.terminal_arm
    if terminal in outcomes:
        hit = outcomes[terminal]
    else:  # an arm with a missing list fuses what there is
        hit = _fused_hit(case, ARM_PIPELINES[terminal], mahc)
    first = case.latency_ms.get("dpipe", 0)
    if g.run_g:
        first += case.latency_ms.get("gpipe", 0)
    return Simulated(esc.stage1_arm, terminal, esc.reason, g_ran, hit, first)


def _with_tau(params: RouterParams, tau: float) -> RouterParams:
    return dataclasses.replace(params, tau_acc=tau)


def _hr(values: Sequence[int]) -> float:
    return sum(values) / len(values) if values else 0


def choose_tau(
    cases: Sequence[RouterCase],
    held_out: Mapping[int, RouterParams],
    outcomes: Sequence[dict[Arm, int]],
    mahc: MAHCParams,
    *,
    tolerance: float = TOLERANCE,
) -> float | None:
    """The lowest held-out lower bound meeting the R-d rule in every corpus."""
    uniform = [uniform_hit(c, mahc) for c in cases]
    candidates: set[float] = set()
    for i, case in enumerate(cases):
        for arm in SELECTABLE:
            x = _x(case, arm)
            if x is not None:
                candidates.add(
                    held_out[i].arms[arm].estimate(x, alpha=held_out[i].alpha)[1]
                )
    corpora = sorted({c.corpus for c in cases})
    for tau in sorted(candidates):
        sims = [
            simulate(c, _with_tau(held_out[i], tau), outcomes[i], mahc)
            for i, c in enumerate(cases)
        ]
        routed = [s.hit for s in sims]
        # A τ under which nothing stops before the L-pipe is uniform routing
        # under another name: it meets the tolerance trivially and is skipped.
        stops = sum(1 for s in sims if "lpipe" not in ARM_PIPELINES[s.terminal_arm])
        if stops and all(
            _hr([routed[i] for i, c in enumerate(cases) if c.corpus == k])
            >= _hr([uniform[i] for i, c in enumerate(cases) if c.corpus == k])
            - tolerance
            for k in corpora
        ):
            return tau
    return None


def fit_all(
    cases: Sequence[RouterCase],
    outcomes: Sequence[dict[Arm, int]],
    *,
    lam: float,
    alpha: float,
    tau: float,
    medians: Mapping[str, float],
    digest: str,
) -> RouterParams:
    """The frozen refit on every build case."""
    rows = _rows(cases, range(len(cases)), outcomes)
    return _params(
        {a: fit_arm(rows[a], lam) for a in SELECTABLE},
        lam=lam,
        alpha=alpha,
        tau=tau,
        medians=medians,
        digest=digest,
        provisional=False,
    )


def stage_medians(cases: Sequence[RouterCase]) -> dict[str, float]:
    """Per pipeline, the larger of the corpora's median latencies (design §5.4)."""
    out: dict[str, float] = {}
    for corpus in sorted({c.corpus for c in cases}):
        for name in ("dpipe", "gpipe", "lpipe"):
            values = [
                c.latency_ms[name]
                for c in cases
                if c.corpus == corpus and name in c.latency_ms
            ]
            if values:
                out[name] = max(out.get(name, 0), statistics.median(values))
    return out


def _rate(n: int, d: int) -> float | None:
    return round(n / d, _DIGITS) if d else None


def evaluate(
    cases: Sequence[RouterCase],
    held_out: Mapping[int, RouterParams],
    outcomes: Sequence[dict[Arm, int]],
    mahc: MAHCParams,
    tau: float | None,
) -> dict[str, Any]:
    """Held-out routed vs uniform per corpus (aggregates only, no incident ID)."""
    report: dict[str, Any] = {"tau_acc": tau, "tolerance": TOLERANCE, "by_corpus": {}}
    sims = (
        [
            simulate(c, _with_tau(held_out[i], tau), outcomes[i], mahc)
            for i, c in enumerate(cases)
        ]
        if tau is not None
        else []
    )
    for corpus in sorted({c.corpus for c in cases}):
        idx = [i for i, c in enumerate(cases) if c.corpus == corpus]
        uniform = [uniform_hit(cases[i], mahc) for i in idx]
        entry: dict[str, Any] = {
            "cases": len(idx),
            "uniform_hr3": round(_hr(uniform), _DIGITS),
            "arm_hr3": {
                a.value: round(
                    _hr([outcomes[i][a] for i in idx if a in outcomes[i]]), _DIGITS
                )
                for a in SELECTABLE
            },
        }
        if sims:
            s = [sims[i] for i in idx]
            escalated = [x for x in s if x.terminal_arm != x.stage1_arm]
            reasons: dict[str, int] = {}
            for x in s:
                reasons[x.reason] = reasons.get(x.reason, 0) + 1
            by_signal: dict[str, list[int]] = {}
            for i, x in zip(idx, s, strict=True):
                esc = int(x.terminal_arm != x.stage1_arm)
                by_signal.setdefault(cases[i].signal.value, []).append(esc)
            saved = [
                cases[i].latency_ms.get("lpipe", 0)
                for i, x in zip(idx, s, strict=True)
                if "lpipe" not in ARM_PIPELINES[x.terminal_arm]
            ]
            entry.update(
                {
                    "routed_hr3": round(_hr([x.hit for x in s]), _DIGITS),
                    "escalated_share": _rate(len(escalated), len(s)),
                    "terminal_arms": {
                        a.value: sum(1 for x in s if x.terminal_arm == a)
                        for a in SELECTABLE
                    },
                    "reasons": dict(sorted(reasons.items())),
                    "escalated_share_by_signal": {
                        k: _rate(sum(v), len(v)) for k, v in sorted(by_signal.items())
                    },
                    "gpipe_runs": sum(1 for x in s if x.g_ran),
                    "first_publication_median_ms": round(
                        statistics.median([x.first_ms for x in s]), 1
                    ),
                    "lpipe_calls_saved": len(saved),
                    "lpipe_seconds_saved": round(sum(saved) / 1_000, 1),
                }
            )
        report["by_corpus"][corpus] = entry
    return report
