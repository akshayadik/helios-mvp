"""One L-pipe worker: a model call over its digest, then validation (S2.3 design §5.3).

Validation, in order (L-e): JSON schema; services must be candidate aliases;
a ranked service keeps only claims whose citations all exist in **this
worker's** digest, and is dropped without one. There is no retry: Protocol A
decoding is deterministic, so a schema failure drops the worker. A worker
with nothing left, whose call fails or whose prompt would leak a real name
is invalid with a recorded reason; nothing raises out of here.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, ValidationError

from helios.pipelines.l_pipe.aliases import AliasLeakError
from helios.pipelines.l_pipe.cache import CachedCall, ResponseCache, cache_key
from helios.pipelines.l_pipe.lpipe_config import (
    MAX_RANKED,
    TIMEOUT_S,
)
from helios.pipelines.l_pipe.ollama_client import (
    OllamaConnectionError,
    OllamaGenerateResult,
    OllamaResponseError,
    OllamaTimeoutError,
)
from helios.pipelines.l_pipe.personas import prompt_sha, render_prompt
from helios.pipelines.l_pipe.response_handler import sanitize_llm_output
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping

    from helios.pipelines.l_pipe.aliases import AliasMap
    from helios.pipelines.l_pipe.digests import Digest
    from helios.pipelines.l_pipe.gateway import LLMGateway
    from helios.pipelines.l_pipe.personas import PersonaProfile

__all__ = ["Claim", "DropReason", "WorkerResult", "run_worker"]

HELIOS_ENABLE_LPIPE_WORKERS: bool = True

_log = logging.getLogger(__name__)

_ALIAS_TOKEN = re.compile(r"\b(?:svc|dep|flag)-\d+\b")


class DropReason(StrEnum):
    """Why a worker's answer was not used."""

    NO_DIGEST = "no_digest"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    HTTP = "http"
    SCHEMA = "schema"
    NO_VALID_CLAIM = "no_valid_claim"
    ALIAS_LEAK = "alias_leak"


@dataclass(frozen=True)
class Claim:
    """One supported claim, unmasked."""

    text: str
    cites: tuple[str, ...]


@dataclass(frozen=True)
class WorkerResult:
    """A worker's validated ranking (real names) or the reason it was dropped."""

    persona: str
    ranked: tuple[str, ...] = ()
    claims: Mapping[str, tuple[Claim, ...]] = field(default_factory=dict)
    dropped: DropReason | None = None
    raw: str | None = None
    cache_hit: bool = False
    wall_ms: float = 0

    @property
    def valid(self) -> bool:
        return self.dropped is None


_CALL_DROPS: dict[type[Exception], DropReason] = {
    OllamaTimeoutError: DropReason.TIMEOUT,
    OllamaConnectionError: DropReason.CONNECTION,
    OllamaResponseError: DropReason.HTTP,
}


class _ClaimIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str
    cites: list[str]


class _RankedIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    service: str
    claims: list[_ClaimIn]


class _AnswerIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ranked: list[_RankedIn]


def _unmask_text(text: str, alias: AliasMap) -> str:
    return _ALIAS_TOKEN.sub(lambda m: alias.backward.get(m.group(0), m.group(0)), text)


def _validate(
    answer: _AnswerIn, digest: Digest, alias: AliasMap
) -> tuple[tuple[str, ...], dict[str, tuple[Claim, ...]]]:
    ids = digest.ids()
    ranked: list[str] = []
    claims: dict[str, tuple[Claim, ...]] = {}
    for entry in answer.ranked:
        if not entry.service.startswith("svc-") or entry.service not in alias.backward:
            continue
        real = alias.unmask(entry.service)
        if real in claims:
            continue
        kept = tuple(
            Claim(_unmask_text(c.text, alias), tuple(c.cites))
            for c in entry.claims
            if c.cites and all(x in ids for x in c.cites)
        )
        if not kept:
            continue
        ranked.append(real)
        claims[real] = kept
        if len(ranked) == MAX_RANKED:
            break
    return tuple(ranked), claims


def _cached(cache: ResponseCache | None, key: str) -> CachedCall | None:
    if cache is None:
        return None
    try:
        return cache.get(key)
    except sqlite3.Error as exc:  # a broken cache never fails a worker
        _log.warning("lpipe cache read failed: %s", exc)
        return None


def _store(cache: ResponseCache | None, key: str, call: CachedCall) -> None:
    if cache is None:
        return
    try:
        cache.put(key, call)
    except sqlite3.Error as exc:
        _log.warning("lpipe cache write failed: %s", exc)


def run_worker(
    persona: PersonaProfile,
    digest: Digest | None,
    alias: AliasMap,
    gateway: LLMGateway,
    *,
    cache: ResponseCache | None = None,
    model_digest: str = "",
) -> WorkerResult:
    """One model call over the worker's digest, then validation.

    No retry: Protocol A decoding is deterministic, so the same prompt gives
    the same answer; a schema failure drops the worker.
    """
    if digest is None or not digest.lines:
        return WorkerResult(persona.name, dropped=DropReason.NO_DIGEST)
    try:
        prompt = render_prompt(persona, digest, alias)
    except AliasLeakError:
        return WorkerResult(persona.name, dropped=DropReason.ALIAS_LEAK)
    key = cache_key(model_digest, prompt_sha(persona), prompt)
    hit = _cached(cache, key)
    if hit is not None:
        raw = hit.text
        gateway.replay(
            OllamaGenerateResult(
                raw, hit.prompt_tokens, hit.completion_tokens, hit.compute_ms
            )
        )
        wall_ms, cache_hit = hit.wall_ms, True
    else:
        t0 = time.monotonic()
        try:
            result = gateway.generate(prompt, timeout_s=TIMEOUT_S)
        except (OllamaTimeoutError, OllamaConnectionError, OllamaResponseError) as exc:
            return WorkerResult(
                persona.name,
                dropped=_CALL_DROPS[type(exc)],
                wall_ms=(time.monotonic() - t0) * 1_000,
            )
        raw, wall_ms, cache_hit = result.text, (time.monotonic() - t0) * 1_000, False
        _store(
            cache,
            key,
            CachedCall(
                raw,
                result.prompt_tokens,
                result.completion_tokens,
                result.compute_ms,
                wall_ms,
            ),
        )
    done = {"raw": raw, "cache_hit": cache_hit, "wall_ms": wall_ms}
    try:
        answer = _AnswerIn.model_validate(json.loads(sanitize_llm_output(raw)))
    except (json.JSONDecodeError, ValidationError):
        return WorkerResult(persona.name, dropped=DropReason.SCHEMA, **done)  # type: ignore[arg-type]
    ranked, claims = _validate(answer, digest, alias)
    if not ranked:
        return WorkerResult(persona.name, dropped=DropReason.NO_VALID_CLAIM, **done)  # type: ignore[arg-type]
    return WorkerResult(persona.name, ranked, claims, **done)  # type: ignore[arg-type]
