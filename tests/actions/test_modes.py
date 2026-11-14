"""Shadow and recommendation modes (S4.5, design s4_4_7_tier2_design.md T-d)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from helios.actions.modes import (
    ACTION_MODE_ENV,
    ActionMode,
    ActionRefusedError,
    NoActuator,
    action_mode,
    parse_mode,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

ROOT = Path(__file__).resolve().parents[2]


def test_recommend_is_the_default() -> None:
    assert parse_mode(None) is ActionMode.RECOMMEND
    assert action_mode({}) is ActionMode.RECOMMEND
    assert action_mode({ACTION_MODE_ENV: " Shadow "}) is ActionMode.SHADOW


@pytest.mark.parametrize("value", ["auto", "AUTOMATIC", "autonomous"])
def test_there_is_no_automatic_mode(value: str) -> None:
    with pytest.raises(ValueError, match="Stage B"):
        parse_mode(value)


def test_unknown_modes_are_refused() -> None:
    with pytest.raises(ValueError, match="recommend, shadow"):
        parse_mode("live")


def test_the_only_actuator_refuses() -> None:
    with pytest.raises(ActionRefusedError, match="no actuator"):
        NoActuator().execute({"kind": "restart", "target": "cart"})


def test_no_module_defines_another_actuator() -> None:
    """Stage A never writes to production: no class in helios/ or bin/ has an
    ``execute`` method except ``NoActuator``."""
    found = []
    for path in [
        *ROOT.joinpath("helios").rglob("*.py"),
        *ROOT.joinpath("bin").glob("*.py"),
    ]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and any(
                isinstance(b, ast.FunctionDef) and b.name == "execute"
                for b in node.body
            ):
                found.append(f"{path.relative_to(ROOT)}:{node.name}")
    assert found == [
        "helios/actions/modes.py:Actuator",
        "helios/actions/modes.py:NoActuator",
    ]
