"""bin/analyse.py trace presence from sealed captures (deviation entry 93)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from bin.analyse import trace_presence
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path


class _Reader:
    """Stands in for CaptureReader: per case (traces path, rows, intact)."""

    def __init__(self, table: dict[str, tuple[str | None, int, bool]]) -> None:
        self.table = table

    def read(self, case: str) -> Any:
        path, rows, intact = self.table[case]
        return SimpleNamespace(
            window=SimpleNamespace(p2_traces_path=path),
            stream_row_counts={"p2_traces": rows} if path else {},
            intact=intact,
        )


def _captures(tmp_path: Path, cases: list[str]) -> Path:
    for case in cases:
        (tmp_path / case).mkdir()
        (tmp_path / case / "manifest.json").write_text("{}")
    return tmp_path


def test_trace_presence_reads_declared_non_empty_trace_streams(tmp_path: Path) -> None:
    root = _captures(tmp_path, ["a", "b", "c"])
    table = {"a": ("a/p2.parquet", 12, True), "b": (None, 0, True), "c": ("x", 0, True)}
    out = trace_presence(
        root, ["a", "b", "c", "d"], b"k", reader_factory=lambda p, k: _Reader(table)
    )
    # d has no capture: left out (unknown), never taken as "no traces".
    assert out == {"a": True, "b": False, "c": False}


def test_trace_presence_refuses_a_broken_seal(tmp_path: Path) -> None:
    root = _captures(tmp_path, ["a"])
    reader = _Reader({"a": ("a/p2.parquet", 3, False)})
    with pytest.raises(ValueError, match="1 capture"):
        trace_presence(root, ["a"], b"k", reader_factory=lambda p, k: reader)
