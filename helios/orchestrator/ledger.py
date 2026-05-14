"""ReconciliationLedger — per-incident outcome tracking for a corpus run (§5.1).

HMAC-chained JSONL (same chain as deviation log and exclusion ledger). One row
per incident per run: outcome ∈ {attempted, passed, excluded, skipped}. Provides
the audit trail proving C1 gate compliance across all calibration incidents.
"""

from __future__ import annotations

from helios.vcl.hmac_chain import HMACChainedLog

__all__ = ["ReconciliationLedger"]

HELIOS_ENABLE_ORCHESTRATOR: bool = True


class ReconciliationLedger(HMACChainedLog):
    """HMAC-chained per-incident outcome log for a corpus run."""

    REQUIRED_FIELDS: tuple[str, ...] = (
        "run_id",
        "incident_id",
        "variant_config_hash",
        "outcome",
    )

    OUTCOMES: frozenset[str] = frozenset({"attempted", "passed", "excluded", "skipped"})

    def record(
        self,
        *,
        run_id: str,
        incident_id: str,
        variant_config_hash: str,
        outcome: str,
        gate_check: str = "",
    ) -> dict[str, str]:
        """Append a signed outcome row. Raises ValueError for invalid outcome."""
        if outcome not in self.OUTCOMES:
            raise ValueError(
                f"outcome must be one of {sorted(self.OUTCOMES)}, got {outcome!r}"
            )
        return self.append(
            {
                "run_id": run_id,
                "incident_id": incident_id,
                "variant_config_hash": variant_config_hash,
                "outcome": outcome,
                "gate_check": gate_check,
            }
        )
