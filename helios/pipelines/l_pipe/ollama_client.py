"""OllamaClient — Protocol A HTTP wrapper for Ollama /api/generate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from helios.pipelines.l_pipe.lpipe_config import (
    LLAMA_SEED,
    PROTOCOL_A_TEMPERATURE,
    PROTOCOL_A_TOP_K,
    PROTOCOL_A_TOP_P,
)
from helios.vcl import VCLFlag  # noqa: F401 — satisfies flag-guard

HELIOS_ENABLE_OLLAMA_CLIENT: bool = True


class OllamaTimeoutError(Exception):
    pass


class OllamaConnectionError(Exception):
    pass


class OllamaResponseError(Exception):
    pass


@dataclass(frozen=True)
class OllamaGenerateResult:
    text: str
    prompt_tokens: int
    completion_tokens: int


class OllamaClient:
    def __init__(self, base_url: str, model_name: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name

    def generate(self, prompt: str, timeout_s: float) -> OllamaGenerateResult:
        payload: dict[str, Any] = {
            "model": self._model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": PROTOCOL_A_TEMPERATURE,
                "top_p": PROTOCOL_A_TOP_P,
                "top_k": PROTOCOL_A_TOP_K,
                "seed": LLAMA_SEED,
            },
        }
        try:
            response = requests.post(
                f"{self._base_url}/api/generate",
                json=payload,
                timeout=timeout_s,
            )
        except requests.exceptions.Timeout as exc:
            raise OllamaTimeoutError(str(exc)) from exc
        except requests.exceptions.ConnectionError as exc:
            raise OllamaConnectionError(str(exc)) from exc
        if response.status_code >= 300:
            raise OllamaResponseError(f"Ollama returned HTTP {response.status_code}")
        body = response.json()
        return OllamaGenerateResult(
            text=body["response"],
            prompt_tokens=body.get("prompt_eval_count", 0),
            completion_tokens=body.get("eval_count", 0),
        )
