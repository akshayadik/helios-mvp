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

Corpus v2 (``otel_build_v2``, S2.1 recapture, 2026-10-27): the normal period
varies per case between ``PRE_S_MIN`` and ``PRE_S_MAX`` (15 s steps), derived
from the case's opaque ID — deterministic and label-free — so the onset no
longer sits at a fixed position in the window (validity threat T19) and the
label-free detector has enough history. The v1 corpus (fixed ``PRE_S``) is
kept unchanged.

Corpus v3 (``otel_build_v3``, S2-M7-ENG10, 2026-10-28): as v2, with the logs'
service and severity captured (the earlier fetcher misread them), per-service
span metrics in place of the latency histograms, and the load generator held
at ``LOAD_USERS_V3`` users, checked before every case (the demo's default 5
users gave payment about half a request a minute: too few for any detector).
``otel_pilot_v3`` is the same protocol under its own IDs, for the pilot.
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
    "CORPUS_PILOT_V3",
    "CORPUS_V2",
    "CORPUS_V3",
    "DEFAULT_REPS",
    "FAULTS",
    "INGEST_LAG_S",
    "LOAD_USERS_V3",
    "POST_S",
    "PRE_S",
    "PRE_S_MAX",
    "PRE_S_MIN",
    "PRE_S_STEP",
    "RECOVERY_S",
    "SLICE_S",
    "Campaign",
    "FaultSpec",
    "FlagdFile",
    "GroundTruthFile",
    "PlannedCase",
    "load_users_for",
    "opaque_id",
    "plan",
    "pre_s_for",
]

HELIOS_ENABLE_OTEL_CAMPAIGN: bool = True

CORPUS = "otel_build"
CORPUS_V2 = "otel_build_v2"
CORPUS_V3 = "otel_build_v3"
CORPUS_PILOT_V3 = "otel_pilot_v3"
_VARIED_PRE = (CORPUS_V2, CORPUS_V3, CORPUS_PILOT_V3)
LOAD_USERS_V3 = 25  # owner decision 2026-10-28
# The OTel Demo's registered opaque-ID slot. Adding a slot would change the
# seed register deposited at OSF (deposit 1); case names carry the corpus.
_OPAQUE_SLOT = "otel_exploratory"
DEFAULT_REPS = 7
PRE_S = 300  # normal traffic before the onset (v1)
PRE_S_MIN = 480  # v2: varied normal period, 8 to 15 minutes in 15 s steps
PRE_S_MAX = 900
PRE_S_STEP = 15
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
    pre_s: int = PRE_S


def pre_s_for(incident_id: str) -> int:
    """v2 normal period of a case, from its opaque ID (label-free, deterministic)."""
    steps = (PRE_S_MAX - PRE_S_MIN) // PRE_S_STEP + 1
    return PRE_S_MIN + (int(incident_id[:8], 16) % steps) * PRE_S_STEP


def load_users_for(corpus: str) -> int | None:
    """Load-generator users a corpus is captured at; None = not enforced (v1, v2)."""
    return LOAD_USERS_V3 if corpus in (CORPUS_V3, CORPUS_PILOT_V3) else None


def opaque_id(case: str) -> str:
    """128-bit opaque incident ID (32 hex digits) from the registered OTel seed."""
    seed = opaque_id_seed(_OPAQUE_SLOT)
    return hashlib.sha256(f"{seed}:{case}".encode()).hexdigest()[:32]


def plan(
    reps: int = DEFAULT_REPS,
    *,
    corpus: str = CORPUS,
    faults: Sequence[str] | None = None,
) -> list[PlannedCase]:
    """Rep-major schedule: every fault once per repetition, variants rotated.

    ``corpus`` v2 and later give each case its own normal period
    (``pre_s_for``); ``faults`` keeps only the named flags (pilots).
    """
    if reps < 1:
        raise ValueError("reps must be >= 1")
    if corpus not in (CORPUS, *_VARIED_PRE):
        raise ValueError(f"unknown campaign corpus {corpus!r}")
    known = {f.flag for f in FAULTS}
    if faults is not None and not set(faults) <= known:
        raise ValueError(f"unknown fault(s) {sorted(set(faults) - known)}")
    chosen = [f for f in FAULTS if faults is None or f.flag in faults]
    cases = []
    for r in range(1, reps + 1):
        for f in chosen:
            variant = f.variants[(r - 1) % len(f.variants)]
            case = f"{corpus}/{f.flag}/{variant}/r{r:02d}"
            incident_id = opaque_id(case)
            pre = pre_s_for(incident_id) if corpus in _VARIED_PRE else PRE_S
            cases.append(PlannedCase(case, incident_id, f, variant, r, pre))
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

    def __init__(
        self, path: Path, key: bytes, *, demo_commit: str, corpus: str = CORPUS
    ) -> None:
        self._path = path
        self._key = key
        self._demo_commit = demo_commit
        self._corpus = corpus

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
            "corpus": self._corpus,
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
    check_load: Callable[[], None] = lambda: None  # raises when the load is wrong
    load_users: int | None = None  # recorded with each label when enforced

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
        self.check_load()
        self.log(f"[campaign] case {position}/{total}: normal period ({case.pre_s}s)")
        self.sleep(RECOVERY_S + case.pre_s)
        self.flagd.set(f.flag, case.variant)
        self._wait_for_flag(f.flag, case.variant)
        inject = self.clock()
        self.log(f"[campaign] case {position}/{total}: fault active ({POST_S}s)")
        self.sleep(POST_S)
        self.flagd.set(f.flag, _OFF)
        self._wait_for_flag(f.flag, _OFF)
        self.sleep(INGEST_LAG_S)
        start = inject - timedelta(seconds=case.pre_s)
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
                **({"load_users": self.load_users} if self.load_users else {}),
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
