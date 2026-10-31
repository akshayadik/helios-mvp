"""Narrative Engine (S2.8 design §5.6): the narrator for this variant, the
rendered text, and the CoE step ``N`` that records it in the signed entry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from helios.narrative.claims import SLOTS
from helios.narrative.llm import MODEL_ERROR, SlotResult, llm_slots
from helios.narrative.render import render
from helios.narrative.template import template_slots
from helios.pipelines.l_pipe.gateway import LLMGateway
from helios.pipelines.l_pipe.lpipe_config import MODEL_NAME, OLLAMA_BASE_URL
from helios.pipelines.l_pipe.ollama_client import (
    OllamaClient,
    OllamaConnectionError,
    OllamaResponseError,
    OllamaTimeoutError,
)
from helios.vcl import VCLFlag, gated_by

if TYPE_CHECKING:
    from collections.abc import Mapping

    from helios.narrative.params import NarratorParams
    from helios.pipelines.l_pipe.cache import ResponseCache

__all__ = ["Narrative", "run_narrative"]

_DIGEST_TIMEOUT_S = 30.0


@dataclass(frozen=True)
class Narrative:
    """One run's narrative and what producing it cost."""

    narrator: str
    slots: dict[str, SlotResult]
    rendered: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    wall_ms: float = 0

    def as_step(self) -> dict[str, Any]:
        """CoE step N: claims and verdict history per slot; tokens under
        ``cost`` (replayed from the cache, so deterministic), time under
        ``measured``."""
        return {
            "id": "N",
            "narrator": self.narrator,
            "slots": {
                name: {
                    "source": r.source,
                    "attempts": r.attempts,
                    "fallback": r.fallback,
                    "rejections": [list(x) for x in r.rejections],
                    "drafted_first": r.drafted_first,
                    "accepted_first": r.accepted_first,
                    "claims": [
                        c.model_dump(mode="json", exclude_none=True) for c in r.claims
                    ],
                }
                for name, r in self.slots.items()
            },
            "rendered": self.rendered,
            "cost": {
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
            },
            "measured": {"wall_ms": self.wall_ms},
        }


def _template(
    entry: Mapping[str, Any], params: NarratorParams
) -> dict[str, SlotResult]:
    return {
        k: SlotResult("template", tuple(v), attempts=0)
        for k, v in template_slots(entry, params).items()
    }


@gated_by(VCLFlag.COE_NARRATIVE)
def run_narrative(
    entry: Mapping[str, Any],
    *,
    params: NarratorParams,
    llm: bool,
    client: OllamaClient | None,
    cache: ResponseCache | None,
) -> Narrative:
    """The template narrative when ``llm`` is off (N-a: no model call at all);
    otherwise the LLM narrator with per-slot fallback (N-d)."""
    if not llm:
        slots = _template(entry, params)
        return Narrative("template", slots, render(entry, _claims(slots)))
    client = client or OllamaClient(OLLAMA_BASE_URL, MODEL_NAME)
    gateway = LLMGateway(client)
    try:
        digest = client.model_digest(timeout_s=_DIGEST_TIMEOUT_S)
    except (OllamaTimeoutError, OllamaConnectionError, OllamaResponseError):
        slots = {
            k: SlotResult(
                "template",
                v.claims,
                0,
                ((-1, MODEL_ERROR),) if v.claims else (),
                fallback=bool(v.claims),
            )
            for k, v in _template(entry, params).items()
        }
        return Narrative("llm", slots, render(entry, _claims(slots)))
    slots = llm_slots(entry, params, gateway=gateway, cache=cache, model_digest=digest)
    usage = gateway.usage
    return Narrative(
        "llm",
        slots,
        render(entry, _claims(slots)),
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        wall_ms=sum(r.wall_ms for r in slots.values()),
    )


def _claims(slots: Mapping[str, SlotResult]) -> dict[str, Any]:
    return {k: list(slots[k].claims) for k in SLOTS if k in slots}
