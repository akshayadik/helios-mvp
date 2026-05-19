"""PromptRegistry unit tests — SHA governance."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from helios.pipelines.l_pipe.prompt_registry import PROMPT_PATH, PromptRegistry
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def _load_registry() -> PromptRegistry:
    return PromptRegistry(PROMPT_PATH)


def test_sha_stable_across_two_loads() -> None:
    r1 = _load_registry()
    r2 = _load_registry()
    assert r1.prompt_sha == r2.prompt_sha


def test_render_substitutes_placeholders() -> None:
    registry = _load_registry()
    rendered = registry.render(
        incident_id="inc-001",
        service_list=["frontend", "checkout"],
        anomaly_summary="Latency spike detected",
    )
    assert "inc-001" in rendered
    assert "frontend, checkout" in rendered
    assert "Latency spike detected" in rendered


def test_verify_sha_passes_on_correct_hash() -> None:
    registry = _load_registry()
    assert registry.verify_sha(registry.prompt_sha) is True


def test_verify_sha_fails_on_tampered_content() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("tampered content")
        tmp_path = Path(f.name)
    try:
        registry = PromptRegistry(tmp_path)
        original = _load_registry()
        assert registry.verify_sha(original.prompt_sha) is False
    finally:
        tmp_path.unlink()


def test_tamper_raises_on_pipeline_init() -> None:
    from helios.pipelines.l_pipe.prompt_registry import PromptTamperError

    registry = _load_registry()
    with pytest.raises(PromptTamperError):
        registry.verify_sha_or_raise("wrong-sha-value-that-will-not-match")
