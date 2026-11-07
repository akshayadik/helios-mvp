"""S3.5: an unreachable model is reported, and the cache is read without it."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from helios.pipelines.l_pipe import lpipe_config
from helios.pipelines.l_pipe.cache import ResponseCache
from helios.pipelines.l_pipe.ollama_client import (
    OllamaConnectionError,
    OllamaGenerateResult,
    OllamaTimeoutError,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from tests.pipelines.l_pipe.test_pipeline import OTEL, FakeClient, _run, _window

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


class Down(FakeClient):
    """The model endpoint refuses every request."""

    def model_digest(self, timeout_s: float) -> str:
        raise OllamaConnectionError("refused")

    def generate(
        self, prompt: str, timeout_s: float, schema: dict[str, Any] | None = None
    ) -> OllamaGenerateResult:
        self.calls += 1
        raise OllamaConnectionError("refused")


class DiesAfterDigest(FakeClient):
    """Reports its digest, then times out on every call."""

    def generate(
        self, prompt: str, timeout_s: float, schema: dict[str, Any] | None = None
    ) -> OllamaGenerateResult:
        self.calls += 1
        raise OllamaTimeoutError("slow")


def test_served_run_is_available_and_keeps_its_evidence_keys() -> None:
    out = _run(_window(OTEL), FakeClient())
    assert out["llm_unavailable"] is None
    assert "model_source" not in out["evidence"]


def test_endpoint_down_without_a_cache_fails_as_unavailable() -> None:
    client = Down()
    out = _run(_window(OTEL), client)
    assert out["status"] == "failed"
    assert out["llm_unavailable"] == "endpoint"
    assert client.calls == 0


def test_endpoint_down_with_unpinned_model_does_not_read_the_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = ResponseCache(tmp_path / "c.sqlite")
    _run(_window(OTEL), FakeClient(), cache=cache)
    monkeypatch.setattr(lpipe_config, "EXPECTED_MODEL_DIGEST", None)
    out = _run(_window(OTEL), Down(), cache=cache)
    assert out["status"] == "failed"
    assert out["llm_unavailable"] == "endpoint"


def test_endpoint_down_replays_the_cache_under_the_pinned_digest(
    tmp_path: Path,
) -> None:
    assert lpipe_config.EXPECTED_MODEL_DIGEST is not None
    cache = ResponseCache(tmp_path / "c.sqlite")
    served = _run(_window(OTEL), FakeClient(), cache=cache)
    client = Down()
    replay = _run(_window(OTEL), client, cache=cache)
    assert client.calls == 0
    assert replay["llm_unavailable"] is None
    assert replay["ranked_candidates"] == served["ranked_candidates"]
    assert replay["evidence"]["model_source"] == "cache_only"
    assert replay["evidence"]["model_digest"] == lpipe_config.EXPECTED_MODEL_DIGEST


def test_cache_miss_with_endpoint_down_is_unavailable_and_writes_nothing(
    tmp_path: Path,
) -> None:
    cache = ResponseCache(tmp_path / "c.sqlite")
    client = Down()
    out = _run(_window(OTEL), client, cache=cache)
    assert client.calls == 0
    assert cache.size() == 0
    assert out["status"] == "abstained"
    assert out["llm_unavailable"] == "cache_miss"
    drops = {w["dropped"] for w in out["evidence"]["workers"].values()}
    assert drops == {"cache_miss"}


def test_every_call_failing_after_the_digest_is_unavailable(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path / "c.sqlite")
    out = _run(_window(OTEL), DiesAfterDigest(), cache=cache)
    assert out["llm_unavailable"] == "calls"
    assert cache.size() == 0


def test_an_invalid_answer_means_the_model_was_available() -> None:
    out = _run(_window(OTEL), FakeClient(answer="not json"))
    assert out["status"] == "abstained"
    assert out["llm_unavailable"] is None
