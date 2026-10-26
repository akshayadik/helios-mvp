"""RunOrchestrator — wires full C1 pipeline dispatch for a corpus run (§3.6.8, §5.1).

For each incident: CaptureReader verifies hash → SnapshotRegistry registers snapshot
→ three pipelines dispatch, each giving a PipelineVerdict (S1.8) → MetricIntegrityGate checks consistency
→ ResultStore inserts passing verdicts → ReconciliationLedger records outcome.
"""

from __future__ import annotations

import contextlib
import time
import uuid
from typing import TYPE_CHECKING, Any

from helios.graph.khop_pruner import khop_prune
from helios.graph.structural_bundle import apply_structural_bundle
from helios.graph.ueg_c_builder import build_ueg_c
from helios.integrity_gate import AppendOnlyLedger, MetricIntegrityGate
from helios.orchestrator.corpus import CorpusLoader
from helios.orchestrator.ledger import ReconciliationLedger
from helios.pipelines.d_pipe.pipeline import run_dpipe
from helios.pipelines.g_pipe.pipeline import run_gpipe, should_run_gpipe
from helios.pipelines.l_pipe.pipeline import run_lpipe
from helios.schemas.ueg_c import UEGCSnapshot
from helios.schemas.verdict import (
    PipelineName,
    PipelineVerdict,
    VerdictStatus,
)
from helios.store.result_store import ResultStore
from helios.telemetry.reader import CaptureReader
from helios.vcl.decorators import GatedComponentInactiveError, set_current_manifest
from helios.vcl.snapshot_registry import DuplicateSnapshotError, SnapshotRegistry

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from helios.vcl.config import VCLManifest

__all__ = ["RunOrchestrator"]

HELIOS_ENABLE_ORCHESTRATOR: bool = True

_MS_PER_S = 1_000

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
        self._reader = CaptureReader(captures_dir, seal_key=hmac_key)
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
        # Parquet bytes are outside window_hash; the content seal covers them.
        if not verification.content_intact:
            self._reconciliation.record(
                run_id=run_id,
                incident_id=incident_id,
                variant_config_hash=self._config_hash,
                outcome="skipped",
                gate_check="capture_seal_invalid",
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
            ueg_c = build_ueg_c(window, self._config_hash)
            if ueg_c is not None:
                # ueg_structural ON keeps the typed graph; OFF flattens it to one
                # untyped edge kind (HELIOS-noStructural, S1.6).
                ueg_c = apply_structural_bundle(ueg_c).snapshot
                # Incident-local subgraph, Algorithm 5 (S1.7).
                ueg_c, _prune_result = khop_prune(ueg_c)

        base: dict[str, Any] = {
            "run_id": run_id,
            "incident_id": incident_id,
            "variant_config_hash": self._config_hash,
            "snapshot_hash": snapshot_hash,
            "evaluation_phase": window.evaluation_phase,
        }
        evaluation_phase_str = str(window.evaluation_phase)
        d_verdict, d_out = self._dispatch(
            PipelineName.DPIPE,
            base,
            lambda: run_dpipe(
                window=window,
                ueg_c=ueg_c,
                incident_id=incident_id,
                snapshot_hash=snapshot_hash,
                variant_config_hash=self._config_hash,
                evaluation_phase=window.evaluation_phase,
                run_id=run_id,
            ),
        )
        dpipe_scores: dict[str, float] = d_out.get("candidate_scores", {})
        graph = ueg_c
        if graph is not None and should_run_gpipe(d_out, self._manifest):
            g_verdict, _ = self._dispatch(
                PipelineName.GPIPE,
                base,
                lambda: run_gpipe(
                    incident_id=incident_id,
                    snapshot=graph,
                    snapshot_hash=snapshot_hash,
                    dpipe_scores=dpipe_scores,
                    evaluation_phase=evaluation_phase_str,
                    run_id=run_id,
                ),
            )
        else:
            g_verdict = self._skipped(PipelineName.GPIPE, base)
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
        l_verdict, _ = self._dispatch(
            PipelineName.LPIPE,
            base,
            lambda: run_lpipe(
                incident_id=incident_id,
                snapshot=lpipe_snapshot,
                snapshot_hash=snapshot_hash,
                evaluation_phase=evaluation_phase_str,
                run_id=run_id,
            ),
        )
        verdicts = [d_verdict, g_verdict, l_verdict]

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

    def _dispatch(
        self,
        pipeline: PipelineName,
        base: dict[str, Any],
        call: Callable[[], dict[str, Any]],
    ) -> tuple[PipelineVerdict, dict[str, Any]]:
        """Run one pipeline; latency and CPU time are measured here, the same way
        for every pipeline. A pipeline gated off by its flag gives a SKIPPED
        verdict."""
        wall, cpu = time.perf_counter(), time.process_time()
        try:
            out = call()
        except GatedComponentInactiveError:
            return self._skipped(pipeline, base), {}
        latency_ms = (time.perf_counter() - wall) * _MS_PER_S
        cpu_ms = (time.process_time() - cpu) * _MS_PER_S
        return self._build_verdict(pipeline, base, out, latency_ms, cpu_ms), out

    @staticmethod
    def _skipped(pipeline: PipelineName, base: dict[str, Any]) -> PipelineVerdict:
        return PipelineVerdict(
            **base,
            pipeline=pipeline,
            status=VerdictStatus.SKIPPED,
            latency_ms=0,
            narrative=f"{pipeline.value}-gated-or-skipped",
        )

    @staticmethod
    def _build_verdict(
        pipeline: PipelineName,
        base: dict[str, Any],
        out: dict[str, Any],
        latency_ms: float,
        cpu_ms: float,
    ) -> PipelineVerdict:
        if out.get("pipeline") != pipeline.value:
            raise ValueError(
                f"{pipeline.value} returned a verdict for {out.get('pipeline')!r}"
            )
        # Identity fields come from the pipeline when it reports them, so the
        # integrity gate can catch a pipeline that ran on another snapshot.
        return PipelineVerdict.from_output(
            {**base, **out, "evaluation_phase": base["evaluation_phase"]},
            latency_ms=latency_ms,
            cpu_ms=cpu_ms,
        )
