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

__all__ = ["CONVERGE_MS", "PROVISIONAL_MS", "Schedule", "schedule"]

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
