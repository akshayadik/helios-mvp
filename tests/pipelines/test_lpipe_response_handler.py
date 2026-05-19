"""ResponseHandler unit tests — JSON validation, retry, fallback."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from helios.pipelines.l_pipe.ollama_client import (
    OllamaGenerateResult,
    OllamaTimeoutError,
)
from helios.pipelines.l_pipe.response_handler import LPipeResponse, ResponseHandler
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def _make_result(text: str) -> OllamaGenerateResult:
    return OllamaGenerateResult(text=text, prompt_tokens=25, completion_tokens=75)


def _valid_json() -> str:
    return (
        '{"ranked_candidates": ["svcA", "svcB"], '
        '"narrative": "svcA caused the issue via latency cascade", '
        '"confidence": 0.75}'
    )


def test_valid_response_parsed_correctly() -> None:
    client = MagicMock()
    client.generate.return_value = _make_result(_valid_json())
    handler = ResponseHandler(client, max_retries=1)
    response, ollama_result = handler.handle("test prompt", timeout_s=30.00)
    assert isinstance(response, LPipeResponse)
    assert response.ranked_candidates == ["svcA", "svcB"]
    assert ollama_result is not None
    assert ollama_result.completion_tokens == 75


def test_malformed_json_triggers_retry() -> None:
    client = MagicMock()
    client.generate.side_effect = [
        _make_result("not valid json at all"),
        _make_result(_valid_json()),
    ]
    handler = ResponseHandler(client, max_retries=1)
    response, _ = handler.handle("prompt", timeout_s=30.00)
    assert response.ranked_candidates == ["svcA", "svcB"]
    assert client.generate.call_count == 2


def test_missing_field_triggers_retry() -> None:
    missing_narrative = '{"ranked_candidates": ["svcA"], "confidence": 0.75}'
    client = MagicMock()
    client.generate.side_effect = [
        _make_result(missing_narrative),
        _make_result(missing_narrative),
    ]
    handler = ResponseHandler(client, max_retries=1)
    response, ollama_result = handler.handle("prompt", timeout_s=30.00)
    assert response.ranked_candidates == ["l-pipe-fallback"]
    assert ollama_result is None


def test_retry_exhaustion_returns_fallback() -> None:
    client = MagicMock()
    client.generate.return_value = _make_result("bad json")
    handler = ResponseHandler(client, max_retries=1)
    response, ollama_result = handler.handle("prompt", timeout_s=30.00)
    assert response.ranked_candidates == ["l-pipe-fallback"]
    assert response.narrative == "l-pipe-fallback-schema-error"
    assert ollama_result is None


def test_timeout_is_reraised() -> None:
    client = MagicMock()
    client.generate.side_effect = OllamaTimeoutError("timed out")
    handler = ResponseHandler(client, max_retries=1)
    with pytest.raises(OllamaTimeoutError):
        handler.handle("prompt", timeout_s=30.00)


def test_extra_field_rejected() -> None:
    extra_field = (
        '{"ranked_candidates": ["svcA"], '
        '"narrative": "ok", '
        '"confidence": 0.75, '
        '"extra_unknown_field": "value"}'
    )
    client = MagicMock()
    client.generate.side_effect = [
        _make_result(extra_field),
        _make_result(_valid_json()),
    ]
    handler = ResponseHandler(client, max_retries=1)
    response, _ = handler.handle("prompt", timeout_s=30.00)
    assert response.ranked_candidates == ["svcA", "svcB"]
    assert client.generate.call_count == 2


def test_markdown_wrapped_json_sanitized() -> None:
    wrapped = "```json\n" + _valid_json() + "\n```"
    client = MagicMock()
    client.generate.return_value = _make_result(wrapped)
    handler = ResponseHandler(client, max_retries=1)
    response, _ = handler.handle("prompt", timeout_s=30.00)
    assert response.ranked_candidates == ["svcA", "svcB"]
