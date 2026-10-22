"""HMAC-SHA256 chained append-only JSONL — C1 audit base for deviation log and exclusion ledger.

Integrity model:
- Each entry signs its own fields plus the previous entry's signature, so any
  edit, deletion, insertion or reordering inside the log breaks verification.
- A chain alone cannot detect removal of entries from the END of the log (the
  shorter prefix is still a valid chain). A signed head anchor
  (`<log stem>.anchor.json`) records the entry count and head signature;
  `verify()` fails when the log and its anchor disagree, and `append()` refuses
  to extend a log whose tail no longer matches its anchor.
- `verify()` also checks every entry carries the subclass REQUIRED_FIELDS, so a
  log of one kind cannot be substituted for another (all ledgers share a key).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
import subprocess
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "GENESIS",
    "HMACChainedLog",
    "TamperDetectedError",
]


class TamperDetectedError(RuntimeError):
    """Raised by verify_hmac_chain() when HMAC chain integrity fails."""


GENESIS = "GENESIS"
_UNSIGNED_KEYS: frozenset[str] = frozenset({"signature", "deviation_id"})
_ANCHOR_VERSION = 1
_ANCHOR_SIGNATURE_KEY = "anchor_signature"


def _resolve_commit_sha() -> str:
    """Return the current git HEAD SHA, falling back to LOCAL."""
    sha = os.getenv("GITHUB_SHA")
    if sha:
        return sha
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return result.stdout.strip()
    except Exception:  # subprocess failure, git absent, or timeout
        return "LOCAL"


class HMACChainedLog:
    """Append-only JSONL with HMAC-SHA256 chain integrity and a signed head anchor.

    Subclasses set REQUIRED_FIELDS to add domain field validation and LOG_KIND
    to bind the anchor to one kind of log.
    Post-sign convenience fields are excluded from the signed payload via
    _UNSIGNED_KEYS. Override _post_sign_fields() to add them and
    _check_post_sign_fields() to verify them.
    """

    REQUIRED_FIELDS: tuple[str, ...] = ()
    LOG_KIND: str = "generic"

    def __init__(self, key: bytes, log_path: Path) -> None:
        if len(key) < 32:
            raise ValueError(f"HMAC key must be at least 32 bytes (got {len(key)}).")
        self._key = key
        self._path = log_path

    @property
    def anchor_path(self) -> Path:
        """Sibling file holding the signed (entry count, head signature) anchor."""
        return self._path.with_name(f"{self._path.stem}.anchor.json")

    # ------------------------------------------------------------------
    # Signing
    # ------------------------------------------------------------------

    def _sign(self, payload_dict: dict[str, Any]) -> str:
        payload = json.dumps(
            payload_dict, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hmac.new(self._key, payload, hashlib.sha256).hexdigest()

    def compute_signature(self, entry: dict[str, Any]) -> str:
        """HMAC-SHA256 over canonical JSON of entry, excluding _UNSIGNED_KEYS."""
        return self._sign({k: v for k, v in entry.items() if k not in _UNSIGNED_KEYS})

    # ------------------------------------------------------------------
    # Tail and anchor
    # ------------------------------------------------------------------

    def _tail(self) -> tuple[int, str]:
        """Return (entry count, last signature or GENESIS) without verifying."""
        if not self._path.exists() or self._path.stat().st_size == 0:
            return 0, GENESIS
        count, last = 0, ""
        with self._path.open("r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped:
                    count += 1
                    last = stripped
        if not last:
            return 0, GENESIS
        return count, str(json.loads(last)["signature"])

    def previous_signature(self) -> str:
        """Return the last entry's signature, or GENESIS if file is empty/missing."""
        return self._tail()[1]

    def _anchor_fields(self, entries: int, head_signature: str) -> dict[str, Any]:
        return {
            "anchor_version": _ANCHOR_VERSION,
            "log_kind": self.LOG_KIND,
            "entries": entries,
            "head_signature": head_signature,
        }

    def _write_anchor(self, entries: int, head_signature: str) -> None:
        fields = self._anchor_fields(entries, head_signature)
        anchor = {**fields, _ANCHOR_SIGNATURE_KEY: self._sign(fields)}
        tmp = self.anchor_path.with_name(self.anchor_path.name + ".tmp")
        tmp.write_text(json.dumps(anchor, sort_keys=True, indent=2) + "\n", "utf-8")
        os.replace(tmp, self.anchor_path)

    def _check_anchor(self, entries: int, head_signature: str) -> str | None:
        """Return an error message if the anchor does not match, else None."""
        if not self.anchor_path.exists():
            if entries == 0:
                return None
            return (
                f"No anchor file {self.anchor_path.name} for a log with {entries} "
                "entries — truncation cannot be ruled out. Run anchor init once "
                "after an independent review of the log."
            )
        try:
            anchor = json.loads(self.anchor_path.read_text(encoding="utf-8"))
            claimed_sig = anchor.pop(_ANCHOR_SIGNATURE_KEY)
        except (json.JSONDecodeError, KeyError, AttributeError):
            return f"Anchor {self.anchor_path.name} is unreadable or unsigned."
        if not hmac.compare_digest(self._sign(anchor), str(claimed_sig)):
            return f"Anchor {self.anchor_path.name} signature does not verify."
        if anchor.get("log_kind") != self.LOG_KIND:
            return (
                f"Anchor is for log kind {anchor.get('log_kind')!r}, "
                f"expected {self.LOG_KIND!r}."
            )
        if anchor.get("anchor_version") != _ANCHOR_VERSION:
            return f"Unsupported anchor version {anchor.get('anchor_version')!r}."
        if (anchor.get("entries"), anchor.get("head_signature")) != (
            entries,
            head_signature,
        ):
            return (
                f"Anchor records {anchor.get('entries')} entries ending "
                f"{str(anchor.get('head_signature'))[:12]}..., log has {entries} "
                f"ending {head_signature[:12]}... (entries removed, rolled back, "
                "or appended without the anchor)."
            )
        return None

    def init_anchor(self) -> str:
        """Create the anchor for an existing, verified log. Refuses to overwrite."""
        if self.anchor_path.exists():
            raise FileExistsError(f"{self.anchor_path} already exists.")
        ok, msg, entries, head = self._walk()
        if not ok:
            raise TamperDetectedError(f"Refusing to anchor an invalid log: {msg}")
        self._write_anchor(entries, head)
        return f"Anchored {entries} entries (head {head[:12]}...)."

    # ------------------------------------------------------------------
    # Append and verify
    # ------------------------------------------------------------------

    def _post_sign_fields(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Override in subclasses to append post-sign convenience fields before writing."""
        return entry

    def _check_post_sign_fields(self, entry: dict[str, Any]) -> str | None:
        """Override to verify post-sign fields; return an error message or None."""
        return None

    def append(self, fields: dict[str, Any]) -> dict[str, Any]:
        """Validate required fields, build signed envelope, append JSONL line."""
        if missing := [f for f in self.REQUIRED_FIELDS if not fields.get(f)]:
            raise ValueError(f"Missing required fields: {missing}")
        entries, prev_sig = self._tail()
        if err := self._check_anchor(entries, prev_sig):
            raise TamperDetectedError(f"Refusing to append: {err}")
        entry: dict[str, Any] = {
            "timestamp_utc": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
            "commit_sha": _resolve_commit_sha(),
            "prev_signature": prev_sig,
            **fields,
        }
        entry["signature"] = self.compute_signature(entry)
        entry = self._post_sign_fields(entry)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
        self._write_anchor(entries + 1, entry["signature"])
        return entry

    def _walk(self) -> tuple[bool, str, int, str]:
        """Verify chain, schema and post-sign fields; return (ok, msg, count, head)."""
        expected_prev = GENESIS
        count = 0
        if not self._path.exists():
            return True, "", 0, GENESIS
        with self._path.open("r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                entry = json.loads(stripped)
                if entry.get("prev_signature") != expected_prev:
                    got = entry.get("prev_signature", "")[:12]
                    return (
                        False,
                        f"Line {lineno}: prev_signature mismatch "
                        f"(expected {expected_prev[:12]}..., got {got}...)",
                        count,
                        expected_prev,
                    )
                recomputed = self.compute_signature(entry)
                if recomputed != entry.get("signature"):
                    return (
                        False,
                        f"Line {lineno}: signature does not verify (entry tampered).",
                        count,
                        expected_prev,
                    )
                if missing := [f for f in self.REQUIRED_FIELDS if not entry.get(f)]:
                    return (
                        False,
                        f"Line {lineno}: missing required fields {missing} "
                        f"(not a {self.LOG_KIND} entry).",
                        count,
                        expected_prev,
                    )
                if err := self._check_post_sign_fields(entry):
                    return False, f"Line {lineno}: {err}", count, expected_prev
                expected_prev = entry["signature"]
                count += 1
        return True, "", count, expected_prev

    def verify(self) -> tuple[bool, str]:
        """Walk the chain from genesis and check the head anchor; return (ok, message)."""
        ok, msg, count, head = self._walk()
        if not ok:
            return False, msg
        if err := self._check_anchor(count, head):
            return False, err
        if count == 0:
            return True, "Empty log — vacuously valid."
        return True, "Chain verified."

    def verify_hmac_chain(self) -> None:
        """Raises TamperDetectedError on failure; delegates to verify()."""
        ok, msg = self.verify()
        if not ok:
            raise TamperDetectedError(msg)
