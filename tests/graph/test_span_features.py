"""Span features for G-pipe (S2.2 design §5.1, G-d, G-e)."""

from __future__ import annotations

import pandas as pd

from helios.graph.span_features import (
    analyse_spans,
    call_edges,
    ghost_edges,
    self_share,
    span_totals,
    split_at,
    wait_by_callee,
    wait_share,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

_T0 = 1_790_000_000_000_000  # us


def _spans(rows: list[tuple[str, str, str | None, str, int, int]]) -> pd.DataFrame:
    """(trace, span, parent, service, start offset us, end offset us)."""
    return pd.DataFrame(
        {
            "trace_id": [r[0] for r in rows],
            "span_id": [r[1] for r in rows],
            "parent_span_id": [r[2] for r in rows],
            "operation_name": ["op"] * len(rows),
            "service_name": [r[3] for r in rows],
            "start_time_us": [_T0 + r[4] for r in rows],
            "duration_us": [r[5] - r[4] for r in rows],
            "status_code": ["UNSET"] * len(rows),
        }
    )


def test_concurrent_children_count_once() -> None:
    a = analyse_spans(
        _spans(
            [
                ("t", "p", None, "A", 0, 120),
                ("t", "b", "p", "B", 10, 60),
                ("t", "c", "p", "C", 40, 90),
            ]
        )
    )
    assert wait_by_callee(a) == {("A", "B"): 50, ("A", "C"): 50}
    duration, self_us = span_totals(a)["A"]
    assert (duration, self_us) == (120, 40)  # union 10-90, never the sum


def test_overlapping_children_of_one_callee_union() -> None:
    a = analyse_spans(
        _spans(
            [
                ("t", "p", None, "A", 0, 120),
                ("t", "b1", "p", "B", 10, 60),
                ("t", "b2", "p", "B", 40, 90),
            ]
        )
    )
    assert wait_by_callee(a) == {("A", "B"): 80}


def test_wait_reaches_through_same_service_client_spans() -> None:
    # OTel: A server span -> A client span -> B server span.
    a = analyse_spans(
        _spans(
            [
                ("t", "srv", None, "A", 0, 120),
                ("t", "cli", "srv", "A", 10, 60),
                ("t", "b", "cli", "B", 12, 58),
            ]
        )
    )
    assert wait_by_callee(a) == {("A", "B"): 46}
    assert span_totals(a)["A"] == (120, 74)  # one entry span, not two
    assert call_edges(a) == frozenset({("A", "B")})


def test_same_service_child_is_not_wait_or_edge() -> None:
    a = analyse_spans(
        _spans([("t", "p", None, "A", 0, 120), ("t", "q", "p", "A", 10, 60)])
    )
    assert wait_by_callee(a) == {}
    assert call_edges(a) == frozenset()
    assert span_totals(a)["A"] == (120, 120)


def test_child_past_parent_is_clipped() -> None:
    a = analyse_spans(
        _spans([("t", "p", None, "A", 0, 120), ("t", "b", "p", "B", 80, 150)])
    )
    assert wait_by_callee(a) == {("A", "B"): 40}
    assert span_totals(a)["A"] == (120, 80)


def test_missing_parent_is_a_root() -> None:
    a = analyse_spans(
        _spans([("t", "b", "gone", "B", 10, 60), ("t", "c", "b", "C", 20, 40)])
    )
    assert call_edges(a) == frozenset({("B", "C")})  # no edge into B
    assert span_totals(a)["B"] == (50, 30)


def test_empty_parent_string_and_none_both_mean_root() -> None:
    rows = [("t", "p", "", "A", 0, 120), ("u", "q", None, "A", 0, 120)]
    a = analyse_spans(_spans(rows))
    assert span_totals(a)["A"] == (240, 240)
    assert call_edges(a) == frozenset()


def _edge_at(
    trace: str, offset: int, callee: str
) -> list[tuple[str, str, str | None, str, int, int]]:
    return [
        (trace, f"{trace}p", None, "A", offset, offset + 50),
        (trace, f"{trace}c", f"{trace}p", callee, offset + 10, offset + 40),
    ]


def test_edge_only_before_is_not_ghost() -> None:
    a = analyse_spans(_spans(_edge_at("t1", 0, "B") + _edge_at("t2", 1_000, "C")))
    before, after = split_at(a, (_T0 + 500) / 1e6)
    assert call_edges(before) == frozenset({("A", "B")})
    assert ghost_edges(before, after) == frozenset({("A", "C")})


def test_edge_only_after_is_ghost() -> None:
    a = analyse_spans(
        _spans(
            _edge_at("t1", 0, "B")
            + _edge_at("t2", 1_000, "B")
            + _edge_at("t3", 1_100, "D")
        )
    )
    before, after = split_at(a, (_T0 + 500) / 1e6)
    assert ghost_edges(before, after) == frozenset({("A", "D")})


def test_split_keeps_a_straddling_tree_whole() -> None:
    # Entry starts before t, its callee after t: the pair stays with the entry.
    a = analyse_spans(
        _spans([("t", "p", None, "A", 0, 2_000), ("t", "b", "p", "B", 1_500, 1_900)])
    )
    before, after = split_at(a, (_T0 + 1_000) / 1e6)
    assert wait_by_callee(before) == {("A", "B"): 400}
    assert wait_by_callee(after) == {}


def test_shares_count_each_request_once_so_a_stream_cannot_dominate() -> None:
    # 3 short A requests waiting half their time on B, plus one 600 s A
    # stream to C (a flagd event stream in the v3 data).
    rows = []
    for i in range(3):
        rows += [
            (f"t{i}", "p", None, "A", 0, 40),
            (f"t{i}", "b", "p", "B", 10, 30),
        ]
    rows += [
        ("s", "p", None, "A", 0, 600_000_000),
        ("s", "c", "p", "C", 0, 600_000_000),
    ]
    a = analyse_spans(_spans(rows))
    shares = wait_share(a)
    assert shares["A", "B"] == 0.375  # (0.5 * 3 + 0) / 4
    assert shares["A", "C"] == 0.25  # one request of four
    assert self_share(a)["A"] == 0.5  # median of 0.5, 0.5, 0.5, 0
