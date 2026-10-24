"""Ed25519 public-key signatures for append-only ledgers (owner decision D7).

The HMAC chain proves integrity only to holders of the shared secret. An
Ed25519 signature lets anyone holding the public key (committed in the repo
and deposited on OSF) check that an entry was written by the key holder and
not altered since. Signatures are deterministic (RFC 8032), so re-signing the
same payload gives the same bytes.

Key formats:
    private key: base64 of the raw 32-byte seed, in $DEVIATION_ED25519_PRIVATE_KEY
                 (.env, never committed)
    public key:  PEM SubjectPublicKeyInfo, committed (openssl can read it)
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import TYPE_CHECKING, Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "canonical_payload",
    "generate_private_key",
    "load_private_key",
    "load_public_key",
    "private_key_to_env_value",
    "public_key_pem",
    "sign_fields",
    "verify_fields",
]


def canonical_payload(fields: dict[str, Any]) -> bytes:
    """The exact bytes that are signed: sorted-key compact JSON, UTF-8."""
    return json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")


def generate_private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def private_key_to_env_value(key: Ed25519PrivateKey) -> str:
    raw = key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return base64.b64encode(raw).decode("ascii")


def load_private_key(env_value: str) -> Ed25519PrivateKey:
    """Parse the base64 raw seed; raises ValueError on a malformed value."""
    try:
        raw = base64.b64decode(env_value.strip(), validate=True)
    except binascii.Error as exc:
        raise ValueError("Ed25519 private key is not valid base64") from exc
    if len(raw) != 32:
        raise ValueError(f"Ed25519 private key must be 32 bytes (got {len(raw)})")
    return Ed25519PrivateKey.from_private_bytes(raw)


def public_key_pem(material: Ed25519PrivateKey | Ed25519PublicKey) -> bytes:
    public = (
        material.public_key() if isinstance(material, Ed25519PrivateKey) else material
    )
    return public.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def load_public_key(path: Path) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(path.read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError(f"{path} is not an Ed25519 public key")
    return key


def sign_fields(key: Ed25519PrivateKey, fields: dict[str, Any]) -> str:
    """Hex Ed25519 signature over canonical_payload(fields)."""
    return key.sign(canonical_payload(fields)).hex()


def verify_fields(
    key: Ed25519PublicKey, fields: dict[str, Any], signature: str
) -> bool:
    try:
        key.verify(bytes.fromhex(signature), canonical_payload(fields))
    except (InvalidSignature, ValueError):
        return False
    return True
