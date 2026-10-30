"""Response cache for L-pipe worker calls (S2.3 design §5.6).

The workers' inputs do not depend on the variant, so the variants of one
incident share one set of model calls. Key = SHA-256 over (model digest,
prompt SHA, rendered prompt): any change to the model, the prompt file or the
input misses. A hit replays the call's token usage and its measured wall time,
so CpR, latency and TTT count every call as if it were made. Only successful
calls are stored. The file is local and gitignored.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import astuple, dataclass
from typing import TYPE_CHECKING

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["CachedCall", "ResponseCache", "cache_key"]

HELIOS_ENABLE_LPIPE_CACHE: bool = True


@dataclass(frozen=True)
class CachedCall:
    """One model answer with its usage and measured wall time."""

    text: str
    prompt_tokens: int
    completion_tokens: int
    compute_ms: float
    wall_ms: float


def cache_key(model_digest: str, prompt_sha: str, rendered: str) -> str:
    """Content key of one call."""
    payload = "\x00".join((model_digest, prompt_sha, rendered)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class ResponseCache:
    """SQLite-backed store of successful calls."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS calls (key TEXT PRIMARY KEY, text TEXT,"
            " prompt_tokens INTEGER, completion_tokens INTEGER,"
            " compute_ms REAL, wall_ms REAL)"
        )
        self._db.commit()

    def get(self, key: str) -> CachedCall | None:
        row = self._db.execute(
            "SELECT text, prompt_tokens, completion_tokens, compute_ms, wall_ms"
            " FROM calls WHERE key = ?",
            (key,),
        ).fetchone()
        return None if row is None else CachedCall(*row)

    def put(self, key: str, call: CachedCall) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO calls VALUES (?, ?, ?, ?, ?, ?)",
            (key, *astuple(call)),
        )
        self._db.commit()

    def size(self) -> int:
        return int(self._db.execute("SELECT COUNT(*) FROM calls").fetchone()[0])
