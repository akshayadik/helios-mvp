#!/usr/bin/env python3
"""Check that the model server serves the pinned model (S4.3, design C-d).

Usage:
    HELIOS_OLLAMA_URL=http://model:11434 python bin/check_model.py

Compares the served digest of ``MODEL_NAME`` with ``EXPECTED_MODEL_DIGEST``
(deviation entry 58). Exits non-zero on a mismatch, an unserved model or an
unreachable server, so the compose runner, which depends on this check, never
starts against a different model. The run-start check stays in force as well.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helios.pipelines.l_pipe import lpipe_config
from helios.pipelines.l_pipe.ollama_client import (
    OllamaClient,
    OllamaConnectionError,
    OllamaResponseError,
    OllamaTimeoutError,
)
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance

_TIMEOUT_S = 30.0


def check(client: OllamaClient, expected: str | None) -> str:
    """The served digest when it equals ``expected``; SystemExit otherwise."""
    if expected is None:
        raise SystemExit("EXPECTED_MODEL_DIGEST is not set; nothing to check against")
    try:
        served = client.model_digest(timeout_s=_TIMEOUT_S)
    except (OllamaTimeoutError, OllamaConnectionError, OllamaResponseError) as exc:
        raise SystemExit(f"model check failed: {exc}") from exc
    if served != expected:
        raise SystemExit(
            f"model digest mismatch: served {served[:12]}, expected {expected[:12]}"
        )
    return served


def main() -> int:
    client = OllamaClient(lpipe_config.OLLAMA_BASE_URL, lpipe_config.MODEL_NAME)
    served = check(client, lpipe_config.EXPECTED_MODEL_DIGEST)
    print(f"[model] {lpipe_config.MODEL_NAME} digest {served[:12]} matches entry 58")
    return 0


if __name__ == "__main__":
    sys.exit(main())
