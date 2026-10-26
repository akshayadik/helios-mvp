"""L-pipe pipeline entry-point — Ollama Protocol A + prompt governance (§3.6.7)."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

__all__ = ["run_lpipe"]

from helios.pipelines.l_pipe.lpipe_config import (
    EXPECTED_PROMPT_SHA,
    LPIPE_MAX_RETRIES,
    MODEL_NAME,
    OLLAMA_BASE_URL,
    TIMEOUT_S,
)
from helios.pipelines.l_pipe.ollama_client import (
    OllamaClient,
    OllamaConnectionError,
    OllamaResponseError,
    OllamaTimeoutError,
)
from helios.pipelines.l_pipe.prompt_registry import PROMPT_PATH, PromptRegistry
from helios.pipelines.l_pipe.response_handler import ResponseHandler
from helios.schemas.verdict import VERDICT_SCHEMA_VERSION, VerdictStatus
from helios.vcl import VCLFlag, gated_by
from helios.vcl.decorators import get_current_manifest

if TYPE_CHECKING:
    from helios.schemas.ueg_c import UEGCSnapshot

_log = logging.getLogger(__name__)

HELIOS_ENABLE_LPIPE_PIPELINE: bool = True


def _service_list_from_snapshot(snapshot: UEGCSnapshot) -> list[str]:
    return sorted({node.service_name for node in snapshot.nodes})


def _anomaly_summary(snapshot: UEGCSnapshot) -> str:
    services = _service_list_from_snapshot(snapshot)
    return f"Anomalies detected across {len(services)} services: {', '.join(services)}"


@gated_by(VCLFlag.L2C_LLM)
def run_lpipe(
    incident_id: str,
    snapshot: UEGCSnapshot,
    snapshot_hash: str,
    evaluation_phase: str,
    run_id: str,
) -> dict[str, Any]:
    t0 = time.monotonic()
    manifest = get_current_manifest()
    assert manifest is not None
    registry = PromptRegistry(PROMPT_PATH)
    if EXPECTED_PROMPT_SHA is not None:
        registry.verify_sha_or_raise(EXPECTED_PROMPT_SHA)
    else:
        _log.warning(
            "lpipe: EXPECTED_PROMPT_SHA not frozen — prompt tamper-guard disabled. "
            "Freeze after committing rca_v1.txt (see lpipe_config.py)."
        )
    client = OllamaClient(OLLAMA_BASE_URL, MODEL_NAME)
    handler = ResponseHandler(client, max_retries=LPIPE_MAX_RETRIES)
    prompt = registry.render(
        incident_id=incident_id,
        service_list=_service_list_from_snapshot(snapshot),
        anomaly_summary=_anomaly_summary(snapshot),
    )
    try:
        response, ollama_result = handler.handle(prompt, timeout_s=TIMEOUT_S)
    except (OllamaTimeoutError, OllamaConnectionError, OllamaResponseError) as exc:
        latency_ms = (time.monotonic() - t0) * 1_000.00
        _log.error("lpipe transient error for %s: %s", incident_id, exc)
        return {
            "pipeline": "lpipe",
            "incident_id": incident_id,
            "run_id": run_id,
            "variant_config_hash": manifest.compute_variant_config_hash(),
            "snapshot_hash": snapshot_hash,
            "status": VerdictStatus.FAILED,
            "ranked_candidates": [],
            "candidate_scores": {},
            "mu": None,
            "sigma": None,
            "prompt_version": registry.prompt_version,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "narrative": f"l-pipe-connectivity-error: {type(exc).__name__}",
            "latency_ms": latency_ms,
            "evaluation_phase": evaluation_phase,
            "schema_version": VERDICT_SCHEMA_VERSION,
        }
    latency_ms = (time.monotonic() - t0) * 1_000.00
    # A model can name a service twice; the verdict keeps its first position.
    # No result means every retry failed schema validation: the handler's
    # fallback placeholder is not a candidate, so the verdict is FAILED.
    ranked = (
        list(dict.fromkeys(response.ranked_candidates))
        if ollama_result is not None
        else []
    )
    if ollama_result is None:
        status = VerdictStatus.FAILED
    else:
        status = VerdictStatus.RANKED if ranked else VerdictStatus.ABSTAINED
    return {
        "pipeline": "lpipe",
        "incident_id": incident_id,
        "run_id": run_id,
        "variant_config_hash": manifest.compute_variant_config_hash(),
        "snapshot_hash": snapshot_hash,
        "status": status,
        "ranked_candidates": ranked,
        "candidate_scores": {},
        # mu and sigma come from the S2.3 workers; a single prompt has neither.
        "mu": None,
        "sigma": None,
        "prompt_version": registry.prompt_version,
        "prompt_tokens": ollama_result.prompt_tokens if ollama_result else 0,
        "completion_tokens": ollama_result.completion_tokens if ollama_result else 0,
        "narrative": response.narrative,
        "latency_ms": latency_ms,
        "evaluation_phase": evaluation_phase,
        "schema_version": VERDICT_SCHEMA_VERSION,
    }
