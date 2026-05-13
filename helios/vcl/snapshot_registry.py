"""Content-addressable snapshot identity registry (§6.2, §3.6.5).

Append-only JSONL mapping snapshot_hash → variant_config_hash + timestamp.
Used by the metric integrity gate to verify C1 run-level inclusion (§5.1).
No HMAC: identity is proved by hash content, not chain signatures.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "DuplicateSnapshotError",
    "SnapshotRegistry",
]

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


class DuplicateSnapshotError(ValueError):
    """Raised when a snapshot_hash is registered more than once."""


class SnapshotRegistry:
    """Append-only JSONL registry for UEGCSnapshot content-addressable identity.

    Each line: {"snapshot_hash": ..., "variant_config_hash": ..., "registered_at": ...}
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def register(self, snapshot_hash: str, variant_config_hash: str) -> None:
        """Append a new entry. Raises DuplicateSnapshotError if already present."""
        _validate_hex64("snapshot_hash", snapshot_hash)
        _validate_hex64("variant_config_hash", variant_config_hash)
        if self.contains(snapshot_hash):
            raise DuplicateSnapshotError(
                f"snapshot_hash already registered: {snapshot_hash[:16]}..."
            )
        entry = {
            "snapshot_hash": snapshot_hash,
            "variant_config_hash": variant_config_hash,
            "registered_at": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")

    def contains(self, snapshot_hash: str) -> bool:
        """Return True if snapshot_hash has been registered."""
        return snapshot_hash in self._load_hashes()

    def all_hashes(self) -> list[str]:
        """Return all registered hashes in insertion order."""
        return list(self._load_hashes())

    def verify(self) -> None:
        """Raise DuplicateSnapshotError if any hash appears more than once."""
        seen: set[str] = set()
        for entry in self._iter_entries():
            h = entry["snapshot_hash"]
            if h in seen:
                raise DuplicateSnapshotError(
                    f"Duplicate snapshot_hash in registry: {h[:16]}..."
                )
            seen.add(h)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _iter_entries(self) -> list[dict[str, str]]:
        if not self._path.exists():
            return []
        entries = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped:
                entries.append(json.loads(stripped))
        return entries

    def _load_hashes(self) -> dict[str, None]:
        return {e["snapshot_hash"]: None for e in self._iter_entries()}


def _validate_hex64(field: str, value: str) -> None:
    if not _HEX64_RE.match(value):
        raise ValueError(
            f"{field} must be a 64-character lowercase hex string (got {repr(value)[:20]})"
        )
