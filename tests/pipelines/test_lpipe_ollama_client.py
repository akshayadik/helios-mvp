"""OllamaClient unit tests — Protocol A enforcement."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from helios.pipelines.l_pipe.lpipe_config import (
    LLAMA_SEED,
    PROTOCOL_A_TEMPERATURE,
    PROTOCOL_A_TOP_K,
    PROTOCOL_A_TOP_P,
)
from helios.pipelines.l_pipe.ollama_client import (
    OllamaClient,
    OllamaConnectionError,
    OllamaGenerateResult,
    OllamaResponseError,
    OllamaTimeoutError,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def _mock_response(text: str, status_code: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = {"response": text, "prompt_eval_count": 25, "eval_count": 75}
    return r


def test_generate_returns_response_on_success() -> None:
    client = OllamaClient("http://localhost:11434", "llama3.1:8b")
    with patch("requests.post") as mock_post:
        mock_post.return_value = _mock_response('{"ranked_candidates": ["svcA"]}')
        result = client.generate("test prompt", timeout_s=30.00)
    assert isinstance(result, OllamaGenerateResult)
    assert "svcA" in result.text
    assert result.prompt_tokens == 25
    assert result.completion_tokens == 75


def test_generate_raises_timeout() -> None:
    import requests

    client = OllamaClient("http://localhost:11434", "llama3.1:8b")
    with (
        patch("requests.post", side_effect=requests.exceptions.Timeout),
        pytest.raises(OllamaTimeoutError),
    ):
        client.generate("prompt", timeout_s=30.00)


def test_generate_raises_connection_error() -> None:
    import requests

    client = OllamaClient("http://localhost:11434", "llama3.1:8b")
    with (
        patch("requests.post", side_effect=requests.exceptions.ConnectionError),
        pytest.raises(OllamaConnectionError),
    ):
        client.generate("prompt", timeout_s=30.00)


def test_generate_raises_on_non_2xx() -> None:
    client = OllamaClient("http://localhost:11434", "llama3.1:8b")
    with patch("requests.post") as mock_post:
        mock_post.return_value = _mock_response("error", status_code=500)
        with pytest.raises(OllamaResponseError):
            client.generate("prompt", timeout_s=30.00)


def test_protocol_a_options_always_sent() -> None:
    client = OllamaClient("http://localhost:11434", "llama3.1:8b")
    with patch("requests.post") as mock_post:
        mock_post.return_value = _mock_response('{"response": "ok"}')
        client.generate("prompt", timeout_s=30.00)
    call_kwargs = mock_post.call_args.kwargs if mock_post.call_args.kwargs else {}
    call_json = call_kwargs.get("json", {})
    opts = call_json.get("options", {})
    assert opts.get("temperature") == PROTOCOL_A_TEMPERATURE
    assert opts.get("top_p") == PROTOCOL_A_TOP_P
    assert opts.get("top_k") == PROTOCOL_A_TOP_K
    assert opts.get("seed") == LLAMA_SEED


def test_protocol_a_options_not_overridable() -> None:
    import inspect

    sig = inspect.signature(OllamaClient.generate)
    params = list(sig.parameters.keys())
    assert "temperature" not in params
    assert "top_p" not in params
    assert "seed" not in params
