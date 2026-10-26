"""LLM gateway (S1.10): every model call of an episode is metered, retries included."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from helios.pipelines.l_pipe.gateway import LLMGateway, LLMUsage
from helios.pipelines.l_pipe.ollama_client import (
    OllamaClient,
    OllamaConnectionError,
    OllamaGenerateResult,
)
from helios.pipelines.l_pipe.response_handler import ResponseHandler
from helios.schemas.ueg_c import NodeType, UEGCNode, UEGCSnapshot
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.decorators import set_current_manifest
from helios.vcl.variants import get_variant

_VALID = json.dumps(
    {"ranked_candidates": ["svcA"], "narrative": "svcA failed", "confidence": 0.9}
)


def _result(text: str, p: int, c: int, ms: float) -> OllamaGenerateResult:
    return OllamaGenerateResult(
        text=text, prompt_tokens=p, completion_tokens=c, compute_ms=ms
    )


def test_client_reports_model_compute_time() -> None:
    body = {
        "response": _VALID,
        "prompt_eval_count": 120,
        "eval_count": 40,
        "prompt_eval_duration": 250_000_000,  # ns
        "eval_duration": 1_750_000_000,
    }
    with patch("requests.post") as post:
        post.return_value = MagicMock(status_code=200, json=lambda: body)
        result = OllamaClient("http://x", "m").generate("p", timeout_s=1)
    assert (result.prompt_tokens, result.completion_tokens) == (120, 40)
    assert result.compute_ms == pytest.approx(2_000)


def test_retries_are_metered() -> None:
    client = MagicMock()
    client.generate.side_effect = [
        _result("not json", 90, 20, 300),
        _result(_VALID, 110, 30, 450),
    ]
    gateway = LLMGateway(client)
    response, result = ResponseHandler(gateway, max_retries=1).handle("p", 5)
    assert response.ranked_candidates == ["svcA"]
    assert result is not None
    assert gateway.usage == LLMUsage(
        calls=2,
        failed_calls=0,
        prompt_tokens=200,
        completion_tokens=50,
        accelerator_ms=750,
    )
    assert gateway.usage.total_tokens == 250


def test_failed_calls_are_counted_without_tokens() -> None:
    client = MagicMock()
    client.generate.side_effect = [
        _result("x", 10, 2, 5),
        OllamaConnectionError("refused"),
    ]
    gateway = LLMGateway(client)
    gateway.generate("p", 1)
    with pytest.raises(OllamaConnectionError):
        gateway.generate("p", 1)
    assert gateway.usage == LLMUsage(2, 1, 10, 2, 5)


def test_lpipe_episode_reports_all_attempts() -> None:
    from helios.pipelines.l_pipe.pipeline import run_lpipe

    set_current_manifest(get_variant("HELIOS-Full"))
    snapshot = UEGCSnapshot(
        incident_id="inc-001",
        variant_config_hash="a" * 64,
        nodes=[
            UEGCNode(node_id="svcA", node_type=NodeType.SERVICE, service_name="svcA")
        ],
        edges=[],
        captured_at_iso="2026-01-01T00:00:00+00:00",
    )
    with (
        patch("helios.pipelines.l_pipe.pipeline.PromptRegistry") as reg_cls,
        patch("helios.pipelines.l_pipe.pipeline.OllamaClient") as client_cls,
    ):
        reg_cls.return_value.render.return_value = "prompt"
        reg_cls.return_value.prompt_version = "rca_v1"
        client_cls.return_value.generate.side_effect = [
            _result("{}", 90, 20, 300),
            _result(_VALID, 110, 30, 450),
        ]
        out = run_lpipe(
            incident_id="inc-001",
            snapshot=snapshot,
            snapshot_hash="b" * 64,
            evaluation_phase="exploratory",
            run_id="r",
        )
    assert out["status"] == "ranked"
    assert (out["prompt_tokens"], out["completion_tokens"]) == (200, 50)
    assert out["gpu_ms"] == pytest.approx(750)
    assert (out["llm_calls"], out["llm_failed_calls"]) == (2, 0)
