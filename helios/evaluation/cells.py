"""Cell bookkeeping and the score-time metric check (S4.10 O-c, O-e; entry 87).

A cell is (system, benchmark system of the case, metric): ``system`` is a
variant or baseline name, ``app`` the application the case ran on (OB, TT).
Its share is the cases with a value for the metric over the cases the schedule
gave that system on that app. A cell enters inference only with a share of at
least 4/5 (Ch3's cell rule, analysis plan ``cell_inclusion_rule``).

A hypothesis is tested on the cases of the apps where both of its compared
cells pass (O-e (a)); with no such app it is untestable.

Score-time check: a run that passed its gate but has no value for a metric of
its cell set is excluded for that metric only. H_fact is checked only once its
labels are due (a NULL before then is pending, not missing).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from fractions import Fraction
from typing import TYPE_CHECKING, Any

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping

__all__ = [
    "CELL_METRICS",
    "CELL_SHARE",
    "Cell",
    "CellTable",
    "cell_key",
    "cell_table",
    "missing_metrics",
    "passing_apps",
]

HELIOS_ENABLE_CELLS: bool = True

CELL_SHARE = Fraction(4, 5)
# The case-table keys of every metric a hypothesis or Family E item tests.
CELL_METRICS: tuple[str, ...] = (
    "hr_at_3",
    "avg_at_5",
    "log_cpr",
    "log_ttcd",
    "ttt_ms",
    "h_fact",
    "h_struct",
)
_LABELLED = frozenset({"h_fact"})


@dataclass(frozen=True)
class Cell:
    system: str
    app: str
    metric: str
    scheduled: int
    included: int

    @property
    def share(self) -> Fraction:
        return (
            Fraction(self.included, self.scheduled) if self.scheduled else Fraction(0)
        )

    @property
    def passes(self) -> bool:
        return self.scheduled > 0 and self.share >= CELL_SHARE

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "share": float(self.share), "passes": self.passes}


CellTable = dict[str, Cell]


def cell_key(system: str, app: str, metric: str) -> str:
    return f"{system}|{app}|{metric}"


def _has(row: Mapping[str, Any] | None, metric: str) -> bool:
    return row is not None and row.get(metric) is not None


def cell_table(
    table: Mapping[str, Mapping[str, Mapping[str, Any]]],
    apps: Mapping[str, str],
    scheduled: Mapping[str, Collection[str]],
) -> CellTable:
    """Cells of every scheduled system, over ``CELL_METRICS``.

    ``table`` is the analysis case table (system -> case -> fields);
    ``scheduled`` maps each system to the cases the schedule gave it.
    """
    out: CellTable = {}
    for system, cases in sorted(scheduled.items()):
        rows = table.get(system, {})
        for app in sorted({apps[c] for c in cases}):
            mine = [c for c in cases if apps[c] == app]
            for metric in CELL_METRICS:
                included = sum(_has(rows.get(c), metric) for c in mine)
                out[cell_key(system, app, metric)] = Cell(
                    system, app, metric, len(mine), included
                )
    return out


def passing_apps(cells: CellTable, a: str, b: str, metric: str) -> list[str]:
    """Apps where the cells of both compared systems pass for ``metric``."""
    apps = {c.app for c in cells.values() if c.system == a and c.metric == metric}
    return sorted(
        app
        for app in apps
        if (ca := cells.get(cell_key(a, app, metric))) is not None
        and (cb := cells.get(cell_key(b, app, metric))) is not None
        and ca.passes
        and cb.passes
    )


def missing_metrics(
    table: Mapping[str, Mapping[str, Mapping[str, Any]]],
    passed: Collection[tuple[str, str]],
    *,
    labels_due: bool,
) -> list[tuple[str, str, str]]:
    """(system, case, metric) of passed runs that lack a metric value.

    A passed run with no scored row at all lacks every metric.
    """
    out: list[tuple[str, str, str]] = []
    for system, case in sorted(passed):
        row = table.get(system, {}).get(case)
        for metric in CELL_METRICS:
            if metric in _LABELLED and not labels_due:
                continue
            if not _has(row, metric):
                out.append((system, case, metric))
    return out
