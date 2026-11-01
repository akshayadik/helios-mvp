"""LLM narrator (S2.8 design §5.4; owner decisions N-b, N-d and (b)).

Owner decision (b), 2026-11-01, after prompt rounds 1-2: the model chooses and
orders claims; code writes every sentence. Per slot the model sees numbered
candidate claims (``candidate_claims``: the template's wording, each already
accepted by the verifier) and answers with candidate IDs, constrained by a
JSON schema listing only those IDs. One call per slot through L-pipe's gateway
and response cache; an answer with an unknown, repeated or surplus pick gets
one retry carrying the reasons, then the template narrator's slot. A model
error never fails the run.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import sqlite3
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from helios.narrative.claims import SLOTS, Claim
from helios.narrative.prompt import MAX_PICKS, NARRATOR_PROMPT_SHA, PROMPT_TEMPLATE
from helios.narrative.template import candidate_claims, template_slots
from helios.narrative.verifier import Reason
from helios.pipelines.l_pipe.cache import CachedCall, cache_key
from helios.pipelines.l_pipe.ollama_client import (
    OllamaConnectionError,
    OllamaGenerateResult,
    OllamaResponseError,
    OllamaTimeoutError,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from helios.narrative.params import NarratorParams
    from helios.pipelines.l_pipe.cache import ResponseCache
    from helios.pipelines.l_pipe.gateway import LLMGateway

__all__ = ["MODEL_ERROR", "SlotResult", "llm_slots", "pick_schema", "render_prompt"]

MODEL_ERROR = "model_error"
TIMEOUT_S = 180.0
_MAX_ATTEMPTS = 2
_TASKS = {
    "story": "tell what happened: which services are the top suspects and the "
    "evidence that matters most for each.",
    "contradictions": "show where the pipelines disagree with the fused verdict.",
    "verification": "choose the read-only checks an engineer should run first to "
    "confirm the top suspect.",
}


@dataclass(frozen=True)
class SlotResult:
    """One slot as displayed: who chose it, its claims and how it got there."""

    source: str
    claims: tuple[Claim, ...]
    attempts: int
    rejections: tuple[tuple[int, str], ...] = ()
    fallback: bool = False
    wall_ms: float = 0
    # The first answer's pick count and how many of them were valid
    # (owner N-h: first-pass acceptance rate).
    drafted_first: int = 0
    accepted_first: int = 0


def _clock(iso: Any) -> str:
    return dt.datetime.fromisoformat(str(iso)).strftime("%H:%M") if iso else "?"


def _most(slot: str, params: NarratorParams) -> int:
    return params.max_steps if slot == "verification" else MAX_PICKS[slot]


def _ids(candidates: Sequence[Claim]) -> list[str]:
    return [f"C{n}" for n in range(1, len(candidates) + 1)]


def pick_schema(
    slot: str, candidates: Sequence[Claim], params: NarratorParams
) -> dict[str, Any]:
    """The answer format: a list of distinct candidate IDs, at most the slot's
    limit (sent to the model; the picks are checked again on return)."""
    return {
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "items": {"enum": _ids(candidates)},
                "minItems": 1,
                "maxItems": min(_most(slot, params), len(candidates)),
            }
        },
        "required": ["claims"],
        "additionalProperties": False,
    }


def render_prompt(
    slot: str,
    entry: Mapping[str, Any],
    params: NarratorParams,
    *,
    previous: str | None = None,
    rejections: Sequence[tuple[int, str]] = (),
) -> str:
    """The prompt for one slot; a retry also carries the rejected answer and
    the reasons (deterministic, so the retry is cached like any call)."""
    steps = {str(s["id"]): s for s in entry["steps"]}
    fusion, trigger = steps["F"], steps.get("T", {})
    ranked = list(fusion.get("ranked") or [])[:3]
    fused = ", ".join(f"{n}. {s}" for n, s in enumerate(ranked, start=1)) or "none"
    disagree = [
        f"{p} (top: {(steps.get(f'P:{p}', {}).get('ranked') or ['?'])[0]})"
        for p in fusion.get("disagree") or []
    ]
    candidates = candidate_claims(entry, params)[slot]
    retry = ""
    if previous is not None:
        reasons = "; ".join(f"pick {i}: {r}" for i, r in rejections)
        retry = (
            f"\nYOUR PREVIOUS ANSWER WAS REJECTED ({reasons}).\n"
            f"PREVIOUS ANSWER: {previous}\nPick only listed IDs, each once.\n"
        )
    return PROMPT_TEMPLATE.format(
        slot=slot,
        task=_TASKS[slot],
        most=min(_most(slot, params), len(candidates)),
        window=f"{_clock(trigger.get('window_start'))} to "
        f"{_clock(trigger.get('window_end'))}",
        fused=f"{fused} (confidence {fusion.get('confidence')}, "
        f"state {fusion.get('state')})",
        disagree=", ".join(disagree) or "none",
        candidates="\n".join(
            f"{cid} | {c.kind.value} | {c.sentence}"
            for cid, c in zip(_ids(candidates), candidates, strict=True)
        ),
        retry=retry,
    )


def _call(
    prompt: str,
    gateway: LLMGateway,
    cache: ResponseCache | None,
    model_digest: str,
    schema: dict[str, Any] | None = None,
) -> tuple[str | None, float]:
    """The model's answer (cached or fresh) and its wall time; None on a model
    error. The cache key covers the output schema as well as the prompt."""
    fmt = json.dumps(schema, sort_keys=True) if schema is not None else "json"
    key = cache_key(model_digest, NARRATOR_PROMPT_SHA, f"{prompt}\nFORMAT: {fmt}")
    hit = None
    if cache is not None:
        try:
            hit = cache.get(key)
        except sqlite3.Error:
            hit = None
    if hit is not None:
        gateway.replay(
            OllamaGenerateResult(
                hit.text, hit.prompt_tokens, hit.completion_tokens, hit.compute_ms
            )
        )
        return hit.text, hit.wall_ms
    t0 = time.monotonic()
    try:
        result = gateway.generate(prompt, timeout_s=TIMEOUT_S, schema=schema)
    except (OllamaTimeoutError, OllamaConnectionError, OllamaResponseError):
        return None, (time.monotonic() - t0) * 1_000
    wall_ms = (time.monotonic() - t0) * 1_000
    if cache is not None:
        call = CachedCall(
            result.text,
            result.prompt_tokens,
            result.completion_tokens,
            result.compute_ms,
            wall_ms,
        )
        with contextlib.suppress(sqlite3.Error):  # a broken cache never fails a run
            cache.put(key, call)
    return result.text, wall_ms


def _judge(
    raw: str | None, candidates: Sequence[Claim], most: int
) -> tuple[list[Claim], list[tuple[int, str]], int]:
    """The picked claims in the model's order, the rejections, and how many
    picks the answer made."""
    if raw is None:
        return [], [(-1, MODEL_ERROR)], 0
    try:
        data: Any = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return [], [(-1, Reason.SCHEMA.value)], 0
    picks = data.get("claims") if isinstance(data, dict) else data
    if not isinstance(picks, list) or not picks:
        return [], [(-1, Reason.SCHEMA.value)], 0
    by_id = dict(zip(_ids(candidates), candidates, strict=True))
    claims: list[Claim] = []
    rejections: list[tuple[int, str]] = []
    seen: set[str] = set()
    for n, pick in enumerate(picks):
        if not isinstance(pick, str) or pick in seen or n >= most:
            rejections.append((n, Reason.SCHEMA.value))
        elif pick not in by_id:
            rejections.append((n, Reason.UNKNOWN_ID.value))
        else:
            claims.append(by_id[pick])
        if isinstance(pick, str):
            seen.add(pick)
    return claims, rejections, len(picks)


def llm_slots(
    entry: Mapping[str, Any],
    params: NarratorParams,
    *,
    gateway: LLMGateway,
    cache: ResponseCache | None,
    model_digest: str,
) -> dict[str, SlotResult]:
    """Each slot as the model picked it; else the template's slot."""
    template = template_slots(entry, params)
    candidates = candidate_claims(entry, params)
    out: dict[str, SlotResult] = {}
    for slot in SLOTS:
        if not template[slot] or not candidates[slot]:
            out[slot] = SlotResult("template", tuple(template[slot]), attempts=0)
            continue
        schema = pick_schema(slot, candidates[slot], params)
        most = min(_most(slot, params), len(candidates[slot]))
        previous: str | None = None
        last: list[tuple[int, str]] = []
        seen: list[tuple[int, str]] = []
        wall = 0.0
        first = (0, 0)
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            prompt = render_prompt(
                slot, entry, params, previous=previous, rejections=last
            )
            raw, ms = _call(prompt, gateway, cache, model_digest, schema)
            wall += ms
            claims, last, picked = _judge(raw, candidates[slot], most)
            if attempt == 1:
                first = (picked, len(claims) if picked else 0)
            if not last:
                out[slot] = SlotResult(
                    "llm",
                    tuple(claims),
                    attempt,
                    tuple(seen),
                    wall_ms=wall,
                    drafted_first=first[0],
                    accepted_first=first[1],
                )
                break
            seen += last
            previous = raw if raw is not None else ""
        else:
            out[slot] = SlotResult(
                "template",
                tuple(template[slot]),
                _MAX_ATTEMPTS,
                tuple(seen),
                fallback=True,
                wall_ms=wall,
                drafted_first=first[0],
                accepted_first=first[1],
            )
    return out
