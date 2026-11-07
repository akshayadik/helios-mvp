"""Two-stage reward replay on delayed labels (S3.3 design; deviation entry 74).

Ch3 Algorithm 1's learning path, exploratory only (E-H5). Build cases from the
S3.1 full-information pass are played as an incident stream through a thawed
copy of the router (the runtime ``decide_g`` / ``decide_escalation`` policy,
frozen τ_acc, λ and alpha). Rewards arrive on an injected clock:

- provisional r¹, 1-5 min after the decision: the frozen MAHC calibrated
  confidence of the published arm's fused list (no ground truth; none for a
  stop on D alone, R-e);
- terminal r², log-normal (mu_log 8.7, sigma_log 1.4, seconds) later: the HR@3 hit of
  that list.

Per published arm (stage 1 and, if escalated, terminal), ridge LinUCB:
on r¹ A += xxᵀ, b += r¹x; on r² b += (r² - r¹)x, or A += xxᵀ, b += r²x
without r¹. The terminal update is gated by ``reconcile_terminal``
(HELIOS-noReconcile has none, and writes no terminal record). Every update goes
through the reward ledger first, which refuses a repeated reward.

Starting state: a batch ridge fit (full information) on one half of the build
folds; the other half is streamed; then the halves swap (W-f). The confirmatory
router file and the run path are never touched.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import heapq
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from helios.consensus.calibration import features
from helios.consensus.mahc import Fusion, fuse
from helios.consensus.router_params import (
    ARM_PIPELINES,
    SELECTABLE,
    Arm,
    ArmModel,
    RouterParams,
)
from helios.evaluation.router_calibration import simulate
from helios.evaluation.scoring import score_ranking
from helios.orchestrator.reward_ledger import PROVISIONAL, TERMINAL
from helios.research.seeds import training_seed
from helios.vcl import VCLFlag, gated_by
from helios.vcl.decorators import GatedComponentInactiveError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from helios.consensus.params import MAHCParams
    from helios.evaluation.router_calibration import RouterCase
    from helios.orchestrator.reward_ledger import RewardLedger

__all__ = [
    "MEAN_GAPS_S",
    "R1_DELAY_S",
    "R2_MU_LOG",
    "R2_SIGMA_LOG",
    "SEED_SLOT",
    "STREAMS",
    "Decision",
    "StreamDraws",
    "ThawedRouter",
    "draws",
    "features_for",
    "full_information_rows",
    "halves",
    "provisional_reward",
    "reconcile",
    "replay",
    "rre",
    "terminal_reward",
]

HELIOS_ENABLE_REWARD_REPLAY: bool = True

# Entry 74 (4): the clock and the stream seeds.
R1_DELAY_S: tuple[int, int] = (60, 300)
R2_MU_LOG = 8.7
R2_SIGMA_LOG = 1.4
MEAN_GAPS_S: tuple[int, ...] = (3_600, 900, 14_400)  # primary, then sensitivity
STREAMS = 8
SEED_SLOT = "orar_prewarm_order"


def features_for(case: RouterCase, arm: Arm) -> tuple[float, ...] | None:
    """The features the runtime policy evaluates the arm on (S3.1 §5.1)."""
    if arm in (Arm.D, Arm.D_L):
        return case.x_cheap
    return case.x_dg


def _fusion(case: RouterCase, arm: Arm, mahc: MAHCParams) -> Fusion | None:
    votes = [case.votes[p] for p in ARM_PIPELINES[arm] if p in case.votes]
    if not votes:
        return None
    priors = {v.pipeline: mahc.priors.lookup(v.pipeline, case.signal)[0] for v in votes}
    return fuse(votes, priors)


def terminal_reward(case: RouterCase, arm: Arm, mahc: MAHCParams) -> int:
    """r²: HR@3 hit of the arm's fused list (an arm with a missing list fuses
    what there is, as the S3.1 simulation)."""
    fusion = _fusion(case, arm, mahc)
    if fusion is None or not fusion.ranked:
        return 0
    return score_ranking(list(fusion.ranked), case.root).hr_at_3


def provisional_reward(case: RouterCase, arm: Arm, mahc: MAHCParams) -> float | None:
    """r¹: the frozen MAHC calibrated confidence; None for D alone (R-e)."""
    if arm == Arm.D or mahc.calibrator is None:
        return None
    fusion = _fusion(case, arm, mahc)
    if fusion is None:
        return None
    return float(mahc.calibrator.predict(features(fusion)))


def halves(cases: Sequence[RouterCase]) -> tuple[list[int], list[int]]:
    """Two halves of whole (corpus, group) folds (W-f): within each corpus,
    groups largest first (ties by name), each to the currently smaller half."""
    out: tuple[list[int], list[int]] = ([], [])
    for corpus in sorted({c.corpus for c in cases}):
        groups: dict[str, list[int]] = {}
        for i, c in enumerate(cases):
            if c.corpus == corpus:
                groups.setdefault(c.group, []).append(i)
        sizes = [0, 0]
        for name in sorted(groups, key=lambda g: (-len(groups[g]), g)):
            side = 0 if sizes[0] <= sizes[1] else 1
            out[side].extend(groups[name])
            sizes[side] += len(groups[name])
    return sorted(out[0]), sorted(out[1])


class ThawedRouter:
    """Per-arm ridge state (A, b) on top of the frozen router's settings."""

    def __init__(
        self,
        frozen: RouterParams,
        rows: Mapping[Arm, Sequence[tuple[tuple[float, ...], float]]],
    ) -> None:
        d = len(frozen.feature_names)
        self._frozen = frozen
        self._cached: RouterParams | None = None
        self.a = {arm: frozen.lam * np.eye(d) for arm in SELECTABLE}
        self.b = {arm: np.zeros(d) for arm in SELECTABLE}
        self.n = dict.fromkeys(SELECTABLE, 0)
        for arm, arm_rows in rows.items():
            for x, r in arm_rows:
                self.add(arm, x, r, count=True)

    def add(self, arm: Arm, x: Sequence[float], r: float, *, count: bool) -> None:
        """b += r x; also A += x xᵀ when the case is new to the arm."""
        v = np.asarray(x, dtype=float)
        if count:
            self.a[arm] += np.outer(v, v)
            self.n[arm] += 1
        self.b[arm] += r * v
        self._cached = None

    def params(self) -> RouterParams:
        """The current state as router parameters (frozen τ, λ, alpha)."""
        if self._cached is None:
            arms = {}
            for arm in SELECTABLE:
                a_inv = np.linalg.inv(self.a[arm])
                arms[arm] = ArmModel(
                    a_inv=tuple(tuple(float(v) for v in row) for row in a_inv),
                    theta=tuple(float(v) for v in a_inv @ self.b[arm]),
                    n=self.n[arm],
                )
            self._cached = dataclasses.replace(self._frozen, arms=arms)
        return self._cached


