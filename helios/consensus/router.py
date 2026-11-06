"""Cheap-first router (S3.1 design §5.1, §5.4; Ch3 Algorithm 1, IN3).

Two decisions per routed run, both deterministic functions of the incident's
features and the frozen parameters (static policy, Ch3 p.114):

1. **G decision**, after the D-pipe. D is cheaper than D+G, so G-pipe runs
   exactly when a graph exists and D alone is infeasible. It needs only the D
   arm's model on the features known before G-pipe runs.
2. **Escalation**, after the cheap stage. Escalate to the L-pipe when D and G
   both ran and their top-1s differ (by rule, IN3), or the cheap arm is
   infeasible. The target is D+L without G-pipe, Full with it; if the target
   is infeasible too, the run still goes to Full and records
   ``constraint_empty`` (Ch3's fallback).

An arm is feasible when its lower bound reaches τ_acc and its staged
build-median finish is within the 90 s convergence bound (τ_lat). With no
τ_acc (provisional parameters) nothing is feasible, so every run goes to Full.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from helios.consensus.router_params import ARM_PIPELINES, Arm
from helios.consensus.timing import CONVERGE_MS
from helios.vcl import VCLFlag, gated_by

if TYPE_CHECKING:
    from collections.abc import Sequence

    from helios.consensus.router_params import RouterParams

__all__ = [
    "Escalation",
    "Feasibility",
    "GDecision",
    "decide_escalation",
    "decide_g",
    "feasible",
]

HELIOS_ENABLE_ROUTER: bool = True

Reason = Literal[
    "disagreement", "low_confidence", "none", "llm_off", "constraint_empty"
]


@dataclass(frozen=True)
class Feasibility:
    """One arm's estimate and whether it meets both constraints."""

    p: float
    lcb: float
    finish_ms: float
    feasible: bool


@dataclass(frozen=True)
class GDecision:
    """Whether G-pipe runs, and why."""

    run_g: bool
    reason: Literal["no_graph", "d_feasible", "d_infeasible"]
    estimates: dict[str, list[float]] = field(default_factory=dict)


@dataclass(frozen=True)
class Escalation:
    """Whether the L-pipe runs, the arms before and after, and why.

    ``wanted`` is the reason the router would have escalated when the L-pipe
    is off (``reason`` is then ``llm_off``); otherwise it equals ``reason``.
    """

    escalate: bool
    reason: Reason
    wanted: Reason
    stage1_arm: Arm
    terminal_arm: Arm
    estimates: dict[str, list[float]] = field(default_factory=dict)


def feasible(arm: Arm, x: Sequence[float], params: RouterParams) -> Feasibility:
    """The arm's (p, lower bound), staged finish and feasibility."""
    p, lcb = params.arms[arm].estimate(x, alpha=params.alpha)
    finish = sum(params.stage_median_ms.get(name, 0) for name in ARM_PIPELINES[arm])
    ok = params.tau_acc is not None and lcb >= params.tau_acc and finish <= CONVERGE_MS
    return Feasibility(p, lcb, finish, ok)


def _record(f: Feasibility) -> list[float]:
    return [f.p, f.lcb]


@gated_by(VCLFlag.CBR_ROUTING)
def decide_g(x: Sequence[float], params: RouterParams, *, graph: bool) -> GDecision:
    """Run G-pipe when a graph exists and D alone is infeasible."""
    if not graph:
        return GDecision(run_g=False, reason="no_graph")
    d = feasible(Arm.D, x, params)
    return GDecision(
        run_g=not d.feasible,
        reason="d_feasible" if d.feasible else "d_infeasible",
        estimates={Arm.D.value: _record(d)},
    )


@gated_by(VCLFlag.CBR_ROUTING)
def decide_escalation(
    x: Sequence[float],
    params: RouterParams,
    *,
    g_ran: bool,
    d_top: str | None,
    g_top: str | None,
    llm_on: bool,
) -> Escalation:
    """Stop on the cheap arm or escalate to the L-pipe (design §5.1 step 4)."""
    cheap = Arm.D_G if g_ran else Arm.D
    target = Arm.FULL if g_ran else Arm.D_L
    c = feasible(cheap, x, params)
    t = feasible(target, x, params)
    estimates = {cheap.value: _record(c), target.value: _record(t)}

    wanted: Reason
    if g_ran and d_top is not None and g_top is not None and d_top != g_top:
        wanted = "disagreement"
    elif c.feasible:
        wanted = "none"
    elif t.feasible:
        wanted = "low_confidence"
    else:
        wanted = "constraint_empty"

    if wanted == "none":
        return Escalation(False, "none", "none", cheap, cheap, estimates)
    if not llm_on:
        return Escalation(False, "llm_off", wanted, cheap, cheap, estimates)
    terminal = Arm.FULL if wanted == "constraint_empty" else target
    return Escalation(True, wanted, wanted, cheap, terminal, estimates)
