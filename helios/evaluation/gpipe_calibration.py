"""G-pipe selection on build data (S2.2 design §5.3; owner decisions G-c, G-f).

Build labels only; the confirmatory pool is never loaded here. Fixed before
the selection run:

- Build cases: the 63 ``otel_build_v3`` cases (signed labels; 9 fault types,
  6 root services). The earlier OTel captures are left out: their spans are
  attributed to every queried service (owner 2026-10-30, PR 1 review C1).
- The learned ranker is scored leaving one **root service** out (6 folds), so
  it never trains on the service it is tested on (PR 1 review C2).
- A more complex candidate beats a simpler one only with at least
  ``MARGIN_HITS`` more top-3 hits **and** more faults better than worse;
  otherwise — a tie included — the simpler one stays. Order: the learned
  ranker against feature-weighted PPR, then the survivor against plain PPR.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from helios.evaluation.trigger_calibration import load_cases
from helios.schemas.telemetry import TelemetryWindow  # noqa: TCH001
from helios.telemetry.scope import scope_key
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

__all__ = [
    "CANDIDATES",
    "MARGIN_HITS",
    "GPipeCase",
    "beats",
    "load_gpipe_cases",
    "root_folds",
    "scope_key",
    "select_gpipe",
]

MARGIN_HITS: int = 3
CANDIDATES: tuple[str, ...] = ("learned", "weighted_ppr", "ppr")


@dataclass(frozen=True)
class GPipeCase:
    """One build window with its label (selection only)."""

    incident_id: str
    window: TelemetryWindow
    root_cause: str
    fault: str
    stem: bool  # stem matching (``adService`` ~ ``ad``); False for v3 labels


def load_gpipe_cases(*, root: Path, key: bytes) -> list[GPipeCase]:
    """The 63 G-pipe build cases (otel_build_v3, signed labels)."""
    return [
        GPipeCase(
            incident_id=c.incident_id,
            window=c.window,
            root_cause=c.root_cause,
            fault=str(c.fault),
            stem=False,
        )
        for c in load_cases("otel_build_v3", root=root, key=key)
    ]


def root_folds(roots: Sequence[str]) -> list[tuple[list[int], list[int]]]:
    """(train, test) index lists, one fold per root service (scope_key order)."""
    keys = [scope_key(r) for r in roots]
    return [
        (
            [i for i, k in enumerate(keys) if k != held],
            [i for i, k in enumerate(keys) if k == held],
        )
        for held in sorted(set(keys))
    ]


def beats(
    complex_hits: Mapping[str, list[int]], simple_hits: Mapping[str, list[int]]
) -> bool:
    """The design §5.3 bar: ≥ MARGIN_HITS more hits and more faults better than worse."""
    faults = sorted(set(complex_hits) | set(simple_hits))
    diffs = [sum(complex_hits.get(f, [])) - sum(simple_hits.get(f, [])) for f in faults]
    better = sum(d > 0 for d in diffs)
    worse = sum(d < 0 for d in diffs)
    return sum(diffs) >= MARGIN_HITS and better > worse


def select_gpipe(hits: Mapping[str, Mapping[str, list[int]]]) -> str:
    """The frozen candidate: learned vs weighted PPR, then the survivor vs PPR."""
    learned, weighted, plain = (hits[c] for c in CANDIDATES)
    survivor = "learned" if beats(learned, weighted) else "weighted_ppr"
    return survivor if beats(hits[survivor], plain) else "ppr"
