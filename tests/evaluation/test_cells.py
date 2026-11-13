"""S4.10 cells (O-e) and the score-time metric check (O-c)."""

from __future__ import annotations

from fractions import Fraction

from helios.evaluation.cells import (
    CELL_METRICS,
    cell_key,
    cell_table,
    missing_metrics,
    passing_apps,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

APPS = {
    "o1": "OB",
    "o2": "OB",
    "o3": "OB",
    "o4": "OB",
    "o5": "OB",
    "t1": "TT",
    "t2": "TT",
}


def _row(**kw: float | None) -> dict[str, float | None]:
    return dict.fromkeys(CELL_METRICS, 1) | kw


def test_cell_shares_and_the_four_fifths_rule() -> None:
    table = {
        "A": {c: _row() for c in APPS},
        # B: OB 4 of 5 have HR@3 (passes exactly at 4/5); TT 1 of 2 (fails).
        "B": {
            "o1": _row(hr_at_3=None),
            "o2": _row(),
            "o3": _row(),
            "o4": _row(),
            "o5": _row(),
            "t1": _row(),
            # t2 never stored (excluded at the gate)
        },
    }
    cells = cell_table(table, APPS, {"A": list(APPS), "B": list(APPS)})
    ob = cells[cell_key("B", "OB", "hr_at_3")]
    assert (ob.scheduled, ob.included, ob.share, ob.passes) == (
        5,
        4,
        Fraction(4, 5),
        True,
    )
    tt = cells[cell_key("B", "TT", "hr_at_3")]
    assert (tt.scheduled, tt.included, tt.passes) == (2, 1, False)
    assert passing_apps(cells, "A", "B", "hr_at_3") == ["OB"]
    assert passing_apps(cells, "A", "B", "log_cpr") == ["OB"]  # t2 missing too
    assert cells[cell_key("A", "TT", "h_fact")].as_dict()["share"] == 1


def test_unscheduled_and_unknown_systems() -> None:
    cells = cell_table({}, APPS, {"C": ["o1", "o2"]})
    assert cells[cell_key("C", "OB", "hr_at_3")].included == 0
    assert passing_apps(cells, "C", "missing", "hr_at_3") == []


def test_missing_metrics_after_scoring() -> None:
    table = {"A": {"o1": _row(log_cpr=None, h_fact=None)}}
    passed = [("A", "o1"), ("A", "o2")]  # o2 passed the gate but was never scored
    before = missing_metrics(table, passed, labels_due=False)
    assert ("A", "o1", "log_cpr") in before
    assert ("A", "o1", "h_fact") not in before  # pending labels are not missing
    assert {m for s, c, m in before if c == "o2"} == set(CELL_METRICS) - {"h_fact"}
    after = missing_metrics(table, passed, labels_due=True)
    assert ("A", "o1", "h_fact") in after
