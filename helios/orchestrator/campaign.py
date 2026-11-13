"""Campaign execution: outcomes, retries and resume (S4.10 O-c, O-i; entry 87).

A campaign runs one frozen ``Schedule`` through one executor per system
(a HELIOS variant's ``RunOrchestrator`` or a baseline adapter). Every step is
appended to ``campaign_log.jsonl`` in the campaign directory, so an interrupted
campaign resumes from its log.

Outcomes (O-c):
- passed / excluded: what the executor's integrity gate decided;
- retry: an infrastructure error (decided by the exception class, never by the
  result), at most ``MAX_RETRIES`` times, then an exclusion;
- excluded with ``run_error``: any other exception; the campaign continues;
- stop: configuration refusals propagate and stop the campaign; they are setup
  faults, not missing data.

A run that started and has no final record (the process died) is discarded
from the result store and re-run from scratch under its next attempt number.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from helios.baselines.container import BaselineConfigError
from helios.orchestrator.runner import (
    MissingSigningKeyError,
    RouterParamsMismatchError,
)
from helios.pipelines.l_pipe.ollama_client import (
    OllamaConnectionError,
    OllamaResponseError,
    OllamaTimeoutError,
)
from helios.pipelines.l_pipe.pipeline import ModelMismatchError, ProvisionalPromptError
from helios.telemetry.pool_lock import PoolLockedError
from helios.telemetry.trigger import (
    ExternalTriggerRefusedError,
    ProvisionalParametersError,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Mapping
    from pathlib import Path

    from helios.integrity_gate import AppendOnlyLedger
    from helios.orchestrator.runner import RunOutcome
    from helios.orchestrator.schedule import RunSpec, Schedule

__all__ = [
    "INFRASTRUCTURE_ERRORS",
    "MAX_RETRIES",
    "NO_ANSWER_REASON",
    "OPERATIONAL_KEYS",
    "STOP_ERRORS",
    "Campaign",
    "CampaignState",
    "Executor",
    "compare_rerun",
    "read_log",
    "strip_operational",
]

HELIOS_ENABLE_ORCHESTRATOR: bool = True

MAX_RETRIES = 2
INFRASTRUCTURE_ERRORS: tuple[type[BaseException], ...] = (
    OllamaTimeoutError,
    OllamaConnectionError,
    OllamaResponseError,
    ConnectionError,
    TimeoutError,
    MemoryError,
)
STOP_ERRORS: tuple[type[BaseException], ...] = (
    ProvisionalParametersError,
    ProvisionalPromptError,
    MissingSigningKeyError,
    RouterParamsMismatchError,
    ExternalTriggerRefusedError,
    ModelMismatchError,
    PoolLockedError,
    BaselineConfigError,
)
LOG_NAME = "campaign_log.jsonl"
_FINAL = frozenset({"passed", "excluded"})
_CONSEQUENCE = (
    "S4.10 campaign: run excluded from analysis; its cell share and the "
    "MCAR/IPW sensitivity count it"
)


class Executor(Protocol):
    """One system's runner: a HELIOS variant or a baseline adapter."""

    @property
    def config_hash(self) -> str: ...

    def prepare(self) -> None: ...

    def run_incident(
        self, incident_id: str, run_id: str, context: Mapping[str, str] | None = None
    ) -> RunOutcome: ...

    def discard_run(self, run_id: str) -> int: ...


@dataclass
class CampaignState:
    """Per spec key: attempts started, infrastructure retries, final record."""

    started: dict[str, int]
    retries: dict[str, int]
    final: dict[str, dict[str, Any]]
    open_run: dict[str, str]  # key -> run_id started without a final record


