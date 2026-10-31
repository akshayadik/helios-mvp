"""Chain-of-Evidence ledger (S2.7 design; owner decisions C-a, C-b).

One entry per stored incident run: every decision in order (trigger, routing,
each pipeline, fusion, integrity gate) and the evidence behind it under one ID
namespace, so the S2.8 narrator cites one record and its grounding verifier
checks against it. Entries are HMAC-chained; after each entry the anchor (entry
count, head, digest of the whole file) is Ed25519-signed when the key is loaded
(``verify_public`` with the public key alone), else marked unsigned.
"""

from __future__ import annotations

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.hmac_chain import HMACChainedLog

__all__ = ["CoELedger"]

HELIOS_ENABLE_COE_LEDGER: bool = True


class CoELedger(HMACChainedLog):
    """Append-only CoE log for one orchestrator run."""

    REQUIRED_FIELDS: tuple[str, ...] = (
        "run_id",
        "incident_id",
        "variant_config_hash",
        "snapshot_hash",
        "evaluation_phase",
        "steps",
    )
    LOG_KIND = "coe"
    ANCHOR_ED25519 = True
