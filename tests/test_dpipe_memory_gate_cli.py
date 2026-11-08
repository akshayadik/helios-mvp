"""bin/dpipe_memory_gate.py (OTel fix B gate, entry 76)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_rank_counts_strictly_larger_values_and_puts_zero_last() -> None:
    from bin.dpipe_memory_gate import rank_of

    assert rank_of({"email": 3, "a": 5, "b": 3, "c": 1}, "email") == 2
    assert rank_of({"email": 9, "a": 5}, "email") == 1
    assert rank_of({"email": 0, "a": 0, "b": 0}, "email") == 3


def test_the_gate_runs_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from bin import dpipe_memory_gate

    (tmp_path / dpipe_memory_gate.REPORT).parent.mkdir(parents=True)
    (tmp_path / dpipe_memory_gate.REPORT).write_text("{}")
    monkeypatch.setattr(dpipe_memory_gate, "REPO_ROOT", tmp_path)
    assert dpipe_memory_gate.main([]) == 2
    assert "runs once" in capsys.readouterr().err
