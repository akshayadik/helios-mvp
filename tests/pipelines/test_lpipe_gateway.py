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
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

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
    """Every call of the episode is metered, schema retries included (S1.10)."""
    from tests.pipelines.l_pipe.test_pipeline import OTEL, FakeClient, _run, _window

    class RetryOnce(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.seen: set[str] = set()

        def generate(self, prompt: str, timeout_s: float) -> OllamaGenerateResult:
            if prompt not in self.seen:
                self.seen.add(prompt)
                self.calls += 1
                return _result("{}", 90, 20, 300)
            return super().generate(prompt, timeout_s)

    client = RetryOnce()
    out = _run(_window(OTEL), client)
    assert out["status"] == "ranked"
    assert (out["llm_calls"], out["llm_failed_calls"]) == (6, 0)
    assert out["prompt_tokens"] == 3 * (90 + 50)
    assert out["gpu_ms"] == pytest.approx(3 * (300 + 90))