def read_log(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _state(records: list[dict[str, Any]]) -> CampaignState:
    state = CampaignState({}, {}, {}, {})
    for r in records:
        key = r["key"]
        if r["event"] == "started":
            state.started[key] = state.started.get(key, 0) + 1
            state.open_run[key] = r["run_id"]
        elif r["event"] == "retry":
            state.retries[key] = state.retries.get(key, 0) + 1
            state.open_run.pop(key, None)
        elif r["event"] in _FINAL:
            state.final[key] = r
            state.open_run.pop(key, None)
    return state


class Campaign:
    """Run a schedule; resumable from its log."""

    def __init__(
        self,
        directory: Path,
        schedule: Schedule,
        executors: Mapping[str, Executor],
        *,
        exclusion_ledger: AppendOnlyLedger,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._dir = directory
        self._schedule = schedule
        self._digest = schedule.digest
        self._executors = executors
        self._exclusions = exclusion_ledger
        self._clock = clock
        directory.mkdir(parents=True, exist_ok=True)
        self._check_schedule_file()
        self.log_path = directory / LOG_NAME

    def _check_schedule_file(self) -> None:
        path = self._dir / "schedule.json"
        if path.is_file():
            recorded = json.loads(path.read_text())["digest"]
            if recorded != self._digest:
                raise ValueError(
                    f"campaign {self._dir} was planned with schedule "
                    f"{recorded[:12]}, not {self._digest[:12]}; start a new campaign"
                )
        else:
            path.write_text(self._schedule.to_json())

    def state(self) -> CampaignState:
        return _state(read_log(self.log_path))

    def _log(self, record: dict[str, Any]) -> None:
        line = json.dumps({**record, "at": self._clock()}, sort_keys=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def run(
        self,
        phases: Collection[str] | None = None,
        *,
        limit: int | None = None,
    ) -> dict[str, int]:
        """Run every unfinished spec (of ``phases``), at most ``limit`` of them.

        Returns counts of the final outcomes written by this call.
        """
        state = self.state()
        todo = [
            s
            for s in self._schedule.specs
            if (phases is None or s.phase in phases) and s.key not in state.final
        ]
        missing = sorted({s.system for s in todo} - set(self._executors))
        if missing:
            raise ValueError(f"no executor for {missing}")
        for system in sorted({s.system for s in todo}):
            self._executors[system].prepare()
        done: dict[str, int] = {}
        for spec in todo[:limit]:
            outcome = self._run_spec(spec, state)
            done[outcome] = done.get(outcome, 0) + 1
        return done

    def _context(self, spec: RunSpec, attempt: int) -> dict[str, str]:
        return {
            "phase": spec.phase,
            "corpus": self._schedule.corpus,
            "app": spec.app,
            "system": spec.system,
            "seed": str(spec.seed),
            "attempt": str(attempt),
            "schedule_digest": self._digest,
        }

    def _run_spec(self, spec: RunSpec, state: CampaignState) -> str:
        executor = self._executors[spec.system]
        stale = state.open_run.get(spec.key)
        if stale is not None:
            removed = executor.discard_run(stale)
            self._log(
                {
                    "key": spec.key,
                    "event": "discarded",
                    "run_id": stale,
                    "rows": removed,
                }
            )
        attempt = state.started.get(spec.key, 0)
        retries = state.retries.get(spec.key, 0)
        while True:
            run_id = spec.run_id(self._digest, attempt)
            base = {
                "key": spec.key,
                "run_id": run_id,
                "attempt": attempt,
                "position": spec.position,
            }
            self._log({**base, "event": "started"})
            context = self._context(spec, attempt)
            try:
                result = executor.run_incident(spec.case, run_id, context)
            except STOP_ERRORS as exc:
                self._log({**base, "event": "stopped", "error": type(exc).__name__})
                raise
            except INFRASTRUCTURE_ERRORS as exc:
                executor.discard_run(run_id)
                if retries < MAX_RETRIES:
                    retries += 1
                    attempt += 1
                    self._log({**base, "event": "retry", "error": type(exc).__name__})
                    continue
                return self._exclude(
                    spec,
                    base,
                    context,
                    executor,
                    "infrastructure_retries_exhausted",
                    exc,
                )
            except Exception as exc:
                executor.discard_run(run_id)
                return self._exclude(spec, base, context, executor, "run_error", exc)
            self._log(
                {**base, "event": result.outcome, "gate_check": result.gate_check}
            )
            return result.outcome

    def _exclude(
        self,
        spec: RunSpec,
        base: dict[str, Any],
        context: dict[str, str],
        executor: Executor,
        gate_check: str,
        exc: BaseException,
    ) -> str:
        trace = "".join(traceback.format_exception(exc))
        digest = hashlib.sha256(trace.encode()).hexdigest()[:16]
        reason = f"{type(exc).__name__}: {str(exc)[:200]} (traceback {digest})"
        self._exclusions.append(
            {
                **context,
                "variant_config_hash": executor.config_hash,
                "snapshot_hash": "UNKNOWN",
                "run_id": base["run_id"],
                "incident_id": spec.case,
                "gate_check": gate_check,
                "reason": reason,
                "analytic_consequence": _CONSEQUENCE,
                "covariates": "{}",
            }
        )
        self._log(
            {
                **base,
                "event": "excluded",
                "gate_check": gate_check,
                "error": type(exc).__name__,
            }
        )
        return "excluded"


# ── determinism rerun (O-g) ─────────────────────────────────────────────────

# Per-call measurements and bookkeeping that legitimately differ between a run
# and its rerun (the rerun bypasses the cache by design); never model output.
OPERATIONAL_KEYS: frozenset[str] = frozenset({"wall_ms", "cache_hit"})


def strip_operational(value: Any) -> Any:
    """``value`` without ``OPERATIONAL_KEYS``, at any depth."""
    if isinstance(value, dict):
        return {
            k: strip_operational(v)
            for k, v in value.items()
            if k not in OPERATIONAL_KEYS
        }
    if isinstance(value, list):
        return [strip_operational(v) for v in value]
    return value


NO_ANSWER_REASON = "model_error"


def _no_answer(narrative: Mapping[str, Any]) -> bool:
    """A slot fell back to the template without any model answer to judge
    (every rejection is a model error: a cache miss, timeout or outage)."""
    for slot in (narrative.get("slots") or {}).values():
        reasons = [r[1] for r in slot.get("rejections", [])]
        if slot.get("fallback") and reasons and set(reasons) == {NO_ANSWER_REASON}:
            return True
    return False


def compare_rerun(
    first: Mapping[str, Any], again: Mapping[str, Any]
) -> dict[str, list[str]]:
    """Compare one run with its rerun: fused list, L-pipe evidence, narrative.

    Each side maps ``fused`` (ranked list), ``lpipe`` (evidence) and
    ``narrative`` (the stored narrative record or None). Rendered narratives
    that differ are ``not_comparable`` when either side has a slot that got no
    model answer at all (``_no_answer``): there is no token sequence to compare.
    A slot whose model answers were rejected differently is a real difference.
    """
    differs: list[str] = []
    not_comparable: list[str] = []
    if first.get("fused") != again.get("fused"):
        differs.append("fused")
    if strip_operational(first.get("lpipe")) != strip_operational(again.get("lpipe")):
        differs.append("lpipe")
    na, nb = first.get("narrative"), again.get("narrative")
    if (na is None) != (nb is None):
        differs.append("narrative")
    elif na is not None and nb is not None and na.get("rendered") != nb.get("rendered"):
        if _no_answer(na) or _no_answer(nb):
            not_comparable.append("narrative")
        else:
            differs.append("narrative")
    return {"differs": differs, "not_comparable": not_comparable}
