"""Annotations ledger: every rater, adjudicator and blinding-check answer
(S2.9 design §5.5, R-n).

HMAC-chained per entry like every ledger here, with an Ed25519-signed anchor
(the CoE ledger's anchor-only mode, S2.7) under its own key pair, so the
deviation log's private key never sits in the long-running labelling server.
A label is changed only by appending a newer entry; ``latest`` keeps the last
one per (item, person).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.hmac_chain import HMACChainedLog

__all__ = [
    "ANNOTATIONS_ENV_VAR",
    "ANNOTATIONS_PUBLIC_KEY_FILE",
    "CATEGORIES",
    "GUESSES",
    "KINDS",
    "VERDICTS",
    "AnnotationLedger",
    "latest",
]

ANNOTATIONS_ENV_VAR = "ANNOTATIONS_ED25519_PRIVATE_KEY"
ANNOTATIONS_PUBLIC_KEY_FILE = Path("keys/annotations_ed25519.pub.pem")

# Error categories in the order a rater checks them (owner decision R-e).
CATEGORIES: tuple[str, ...] = (
    "numeric_drift",
    "entity_mismatch",
    "directional_inversion",
    "log_quote_mismatch",
    "missing_citation",
)
KINDS: tuple[str, ...] = ("label", "adjudication", "blind_guess")
VERDICTS: tuple[str, ...] = ("supported", "unsupported")
GUESSES: tuple[str, ...] = ("A", "B", "unsure")  # blinding check (R-k)


def _check(fields: dict[str, Any]) -> None:
    kind, verdict = fields.get("kind"), fields.get("verdict")
    category = fields.get("category", "")
    if kind not in KINDS:
        raise ValueError(f"unknown annotation kind {kind!r}")
    if kind == "blind_guess":
        if verdict not in GUESSES or category:
            raise ValueError("a blinding-check answer is A, B or unsure")
    elif verdict not in VERDICTS:
        raise ValueError(f"unknown verdict {verdict!r}")
    elif (verdict == "unsupported") != bool(category):
        raise ValueError("a category is required for, and only for, unsupported")
    elif category and category not in CATEGORIES:
        raise ValueError(f"unknown category {category!r}")
    dwell = fields.get("dwell_ms")
    if not isinstance(dwell, int) or dwell < 0:
        raise ValueError("dwell_ms must be a non-negative integer")
    if not isinstance(fields.get("note", ""), str):
        raise ValueError("note must be text")


class AnnotationLedger(HMACChainedLog):
    """Append-only labels for one labelling set."""

    # Only fields that are never empty; category, note and dwell are checked
    # in ``append`` (a supported label has an empty category, dwell may be 0).
    REQUIRED_FIELDS: tuple[str, ...] = ("set_hash", "item", "person", "kind", "verdict")
    LOG_KIND = "annotations"
    ANCHOR_ED25519 = True

    def append(self, fields: dict[str, Any]) -> dict[str, Any]:
        record = {"category": "", "note": "", **fields}
        _check(record)
        return super().append(record)


def latest(
    ledger: AnnotationLedger, kind: str
) -> dict[tuple[str, str], dict[str, Any]]:
    """The last entry of ``kind`` per (item, person), in ledger order."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    path = ledger._path
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("kind") == kind:
            out[str(entry["item"]), str(entry["person"])] = entry
    return out
