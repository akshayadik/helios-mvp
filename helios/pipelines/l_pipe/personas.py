"""Persona Profiles of the L-pipe workers (S2.3 design §5.1).

Each worker reads exactly one stream through its own digest builder, and has
no tools: the builder is the only code that opens telemetry for it. Each has
one registered prompt; its SHA-256 is frozen in ``lpipe_config``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from helios.pipelines.l_pipe import lpipe_config
from helios.pipelines.l_pipe.digests import log_digest, metric_digest, trace_digest
from helios.pipelines.l_pipe.lpipe_config import MAX_RANKED
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Callable

    from helios.pipelines.l_pipe.aliases import AliasMap
    from helios.pipelines.l_pipe.digests import Digest

__all__ = ["PERSONAS", "PersonaProfile", "prompt_sha", "provisional", "render_prompt"]

HELIOS_ENABLE_LPIPE_PERSONAS: bool = True

_PROMPTS = Path(__file__).parent / "prompts"


@dataclass(frozen=True)
class PersonaProfile:
    """One worker: the stream it may read, its digest builder and its prompt."""

    name: Literal["metric", "log", "trace"]
    stream: Literal["p1", "p3", "p2"]
    prompt_path: Path
    build: Callable[..., Digest | None]


PERSONAS: tuple[PersonaProfile, ...] = (
    PersonaProfile("metric", "p1", _PROMPTS / "metric_v1.txt", metric_digest),
    PersonaProfile("log", "p3", _PROMPTS / "log_v1.txt", log_digest),
    PersonaProfile("trace", "p2", _PROMPTS / "trace_v1.txt", trace_digest),
)


def prompt_sha(persona: PersonaProfile) -> str:
    """SHA-256 of the worker's prompt file."""
    return hashlib.sha256(persona.prompt_path.read_bytes()).hexdigest()


def provisional() -> bool:
    """True while any worker prompt SHA is not frozen."""
    return any(v is None for v in lpipe_config.WORKER_PROMPT_SHAS.values())


def render_prompt(persona: PersonaProfile, digest: Digest, alias: AliasMap) -> str:
    """The worker's prompt over its masked digest; refuses a surviving real name."""
    candidates = sorted(a for a in alias.backward if a.startswith("svc-"))
    text = persona.prompt_path.read_text(encoding="utf-8").format(
        candidates=", ".join(candidates),
        digest=digest.render(alias),
        max_ranked=MAX_RANKED,
    )
    alias.check(text)
    return text
