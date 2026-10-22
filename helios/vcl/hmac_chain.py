"""HMAC-SHA256 chained append-only JSONL — C1 audit base for deviation log and exclusion ledger."""

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
    """Append-only JSONL with HMAC-SHA256 chain integrity.

    Subclasses set REQUIRED_FIELDS to add domain field validation.
    Post-sign convenience fields are excluded from the signed payload via
    _UNSIGNED_KEYS. Override _post_sign_fields() to add them.
    """

    REQUIRED_FIELDS: tuple[str, ...] = ()

    def __init__(self, key: bytes, log_path: Path) -> None:
        if len(key) < 32:
            raise ValueError(f"HMAC key must be at least 32 bytes (got {len(key)}).")
        self._key = key
        self._path = log_path

    def previous_signature(self) -> str:
        """Return the last entry's signature, or GENESIS if file is empty/missing."""
        if not self._path.exists() or self._path.stat().st_size == 0:
            return GENESIS
        last = ""
        with self._path.open("r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped:
                    last = stripped
        if not last:
            return GENESIS
        return str(json.loads(last)["signature"])

    def compute_signature(self, entry: dict[str, Any]) -> str:
        """HMAC-SHA256 over canonical JSON of entry, excluding _UNSIGNED_KEYS."""
        payload_dict = {k: v for k, v in entry.items() if k not in _UNSIGNED_KEYS}
        payload = json.dumps(
            payload_dict, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hmac.new(self._key, payload, hashlib.sha256).hexdigest()

    def _post_sign_fields(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Override in subclasses to append post-sign convenience fields before writing."""
        return entry

    def append(self, fields: dict[str, Any]) -> dict[str, Any]:
        """Validate required fields, build signed envelope, append JSONL line."""
        if missing := [f for f in self.REQUIRED_FIELDS if not fields.get(f)]:
            raise ValueError(f"Missing required fields: {missing}")
        prev_sig = self.previous_signature()
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
        return entry

    def verify(self) -> tuple[bool, str]:
        """Walk the chain from genesis; return (ok, message)."""
        if not self._path.exists() or self._path.stat().st_size == 0:
            return True, "Empty log — vacuously valid."
        expected_prev = GENESIS
        with self._path.open("r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                entry = json.loads(stripped)
                if entry.get("prev_signature") != expected_prev:
                    got = entry.get("prev_signature", "")[:12]
                    return False, (
                        f"Line {lineno}: prev_signature mismatch "
                        f"(expected {expected_prev[:12]}..., got {got}...)"
                    )
                recomputed = self.compute_signature(entry)
                if recomputed != entry.get("signature"):
                    return (
                        False,
                        f"Line {lineno}: signature does not verify (entry tampered).",
                    )
                expected_prev = entry["signature"]
        return True, "Chain verified."

    def verify_hmac_chain(self) -> None:
        """Raises TamperDetectedError on failure; delegates to verify()."""
        ok, msg = self.verify()
        if not ok:
            raise TamperDetectedError(msg)
