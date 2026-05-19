"""RunOrchestrator — wires full C1 pipeline dispatch for a corpus run (§3.6.8, §5.1).

For each incident: CaptureReader verifies hash → SnapshotRegistry registers snapshot
→ three pipeline stubs dispatch → MetricIntegrityGate checks consistency
→ ResultStore inserts passing verdicts → ReconciliationLedger records outcome.
"""

from __future__ import annotations

import contextlib
import uuid
from typing import TYPE_CHECKING, Any

from helios.graph.ppr_pruner import prune_graph
from helios.graph.ueg_c_builder import build_ueg_c
from helios.integrity_gate import AppendOnlyLedger, MetricIntegrityGate
from helios.orchestrator.corpus import CorpusLoader
from helios.orchestrator.ledger import ReconciliationLedger
from helios.pipelines.d_pipe.pipeline import run_dpipe
from helios.pipelines.g_pipe.pipeline import run_gpipe, should_run_gpipe
from helios.pipelines.l_pipe.pipeline import run_lpipe
from helios.schemas.telemetry import EvaluationPhase
from helios.schemas.ueg_c import UEGCSnapshot
from helios.schemas.verdict import VERDICT_SCHEMA_VERSION, PipelineVerdict
from helios.store.result_store import ResultStore
from helios.telemetry.reader import CaptureReader
from helios.vcl.decorators import GatedComponentInactiveError, set_current_manifest
from helios.vcl.snapshot_registry import DuplicateSnapshotError, SnapshotRegistry

if TYPE_CHECKING:
    from pathlib import Path

    from helios.vcl.config import VCLManifest

__all__ = ["RunOrchestrator"]

HELIOS_ENABLE_ORCHESTRATOR: bool = True

_ANALYTIC_CONSEQUENCE = (
    "C1 gate failure — incident excluded from analysis; "
    "see exclusion_ledger.jsonl for details"
)


