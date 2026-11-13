"""Campaign schedule (S4.10 O-a, O-b, O-g, O-h; deviation entry 87).

A schedule is a pure function of one sealed corpus manifest's ``case_order``,
the case -> system (application) map, the variant catalogue and the baseline
slots. The same inputs give byte-identical JSON and the same digest, which every
run records.

Order (O-b): phases run in order; inside a phase, case by case in the frozen
``case_order``; inside a case, HELIOS-noRouter first (its L-pipe calls fill the
response cache whose wall times every later variant replays), then the other
variants in Ch3 Table 17 order.

Subsets (O-g): the case order is the sorted list of opaque IDs, which are drawn
from the seed register, so a fixed stride through each system's cases is a
seeded random sample and needs no new seed block. The determinism rerun takes
every 10th case of each system, the E-H5 delayed-label subset every 4th.

schedule-v2 (S4.8, design B-b and B-g): the baselines run a second time with
HELIOS's detection-trigger time instead of the injection time
(``baseline_trigger``, a sensitivity row under the same seed), and the
determinism rerun also covers the baselines (RCD is stochastic).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from helios.research.analysis_plan import BASELINES
from helios.research.seeds import RUN_SYSTEM_SLOTS, run_seed
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.variants import CONFIRMATORY_VARIANTS, EXPLORATORY_VARIANTS

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "BASELINE_SLOTS",
    "EH5_STRIDE",
    "FIRST_VARIANT",
    "RERUN_STRIDE",
    "SCHEDULE_VERSION",
    "TRIGGER_SUFFIX",
    "CacheMode",
    "Phase",
    "RunSpec",
    "Schedule",
    "build_schedule",
    "confirmatory_order",
    "scheduled_by_system",
    "stride_subset",
    "system_name",
]

HELIOS_ENABLE_ORCHESTRATOR: bool = True

SCHEDULE_VERSION = "schedule-v2"
FIRST_VARIANT = "HELIOS-noRouter"
RERUN_STRIDE = 10
EH5_STRIDE = 4
TRIGGER_SUFFIX = " [trigger time]"  # analysis name suffix of baseline_trigger runs
BASELINE_SLOTS: tuple[str, ...] = tuple(
    s for s in RUN_SYSTEM_SLOTS if s.startswith("BASELINE-")
)


class Phase(StrEnum):
    """Campaign phases with run specs, in execution order (O-a)."""

    CONFIRMATORY = "confirmatory"
    BASELINE = "baseline"
    EXPLORATORY = "exploratory"
    BASELINE_TRIGGER = "baseline_trigger"  # B-b sensitivity: trigger time
    RERUN = "rerun"


class CacheMode(StrEnum):
    """Whether a run may use the shared L-pipe response cache."""

    SHARED = "shared"
    BYPASS = "bypass"  # the determinism rerun (D11 §4)


@dataclass(frozen=True)
class RunSpec:
    """One scheduled run."""

    position: int
    phase: str
    case: str
    app: str  # the benchmark system of the case (e.g. OB, TT)
    system: str  # variant or baseline slot (seed register naming)
    seed: int
    cache: str

    @property
    def key(self) -> str:
        """Unique within a schedule."""
        return f"{self.phase}/{self.case}/{self.system}"

    def run_id(self, digest: str, attempt: int) -> str:
        """Deterministic run id (O-a): the same spec and attempt, the same id."""
        raw = f"{digest}|{self.key}|{attempt}".encode()
        return hashlib.sha256(raw).hexdigest()[:32]


@dataclass(frozen=True)
class Schedule:
    """A frozen campaign schedule for one corpus."""

    corpus: str
    case_order: tuple[str, ...]
    apps: dict[str, str]
    specs: tuple[RunSpec, ...]
    refused: dict[str, str] = field(default_factory=dict)
    rerun_cases: tuple[str, ...] = ()
    eh5_cases: tuple[str, ...] = ()

    def body(self) -> dict[str, Any]:
        """Everything the digest covers."""
        return {
            "version": SCHEDULE_VERSION,
            "corpus": self.corpus,
            "case_order": list(self.case_order),
            "apps": dict(sorted(self.apps.items())),
            "refused": dict(sorted(self.refused.items())),
            "rerun_cases": list(self.rerun_cases),
            "eh5_cases": list(self.eh5_cases),
            "specs": [asdict(s) for s in self.specs],
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(_canonical(self.body())).hexdigest()

    def to_json(self) -> str:
        return json.dumps({**self.body(), "digest": self.digest}, indent=1) + "\n"

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for spec in self.specs:
            out[spec.phase] = out.get(spec.phase, 0) + 1
        return out


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def confirmatory_order() -> list[str]:
    """HELIOS-noRouter first, then Ch3 Table 17 order (O-b)."""
    rest = [v for v in CONFIRMATORY_VARIANTS if v != FIRST_VARIANT]
    return [FIRST_VARIANT, *rest]


def stride_subset(
    case_order: Sequence[str], apps: Mapping[str, str], stride: int
) -> tuple[str, ...]:
    """Every ``stride``-th case of each system, in case order (O-g).

    Positions stride - 1, 2 * stride - 1, ... of each system's own sub-order,
    returned in the overall case order.
    """
    if stride < 1:
        raise ValueError("stride must be positive")
    seen: dict[str, int] = {}
    chosen: list[str] = []
    for case in case_order:
        app = apps[case]
        seen[app] = seen.get(app, 0) + 1
        if seen[app] % stride == 0:
            chosen.append(case)
    return tuple(chosen)


def _calls_model(name: str) -> bool:
    manifest = {**CONFIRMATORY_VARIANTS, **EXPLORATORY_VARIANTS}[name]
    return bool(manifest.l2c_llm)


def build_schedule(
    corpus: str,
    case_order: Sequence[str],
    apps: Mapping[str, str],
    *,
    refused: Mapping[str, str],
    baselines: Sequence[str] = BASELINE_SLOTS,
) -> Schedule:
    """The full campaign schedule of one corpus.

    ``refused`` maps exploratory variants to the reason they are left out
    (``helios.vcl.catalog.unconsumed_variants``). A refused confirmatory
    variant is an error: the campaign cannot run without it.
    """
    order = tuple(case_order)
    if len(set(order)) != len(order):
        raise ValueError("case_order contains duplicate case IDs")
    missing = [c for c in order if c not in apps]
    if missing:
        raise ValueError(f"{len(missing)} cases have no system")
    bad = sorted(set(refused) & set(CONFIRMATORY_VARIANTS))
    if bad:
        raise ValueError(f"confirmatory variants cannot be refused: {bad}")
    unknown = sorted(set(baselines) - set(BASELINE_SLOTS))
    if unknown:
        raise ValueError(f"unregistered baseline slots: {unknown}")
    exploratory = [v for v in EXPLORATORY_VARIANTS if v not in refused]
    rerun_cases = stride_subset(order, apps, RERUN_STRIDE)
    plan: list[tuple[str, Sequence[str], Sequence[str], str]] = [
        (Phase.CONFIRMATORY, order, confirmatory_order(), CacheMode.SHARED),
        (Phase.BASELINE, order, list(baselines), CacheMode.SHARED),
        (Phase.EXPLORATORY, order, exploratory, CacheMode.SHARED),
        (Phase.BASELINE_TRIGGER, order, list(baselines), CacheMode.SHARED),
        (
            Phase.RERUN,
            rerun_cases,
            [
                *(v for v in (*confirmatory_order(), *exploratory) if _calls_model(v)),
                *baselines,
            ],
            CacheMode.BYPASS,
        ),
    ]
    specs: list[RunSpec] = []
    for phase, cases, systems, cache in plan:
        for case in cases:
            for system in systems:
                specs.append(
                    RunSpec(
                        position=len(specs),
                        phase=str(phase),
                        case=case,
                        app=apps[case],
                        system=system,
                        seed=run_seed(case, system, case_order=order),
                        cache=str(cache),
                    )
                )
    return Schedule(
        corpus=corpus,
        case_order=order,
        apps={c: apps[c] for c in order},
        specs=tuple(specs),
        refused=dict(refused),
        rerun_cases=rerun_cases,
        eh5_cases=stride_subset(order, apps, EH5_STRIDE),
    )


def system_name(slot: str) -> str:
    """The analysis name of a schedule system: baseline slots map to the
    registered baseline names (``BASELINE-k`` -> ``BASELINES[k - 1]``)."""
    if slot in BASELINE_SLOTS:
        return BASELINES[BASELINE_SLOTS.index(slot)]
    return slot


def scheduled_by_system(body: Mapping[str, Any]) -> dict[str, list[str]]:
    """System name -> its scheduled cases, from a ``schedule.json`` body.

    The determinism rerun is not a scheduled case of the analysis; a
    trigger-time baseline run counts under its suffixed name.
    """
    out: dict[str, list[str]] = {}
    for spec in body["specs"]:
        if spec["phase"] == Phase.RERUN:
            continue
        name = system_name(str(spec["system"]))
        if spec["phase"] == Phase.BASELINE_TRIGGER:
            name += TRIGGER_SUFFIX
        out.setdefault(name, []).append(str(spec["case"]))
    return out
