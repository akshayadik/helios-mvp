"""Narrator prompt, round 3: the model picks and orders code-written claims
(S2.8 design §5.4, §5.7; owner decision (b), 2026-11-01). Provisional until
the prompt round is chosen and frozen by SHA in a deviation entry (entry C)."""

from __future__ import annotations

import hashlib

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

__all__ = [
    "MAX_PICKS",
    "NARRATOR_PROMPT_SHA",
    "PROMPT_TEMPLATE",
    "PROVISIONAL",
    "SLOT_KINDS",
]

PROVISIONAL = True

SLOT_KINDS: dict[str, tuple[str, ...]] = {
    "story": ("ranking", "shift", "call_structure", "log_message"),
    "contradictions": ("contradiction",),
    "verification": ("verification_step",),
}

MAX_PICKS: dict[str, int] = {"story": 5, "contradictions": 3}
"""Claims the model may pick per slot; verification uses params.max_steps."""

PROMPT_TEMPLATE = """HELIOS-NARRATOR
You choose what an on-call engineer reads in one part of an incident narrative.
SLOT: {slot}
Task: {task}

Every CANDIDATE below is a true statement, already checked against the
incident's evidence. Choose at most {most} of them: the ones the engineer needs
most, most important first. Use each at most once. Answer with candidate IDs
only; you do not write sentences.

INCIDENT WINDOW (UTC): {window}
FUSED VERDICT: {fused}
DISAGREEING PIPELINES: {disagree}

CANDIDATES (ID | kind | statement):
{candidates}
{retry}
Answer with JSON only: {{"claims": ["C1", ...]}}
"""

NARRATOR_PROMPT_SHA = hashlib.sha256(PROMPT_TEMPLATE.encode("utf-8")).hexdigest()