class RunOrchestrator:
    """Coordinate a corpus run through the full C1 gating path."""

    def __init__(
        self,
        *,
        manifest: VCLManifest,
        captures_dir: Path,
        db_path: Path,
        registry_path: Path,
        reconciliation_path: Path,
        exclusion_ledger: AppendOnlyLedger,
        hmac_key: bytes,
    ) -> None:
        set_current_manifest(manifest)
        self._manifest = manifest
        self._reader = CaptureReader(captures_dir)
        self._registry = SnapshotRegistry(registry_path)
        self._store = ResultStore(db_path)
        self._reconciliation = ReconciliationLedger(
            key=hmac_key, log_path=reconciliation_path
        )
        self._exclusion_ledger = exclusion_ledger
        self._config_hash = manifest.compute_variant_config_hash()

    def run(self, corpus: Path) -> None:
        """Process every incident in corpus through the full C1 path."""
        for incident_id in CorpusLoader(corpus).incident_ids():
            self._process_incident(incident_id)

    def _process_incident(self, incident_id: str) -> None:
        run_id = str(uuid.uuid4())

        verification = self._reader.read(incident_id)
        if not verification.hash_matches:
            self._reconciliation.record(
                run_id=run_id,
                incident_id=incident_id,
                variant_config_hash=self._config_hash,
                outcome="skipped",
                gate_check="capture_hash_mismatch",
            )
            return

        window = verification.window
        snapshot_hash = window.compute_window_hash()

        if not self._registry.contains(snapshot_hash):
            with contextlib.suppress(DuplicateSnapshotError):
                self._registry.register(snapshot_hash, self._config_hash)

        # Build UEG-C once per incident
        ueg_c = None
        if self._manifest.l2b_graph and window.p2_traces_path is not None:
            ueg_c = build_ueg_c(
                window,
                self._config_hash,
                enable_structural=self._manifest.ueg_c_structural,
            )
            if ueg_c is not None:
                ueg_c, _prune_result = prune_graph(ueg_c)

        d_out = run_dpipe(
            window=window,
            ueg_c=ueg_c,
            incident_id=incident_id,
            snapshot_hash=snapshot_hash,
            variant_config_hash=self._config_hash,
            evaluation_phase=window.evaluation_phase,
            run_id=run_id,
        )
        d_out["schema_version"] = VERDICT_SCHEMA_VERSION
        dpipe_scores: dict[str, float] = d_out.get("ppr_scores", {})
        g_out: dict[str, Any]
        evaluation_phase_str = str(window.evaluation_phase)
        if ueg_c is not None and should_run_gpipe(d_out, self._manifest):
            try:
                g_out = run_gpipe(
                    incident_id=incident_id,
                    snapshot=ueg_c,
                    snapshot_hash=snapshot_hash,
                    dpipe_scores=dpipe_scores,
                    evaluation_phase=evaluation_phase_str,
                    run_id=run_id,
                )
            except GatedComponentInactiveError:
                g_out = {
                    "pipeline": "gpipe",
                    "incident_id": incident_id,
                    "run_id": run_id,
                    "variant_config_hash": self._config_hash,
                    "snapshot_hash": snapshot_hash,
                    "ranked_candidates": [],
                    "ppr_scores": {},
                    "hr_at_3": 0.00,
                    "cpr": 0.00,
                    "latency_ms": 0.00,
                    "token_count": 0,
                    "narrative": "gpipe-gated-or-skipped",
                    "evaluation_phase": evaluation_phase_str,
                    "schema_version": VERDICT_SCHEMA_VERSION,
                }
        else:
            g_out = {
                "pipeline": "gpipe",
                "incident_id": incident_id,
                "run_id": run_id,
                "variant_config_hash": self._config_hash,
                "snapshot_hash": snapshot_hash,
                "ranked_candidates": [],
                "ppr_scores": {},
                "hr_at_3": 0.00,
                "cpr": 0.00,
                "latency_ms": 0.00,
                "token_count": 0,
                "narrative": "gpipe-gated-or-skipped",
                "evaluation_phase": evaluation_phase_str,
                "schema_version": VERDICT_SCHEMA_VERSION,
            }
        lpipe_snapshot = (
            ueg_c
            if ueg_c is not None
            else UEGCSnapshot(
                incident_id=incident_id,
                variant_config_hash=self._config_hash,
                nodes=[],
                edges=[],
                captured_at_iso="",
            )
        )
        try:
            l_out = run_lpipe(
                incident_id=incident_id,
                snapshot=lpipe_snapshot,
                snapshot_hash=snapshot_hash,
                evaluation_phase=evaluation_phase_str,
                run_id=run_id,
            )
        except GatedComponentInactiveError:
            l_out = {
                "pipeline": "lpipe",
                "incident_id": incident_id,
                "run_id": run_id,
                "variant_config_hash": self._config_hash,
                "snapshot_hash": snapshot_hash,
                "ranked_candidates": [],
                "ppr_scores": {},
                "hr_at_3": 0.00,
                "cpr": 0.00,
                "latency_ms": 0.00,
                "token_count": 0,
                "narrative": "lpipe-gated-or-skipped",
                "evaluation_phase": evaluation_phase_str,
                "schema_version": VERDICT_SCHEMA_VERSION,
            }

        verdicts = [
            self._build_verdict(d_out),
            self._build_verdict(g_out),
            self._build_verdict(l_out),
        ]

        gate = MetricIntegrityGate.from_manifest(
            self._manifest,
            ledger=self._exclusion_ledger,
            run_id=run_id,
            analytic_consequence=_ANALYTIC_CONSEQUENCE,
        )
        rows = [v.model_dump() for v in verdicts]
        gate_result = gate.check_consistency(rows, incident_id=incident_id)

        if gate_result.status == "PASS":
            for verdict in verdicts:
                self._store.insert(verdict)
            self._reconciliation.record(
                run_id=run_id,
                incident_id=incident_id,
                variant_config_hash=self._config_hash,
                outcome="passed",
            )
        else:
            self._reconciliation.record(
                run_id=run_id,
                incident_id=incident_id,
                variant_config_hash=self._config_hash,
                outcome="excluded",
                gate_check=gate_result.gate_check or "",
            )

    def _build_verdict(self, stub_out: dict[str, Any]) -> PipelineVerdict:
        return PipelineVerdict(
            run_id=str(stub_out.get("run_id", str(uuid.uuid4()))),
            incident_id=stub_out["incident_id"],
            variant_config_hash=stub_out["variant_config_hash"],
            snapshot_hash=stub_out["snapshot_hash"],
            pipeline=stub_out["pipeline"],
            evaluation_phase=EvaluationPhase(
                stub_out.get("evaluation_phase", "exploratory")
            ),
            ranked_candidates=stub_out.get("ranked_candidates", []),
            hr_at_3=float(stub_out.get("hr_at_3", 0.00)),
            cpr=float(stub_out.get("cpr", 0.00)),
            latency_ms=float(stub_out.get("latency_ms", 0.00)),
            token_count=int(stub_out.get("token_count", 0)),
            narrative=stub_out.get("narrative", "stub"),
            ppr_scores=stub_out.get("ppr_scores", {}),
            prompt_version=stub_out.get("prompt_version"),
            schema_version=str(stub_out.get("schema_version", VERDICT_SCHEMA_VERSION)),
        )
