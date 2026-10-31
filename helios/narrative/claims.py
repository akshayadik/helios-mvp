"""Typed claims, the one schema both narrators emit (S2.8 design §5.2, N-b)."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

__all__ = ["REQUIRED", "SLOTS", "Claim", "ClaimKind", "ClaimSchemaError", "parse_slot"]

SLOTS = ("story", "contradictions", "verification")


class ClaimKind(StrEnum):
    """What a claim asserts; each kind has its own verifier rule."""

    SHIFT = "shift"
    CALL_STRUCTURE = "call_structure"
    LOG_MESSAGE = "log_message"
    RANKING = "ranking"
    CONTRADICTION = "contradiction"
    VERIFICATION_STEP = "verification_step"


# Fields a claim of each kind must carry (design §5.2).
REQUIRED: dict[ClaimKind, tuple[str, ...]] = {
    ClaimKind.SHIFT: ("service", "channel", "direction"),
    ClaimKind.CALL_STRUCTURE: ("caller", "callee", "feature"),
    ClaimKind.LOG_MESSAGE: ("service", "snippet"),
    ClaimKind.RANKING: ("service", "rank"),
    ClaimKind.CONTRADICTION: ("pipeline", "service"),
    ClaimKind.VERIFICATION_STEP: ("target_service", "action_verb", "modality"),
}


class ClaimSchemaError(ValueError):
    """A narrator answer that is not a list of well-formed typed claims."""


class Claim(BaseModel):
    """One atomic, cited statement; ``sentence`` is what is displayed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ClaimKind
    sentence: str
    cites: tuple[str, ...] = ()
    service: str | None = None
    channel: Literal["error", "latency", "resource"] | None = None
    direction: Literal["up", "down"] | None = None
    caller: str | None = None
    callee: str | None = None
    feature: Literal["wait", "lead", "ghost"] | None = None
    snippet: str | None = None
    rank: int | None = None
    pipeline: Literal["dpipe", "gpipe", "lpipe"] | None = None
    target_service: str | None = None
    action_verb: str | None = None
    modality: Literal["metric", "log", "edge"] | None = None
    window_start: str | None = None
    window_end: str | None = None


def parse_slot(raw: str) -> list[Claim]:
    """Parse a narrator's answer for one slot: a JSON list of claims, or an
    object holding one under ``claims``. Raise ClaimSchemaError otherwise."""
    try:
        data: Any = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ClaimSchemaError(f"not JSON: {exc}") from exc
    if isinstance(data, dict) and isinstance(data.get("claims"), list):
        data = data["claims"]
    if not isinstance(data, list):
        raise ClaimSchemaError("expected a list of claims")
    claims = []
    for n, item in enumerate(data):
        if not isinstance(item, dict):
            raise ClaimSchemaError(f"claim {n} is not an object")
        try:
            claim = Claim(**item)
        except ValidationError as exc:
            raise ClaimSchemaError(f"claim {n}: {exc.errors()[0]['msg']}") from exc
        missing = [f for f in REQUIRED[claim.kind] if getattr(claim, f) is None]
        if missing:
            raise ClaimSchemaError(f"claim {n} ({claim.kind}) lacks {missing}")
        claims.append(claim)
    return claims
