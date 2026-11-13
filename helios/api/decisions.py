"""Human decisions on verdicts and their server-side timing (S4.1 A-e, A-f).

A reviewer first opens a view (``ViewTokens.issue``): the server signs the run,
the key, the issue time and a nonce with the decisions secret. The decision
must come back with that token; the server measures the time to decision from
its own clock, so a participant's browser cannot change the E-H7 measure. A
token is single-use (checked against the ledger, so it survives a restart) and
expires after ``TOKEN_TTL_S`` (Ch3's incident window).

Every view and decision is an entry in ``DecisionLedger``, an HMAC-chained log
with a signed anchor, keyed by its own secret (``DECISIONS_SECRET_ENV``),
never the deviation-log key. A decision is never edited; a changed mind is a
second decision and the latest counts.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.hmac_chain import HMACChainedLog

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "DECISIONS",
    "DECISIONS_SECRET_ENV",
    "TOKEN_TTL_S",
    "DecisionLedger",
    "TokenError",
    "ViewToken",
    "ViewTokens",
    "read_entries",
]

DECISIONS_SECRET_ENV = "HELIOS_DECISIONS_HMAC_SECRET"
DECISIONS = ("accept", "escalate", "reject")
TOKEN_TTL_S = 1800  # Ch3's incident window
_MS_PER_S = 1000


class DecisionLedger(HMACChainedLog):
    """Append-only views and decisions of one campaign."""

    REQUIRED_FIELDS: tuple[str, ...] = ("event", "run_id", "incident_id", "key_id")
    LOG_KIND = "decisions"


def read_entries(path: Path) -> list[dict[str, Any]]:
    """Every ledger entry, in order (an absent ledger has none)."""
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


class TokenError(ValueError):
    """A view token that cannot be used; ``status`` is the HTTP status."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class ViewToken:
    run_id: str
    key_id: str
    issued_at: float
    nonce: str

    @property
    def digest(self) -> str:
        raw = f"{self.run_id}|{self.key_id}|{self.issued_at!r}|{self.nonce}"
        return hashlib.sha256(raw.encode()).hexdigest()


class ViewTokens:
    """Signs and checks view tokens with the decisions secret."""

    def __init__(self, secret: bytes, *, ttl_s: float = TOKEN_TTL_S) -> None:
        if len(secret) < 32:
            raise ValueError("the decisions secret must be at least 32 bytes")
        self._secret = secret
        self._ttl = ttl_s

    def _mac(self, body: bytes) -> str:
        return hmac.new(self._secret, body, hashlib.sha256).hexdigest()

    def issue(self, run_id: str, key_id: str, now: float) -> tuple[str, ViewToken]:
        token = ViewToken(run_id, key_id, now, secrets.token_hex(16))
        body = json.dumps(
            {
                "run_id": run_id,
                "key_id": key_id,
                "issued_at": now,
                "nonce": token.nonce,
            },
            sort_keys=True,
        ).encode()
        text = base64.urlsafe_b64encode(body).decode() + "." + self._mac(body)
        return text, token

    def check(self, text: str, *, run_id: str, key_id: str, now: float) -> ViewToken:
        """The token's contents, or TokenError (400 malformed or not this run
        and key, 410 expired)."""
        try:
            encoded, mac = text.rsplit(".", 1)
            body = base64.urlsafe_b64decode(encoded.encode())
            fields = json.loads(body)
        except (ValueError, json.JSONDecodeError) as exc:
            raise TokenError("malformed view token", 400) from exc
        if not hmac.compare_digest(mac, self._mac(body)):
            raise TokenError("view token signature does not match", 400)
        token = ViewToken(
            str(fields["run_id"]),
            str(fields["key_id"]),
            float(fields["issued_at"]),
            str(fields["nonce"]),
        )
        if token.run_id != run_id or token.key_id != key_id:
            raise TokenError("view token is for another run or key", 400)
        if now - token.issued_at > self._ttl:
            raise TokenError("view token expired; open the verdict again", 410)
        return token

    @staticmethod
    def decision_ms(token: ViewToken, now: float) -> float:
        return (now - token.issued_at) * _MS_PER_S
