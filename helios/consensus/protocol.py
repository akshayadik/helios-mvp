"""ConsensusAlgorithm Protocol — interface contract for fusion algorithm implementations.

Defines the single method every consensus algorithm must expose, decoupling
callers (fuse_verdicts.py) from concrete classes (UniformBordaConsensus,
PassthroughConsensus).  Structural subtyping — no explicit inheritance required.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from helios.consensus.verdict import ConsensusVerdict

HELIOS_ENABLE_CONSENSUS_PROTOCOL: bool = True


class ConsensusAlgorithm(Protocol):
    """Structural protocol satisfied by any object with a `fuse` method."""

    def fuse(
        self,
        *,
        incident_id: str,
        variant: str,
        pipeline_rows: list[dict[str, Any]],
        run_id: str,
    ) -> ConsensusVerdict: ...
