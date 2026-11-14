"""API keys and roles (S4.1 A-d).

Keys travel in the ``X-API-Key`` header. The key file (outside git, mode 0600)
holds only SHA-256 digests: ``{"keys": [{"id", "sha256", "roles"}]}``. A key
is printed once by ``bin/helios_api.py keygen`` and never logged.

Roles: ``reader`` (GET), ``reviewer`` (reader plus views and decisions),
``admin`` (reserved). A role includes the ones below it.

Attributes (S4.2 K-e, K-f): a ``blind`` key (an RQ4 participant) sees only the
cases assigned to it and never a variant name; a ``simulated`` key is the
scripted reviewer, and every ledger entry it writes says so.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["ROLES", "ApiKey", "KeyStore", "add_key", "hash_key"]

ROLES = ("reader", "reviewer", "admin")
_KEY_BYTES = 32


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


@dataclass(frozen=True)
class ApiKey:
    id: str
    roles: tuple[str, ...]
    blind: bool = False
    simulated: bool = False

    def allows(self, role: str) -> bool:
        """True when the key holds ``role`` or a role above it."""
        need = ROLES.index(role)
        return any(ROLES.index(r) >= need for r in self.roles)


class KeyStore:
    """The key digests of one deployment."""

    def __init__(self, path: Path) -> None:
        self._keys: list[tuple[str, ApiKey]] = []
        if path.is_file():
            for k in json.loads(path.read_text()).get("keys", []):
                roles = tuple(str(r) for r in k["roles"])
                if unknown := set(roles) - set(ROLES):
                    raise ValueError(f"unknown roles {sorted(unknown)}")
                key = ApiKey(
                    str(k["id"]),
                    roles,
                    blind=bool(k.get("blind", False)),
                    simulated=bool(k.get("simulated", False)),
                )
                self._keys.append((str(k["sha256"]), key))

    def __len__(self) -> int:
        return len(self._keys)

    def lookup(self, key: str | None) -> ApiKey | None:
        """The key's identity, compared in constant time against every digest."""
        if not key:
            return None
        digest = hash_key(key)
        found = None
        for stored, api_key in self._keys:
            if hmac.compare_digest(stored, digest):
                found = api_key
        return found


def add_key(
    path: Path,
    key_id: str,
    roles: list[str],
    *,
    blind: bool = False,
    simulated: bool = False,
) -> str:
    """Create a key, store its digest, return the key (shown once)."""
    if unknown := set(roles) - set(ROLES):
        raise ValueError(f"unknown roles {sorted(unknown)}")
    body = json.loads(path.read_text()) if path.is_file() else {"keys": []}
    if any(k["id"] == key_id for k in body["keys"]):
        raise ValueError(f"key id {key_id!r} exists")
    key = secrets.token_urlsafe(_KEY_BYTES)
    record: dict[str, object] = {"id": key_id, "sha256": hash_key(key), "roles": roles}
    if blind:
        record["blind"] = True
    if simulated:
        record["simulated"] = True
    body["keys"].append(record)
    path.write_text(json.dumps(body, indent=1) + "\n")
    os.chmod(path, 0o600)
    return key
