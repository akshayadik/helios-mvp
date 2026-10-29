"""RunOrchestrator — wires full C1 pipeline dispatch for a corpus run (§3.6.8, §5.1).

For each incident: CaptureReader verifies hash → SnapshotRegistry registers snapshot
→ the shared detection trigger is computed and stored (S2.1) → the UEG-C is built and
pruned around the trigger's suspects → three pipelines dispatch, each giving a
PipelineVerdict (S1.8) → MetricIntegrityGate checks consistency → ResultStore inserts
passing verdicts → ReconciliationLedger records outcome.

Out-of-scope services (helios.telemetry.scope, D-f) are dropped from every
pipeline's ranking here, the same way for every pipeline.
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
from helios.pipelines.d_pipe.params import DPipeParams, load_dpipe_params
from helios.pipelines.d_pipe.pipeline import run_dpipe
from helios.pipelines.g_pipe.pipeline import run_gpipe, should_run_gpipe
from helios.pipelines.l_pipe.pipeline import run_lpipe
from helios.schemas.telemetry import EvaluationPhase
from helios.schemas.ueg_c import UEGCSnapshot
from helios.schemas.verdict import (
    PipelineName,
    PipelineVerdict,
    VerdictStatus,
    top1_share,
)
from helios.store.result_store import ResultStore
from helios.telemetry.reader import CaptureReader
from helios.telemetry.scope import OUT_OF_SCOPE_SERVICES, filter_in_scope, in_scope
from helios.telemetry.trigger import (
    DetectorParams,
    ExternalTriggerRefusedError,
    ProvisionalParametersError,
    TriggerRecord,
    detect,
    load_detector_params,
    load_external_triggers,
)
from helios.vcl.decorators import GatedComponentInactiveError, set_current_manifest
from helios.vcl.snapshot_registry import DuplicateSnapshotError, SnapshotRegistry

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from helios.schemas.telemetry import TelemetryWindow
    from helios.vcl.config import VCLManifest

__all__ = ["RunOrchestrator", "incident_graph"]

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
        detector_params: DetectorParams | None = None,
        external_triggers: Path | None = None,
        dpipe_params: DPipeParams | None = None,
    ) -> None:
        """``detector_params`` and ``dpipe_params`` default to the frozen files;
        ``external_triggers`` (exploratory only) replaces the detector with
        supplied records."""
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
        self._detector = (
            detector_params if detector_params is not None else load_detector_params()
        )
        self._dpipe = dpipe_params if dpipe_params is not None else load_dpipe_params()
        self._external = (
            load_external_triggers(external_triggers)
            if external_triggers is not None
            else None
        )

    def _trigger_for(self, window: TelemetryWindow) -> TriggerRecord:
        """The shared trigger of a window; refusals come before anything runs."""
        if window.evaluation_phase == EvaluationPhase.CONFIRMATORY:
            if self._external is not None:
                raise ExternalTriggerRefusedError(
                    "externally supplied triggers are refused in confirmatory runs"
                )
            if self._detector.provisional or self._dpipe.provisional:
                raise ProvisionalParametersError(
                    "detector or D-pipe parameters are provisional; freeze them first"
                )
        if self._external is not None:
            if window.incident_id not in self._external:
                raise ValueError("no supplied trigger for this incident")
            return self._external[window.incident_id]
        return detect(window, self._detector)

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
        trigger = self._trigger_for(window)
        # TTCD/TTT start here (deviation entry 46): graph build and pruning use
        # the trigger, so they are measured analysis, not start-up.
        handover_unix = time.time()

        if not self._registry.contains(snapshot_hash):
            with contextlib.suppress(DuplicateSnapshotError):
                self._registry.register(snapshot_hash, self._config_hash)

        # Build UEG-C once per incident
        ueg_c, seeds = incident_graph(
            window, self._manifest, self._config_hash, trigger
        )
        self._store.insert_trigger(
            trigger,
            run_id=run_id,
            variant_config_hash=self._config_hash,
            seeds_from_trigger=bool(seeds),
            handover_unix=handover_unix,
        )

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
                trigger=trigger,
                evidence_ref=self._detector.threshold,
                w_error=self._dpipe.w_error,
                w_resource=self._dpipe.w_resource,
                rho_threshold=self._dpipe.rho_threshold,
                topology_boost_factor=self._dpipe.topology_boost_factor,
            ),
        )
        # Routing sees what the stored D-pipe verdict shows: in-scope only (D-f).
        d_routed = _in_scope_output(d_out) if d_out else d_out
        dpipe_scores: dict[str, float] = d_routed.get("candidate_scores", {})
        graph = ueg_c
        if graph is not None and should_run_gpipe(d_routed, self._manifest):
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
        started = time.time()
        wall, cpu = time.perf_counter(), time.process_time()
        try:
            out = call()
        except GatedComponentInactiveError:
            return self._skipped(pipeline, base), {}
        latency_ms = (time.perf_counter() - wall) * _MS_PER_S
        cpu_ms = (time.process_time() - cpu) * _MS_PER_S
        verdict = self._build_verdict(pipeline, base, out, latency_ms, cpu_ms)
        self._store.insert_timing(base["run_id"], pipeline, started, time.time())
        return verdict, out

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
        out = _in_scope_output(out)
        # Identity fields come from the pipeline when it reports them, so the
        # integrity gate can catch a pipeline that ran on another snapshot.
        return PipelineVerdict.from_output(
            {**base, **out, "evaluation_phase": base["evaluation_phase"]},
            latency_ms=latency_ms,
            cpu_ms=cpu_ms,
        )


def incident_graph(
    window: TelemetryWindow,
    manifest: VCLManifest,
    config_hash: str,
    trigger: TriggerRecord,
) -> tuple[UEGCSnapshot | None, list[str]]:
    """The incident's UEG-C and the trigger suspects that seeded its pruning.

    ``(None, [])`` without traces or with the graph flag off. D-pipe
    calibration calls this too, so it ranks on the graph the runner uses.
    """
    if not manifest.l2b_graph or window.p2_traces_path is None:
        return None, []
    ueg_c = build_ueg_c(window, config_hash)
    if ueg_c is None:
        return None, []
    # ueg_structural ON keeps the typed graph; OFF flattens it to one
    # untyped edge kind (HELIOS-noStructural, S1.6).
    ueg_c = apply_structural_bundle(ueg_c).snapshot
    # Incident-local subgraph, Algorithm 5 (S1.7), seeded by the
    # trigger's suspects that are services of the graph.
    candidates = set(ueg_c.candidate_ids())
    seeds = [s for s in trigger.suspects if s in candidates]
    ueg_c, _prune_result = khop_prune(
        ueg_c, seeds=seeds or None, exclude=OUT_OF_SCOPE_SERVICES
    )
    return ueg_c, seeds


def _in_scope_output(out: dict[str, Any]) -> dict[str, Any]:
    """A pipeline output without out-of-scope services (D-f).

    mu becomes the top-1 share of the remaining scores; a ranked output left
    with no candidate becomes ABSTAINED (it named only out-of-scope services).
    """
    out = dict(out)
    scores = dict(out.get("candidate_scores", {}))
    kept = {k: v for k, v in scores.items() if in_scope(k)}
    if len(kept) != len(scores):
        out["candidate_scores"] = kept
        if out.get("mu") is not None:
            out["mu"] = top1_share(kept)
    out["ranked_candidates"] = filter_in_scope(out.get("ranked_candidates", []))
    if out.get("status") == VerdictStatus.RANKED.value and not out["ranked_candidates"]:
        out.update(status=VerdictStatus.ABSTAINED.value, mu=None, sigma=None)
    return out