def full_information_rows(
    cases: Sequence[RouterCase], idx: Sequence[int], mahc: MAHCParams
) -> dict[Arm, list[tuple[tuple[float, ...], float]]]:
    """Every arm's (features, r²) on the cases ``idx``: the batch pre-warm,
    the rows the S3.1 fit used (arms whose pipelines all gave a list)."""
    rows: dict[Arm, list[tuple[tuple[float, ...], float]]] = {a: [] for a in SELECTABLE}
    for i in idx:
        case = cases[i]
        for arm in SELECTABLE:
            x = features_for(case, arm)
            if x is not None and all(p in case.votes for p in ARM_PIPELINES[arm]):
                rows[arm].append((x, terminal_reward(case, arm, mahc)))
    return rows


@dataclass(frozen=True)
class StreamDraws:
    """One sub-stream's random draws, shared by every variant and gap."""

    order: tuple[int, ...]
    gaps: tuple[float, ...]  # standard exponential; scaled by the mean gap
    r1_delay_s: tuple[float, ...]
    r2_delay_s: tuple[float, ...]


def draws(
    stream: int, halves_: tuple[list[int], list[int]]
) -> tuple[StreamDraws, StreamDraws]:
    """Both sub-streams of one stream (streamed half 1, then half 0), from
    ``training_seed(SEED_SLOT, stream)``."""
    rng = np.random.default_rng(training_seed(SEED_SLOT, stream))
    out = []
    for streamed in (halves_[1], halves_[0]):
        n = len(streamed)
        order = tuple(int(streamed[k]) for k in rng.permutation(n))
        out.append(
            StreamDraws(
                order=order,
                gaps=tuple(float(v) for v in rng.standard_exponential(n)),
                r1_delay_s=tuple(float(v) for v in rng.uniform(*R1_DELAY_S, n)),
                r2_delay_s=tuple(
                    float(v) for v in rng.lognormal(R2_MU_LOG, R2_SIGMA_LOG, n)
                ),
            )
        )
    return out[0], out[1]


@dataclass(frozen=True)
class Decision:
    """One streamed case: the thawed router's decision and its rewards."""

    position: int
    case: int
    corpus: str
    stage1_arm: Arm
    terminal_arm: Arm
    escalated: bool
    hit: int
    r1: float | None  # of the terminal arm
    r2: int  # of the terminal arm


@dataclass(order=True)
class _Event:
    time_s: float
    seq: int
    case: int = dataclasses.field(compare=False)
    arm: Arm = dataclasses.field(compare=False)
    stage: str = dataclasses.field(compare=False)
    reward: float = dataclasses.field(compare=False)
    r1: float | None = dataclasses.field(compare=False)


