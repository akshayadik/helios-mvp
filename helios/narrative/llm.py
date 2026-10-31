"""LLM narrator (S2.8 design §5.4; owner decisions N-b, N-d).

One call per slot through L-pipe's gateway and response cache; every claim is
verified; a slot with any rejection gets one retry carrying the reasons, then
the template narrator's slot. A model error never fails the run.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import sqlite3
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from helios.narrative.claims import SLOTS, Claim, ClaimSchemaError, parse_slot
from helios.narrative.prompt import (
    NARRATOR_PROMPT_SHA,
    PROMPT_TEMPLATE,
    SLOT_KINDS,
)
from helios.narrative.template import template_slots
from helios.narrative.verifier import Reason, verify
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

__all__ = ["MODEL_ERROR", "SlotResult", "llm_slots", "render_prompt"]

MODEL_ERROR = "model_error"
TIMEOUT_S = 180.0
_MAX_ATTEMPTS = 2
_TASKS = {
    "story": "say what happened: the ranking of the top suspects and, for each, "
    "the evidence behind it.",
    "contradictions": "explain, for each disagreeing pipeline, which service it "
    "ranks first and the evidence it cites.",
    "verification": "propose read-only checks an engineer can run to confirm the "
    "top suspect.",
}


@dataclass(frozen=True)
class SlotResult:
    """One slot as displayed: who wrote it, its claims and how it got there."""

    source: str
    claims: tuple[Claim, ...]
    attempts: int
    rejections: tuple[tuple[int, str], ...] = ()
    fallback: bool = False
    wall_ms: float = 0
    # The first draft's claim count and how many of them the verifier accepted
    # (owner N-h: first-pass acceptance rate).
    drafted_first: int = 0
    accepted_first: int = 0


def _clock(iso: Any) -> str:
    return dt.datetime.fromisoformat(str(iso)).strftime("%H:%M") if iso else "?"


def _evidence_lines(entry: Mapping[str, Any]) -> list[str]:
    lines = []
    for step in entry["steps"]:
        for item in step.get("items", []):
            if ":claim" in item["id"]:
                continue
            values = [f"value={item.get('value')}"]
            for key in ("before", "after", "unit"):
                if key in item:
                    values.append(f"{key}={item[key]}")
            lines.append(
                f"{item['id']} | {item.get('service')} | {item.get('text')} | "
                + " ".join(values)
            )
    return lines


def _slot_words(slot: str, params: NarratorParams | None) -> str:
    """The frozen words a sentence in this slot may use (N-j)."""
    if params is None:
        return ""
    words: set[str] = set(params.vocabulary.get("common", ()))
    for kind in SLOT_KINDS[slot]:
        words |= set(params.vocabulary.get(kind, ()))
    if slot == "story":
        words |= {w for ws in params.direction_words.values() for w in ws}
        words |= {w for ws in params.channel_words.values() for w in ws}
        words |= set(params.rank_words)
    if slot == "contradictions":
        words |= set(params.rank_words) | set(params.pipeline_words)
    if slot == "verification":
        words |= set(params.verbs)
        words |= {w for ws in params.channel_words.values() for w in ws}
    return ", ".join(sorted(words))


def render_prompt(
    slot: str,
    entry: Mapping[str, Any],
    params: NarratorParams | None = None,
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
    retry = ""
    if previous is not None:
        reasons = "; ".join(f"claim {i}: {r}" for i, r in rejections)
        retry = (
            f"\nYOUR PREVIOUS ANSWER WAS REJECTED ({reasons}).\n"
            f"PREVIOUS ANSWER: {previous}\nFix or drop the rejected claims.\n"
        )
    return PROMPT_TEMPLATE.format(
        vocabulary=_slot_words(slot, params),
        slot=slot,
        task=_TASKS[slot],
        kinds=", ".join(SLOT_KINDS[slot]),
        verbs="|".join(params.verbs if params else ()),
        max_steps=params.max_steps if params else 3,
        window=f"{_clock(trigger.get('window_start'))} to "
        f"{_clock(trigger.get('window_end'))}",
        fused=f"{fused} (confidence {fusion.get('confidence')}, "
        f"state {fusion.get('state')}) [F]",
        disagree=", ".join(disagree) or "none",
        evidence="\n".join(_evidence_lines(entry)),
        retry=retry,
    )


def _call(
    prompt: str,
    gateway: LLMGateway,
    cache: ResponseCache | None,
    model_digest: str,
) -> tuple[str | None, float]:
    """The model's answer (cached or fresh) and its wall time; None on a model
    error."""
    key = cache_key(model_digest, NARRATOR_PROMPT_SHA, prompt)
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
        result = gateway.generate(prompt, timeout_s=TIMEOUT_S)
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
    slot: str, raw: str | None, entry: Mapping[str, Any], params: NarratorParams
) -> tuple[list[Claim], list[tuple[int, str]]]:
    if raw is None:
        return [], [(-1, MODEL_ERROR)]
    try:
        claims = parse_slot(raw)
    except ClaimSchemaError:
        return [], [(-1, Reason.SCHEMA.value)]
    if not claims:
        return [], [(-1, Reason.SCHEMA.value)]
    rejections: list[tuple[int, str]] = []
    allowed = SLOT_KINDS[slot]
    for n, claim in enumerate(claims):
        if claim.kind.value not in allowed:
            rejections.append((n, Reason.SCHEMA.value))
        elif reason := verify(claim, entry, params):
            rejections.append((n, reason.value))
    if slot == "verification" and len(claims) > params.max_steps:
        rejections.append((params.max_steps, Reason.SCHEMA.value))
    return claims, rejections


def llm_slots(
    entry: Mapping[str, Any],
    params: NarratorParams,
    *,
    gateway: LLMGateway,
    cache: ResponseCache | None,
    model_digest: str,
) -> dict[str, SlotResult]:
    """Each slot from the model, verified; else the template's slot."""
    template = template_slots(entry, params)
    out: dict[str, SlotResult] = {}
    for slot in SLOTS:
        if not template[slot]:
            out[slot] = SlotResult("template", (), attempts=0)
            continue
        previous: str | None = None
        last: list[tuple[int, str]] = []
        seen: list[tuple[int, str]] = []
        wall = 0.0
        first = (0, 0)
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            prompt = render_prompt(
                slot, entry, params, previous=previous, rejections=last
            )
            raw, ms = _call(prompt, gateway, cache, model_digest)
            wall += ms
            claims, last = _judge(slot, raw, entry, params)
            if attempt == 1:
                bad = {i for i, _ in last if i >= 0}
                first = (len(claims), len(claims) - len(bad))
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
