"""L-pipe: three single-modality workers and a deterministic merge (S2.3 design §5).

L-pipe reads raw telemetry only — never D-pipe or G-pipe output, the UEG-C,
labels or the injection time (L-a) — so HELIOS-LLM-only measures the LLM
alone. Per incident:

1. candidates = the window's in-scope services (not the graph: ``l2b_graph``
   is OFF in HELIOS-LLM-only); every other service name is a component;
2. one alias map for the incident (L-i);
3. the metric, log and trace workers in that order, strictly one call at a
   time (parallel batching can change outputs); the trace worker has no
   digest on RCAEval-format data (L-f);
4. the deterministic merge gives the ranking, mu and sigma (L-b to L-d).

Status: RANKED; ABSTAINED when no worker is valid (k = 0); FAILED when
something outside the workers breaks (a digest builder, the model endpoint
before any call). A confirmatory run refuses provisional prompts.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from helios.pipelines.l_pipe import lpipe_config, personas
from helios.pipelines.l_pipe.aliases import build_alias_map
from helios.pipelines.l_pipe.gateway import LLMGateway, LLMUsage
from helios.pipelines.l_pipe.lpipe_config import MODEL_NAME, OLLAMA_BASE_URL, TIMEOUT_S
from helios.pipelines.l_pipe.merge import merge
from helios.pipelines.l_pipe.ollama_client import (
    OllamaClient,
    OllamaConnectionError,
    OllamaResponseError,
    OllamaTimeoutError,
)
from helios.pipelines.l_pipe.prompt_registry import PromptTamperError
from helios.pipelines.l_pipe.workers import DropReason, WorkerResult, run_worker
from helios.schemas.telemetry import EvaluationPhase
from helios.schemas.verdict import VERDICT_SCHEMA_VERSION, VerdictStatus
from helios.telemetry.scope import in_scope
from helios.telemetry.trigger import load_detector_params, service_scores
from helios.vcl import VCLFlag, gated_by
from helios.vcl.decorators import get_current_manifest

if TYPE_CHECKING:
    from pathlib import Path

    from helios.pipelines.l_pipe.cache import ResponseCache
    from helios.pipelines.l_pipe.digests import Digest
    from helios.schemas.telemetry import TelemetryWindow
    from helios.telemetry.trigger import TriggerRecord

__all__ = ["ProvisionalPromptError", "run_lpipe"]

_log = logging.getLogger(__name__)

HELIOS_ENABLE_LPIPE_PIPELINE: bool = True


class ProvisionalPromptError(RuntimeError):
    """A confirmatory run met worker prompts that are not frozen."""


def _check_prompts(evaluation_phase: str) -> dict[str, str]:
    shas: dict[str, str] = {p.name: personas.prompt_sha(p) for p in personas.PERSONAS}
    if personas.provisional():
        if evaluation_phase == EvaluationPhase.CONFIRMATORY.value:
            raise ProvisionalPromptError(
                "worker prompts are provisional; a confirmatory run needs frozen SHAs"
            )
        return shas
    for name, sha in shas.items():
        if lpipe_config.WORKER_PROMPT_SHAS.get(name) != sha:
            raise PromptTamperError(
                f"{name} worker prompt differs from its frozen SHA; "
                "a deviation entry is required before it changes"
            )
    return shas


def _usage_fields(usage: LLMUsage) -> dict[str, Any]:
    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "gpu_ms": usage.accelerator_ms,
        "llm_calls": usage.calls,
        "llm_failed_calls": usage.failed_calls,
    }


def _digest_record(digest: Digest | None) -> dict[str, Any] | None:
    if digest is None:
        return None
    return {
        "lines": [[d.line_id, d.service, d.text] for d in digest.lines],
        "cut": digest.cut,
    }


def _worker_record(result: WorkerResult) -> dict[str, Any]:
    return {
        "ranked": list(result.ranked),
        "claims": {
            s: [[c.text, list(c.cites)] for c in claims]
            for s, claims in result.claims.items()
        },
        "dropped": None if result.dropped is None else result.dropped.value,
        "raw": result.raw,
        "cache_hit": result.cache_hit,
        "wall_ms": result.wall_ms,
    }


@gated_by(VCLFlag.L2C_LLM)
def run_lpipe(
    incident_id: str,
    snapshot_hash: str,
    evaluation_phase: str,
    run_id: str,
    *,
    window: TelemetryWindow,
    trigger: TriggerRecord,
    root: Path,
    client: OllamaClient | None = None,
    cache: ResponseCache | None = None,
) -> dict[str, Any]:
    t0 = time.monotonic()
    manifest = get_current_manifest()
    assert manifest is not None
    shas = _check_prompts(evaluation_phase)
    client = client or OllamaClient(OLLAMA_BASE_URL, MODEL_NAME)
    gateway = LLMGateway(client)
    base: dict[str, Any] = {
        "pipeline": "lpipe",
        "incident_id": incident_id,
        "run_id": run_id,
        "variant_config_hash": manifest.compute_variant_config_hash(),
        "snapshot_hash": snapshot_hash,
        "evaluation_phase": evaluation_phase,
        "schema_version": VERDICT_SCHEMA_VERSION,
        "candidate_scores": {},
        "mu": None,
        "sigma": None,
    }
    try:
        model_digest = client.model_digest(timeout_s=TIMEOUT_S)
        bucket_seconds = load_detector_params().bucket_seconds
        services = service_scores(window, bucket_seconds, root=root).services
        candidates = [s for s in services if in_scope(s)]
        components = [s for s in services if not in_scope(s)]
        alias = build_alias_map(window.incident_id, candidates, components)
        digests = {
            p.name: p.build(window, trigger, candidates, root=root)
            for p in personas.PERSONAS
        }
    except (OllamaTimeoutError, OllamaConnectionError, OllamaResponseError) as exc:
        _log.error("lpipe model endpoint error for %s: %s", incident_id, exc)
        return _failed(
            base, gateway, t0, f"l-pipe-connectivity-error: {type(exc).__name__}"
        )
    except Exception as exc:
        _log.error("lpipe digest error for %s: %s", incident_id, exc)
        return _failed(base, gateway, t0, f"l-pipe-digest-error: {type(exc).__name__}")
    results = [
        run_worker(
            p, digests[p.name], alias, gateway, cache=cache, model_digest=model_digest
        )
        for p in personas.PERSONAS
    ]
    merged = merge(results)
    called = [r for r in results if r.dropped != DropReason.NO_DIGEST]
    replayed_ms = sum(r.wall_ms for r in results if r.cache_hit)
    status = VerdictStatus.RANKED if merged.k else VerdictStatus.ABSTAINED
    return {
        **base,
        "status": status,
        "ranked_candidates": list(merged.ranked),
        "candidate_scores": merged.scores,
        "mu": merged.mu,
        "sigma": merged.sigma,
        "prompt_version": "workers_v1 model "
        + model_digest[:12]
        + " "
        + ",".join(f"{n}:{s[:12]}" for n, s in sorted(shas.items())),
        **_usage_fields(gateway.usage),
        "narrative": f"l-pipe k={merged.k}",
        "latency_ms": (time.monotonic() - t0) * 1_000 + replayed_ms,
        "cache_hit": bool(called) and all(r.cache_hit for r in called),
        "replayed_ms": replayed_ms,
        "evidence": {
            "k": merged.k,
            "model_digest": model_digest,
            "prompt_shas": shas,
            "candidates": candidates,
            "scores": merged.scores,
            "digests": {n: _digest_record(d) for n, d in digests.items()},
            "workers": {r.persona: _worker_record(r) for r in results},
        },
    }


def _failed(
    base: dict[str, Any], gateway: LLMGateway, t0: float, narrative: str
) -> dict[str, Any]:
    return {
        **base,
        "status": VerdictStatus.FAILED,
        "ranked_candidates": [],
        "prompt_version": "workers_v1",
        **_usage_fields(gateway.usage),
        "narrative": narrative,
        "latency_ms": (time.monotonic() - t0) * 1_000,
        "cache_hit": False,
        "replayed_ms": 0,
    }
