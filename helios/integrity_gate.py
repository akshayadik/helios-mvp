"""Metric Integrity Gate — per-run C1 schema and hash validation (§6.4).

The gate validates result rows produced by pipeline runs:
  1. All required fields are present.
  2. variant_config_hash matches the expected manifest hash.
  3. Across multiple pipelines, both variant_config_hash and snapshot_hash
     must agree (cross_pipeline consistency check).

On any failure the gate auto-writes a signed entry to the supplied
AppendOnlyLedger (typically ExclusionLedger from bin/log_exclusion.py)
and returns a GateResult with status="FAIL".

Design: MetricIntegrityGate depends on the AppendOnlyLedger Protocol only —
no import from bin/ is needed, keeping the helios library layer clean.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Sequence

    from helios.vcl.config import VCLManifest

__all__ = [
    "AppendOnlyLedger",
    "GateResult",
    "MetricIntegrityGate",
]


@runtime_checkable
class AppendOnlyLedger(Protocol):
    """Structural protocol satisfied by ExclusionLedger (and test doubles)."""

    def append(self, fields: dict[str, str]) -> None: ...


@dataclass(frozen=True)
class GateResult:
    """Immutable result returned by MetricIntegrityGate.check()."""

    status: Literal["PASS", "FAIL"]
    reason: str | None = None
    gate_check: str | None = None


class MetricIntegrityGate:
    """Validate per-run result rows and auto-write exclusions on failure.

    Construct via from_manifest() to derive the expected config hash from
    the active VCLManifest, or directly with expected_config_hash for
    testing / orchestrator use.
    """

    REQUIRED_FIELDS: tuple[str, ...] = (
        "variant_config_hash",
        "snapshot_hash",
        "run_id",
    )

    def __init__(
        self,
        *,
        expected_config_hash: str,
        ledger: AppendOnlyLedger,
        run_id: str,
        analytic_consequence: str,
    ) -> None:
        self._expected = expected_config_hash
        self._ledger = ledger
        self._run_id = run_id
        self._analytic_consequence = analytic_consequence

    @classmethod
    def from_manifest(
        cls,
        manifest: VCLManifest,
        *,
        ledger: AppendOnlyLedger,
        run_id: str,
        analytic_consequence: str,
    ) -> MetricIntegrityGate:
        """Construct using the hash of an active VCLManifest as the expected hash."""
        return cls(
            expected_config_hash=manifest.compute_variant_config_hash(),
            ledger=ledger,
            run_id=run_id,
            analytic_consequence=analytic_consequence,
        )

    def check(self, row: dict[str, Any], *, incident_id: str) -> GateResult:
        """Validate a single result row.

        Checks required fields are present, then that variant_config_hash
        matches the expected hash derived from the active manifest.
        Writes to ledger and returns FAIL on the first violation found.
        """
        for field in self.REQUIRED_FIELDS:
            if field not in row:
                return self._fail(
                    row,
                    incident_id,
                    gate_check="required_field_present",
                    reason=f"Required field '{field}' missing from result row",
                )
        if row["variant_config_hash"] != self._expected:
            return self._fail(
                row,
                incident_id,
                gate_check="variant_config_hash_match",
                reason=(
                    f"variant_config_hash mismatch: "
                    f"expected {self._expected[:8]}..., "
                    f"got {str(row['variant_config_hash'])[:8]}..."
                ),
            )
        return GateResult(status="PASS")

    def check_consistency(
        self,
        rows: Sequence[dict[str, Any]],
        *,
        incident_id: str,
    ) -> GateResult:
        """Validate a set of rows from all active pipelines for a single run.

        First validates each row individually, then checks that all rows agree
        on variant_config_hash and snapshot_hash (cross-pipeline consistency).
        """
        for row in rows:
            result = self.check(row, incident_id=incident_id)
            if result.status == "FAIL":
                return result

        snap_hashes = {row["snapshot_hash"] for row in rows}
        if len(snap_hashes) > 1:
            return self._fail(
                rows[0],
                incident_id,
                gate_check="cross_pipeline_snapshot_hash_match",
                reason=(
                    f"snapshot_hash inconsistency across pipelines: "
                    f"{sorted(snap_hashes)}"
                ),
            )

        return GateResult(status="PASS")

    def _fail(
        self,
        row: dict[str, Any],
        incident_id: str,
        *,
        gate_check: str,
        reason: str,
    ) -> GateResult:
        self._ledger.append(
            {
                "variant_config_hash": str(row.get("variant_config_hash", "UNKNOWN")),
                "snapshot_hash": str(row.get("snapshot_hash", "UNKNOWN")),
                "run_id": self._run_id,
                "incident_id": incident_id,
                "gate_check": gate_check,
                "reason": reason,
                "analytic_consequence": self._analytic_consequence,
            }
        )
        return GateResult(status="FAIL", reason=reason, gate_check=gate_check)
