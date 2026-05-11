"""VCLManifest — single source of truth for variant configuration and hash identity."""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict, field_validator

from .utils import canonical_json


class VCLManifest(BaseModel):
    """Immutable variant configuration; hash is the C1 snapshot identity (§6.2).

    All bool fields mirror VCLFlag.bool_flags(). extra='forbid' ensures the
    canonical JSON is exhaustive — no silent omissions from new fields.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # 12 proposal flags (Table 12 / §3.6.7)
    l2c_llm: bool = False
    p4_cognitive: bool = False
    mahc: bool = False
    cbr: bool = False
    l2b_graph: bool = False
    acp: bool = False
    reconcile: bool = False
    ueg_c_structural: bool = False
    dpipe: bool = False
    dpipe_propagation: bool = False
    gpipe: bool = False
    lpipe: bool = False

    # Cross-pipeline routing; True in all variants except HELIOS-noRouter
    router: bool = True

    # Operational string flag — validated, not a boolean gate
    ingest_mode: str = "recorded"

    @field_validator("ingest_mode")
    @classmethod
    def _validate_ingest_mode(cls, v: str) -> str:
        allowed = ("recorded", "live")
        if v not in allowed:
            raise ValueError(f"ingest_mode must be one of {allowed!r}, got {v!r}")
        return v

    def compute_variant_config_hash(self) -> str:
        """SHA-256 of canonical JSON — deterministic run identity for C1 (§6.2)."""
        payload = canonical_json(self.model_dump())
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def from_flags(cls, **flags: bool | str) -> VCLManifest:
        """Factory for variants.py and orchestrator --variant resolution."""
        return cls(**flags)
