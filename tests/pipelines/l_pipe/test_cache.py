"""Response cache and model digest (S2.3 design §5.6)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from helios.pipelines.l_pipe.aliases import build_alias_map
from helios.pipelines.l_pipe.cache import CachedCall, ResponseCache, cache_key
from helios.pipelines.l_pipe.digests import Digest, DigestLine
from helios.pipelines.l_pipe.gateway import LLMGateway
from helios.pipelines.l_pipe.ollama_client import (
    OllamaClient,
    OllamaGenerateResult,
    OllamaTimeoutError,
)
from helios.pipelines.l_pipe.personas import PERSONAS
from helios.pipelines.l_pipe.workers import run_worker
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path

ALIAS = build_alias_map("x", ["cart", "checkout"], [])
DIGEST = Digest("log", (DigestLine("L1", "cart", "cart boom 9 lines", 9),), 0)
ANSWER = json.dumps(
    {
        "ranked": [
            {
                "service": ALIAS.forward["cart"],
                "claims": [{"text": "t", "cites": ["L1"]}],
            }
        ]
    }
)


class FakeClient:
    def __init__(self, answers: list[str | Exception]) -> None:
        self.answers = list(answers)
        self.calls = 0

    def generate(self, prompt: str, timeout_s: float) -> OllamaGenerateResult:
        self.calls += 1
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return OllamaGenerateResult(a, 100, 20, 450)


def _run(cache: ResponseCache, client: FakeClient) -> tuple[object, LLMGateway]:
    gw = LLMGateway(client)  # type: ignore[arg-type]
    return (
        run_worker(PERSONAS[1], DIGEST, ALIAS, gw, cache=cache, model_digest="m1"),
        gw,
    )


def test_miss_calls_model_and_stores(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path / "c.sqlite")
    client = FakeClient([ANSWER])
    result, _ = _run(cache, client)
    assert client.calls == 1
    assert not result.cache_hit  # type: ignore[attr-defined]
    assert cache.size() == 1


def test_hit_replays_usage_and_wall_time(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path / "c.sqlite")
    first, gw1 = _run(cache, FakeClient([ANSWER]))
    client = FakeClient([])
    second, gw2 = _run(cache, client)
    assert client.calls == 0
    assert second.cache_hit  # type: ignore[attr-defined]
    assert second.ranked == first.ranked  # type: ignore[attr-defined]
    assert second.wall_ms == first.wall_ms  # type: ignore[attr-defined]
    assert gw2.usage == gw1.usage


def test_failed_call_not_cached(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path / "c.sqlite")
    _run(cache, FakeClient([OllamaTimeoutError("slow")]))
    assert cache.size() == 0


def test_key_changes_with_model_digest_prompt_sha_or_input() -> None:
    base = cache_key("m1", "p1", "input")
    assert base == cache_key("m1", "p1", "input")
    assert (
        len(
            {
                base,
                cache_key("m2", "p1", "input"),
                cache_key("m1", "p2", "input"),
                cache_key("m1", "p1", "other"),
            }
        )
        == 4
    )


def test_cache_round_trip(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path / "c.sqlite")
    call = CachedCall("text", 1, 2, 3, 4)
    cache.put("k", call)
    assert ResponseCache(tmp_path / "c.sqlite").get("k") == call
    assert cache.get("missing") is None


def test_model_digest_parsed() -> None:
    body = {
        "models": [
            {"name": "other:1b", "digest": "aa"},
            {"name": "llama3.1:8b", "digest": "bb"},
        ]
    }
    response = MagicMock(status_code=200)
    response.json.return_value = body
    with patch("requests.get", return_value=response) as get:
        assert (
            OllamaClient("http://h:1", "llama3.1:8b").model_digest(timeout_s=5) == "bb"
        )
    assert get.call_args.args[0] == "http://h:1/api/tags"
