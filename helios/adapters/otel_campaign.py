"""OTel Demo build-capture campaign (S1.2): trace-bearing build data.

Each case records ten minutes of the pinned OpenTelemetry Demo (v2.2.0):
``PRE_S`` of normal traffic, then one fault flag switched on through flagd
for ``POST_S``. The window holds the fault onset, as the RCAEval windows do,
so a label-free detector (S2.1) and the graph ranker (S2.2) can be built on
it. The injection time and the fault go only into the signed ground truth,
never into the window.

Build data only (D11): the captures live in ``data/otel/build/`` under opaque
incident IDs, apart from the exploratory captures (``data/captures/``, part
of OSF deposit 1), and are never confirmatory.

Fault set: the demo flags whose fault sits in one identifiable service. Flags
whose root cause is split or not a service (kafkaQueueProblems,
imageSlowLoad, loadGeneratorFloodHomepage, llm*, failedReadinessProbe) are
left out. Cases run rep-major (every fault once, then again), with flag
variants rotated across repetitions, so a stopped campaign stays balanced.

All side effects (clock, sleep, flag file, flag check, capture, container
restart) are injected, so the schedule is testable without the demo running.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from helios.adapters.rcaeval import verify_ground_truth
from helios.research.seeds import opaque_id_seed
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

__all__ = [
    "CORPUS",
    "DEFAULT_REPS",
    "FAULTS",
    "INGEST_LAG_S",
    "POST_S",
    "PRE_S",
    "RECOVERY_S",
    "SLICE_S",
    "Campaign",
    "FaultSpec",
    "FlagdFile",
    "GroundTruthFile",
    "PlannedCase",
    "opaque_id",
    "plan",
]

HELIOS_ENABLE_OTEL_CAMPAIGN: bool = True

CORPUS = "otel_build"
# The OTel Demo's registered opaque-ID slot. Adding a slot would change the
# seed register deposited at OSF (deposit 1); case names carry the corpus.
_OPAQUE_SLOT = "otel_exploratory"
DEFAULT_REPS = 7
PRE_S = 300  # normal traffic before the onset
POST_S = 300  # fault active
RECOVERY_S = 60  # flag off (and restart) before the next case's normal period
INGEST_LAG_S = 60  # let exporters and scrapes catch up before querying
SLICE_S = 60  # trace and log query slices
FLAG_CONFIRM_S = 30
_OFF = "off"


@dataclass(frozen=True)
class FaultSpec:
    """One demo fault flag and the service it injects into."""

    flag: str
    root_cause_service: str  # Jaeger service name = UEG-C node name
    fault_class: str
    variants: tuple[str, ...]
    restart_after: bool = False  # the fault leaves state behind (memory)


FAULTS: tuple[FaultSpec, ...] = (
    FaultSpec("adHighCpu", "ad", "resource", ("on",)),
    FaultSpec("adManualGc", "ad", "resource", ("on",)),
    FaultSpec("adFailure", "ad", "code", ("on",)),
    FaultSpec("cartFailure", "cart", "code", ("on",)),
    FaultSpec("paymentFailure", "payment", "code", ("90%", "75%", "50%")),
    # checkout dials a bad payment address: the fault is checkout's.
    FaultSpec("paymentUnreachable", "checkout", "dependency", ("on",)),
    FaultSpec("productCatalogFailure", "product-catalog", "code", ("on",)),
    FaultSpec("recommendationCacheFailure", "recommendation", "dependency", ("on",)),
    FaultSpec("emailMemoryLeak", "email", "resource", ("10x",), restart_after=True),
)


@dataclass(frozen=True)
class PlannedCase:
    """One case of the campaign; ``case`` is label-bearing, ``incident_id`` opaque."""

    case: str
    incident_id: str
    fault: FaultSpec
    variant: str
    repetition: int


def opaque_id(case: str) -> str:
    """128-bit opaque incident ID (32 hex digits) from the registered OTel seed."""
    seed = opaque_id_seed(_OPAQUE_SLOT)
    return hashlib.sha256(f"{seed}:{case}".encode()).hexdigest()[:32]


def plan(reps: int = DEFAULT_REPS) -> list[PlannedCase]:
    """Rep-major schedule: every fault once per repetition, variants rotated."""
    if reps < 1:
        raise ValueError("reps must be >= 1")
    cases = []
    for r in range(1, reps + 1):
        for f in FAULTS:
            variant = f.variants[(r - 1) % len(f.variants)]
            case = f"{CORPUS}/{f.flag}/{variant}/r{r:02d}"
            cases.append(PlannedCase(case, opaque_id(case), f, variant, r))
    return cases


class FlagdFile:
    """The demo's flagd definition file (bind-mounted; flagd watches it).

    Written in place, never replaced, so the bind mount keeps the same inode.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def _load(self) -> dict[str, Any]:
        doc: dict[str, Any] = json.loads(self._path.read_text(encoding="utf-8"))
        return doc

    def _save(self, doc: dict[str, Any]) -> None:
        with self._path.open("r+", encoding="utf-8") as fh:
            fh.write(json.dumps(doc, indent=2) + "\n")
            fh.truncate()

    def state(self) -> dict[str, str]:
        return {k: str(v["defaultVariant"]) for k, v in self._load()["flags"].items()}

    def set(self, flag: str, variant: str) -> None:
        doc = self._load()
        spec = doc["flags"].get(flag)
        if spec is None:
            raise KeyError(f"unknown flag {flag!r}")
        if variant not in spec["variants"]:
            raise ValueError(f"{flag} has no variant {variant!r}")
        spec["defaultVariant"] = variant
        self._save(doc)

    def all_off(self) -> None:
        doc = self._load()
        for spec in doc["flags"].values():
            if _OFF in spec["variants"]:
                spec["defaultVariant"] = _OFF
        self._save(doc)


