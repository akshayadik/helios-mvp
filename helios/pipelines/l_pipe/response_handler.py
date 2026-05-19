"""ResponseHandler — JSON schema validation + single retry + fallback."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from helios.vcl import VCLFlag  # noqa: F401 — satisfies flag-guard

if TYPE_CHECKING:
    from helios.pipelines.l_pipe.ollama_client import (
        OllamaClient,
        OllamaGenerateResult,
    )

HELIOS_ENABLE_RESPONSE_HANDLER: bool = True

_MD_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def sanitize_llm_output(raw: str) -> str:
    """Strip markdown code-block wrapper if present."""
    m = _MD_FENCE_RE.search(raw)
    if m:
        return m.group(1).strip()
    return raw.strip()


class LPipeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ranked_candidates: list[str] = Field(min_length=1)
    narrative: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


_FALLBACK = LPipeResponse(
    ranked_candidates=["l-pipe-fallback"],
    narrative="l-pipe-fallback-schema-error",
    confidence=0.00,
)


class ResponseHandler:
    def __init__(self, client: OllamaClient, max_retries: int) -> None:
        self._client = client
        self._max_retries = max_retries

    def handle(
        self,
        prompt: str,
        timeout_s: float,
    ) -> tuple[LPipeResponse, OllamaGenerateResult | None]:
        retries_remaining = self._max_retries
        while retries_remaining >= 0:
            last_result = self._client.generate(prompt, timeout_s=timeout_s)
            sanitized = sanitize_llm_output(last_result.text)
            try:
                data = json.loads(sanitized)
                return (LPipeResponse(**data), last_result)
            except (json.JSONDecodeError, ValidationError):
                retries_remaining -= 1
        return (_FALLBACK, None)
