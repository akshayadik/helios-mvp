"""bin/dpipe_calibrate.py (S2.1 Task 13)."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from helios.telemetry.trigger import load_detector_params
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_refuses_a_provisional_detector(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from bin import dpipe_calibrate

    provisional = replace(load_detector_params(), provisional=True)
    monkeypatch.setattr(dpipe_calibrate, "load_detector_params", lambda: provisional)
    assert dpipe_calibrate.main([]) == 2
    assert "freeze it first" in capsys.readouterr().err


def test_uses_the_runner_graph_and_the_full_variant() -> None:
    from bin import dpipe_calibrate
    from helios.orchestrator.runner import incident_graph

    assert dpipe_calibrate.incident_graph is incident_graph
    assert dpipe_calibrate.VARIANT == "HELIOS-Full"
