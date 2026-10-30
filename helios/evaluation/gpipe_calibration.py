"""G-pipe selection on build data (S2.2 design §5.3; owner decisions G-c, G-f).

Build labels only; the confirmatory pool is never loaded here. Fixed before
the selection run:

- Build cases: ``otel_build_v3`` (signed labels) plus the earlier OTel
  captures in ``data/captures`` without ``imageSlowLoad`` (its root cause is
  not a single service, deviation entry 44): 79 cases over 9 fault types.
- A more complex candidate beats a simpler one only with at least
  ``MARGIN_HITS`` more top-3 hits **and** more faults better than worse;
  otherwise — a tie included — the simpler one stays. Order: the learned
  ranker against feature-weighted PPR, then the survivor against plain PPR.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from helios.evaluation.trigger_calibration import load_cases
from helios.schemas.telemetry import TelemetryWindow
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

__all__ = [
    "CANDIDATES",
    "EXCLUDED_FAULTS",
    "MARGIN_HITS",
    "GPipeCase",
    "beats",
    "load_gpipe_cases",
    "select_gpipe",
]

MARGIN_HITS: int = 3
CANDIDATES: tuple[str, ...] = ("learned", "weighted_ppr", "ppr")
EXCLUDED_FAULTS: frozenset[str] = frozenset({"imageSlowLoad"})
_CAPTURES = "data/captures"
_CAPTURES_TRUTH = "data/ground_truth.json"


@dataclass(frozen=True)
class GPipeCase:
    """One build window with its label (selection only)."""

    incident_id: str
    window: TelemetryWindow
    root_cause: str
    fault: str
    stem: bool  # earlier captures label ``adService`` where the graph says ``ad``


def load_gpipe_cases(*, root: Path, key: bytes) -> list[GPipeCase]:
    """The 79 G-pipe build cases: OTel v3 (signed) and the earlier captures."""
    cases = [
        GPipeCase(
            incident_id=c.incident_id,
            window=c.window,
            root_cause=c.root_cause,
            fault=str(c.fault),
            stem=False,
        )
        for c in load_cases("otel_build_v3", root=root, key=key)
    ]
    truth = json.loads((root / _CAPTURES_TRUTH).read_text(encoding="utf-8"))
    base = root / _CAPTURES
    for case_dir in sorted(
        d for d in base.iterdir() if (d / "manifest.json").is_file()
    ):
        label = truth[case_dir.name]
        if label["fault_type"] in EXCLUDED_FAULTS:
            continue
        raw = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))
        raw.pop("window_hash", None)
        raw.pop("snapshot_hash", None)
        cases.append(
            GPipeCase(
                incident_id=case_dir.name,
                window=TelemetryWindow(**raw),
                root_cause=str(label["root_cause_service"]),
                fault=str(label["fault_type"]),
                stem=True,
            )
        )
    return cases


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
