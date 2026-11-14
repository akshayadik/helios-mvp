"""Shadow and recommendation modes (S4.5, design s4_4_7_tier2_design.md T-d).

A product setting outside the VCL manifest (owner decision 2026-11-11,
option a): it changes no variant hash. Neither mode writes to production;
there is no automatic mode in Stage A, and the only actuator is
``NoActuator``, which refuses to act.

- ``recommend`` (default, evidence runs): verdicts and proposals are shown to
  responders as recommendations; a person acts outside HELIOS.
- ``shadow``: everything is recorded, but responders see a run only after a
  person has decided on it, so HELIOS cannot influence them; ``admin`` keys
  always see it.
"""

from __future__ import annotations

import os
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "ACTION_MODE_ENV",
    "ActionMode",
    "ActionRefusedError",
    "Actuator",
    "NoActuator",
    "action_mode",
    "parse_mode",
]

HELIOS_ENABLE_ACTIONS: bool = True

ACTION_MODE_ENV = "HELIOS_ACTION_MODE"
_STAGE_B = "Stage B: an automatic mode needs the autonomy threshold and the full twin"


class ActionMode(StrEnum):
    RECOMMEND = "recommend"
    SHADOW = "shadow"


class ActionRefusedError(RuntimeError):
    """Stage A never acts on production."""


def parse_mode(value: str | None) -> ActionMode:
    """``recommend`` when unset; ``auto`` and anything unknown are refused."""
    text = (value or ActionMode.RECOMMEND.value).strip().lower()
    if text in ("auto", "automatic", "autonomous"):
        raise ValueError(f"{ACTION_MODE_ENV}={text}: {_STAGE_B}")
    try:
        return ActionMode(text)
    except ValueError:
        allowed = ", ".join(m.value for m in ActionMode)
        raise ValueError(f"{ACTION_MODE_ENV} must be one of {allowed}") from None


def action_mode(env: Mapping[str, str] | None = None) -> ActionMode:
    """The mode from the environment (``HELIOS_ACTION_MODE``)."""
    return parse_mode((os.environ if env is None else env).get(ACTION_MODE_ENV))


class Actuator(Protocol):
    """Something that could carry out a proposal. Stage B only."""

    def execute(self, proposal: Mapping[str, object]) -> None: ...


class NoActuator:
    """The only actuator in Stage A: it refuses every proposal."""

    def execute(self, proposal: Mapping[str, object]) -> None:
        raise ActionRefusedError(f"no actuator in Stage A ({_STAGE_B}): {proposal}")
