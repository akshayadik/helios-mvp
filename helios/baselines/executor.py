"""A baseline as an S4.10 ``Executor`` (S4.8 design B-a to B-i).

One ``BaselineExecutor`` per (baseline, anomaly-time source). For each
incident it checks the capture (hash and content seal, the same exclusions as
HELIOS), takes the anomaly time (B-b), exports the window (B-a), runs the
method offline in its pinned image (B-e), maps the ranking to services (B-c)
and stores one ``baseline_row`` in one transaction.

Anomaly time (B-b, recommended (c)):
- ``inject``: the injection time from the signed ground truth, read by the
  harness through ``load_inject_times`` (pool refused before build-freeze);
  binding, as in RCAEval's protocol;
- ``trigger``: HELIOS's own detection trigger for the window (label-free; the
  one time anchor every system receives); the sensitivity row. Its source name
  carries ``TRIGGER_SUFFIX`` so it never enters a binding test.

Failures (B-f): a method error or a run past the time limit is an exclusion
(``baseline_error`` / ``baseline_timeout``) written to the exclusion ledger
and the reconciliation ledger; Docker failures propagate to the campaign as
infrastructure errors; a wrong image stops the campaign.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from helios.baselines.container import (
    BaselineConfigError,
    BaselineTimeoutError,
    ContainerRunner,
    Limits,
    adapter_digest,
)
from helios.baselines.export import EXPORT_VERSION, export_window
from helios.orchestrator.ledger import ReconciliationLedger
from helios.orchestrator.runner import RunOutcome
from helios.orchestrator.schedule import TRIGGER_SUFFIX
from helios.research.analysis_plan import BASELINE_ALTERNATES, BASELINES
from helios.schemas.telemetry import EvaluationPhase
from helios.store.result_store import ResultStore
from helios.telemetry.reader import CaptureReader
from helios.telemetry.trigger import (
    ProvisionalParametersError,
    detect,
    load_detector_params,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.utils import canonical_json

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from helios.integrity_gate import AppendOnlyLedger
    from helios.telemetry.trigger import DetectorParams

__all__ = [
    "ANOMALY_SOURCES",
    "DATASET_ARG",
    "METHODS",
    "TRIGGER_SUFFIX",
    "BaselineExecutor",
    "BaselineMethod",
    "services_from_ranks",
    "source_name",
]

ANOMALY_SOURCES = ("inject", "trigger")
METRIC_LENGTH_MIN = 20  # RCAEval main.py --length default


@dataclass(frozen=True)
class BaselineMethod:
    function: str  # RCAEval function (or the PDiagnose adapter)
    env: str  # image key in container.IMAGES


METHODS: dict[str, BaselineMethod] = {
    BASELINES[0]: BaselineMethod("mmbaro", "default"),
    BASELINES[1]: BaselineMethod("tracerca", "default"),
    BASELINES[2]: BaselineMethod("baro", "default"),
    BASELINES[3]: BaselineMethod("pdiagnose", "default"),
    BASELINES[4]: BaselineMethod("mmrcd", "rcd"),
    BASELINE_ALTERNATES[0]: BaselineMethod("circa", "default"),
    BASELINE_ALTERNATES[1]: BaselineMethod("causalrca", "default"),
}
# RCAEval's dataset argument per benchmark system. Only two things read it:
# whether mmbaro uses traces (any RE2/RE3 OB or TT name) and preprocess (any
# name but causalrca-sock-shop). "re2-" for every case never tells a method
# whether a case is RE2 or RE3. OTel Demo descends from Online Boutique.
DATASET_ARG: dict[str, str] = {"ob": "re2-ob", "tt": "re2-tt", "ss": "re2-ss"}
_DEFAULT_DATASET = "re2-ob"

_ANALYTIC_CONSEQUENCE = (
    "baseline run excluded from analysis (S4.8 B-f); "
    "see exclusion_ledger.jsonl for details"
)


def source_name(baseline: str, anomaly: str) -> str:
    """The eval_score ``source`` of a baseline run."""
    return baseline if anomaly == "inject" else baseline + TRIGGER_SUFFIX


def services_from_ranks(ranks: list[str]) -> list[str]:
    """Metric-level ranks to services, first occurrence (B-c, RCAEval's rule:
    the service is the name before the first "_")."""
    out: list[str] = []
    seen: set[str] = set()
    for r in ranks:
        service = str(r).split("_", 1)[0]
        if service and service not in seen:
            seen.add(service)
            out.append(service)
    return out


class BaselineExecutor:
    """One baseline method behind the campaign's ``Executor`` protocol."""

    def __init__(
        self,
        baseline: str,
        *,
        anomaly: str,
        captures_dir: Path,
        repo_root: Path,
        db_path: Path,
        reconciliation_path: Path,
        exclusion_ledger: AppendOnlyLedger,
        hmac_key: bytes,
        runner: ContainerRunner,
        inject_times: Callable[[], Mapping[str, float]],
        dataset_for: Mapping[str, str],
        limits: Limits | None = None,
        detector_params: DetectorParams | None = None,
        work_dir: Path | None = None,
    ) -> None:
        if baseline not in METHODS:
            raise ValueError(f"unknown baseline {baseline!r}")
        if anomaly not in ANOMALY_SOURCES:
            raise ValueError(f"anomaly source must be one of {ANOMALY_SOURCES}")
        self.baseline = baseline
        self.anomaly = anomaly
        self.method = METHODS[baseline]
        self.source = source_name(baseline, anomaly)
        self._captures = captures_dir
        self._root = repo_root
        self._store = ResultStore(db_path)
        self._reader = CaptureReader(captures_dir, seal_key=hmac_key)
        reconciliation_path.parent.mkdir(parents=True, exist_ok=True)
        self._reconciliation = ReconciliationLedger(
            key=hmac_key, log_path=reconciliation_path
        )
        self._exclusions = exclusion_ledger
        self._runner = runner
        self._inject_times = inject_times
        self._inject_cache: Mapping[str, float] | None = None
        self._dataset_for = dataset_for
        self._limits = limits or Limits()
        self._detector = detector_params
        self._work = work_dir
        self._image = ""
        self._config_hash = self._hash()

    def _hash(self) -> str:
        body = {
            "baseline": self.baseline,
            "function": self.method.function,
            "env": self.method.env,
            "anomaly": self.anomaly,
            "adapters": adapter_digest(),
            "export": EXPORT_VERSION,
            "length_min": METRIC_LENGTH_MIN,
            "cpus": self._limits.cpus,
            "memory": self._limits.memory,
            "timeout_s": self._limits.timeout_s,
        }
        return hashlib.sha256(canonical_json(body).encode()).hexdigest()

    @property
    def config_hash(self) -> str:
        return self._config_hash

    def prepare(self) -> None:
        """The pinned image must be present (else the campaign stops)."""
        self._image = self._runner.check_image(self.method.env)

    def discard_run(self, run_id: str) -> int:
        return self._store.delete_run(run_id)

    # ── one incident ────────────────────────────────────────────────────

    def _anomaly_time(self, incident_id: str, window: Any) -> int:
        if self.anomaly == "inject":
            if self._inject_cache is None:
                self._inject_cache = self._inject_times()
            if incident_id not in self._inject_cache:
                raise BaselineConfigError("no injection time for this incident")
            return int(self._inject_cache[incident_id])
        params = self._detector or load_detector_params()
        if (
            window.evaluation_phase == EvaluationPhase.CONFIRMATORY
            and params.provisional
        ):
            raise ProvisionalParametersError(
                "detector parameters are provisional; freeze them first"
            )
        return int(detect(window, params).trigger_time_s)

    def _exclude(
        self,
        run_id: str,
        incident_id: str,
        context: Mapping[str, str],
        *,
        gate_check: str,
        reason: str,
        snapshot_hash: str = "UNKNOWN",
    ) -> RunOutcome:
        self._exclusions.append(
            {
                **context,
                "variant_config_hash": self._config_hash,
                "snapshot_hash": snapshot_hash,
                "run_id": run_id,
                "incident_id": incident_id,
                "gate_check": gate_check,
                "reason": reason,
                "analytic_consequence": _ANALYTIC_CONSEQUENCE,
                "covariates": "{}",
                "baseline": self.source,
            }
        )
        self._reconciliation.record(
            run_id=run_id,
            incident_id=incident_id,
            variant_config_hash=self._config_hash,
            outcome="excluded",
            gate_check=gate_check,
        )
        return RunOutcome("excluded", gate_check, {})

    def run_incident(
        self, incident_id: str, run_id: str, context: Mapping[str, str] | None = None
    ) -> RunOutcome:
        context = dict(context or {})
        verification = self._reader.read(incident_id)
        if not verification.hash_matches:
            return self._exclude(
                run_id,
                incident_id,
                context,
                gate_check="capture_hash_mismatch",
                reason="capture window_hash does not match its manifest",
            )
        if not verification.content_intact:
            return self._exclude(
                run_id,
                incident_id,
                context,
                gate_check="capture_seal_invalid",
                reason="capture content seal missing or not matching",
            )
        window = verification.window
        snapshot = window.compute_window_hash()
        t = self._anomaly_time(incident_id, window)
        seed = int(context.get("seed", "0"))
        tmp = Path(tempfile.mkdtemp(prefix="baseline-", dir=self._work))
        try:
            in_dir, out_dir = tmp / "in", tmp / "out"
            export_window(window, self._root, in_dir)
            out_dir.mkdir()
            job = {
                "method": self.method.function,
                "seed": seed,
                "anomaly_time": t,
                "dataset": self._dataset_for.get(incident_id, _DEFAULT_DATASET),
                "length": METRIC_LENGTH_MIN,
            }
            (in_dir / "job.json").write_text(json.dumps(job))
            try:
                result = self._runner.run(
                    self.method.env, in_dir, out_dir, f"helios-{run_id}", self._limits
                )
            except BaselineTimeoutError as exc:
                return self._exclude(
                    run_id,
                    incident_id,
                    context,
                    gate_check="baseline_timeout",
                    reason=str(exc),
                    snapshot_hash=snapshot,
                )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if "error" in result:
            return self._exclude(
                run_id,
                incident_id,
                context,
                gate_check="baseline_error",
                reason=str(result["error"]),
                snapshot_hash=snapshot,
            )
        raw = [str(r) for r in result.get("ranks", [])]
        ranked = services_from_ranks(raw)
        with self._store.transaction():
            self._store.insert_baseline(
                {
                    "run_id": run_id,
                    "incident_id": incident_id,
                    "baseline": self.baseline,
                    "source": self.source,
                    "method": self.method.function,
                    "config_hash": self._config_hash,
                    "anomaly_source": self.anomaly,
                    "anomaly_time_s": float(t),
                    "ranked": ranked,
                    "raw_ranks": raw,
                    "wall_ms": float(result["wall_ms"]),
                    "cpu_ms": float(result["cpu_ms"]),
                    "cpus": self._limits.cpus,
                    "run_seed": seed,
                    "image_digest": self._image,
                    "evaluation_phase": window.evaluation_phase.value,
                    "snapshot_hash": snapshot,
                }
            )
        self._reconciliation.record(
            run_id=run_id,
            incident_id=incident_id,
            variant_config_hash=self._config_hash,
            outcome="passed",
        )
        return RunOutcome("passed", None, {"ranked": str(len(ranked))})
