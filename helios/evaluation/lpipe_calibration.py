"""L-pipe build runs (S2.3 design §5.8): cases, dev/held-out split, report.

Build labels only; the confirmatory pool is never loaded here.

- Cases: the 63 ``otel_build_v3`` cases and the 495 ``rcaeval_build`` cases
  (120 with logs, none with traces), with their signed labels.
- Each corpus is split in half: its incident IDs sorted by SHA-256, then
  alternately dev and held-out — fixed, label-free, no seed. Prompt revisions are judged
  on dev only; the held-out numbers are reported, never used to revise.
- The report holds aggregates only, never an incident ID.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from helios.evaluation.trigger_calibration import load_cases
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from helios.schemas.telemetry import TelemetryWindow

__all__ = [
    "CORPORA",
    "CaseOutcome",
    "LPipeCase",
    "Split",
    "load_lpipe_cases",
    "split_cases",
    "summarise",
]

Split = Literal["dev", "heldout"]
CORPORA: tuple[str, ...] = ("otel_build_v3", "rcaeval_build")
_SECONDS_DIGITS = 2


@dataclass(frozen=True)
class LPipeCase:
    """One build window with its label (build runs only)."""

    incident_id: str
    corpus: str
    window: TelemetryWindow
    root_cause: str
    fault: str | None


@dataclass(frozen=True)
class CaseOutcome:
    """One case's result, without its ID. A worker hit of None = the worker was invalid."""

    corpus: str
    split: Split
    fault: str | None
    lpipe_hit: int
    worker_hits: Mapping[str, int | None]
    k: int
    drops: Mapping[str, str]
    seconds: float
    cache_hit: bool


def split_cases(incident_ids: Sequence[str]) -> dict[str, Split]:
    """Alternate dev / held-out in SHA-256 order of the IDs (dev gets the odd one)."""
    order = sorted(
        incident_ids, key=lambda i: (hashlib.sha256(i.encode()).hexdigest(), i)
    )
    return {i: ("dev" if n % 2 == 0 else "heldout") for n, i in enumerate(order)}


def load_lpipe_cases(*, root: Path, key: bytes) -> list[LPipeCase]:
    """Every build case of both corpora, in manifest order."""
    return [
        LPipeCase(c.incident_id, corpus, c.window, c.root_cause, c.fault)
        for corpus in CORPORA
        for c in load_cases(corpus, root=root, key=key)
    ]


def _group(rows: Sequence[CaseOutcome]) -> dict[str, Any]:
    workers = sorted({w for r in rows for w in r.worker_hits})
    return {
        "cases": len(rows),
        "lpipe_hr3_hits": sum(r.lpipe_hit for r in rows),
        "worker_hr3_hits": {
            w: sum(r.worker_hits.get(w) or 0 for r in rows) for w in workers
        },
        "worker_valid": {
            w: sum(r.worker_hits.get(w) is not None for r in rows) for w in workers
        },
        "k": {str(k): n for k, n in sorted(Counter(r.k for r in rows).items())},
        "drops": dict(
            sorted(Counter(d for r in rows for d in r.drops.values()).items())
        ),
        "mean_seconds": round(
            sum(r.seconds for r in rows) / len(rows), _SECONDS_DIGITS
        ),
        "cache_hits": sum(r.cache_hit for r in rows),
        "faults": dict(sorted(Counter(r.fault for r in rows if r.fault).items())),
    }


def summarise(rows: Sequence[CaseOutcome]) -> dict[str, dict[str, Any]]:
    """Aggregates per corpus and split."""
    out: dict[str, dict[str, Any]] = {}
    for corpus in sorted({r.corpus for r in rows}):
        mine = [r for r in rows if r.corpus == corpus]
        out[corpus] = {
            split: _group([r for r in mine if r.split == split])
            for split in ("dev", "heldout")
            if any(r.split == split for r in mine)
        }
    return out
