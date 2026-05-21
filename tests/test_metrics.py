"""Tests for helios.evaluation.metrics — hr_at_k hit-rate metric."""

from __future__ import annotations

from typing import TYPE_CHECKING

from helios.evaluation.metrics import hr_at_k

if TYPE_CHECKING:
    from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def test_hr_at_k_hit_at_first_position() -> None:
    assert hr_at_k(["svc-a", "svc-b", "svc-c"], "svc-a", k=3) == 1


def test_hr_at_k_hit_at_boundary() -> None:
    assert hr_at_k(["svc-b", "svc-c", "svc-a"], "svc-a", k=3) == 1


def test_hr_at_k_miss() -> None:
    assert hr_at_k(["svc-b", "svc-c", "svc-d"], "svc-a", k=3) == 0


def test_hr_at_k_empty_verdicts() -> None:
    assert hr_at_k([], "svc-a", k=3) == 0


def test_hr_at_k_truncates_to_k() -> None:
    # svc-a is at position 3 (0-indexed 2), outside k=2 window
    assert hr_at_k(["svc-b", "svc-c", "svc-a"], "svc-a", k=2) == 0


def test_hr_at_k_returns_int() -> None:
    result = hr_at_k(["svc-a"], "svc-a", k=3)
    assert isinstance(result, int)
