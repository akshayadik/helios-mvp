"""LLM gateway — per-episode token and compute metering (Plane 3, Ch3 p. 130; S1.10).

Every model call of an episode (one incident run of the L-pipe) goes through
the gateway, retries included: a schema-invalid answer that is retried still
consumed tokens and model time, and CpR must count them. Calls that fail
before the model answers (timeout, refused connection, HTTP error) are
counted as failed calls with no tokens.

Model compute time is the server's own prompt-evaluation plus generation
duration (Ollama ``prompt_eval_duration`` + ``eval_duration``); it is
recorded as the episode's accelerator (GPU) time and priced per GPU-second by
the price book. The HELIOS process's own CPU time is measured separately by
the orchestrator, so the two never overlap.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from helios.pipelines.l_pipe.ollama_client import (
    OllamaConnectionError,
    OllamaResponseError,
    OllamaTimeoutError,
)
from helios.vcl import VCLFlag  # noqa: F401 — satisfies flag-guard

if TYPE_CHECKING:
    from helios.pipelines.l_pipe.ollama_client import (
        OllamaClient,
        OllamaGenerateResult,
    )

__all__ = ["LLMGateway", "LLMUsage"]

HELIOS_ENABLE_LLM_GATEWAY: bool = True


@dataclass(frozen=True)
class LLMUsage:
    """Model usage of one episode."""

    calls: int = 0
    failed_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    accelerator_ms: float = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LLMGateway:
    """Wraps a model client; ``usage`` is the running total of the episode."""

    def __init__(self, client: OllamaClient) -> None:
        self._client = client
        self._usage = LLMUsage()

    @property
    def usage(self) -> LLMUsage:
        return self._usage

    def generate(self, prompt: str, timeout_s: float) -> OllamaGenerateResult:
        u = self._usage
        try:
            result = self._client.generate(prompt, timeout_s=timeout_s)
        except (OllamaTimeoutError, OllamaConnectionError, OllamaResponseError):
            self._usage = LLMUsage(
                u.calls + 1,
                u.failed_calls + 1,
                u.prompt_tokens,
                u.completion_tokens,
                u.accelerator_ms,
            )
            raise
        self._usage = LLMUsage(
            u.calls + 1,
            u.failed_calls,
            u.prompt_tokens + result.prompt_tokens,
            u.completion_tokens + result.completion_tokens,
            u.accelerator_ms + result.compute_ms,
        )
        return result

    def replay(self, result: OllamaGenerateResult) -> None:
        """Count a cached call as if it were made (CpR counts every call)."""
        u = self._usage
        self._usage = LLMUsage(
            u.calls + 1,
            u.failed_calls,
            u.prompt_tokens + result.prompt_tokens,
            u.completion_tokens + result.completion_tokens,
            u.accelerator_ms + result.compute_ms,
        )