def _x_sha(x: Sequence[float]) -> str:
    text = ",".join(f"{v:.6f}" for v in x)
    return hashlib.sha256(text.encode("ascii")).hexdigest()[:16]


@gated_by(VCLFlag.RECONCILE_TERMINAL)
def reconcile(
    router: ThawedRouter,
    ledger: RewardLedger,
    fields: dict[str, Any],
    arm: Arm,
    x: Sequence[float],
    r2: float,
    r1: float | None,
) -> None:
    """The terminal record and compensating update (gated: noReconcile
    writes none and applies none)."""
    ledger.record({**fields, "reconcile_terminal": True})
    if r1 is None:
        router.add(arm, x, r2, count=True)
    else:
        router.add(arm, x, r2 - r1, count=False)


def replay(
    cases: Sequence[RouterCase],
    outcomes: Sequence[Mapping[Arm, int]],
    stream: StreamDraws,
    router: ThawedRouter,
    mahc: MAHCParams,
    ledger: RewardLedger,
    *,
    variant: str,
    label: str,
    mean_gap_s: float,
    counts: dict[str, int] | None = None,
) -> list[Decision]:
    """Play one sub-stream; every reward event is drained at the end.

    Callers set the variant's manifest (routed; ``reconcile_terminal`` decides
    whether terminal rewards are recorded and applied). A terminal reward that
    arrives before its provisional one applies whole, and the late provisional
    is superseded: neither recorded nor applied (entry 75); ``counts`` gets
    ``superseded`` added.
    """
    queue: list[_Event] = []
    seq = 0
    decisions: list[Decision] = []
    applied_r1: dict[tuple[int, Arm], float] = {}
    closed: set[tuple[int, Arm]] = set()
    tally = counts if counts is not None else {}
    tally.setdefault("superseded", 0)

    def apply(event: _Event) -> None:
        case = cases[event.case]
        x = features_for(case, event.arm)
        assert x is not None  # only published arms with features are queued
        fields = {
            "variant": variant,
            "stream": label,
            "case_id": case.incident_id,
            "arm": event.arm.value,
            "stage": event.stage,
            "reward": event.reward,
            "event_s": round(event.time_s, 3),
            "x_sha": _x_sha(x),
        }
        key = (event.case, event.arm)
        if event.stage == PROVISIONAL:
            if key in closed:  # the label came first: nothing left to estimate
                tally["superseded"] += 1
                return
            ledger.record(fields)
            router.add(event.arm, x, event.reward, count=True)
            applied_r1[key] = event.reward
            return
        r1 = applied_r1.get(key)
        terminal = {**fields, "provisional_reward": r1}
        if r1 is None and event.r1 is not None:
            terminal["superseded"] = True
        # HELIOS-noReconcile: no terminal record, no update.
        with contextlib.suppress(GatedComponentInactiveError):
            reconcile(router, ledger, terminal, event.arm, x, event.reward, r1)
            closed.add(key)

    t: float = 0
    for pos, i in enumerate(stream.order):
        if pos:
            t += stream.gaps[pos - 1] * mean_gap_s
        while queue and queue[0].time_s <= t:
            apply(heapq.heappop(queue))
        case = cases[i]
        sim = simulate(case, router.params(), outcomes[i], mahc)
        published = [sim.stage1_arm]
        if sim.terminal_arm != sim.stage1_arm:
            published.append(sim.terminal_arm)
        rewards: dict[Arm, tuple[float | None, int]] = {}
        for arm in published:
            r1 = provisional_reward(case, arm, mahc)
            r2 = terminal_reward(case, arm, mahc)
            rewards[arm] = (r1, r2)
            if features_for(case, arm) is None:
                continue
            if r1 is not None:
                seq += 1
                when = t + stream.r1_delay_s[pos]
                heapq.heappush(queue, _Event(when, seq, i, arm, PROVISIONAL, r1, None))
            seq += 1
            when = t + stream.r2_delay_s[pos]
            heapq.heappush(queue, _Event(when, seq, i, arm, TERMINAL, r2, r1))
        r1_t, r2_t = rewards[sim.terminal_arm]
        decisions.append(
            Decision(
                position=pos,
                case=i,
                corpus=case.corpus,
                stage1_arm=sim.stage1_arm,
                terminal_arm=sim.terminal_arm,
                escalated=sim.terminal_arm != sim.stage1_arm,
                hit=sim.hit,
                r1=r1_t,
                r2=r2_t,
            )
        )
    while queue:
        apply(heapq.heappop(queue))
    return decisions


def rre(decision: Decision, tau: float) -> int | None:
    """1 when r¹ and r² fall on different sides of τ_acc; None without r¹."""
    if decision.r1 is None:
        return None
    return int((decision.r1 >= tau) != (decision.r2 >= tau))
