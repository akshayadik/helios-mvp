"""Replayed concurrency for MAHC's publications (S2.5 design §5.5).

Recorded runs execute the pipelines one after another; their measured
latencies (cached L-pipe calls replay theirs) are replayed as if the
pipelines had run at the same time. First publication: at the earlier of
PROVISIONAL_MS and all pipelines done, from the pipelines done by then.
Terminal: when all are done, if within CONVERGE_MS; otherwise the case did
not converge. TTT is the first publication time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "CONVERGE_MS",
    "PROVISIONAL_MS",
    "Schedule",
    "finish_times",
    "schedule",
    "staged_finish_times",
    "staged_schedule",
]

HELIOS_ENABLE_MAHC_TIMING: bool = True

PROVISIONAL_MS: float = 30_000
CONVERGE_MS: float = 90_000


@dataclass(frozen=True)
class Schedule:
    """When MAHC publishes, and from which pipelines."""

    first_ms: float
    first_pipelines: tuple[str, ...]
    terminal_ms: float | None
    non_converged: bool


def schedule(latency_ms: Mapping[str, float]) -> Schedule:
    """First and terminal publication times from per-pipeline latencies."""
    if not latency_ms:
        return Schedule(0, (), 0, False)
    last = max(latency_ms.values())
    first = min(PROVISIONAL_MS, last)
    early = tuple(sorted(p for p, ms in latency_ms.items() if ms <= first))
    if last > CONVERGE_MS:
        return Schedule(first, early, None, True)
    return Schedule(first, early, last, False)


def finish_times(latency_ms: Mapping[str, float]) -> dict[str, float]:
    """When each pipeline would finish if run concurrently.

    D-pipe and L-pipe start at the trigger; G-pipe is dispatched only after
    D-pipe's routing gate, so it finishes at D-pipe's latency plus its own.
    """
    out = dict(latency_ms)
    if "gpipe" in out and "dpipe" in out:
        out["gpipe"] = out["dpipe"] + out["gpipe"]
    return out


def staged_finish_times(
    stage1_ms: Mapping[str, float], lpipe_ms: float | None
) -> dict[str, float]:
    """Finish times of a routed run (S3.1 design §5.5).

    The cheap stage runs as today (G-pipe after the D-pipe); the L-pipe is
    dispatched only after the escalation decision, so it finishes at the end
    of the cheap stage plus its own latency.
    """
    out = finish_times(stage1_ms)
    if lpipe_ms is not None:
        out["lpipe"] = max(out.values(), default=0) + lpipe_ms
    return out


def staged_schedule(stage1_ms: Mapping[str, float], lpipe_ms: float | None) -> Schedule:
    """First publication when the cheap stage finishes; terminal after the
    L-pipe if escalated; non-convergence past ``CONVERGE_MS``."""
    cheap = finish_times(stage1_ms)
    first = max(cheap.values(), default=0)
    early = tuple(sorted(cheap))
    terminal = first if lpipe_ms is None else first + lpipe_ms
    if terminal > CONVERGE_MS:
        return Schedule(first, early, None, True)
    return Schedule(first, early, terminal, False)
