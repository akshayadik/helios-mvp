"""The single-prompt rca_v1 stays frozen: OSF deposit 1 fingerprints its SHA.

S2.3 replaced it in the run path with three workers (tests/pipelines/l_pipe);
the file and ``EXPECTED_PROMPT_SHA`` are kept unchanged for verify_osf_freeze.
"""

from __future__ import annotations

from helios.pipelines.l_pipe.lpipe_config import EXPECTED_PROMPT_SHA
from helios.pipelines.l_pipe.prompt_registry import PROMPT_PATH, PromptRegistry
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def test_expected_prompt_sha_matches_registry() -> None:
    registry = PromptRegistry(PROMPT_PATH)
    assert registry.prompt_sha == EXPECTED_PROMPT_SHA
