"""bin/gpipe_select.py (S2.2 Task 8)."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from helios.pipelines.d_pipe.params import load_dpipe_params
from helios.telemetry.trigger import load_detector_params
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_tool_refuses_the_pool(capsys: pytest.CaptureFixture[str]) -> None:
    from bin import gpipe_select

    assert gpipe_select.main(["--corpus", "pool"]) == 2
    assert "pool" in capsys.readouterr().err


def test_tool_refuses_a_provisional_detector(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from bin import gpipe_select

    provisional = replace(load_detector_params(), provisional=True)
    monkeypatch.setattr(gpipe_select, "load_detector_params", lambda: provisional)
    assert gpipe_select.main([]) == 2
    assert "freeze" in capsys.readouterr().err


def test_tool_refuses_provisional_dpipe_params(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from bin import gpipe_select

    provisional = replace(load_dpipe_params(), provisional=True)
    monkeypatch.setattr(gpipe_select, "load_dpipe_params", lambda: provisional)
    assert gpipe_select.main([]) == 2
    assert "freeze" in capsys.readouterr().err
