"""Equal-weight merge, mu and sigma (S2.3 design §5.4; L-c, L-d)."""

from __future__ import annotations

import pytest

from helios.pipelines.l_pipe.merge import merge
from helios.pipelines.l_pipe.workers import DropReason, WorkerResult
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def _w(*ranked: str) -> WorkerResult:
    return WorkerResult("w", ranked=ranked)


def test_two_agreeing_workers() -> None:
    m = merge([_w("a", "b", "c"), _w("a", "c")])
    assert m.scores == pytest.approx({"a": 1, "b": 0.4, "c": 0.7})
    assert m.ranked == ("a", "c", "b")
    assert m.mu == round(1 / 2.1, 6)
    assert m.sigma == pytest.approx(0.7)
    assert m.k == 2


def test_two_disagreeing_workers() -> None:
    m = merge([_w("a", "b"), _w("b", "a")])
    assert m.scores == pytest.approx({"a": 0.9, "b": 0.9})
    assert m.ranked == ("a", "b")
    assert m.sigma == 1


def test_single_worker_sigma_is_one() -> None:
    m = merge([_w("a", "b"), WorkerResult("x", dropped=DropReason.TIMEOUT)])
    assert m.k == 1
    assert m.ranked == ("a", "b")
    assert m.sigma == 1


def test_three_workers_two_agree() -> None:
    m = merge([_w("a"), _w("a"), _w("b")])
    s1, s2 = 2 / 3, 1 / 3
    gap = (s1 - s2) / s1
    assert m.ranked == ("a", "b")
    assert m.sigma == pytest.approx(1 - (2 - 1) / (3 - 1) * gap, abs=1e-6)


def test_no_valid_worker() -> None:
    m = merge([WorkerResult("x", dropped=DropReason.SCHEMA)])
    assert m.k == 0
    assert m.ranked == ()
    assert m.mu is None and m.sigma is None


def test_sigma_stays_in_unit_range_when_no_worker_tops_the_merge() -> None:
    m = merge([_w("a", "c"), _w("b", "c")])
    assert m.ranked[0] == "c"
    assert m.sigma == 1


def test_sigma_always_in_unit_range() -> None:
    lists = [("a", "b", "c"), ("c", "b"), ("b",), ("d", "c", "a"), ("a",)]
    for i, x in enumerate(lists):
        for y in lists[i:]:
            for z in lists:
                m = merge([_w(*x), _w(*y), _w(*z)])
                assert m.sigma is not None and 0 <= m.sigma <= 1
