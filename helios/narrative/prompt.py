"""Narrator prompt, round 2 (S2.8 design §5.4, §5.7). Provisional until the
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

Write at most {most} claims: the ones the engineer needs most. Each claim is
one short sentence. The answer format lists every claim you may make, with its
fields already filled from the evidence; pick claims from it, fill "cites" and
write the "sentence". A claim is shown only if its sentence says exactly what
its fields say; otherwise the whole slot is replaced.

How to write the sentence:
- Use only the ALLOWED WORDS below, the claim's own service names, and numbers
  copied from its own evidence line with their unit. No other words.
- Follow the example shape of the claim's kind (X, Y and Z stand for service
  names; use the real names):
  ranking: "X is the top suspect." / "X is the second suspect."
  shift: "X latency rose from 120 ms to 900 ms." / "X errors rose sharply
  after the trigger."
  call_structure: wait "Y spent 94% of its time waiting on X." / lead "X moved
  before its caller Y." / ghost "Y started calling X after the trigger."
  log_message: X logged "connection pool exhausted".
  contradiction: "G-pipe ranks Y first, while the fused verdict ranks X first."
  verification_step: "Query X latency between 14:42 and 14:56." / "Filter X
  logs between 14:42 and 14:56." / "Inspect X incoming calls between 14:42 and
  14:56." The sentence starts with the action verb ({verbs}).
- A log snippet is an exact run of whole words from the cited log line, at
  least 12 characters, copied character for character. Put the same text in
  "snippet" and, in double quotes, in the sentence. No other quotes.
- One line per sentence; no brackets, no evidence IDs in the sentence.
- Times are HH:MM (UTC) inside the incident window, in verification steps only.

Evidence IDs: F is the fused verdict; D: is a D-pipe metric, L: an L-pipe log
line, G: a G-pipe call-graph edge.

ALLOWED WORDS: {vocabulary}

INCIDENT WINDOW (UTC): {window}
FUSED VERDICT: {fused}
DISAGREEING PIPELINES: {disagree}

EVIDENCE (ID | service | what | values):
{evidence}
{retry}
Answer with JSON only: {{"claims": [ ... ]}}
"""

NARRATOR_PROMPT_SHA = hashlib.sha256(PROMPT_TEMPLATE.encode("utf-8")).hexdigest()
