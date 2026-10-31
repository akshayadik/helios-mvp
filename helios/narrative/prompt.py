"""Narrator prompt, round 1 (S2.8 design §5.4, §5.7). Provisional until the
prompt round is chosen and frozen by SHA in a deviation entry (entry C)."""

from __future__ import annotations

import hashlib

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

__all__ = ["NARRATOR_PROMPT_SHA", "PROMPT_TEMPLATE", "PROVISIONAL", "SLOT_KINDS"]

PROVISIONAL = True

SLOT_KINDS: dict[str, tuple[str, ...]] = {
    "story": ("ranking", "shift", "call_structure", "log_message"),
    "contradictions": ("contradiction",),
    "verification": ("verification_step",),
}

PROMPT_TEMPLATE = """HELIOS-NARRATOR
You write one part of an incident narrative for an on-call engineer.
SLOT: {slot}
Task: {task}

Every statement is one claim. Each claim cites evidence IDs from the list
below and nothing else. A claim is shown only if its cited evidence exists and
supports it; unsupported claims are discarded.

Rules:
- Cite only IDs listed under EVIDENCE (or F for the fused ranking).
- One fact per claim. Name only the services the claim is about.
- Use only numbers that appear in the cited evidence. You may round them, write
  a fraction as a percent, or ms as seconds. Never invent a number.
- A shift claim's direction (up or down) must match the cited evidence.
- A log_message claim quotes its snippet verbatim, in double quotes, and the
  snippet must occur in the cited log line.
- A call_structure claim gives caller and callee exactly as the evidence does.
- Times are UTC within the incident window.
- Allowed kinds in this slot: {kinds}.

Claim fields by kind:
- ranking: service, rank (1-3), cites ["F"]
- shift: service, channel (error|latency|resource), direction (up|down)
- call_structure: caller, callee, feature (wait|lead|ghost)
- log_message: service, snippet
- contradiction: pipeline (dpipe|gpipe|lpipe), service (that pipeline's top suspect)
- verification_step: target_service, action_verb ({verbs}), modality
  (metric|log|edge); the sentence starts with the verb; read-only checks only;
  at most {max_steps} steps
Every claim also has "kind", "sentence" and "cites".

INCIDENT WINDOW (UTC): {window}
FUSED VERDICT: {fused}
DISAGREEING PIPELINES: {disagree}

EVIDENCE (ID | service | what | values):
{evidence}
{retry}
Answer with JSON only: {{"claims": [ ... ]}}
"""

NARRATOR_PROMPT_SHA = hashlib.sha256(PROMPT_TEMPLATE.encode("utf-8")).hexdigest()
