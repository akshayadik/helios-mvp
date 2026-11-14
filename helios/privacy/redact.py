"""Pattern-based PII redaction before any LLM call (S4.4).

Design s4_4_7_tier2_design.md T-b/T-c. A product setting outside the VCL
manifest (owner decision 2026-11-11, option a): ``HELIOS_PII_REDACTION=on``
switches it on; it is OFF by default and refused in confirmatory runs, so the
evidence path and every response-cache key are unchanged.

Each match becomes a deterministic placeholder numbered by first appearance
in one text (``<EMAIL_1>``, ``<IP_2>``): the same value always gets the same
placeholder, so sentences stay readable for the model. Only counts per rule
are ever recorded, never values. NER-based redaction of names in free text is
Stage B (B2).
"""

from __future__ import annotations

import hashlib
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Mapping

__all__ = [
    "PII_REDACTION_ENV",
    "RULES",
    "RULESET_ID",
    "Redaction",
    "luhn_ok",
    "redact",
    "redaction_enabled",
]

HELIOS_ENABLE_PII_REDACTION: bool = True

PII_REDACTION_ENV = "HELIOS_PII_REDACTION"


def luhn_ok(digits: str) -> bool:
    """The Luhn check of a card number (digits only)."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# Issuer prefixes of the major card schemes; with the Luhn check this keeps
# long numeric ids (trace ids, timestamps) out of the CARD rule.
_CARD_PREFIX = re.compile(r"^(?:4|5[1-5]|2[2-7]|3[47]|6(?:011|5))")


def _card(match: re.Match[str]) -> bool:
    digits = re.sub(r"\D", "", match.group(0))
    return (
        13 <= len(digits) <= 19 and bool(_CARD_PREFIX.match(digits)) and luhn_ok(digits)
    )


@dataclass(frozen=True)
class _Rule:
    name: str  # placeholder stem
    pattern: re.Pattern[str]
    group: int = 0  # the part replaced (key=value secrets keep the key)
    check: Callable[[re.Match[str]], bool] | None = field(default=None, compare=False)


_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
_HEX = r"[0-9A-Fa-f]{1,4}"

# Order matters: earlier rules claim text first (a JWT before a key=value
# secret, a MAC before IPv6, an email before anything with a dot).
RULES: tuple[_Rule, ...] = (
    _Rule("JWT", re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+")),
    _Rule("TOKEN", re.compile(r"(?i)\bbearer\s+([\w.~+/=-]{8,})"), group=1),
    _Rule(
        "SECRET",
        re.compile(
            r"(?i)\b(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key)"
            r"\s*[=:]\s*([^\s,;&\"']+)"
        ),
        group=1,
    ),
    _Rule("AWS_KEY", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    _Rule("EMAIL", re.compile(r"\b[\w.%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    _Rule("MAC", re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")),
    _Rule(
        "IP",
        re.compile(
            rf"(?<![\w:])(?:(?:{_HEX}:){{7}}{_HEX}"
            rf"|(?:{_HEX}:){{1,7}}:(?:{_HEX}(?::{_HEX}){{0,6}})?"
            rf"|::(?:{_HEX}(?::{_HEX}){{0,6}}))(?![\w:])"
        ),
    ),
    _Rule("IP", re.compile(rf"(?<![\d.]){_OCTET}(?:\.{_OCTET}){{3}}(?![\d.])")),
    _Rule("CARD", re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)"), check=_card),
    _Rule(
        "PHONE",
        re.compile(r"(?<![\w+])\+\d{1,3}[ .-]?\(?\d{1,4}\)?(?:[ .-]?\d{2,4}){2,4}\b"),
    ),
)

# Bumped whenever a rule's check changes (a check is code, not a pattern).
RULES_VERSION = "2026-11-14.2"  # .2: card-scheme prefixes added to CARD
RULESET_ID = hashlib.sha256(
    "\n".join(
        [RULES_VERSION, *(f"{r.name}\t{r.group}\t{r.pattern.pattern}" for r in RULES)]
    ).encode()
).hexdigest()[:16]


@dataclass(frozen=True)
class Redaction:
    text: str
    counts: Mapping[str, int]


def redact(text: str, *, protected: Collection[str] = ()) -> Redaction:
    """``text`` with every match replaced by its placeholder. A match equal
    to a ``protected`` term (a service name, an evidence id) is kept."""
    keep = set(protected)
    seen: dict[tuple[str, str], str] = {}
    numbers: Counter[str] = Counter()
    counts: Counter[str] = Counter()

    def placeholder(name: str, value: str) -> str:
        if (name, value) not in seen:
            numbers[name] += 1
            seen[name, value] = f"<{name}_{numbers[name]}>"
        counts[name] += 1
        return seen[name, value]

    for rule in RULES:

        def swap(m: re.Match[str], rule: _Rule = rule) -> str:
            value = m.group(rule.group)
            if value in keep or (rule.check is not None and not rule.check(m)):
                return m.group(0)
            if value.startswith("<") and value.endswith(">"):
                return m.group(0)  # already a placeholder
            whole = m.group(0)
            start = m.start(rule.group) - m.start(0)
            end = start + len(value)
            return whole[:start] + placeholder(rule.name, value) + whole[end:]

        text = rule.pattern.sub(swap, text)
    return Redaction(text, dict(sorted(counts.items())))


def redaction_enabled(env: Mapping[str, str] | None = None) -> bool:
    """``HELIOS_PII_REDACTION``: ``on`` or ``off`` (default); anything else is
    an error, so a typo never silently leaves PII in a prompt."""
    raw = (os.environ if env is None else env).get(PII_REDACTION_ENV, "off")
    value = raw.strip().lower()
    if value not in ("on", "off"):
        raise ValueError(f"{PII_REDACTION_ENV} must be on or off, not {raw!r}")
    return value == "on"
