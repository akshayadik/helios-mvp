"""One worker call and its validation (S2.3 design §5.3, L-e)."""

from __future__ import annotations

import json
from typing import Any

from helios.pipelines.l_pipe.aliases import AliasLeakError, build_alias_map
from helios.pipelines.l_pipe.digests import Digest, DigestLine
from helios.pipelines.l_pipe.ollama_client import (
    OllamaGenerateResult,
    OllamaTimeoutError,
)
from helios.pipelines.l_pipe.personas import PERSONAS
from helios.pipelines.l_pipe.workers import DropReason, run_worker
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

SERVICES = ["ad", "cart", "checkout", "email", "payment", "quote", "shipping"]
ALIAS = build_alias_map("x", SERVICES, [])
LOG = PERSONAS[1]
DIGEST = Digest(
    "log",
    (
        DigestLine("L1", "cart", "cart log template boom: 0 lines before, 9 after", 9),
        DigestLine("L2", "checkout", "checkout calls to cart failed", 4),
    ),
    0,
)


def _a(name: str) -> str:
    return ALIAS.forward[name]


class FakeGateway:
    def __init__(self, answers: list[str | Exception]) -> None:
        self.answers = list(answers)
        self.calls = 0

    def generate(self, prompt: str, timeout_s: float) -> OllamaGenerateResult:
        self.calls += 1
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return OllamaGenerateResult(answer, 10, 5, 1)


def _answer(*ranked: tuple[str, list[str]]) -> str:
    return json.dumps(
        {
            "ranked": [
                {"service": s, "claims": [{"text": f"{s} broke", "cites": cites}]}
                for s, cites in ranked
            ]
        }
    )


def _run(
    *answers: str | Exception, digest: Digest | None = DIGEST
) -> tuple[Any, FakeGateway]:
    gw = FakeGateway(list(answers))
    return run_worker(LOG, digest, ALIAS, gw), gw  # type: ignore[arg-type]


def test_valid_answer_unmasked() -> None:
    result, _ = _run(_answer((_a("cart"), ["L1"]), (_a("checkout"), ["L2"])))
    assert result.valid
    assert result.ranked == ("cart", "checkout")
    assert result.claims["cart"][0].text == "cart broke"
    assert result.claims["cart"][0].cites == ("L1",)


def test_claim_citing_missing_id_dropped() -> None:
    result, _ = _run(_answer((_a("cart"), ["L9"]), (_a("checkout"), ["L2"])))
    assert result.ranked == ("checkout",)


def test_real_name_unknown_alias_or_foreign_id_invalid() -> None:
    result, _ = _run(
        _answer(("cart", ["L1"]), ("svc-99", ["L1"]), (_a("email"), ["T3"]))
    )
    assert not result.valid
    assert result.dropped == DropReason.NO_VALID_CLAIM


def test_more_than_five_truncated_to_five() -> None:
    answer = _answer(*[(_a(s), ["L1"]) for s in SERVICES])
    result, _ = _run(answer)
    assert len(result.ranked) == 5


def test_duplicate_service_keeps_first() -> None:
    result, _ = _run(
        _answer((_a("cart"), ["L1"]), (_a("checkout"), ["L2"]), (_a("cart"), ["L2"]))
    )
    assert result.ranked == ("cart", "checkout")
    assert result.claims["cart"][0].cites == ("L1",)


def test_schema_failure_drops_without_retry() -> None:
    # Protocol A decoding is deterministic: the same prompt gives the same text.
    result, gw = _run("not json")
    assert gw.calls == 1
    assert result.dropped == DropReason.SCHEMA
    assert result.raw == "not json"


def test_alias_leak_is_a_drop(monkeypatch: Any) -> None:
    from helios.pipelines.l_pipe import workers

    def leak(*_a: Any, **_k: Any) -> str:
        raise AliasLeakError("1 real name(s) survived masking")

    monkeypatch.setattr(workers, "render_prompt", leak)
    result, gw = _run(_answer((_a("cart"), ["L1"])))
    assert result.dropped == DropReason.ALIAS_LEAK
    assert gw.calls == 0


def test_cache_error_falls_back_to_the_model(tmp_path: Any) -> None:
    import sqlite3

    class Broken:
        def get(self, key: str) -> None:
            raise sqlite3.OperationalError("locked")

        def put(self, key: str, call: Any) -> None:
            raise sqlite3.OperationalError("locked")

    gw = FakeGateway([_answer((_a("cart"), ["L1"]))])
    result = run_worker(LOG, DIGEST, ALIAS, gw, cache=Broken())  # type: ignore[arg-type]
    assert result.valid and gw.calls == 1 and not result.cache_hit


def test_timeout_is_a_drop_not_an_exception() -> None:
    result, gw = _run(OllamaTimeoutError("slow"))
    assert result.dropped == DropReason.TIMEOUT
    assert gw.calls == 1


def test_no_digest_drops_without_calling() -> None:
    result, gw = _run(digest=None)
    assert result.dropped == DropReason.NO_DIGEST
    assert gw.calls == 0
    empty, gw = _run(digest=Digest("log", (), 0))
    assert empty.dropped == DropReason.NO_DIGEST and gw.calls == 0


def test_empty_ranking_is_no_valid_claim() -> None:
    result, _ = _run('{"ranked": []}')
    assert result.dropped == DropReason.NO_VALID_CLAIM