def _canonical(obj: Any) -> bytes:
    # Same canonical form as helios.adapters.rcaeval (verify_ground_truth).
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


class GroundTruthFile:
    """HMAC-signed ground truth of the campaign, re-signed after every case.

    Same layout as the RCAEval ground truth, so ``verify_ground_truth`` and
    the scoring path read it unchanged.
    """

    def __init__(self, path: Path, key: bytes, *, demo_commit: str) -> None:
        self._path = path
        self._key = key
        self._demo_commit = demo_commit

    def cases(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        return dict(verify_ground_truth(self._path, self._key))

    def add(self, incident_id: str, entry: dict[str, Any]) -> None:
        cases = self.cases()
        if incident_id in cases:
            raise ValueError("case already labelled; ground truth is append-only")
        cases[incident_id] = entry
        body = {
            "kind": "otel-ground-truth",
            "corpus": CORPUS,
            "demo_commit": self._demo_commit,
            "cases": cases,
        }
        signature = hmac.new(self._key, _canonical(body), hashlib.sha256).hexdigest()
        text = json.dumps({**body, "signature": signature}, sort_keys=True, indent=2)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(text + "\n", encoding="utf-8")
        tmp.replace(self._path)


@dataclass
class Campaign:
    """Runs planned cases: normal period → flag on → fault period → capture."""

    cases: Sequence[PlannedCase]
    captures_dir: Path
    flagd: FlagdFile
    ground_truth: GroundTruthFile
    capture: Callable[[PlannedCase, datetime, datetime], None]
    confirm_flag: Callable[[str, str], bool]
    restart: Callable[[str], None]
    sleep: Callable[[float], None]
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    log: Callable[[str], None] = print

    def pending(self) -> list[PlannedCase]:
        done = self.ground_truth.cases()
        return [c for c in self.cases if c.incident_id not in done]

    def _wait_for_flag(self, flag: str, variant: str) -> None:
        for _ in range(FLAG_CONFIRM_S):
            if self.confirm_flag(flag, variant):
                return
            self.sleep(1)
        raise RuntimeError(
            f"flagd did not serve {flag}={variant} within {FLAG_CONFIRM_S}s"
        )

    def run_case(self, case: PlannedCase, position: int, total: int) -> None:
        f = case.fault
        partial = self.captures_dir / case.incident_id
        if partial.exists():  # an interrupted, unlabelled capture: start again
            shutil.rmtree(partial)
        self.log(f"[campaign] case {position}/{total}: normal period ({PRE_S}s)")
        self.sleep(RECOVERY_S + PRE_S)
        self.flagd.set(f.flag, case.variant)
        self._wait_for_flag(f.flag, case.variant)
        inject = self.clock()
        self.log(f"[campaign] case {position}/{total}: fault active ({POST_S}s)")
        self.sleep(POST_S)
        self.flagd.set(f.flag, _OFF)
        self._wait_for_flag(f.flag, _OFF)
        self.sleep(INGEST_LAG_S)
        start = inject - timedelta(seconds=PRE_S)
        end = inject + timedelta(seconds=POST_S)
        self.capture(case, start, end)
        self.ground_truth.add(
            case.incident_id,
            {
                "case": case.case,
                "root_cause_service": f.root_cause_service,
                "fault": f.flag,
                "fault_variant": case.variant,
                "fault_class": f.fault_class,
                "repetition": case.repetition,
                "inject_time": inject.isoformat(),
                "window_start": start.isoformat(),
                "window_end": end.isoformat(),
            },
        )
        if f.restart_after:
            self.restart(f.root_cause_service)
        self.log(f"[campaign] case {position}/{total}: captured and labelled")

    def run(self, limit: int | None = None) -> int:
        """Run pending cases (at most ``limit``); returns how many were captured."""
        pending = self.pending()
        todo = pending[:limit] if limit is not None else pending
        done = len(self.cases) - len(pending)
        self.flagd.all_off()
        captured = 0
        try:
            for i, case in enumerate(todo, start=1):
                self.run_case(case, done + i, len(self.cases))
                captured += 1
        finally:
            self.flagd.all_off()
        return captured
