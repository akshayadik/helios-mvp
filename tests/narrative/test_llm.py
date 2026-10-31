"""LLM narrator: one call per slot, one retry, then the template slot
(S2.8 design §5.4, owner decision N-d)."""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any

from helios.narrative.llm import llm_slots, render_prompt
from helios.narrative.params import load_narrator_params
from helios.narrative.template import template_slots
from helios.pipelines.l_pipe.cache import ResponseCache
from helios.pipelines.l_pipe.gateway import LLMGateway
from helios.pipelines.l_pipe.ollama_client import (
    OllamaConnectionError,
    OllamaGenerateResult,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from tests.narrative.test_verifier import ENTRY, SUPPORTED

if TYPE_CHECKING:
    from pathlib import Path

P = load_narrator_params()
DIGEST = "d" * 64


def _json(*names: str) -> str:
    return json.dumps(
        [SUPPORTED[n].model_dump(mode="json", exclude_none=True) for n in names]
    )


GOOD = {
    "story": _json("ranking", "shift", "log_message"),
    "contradictions": _json("contradiction"),
    "verification": _json("verification_step"),
}
BAD_RANK = json.dumps(
    [{**SUPPORTED["ranking"].model_dump(mode="json", exclude_none=True), "rank": 2}]
)


class Scripted:
    """Answers per slot from a queue; an exception in the queue is raised."""

    def __init__(self, answers: dict[str, list[Any]]) -> None:
        self.answers = {k: list(v) for k, v in answers.items()}
        self.prompts: list[str] = []

    def model_digest(self, timeout_s: float) -> str:
        return DIGEST

    def generate(self, prompt: str, timeout_s: float) -> OllamaGenerateResult:
        self.prompts.append(prompt)
        slot = next(s for s in self.answers if f"SLOT: {s}" in prompt)
        answer = self.answers[slot].pop(0)
        if isinstance(answer, Exception):
            raise answer
        return OllamaGenerateResult(answer, 100, 20, 5)


class NoCalls:
    def model_digest(self, timeout_s: float) -> str:
        return DIGEST

    def generate(self, prompt: str, timeout_s: float) -> OllamaGenerateResult:
        raise AssertionError("no model call expected")


def _run(client: Any, cache: ResponseCache | None = None, entry: Any = ENTRY) -> Any:
    gateway = LLMGateway(client)
    out = llm_slots(entry, P, gateway=gateway, cache=cache, model_digest=DIGEST)
    return out, gateway


def test_accepted_first_pass() -> None:
    client = Scripted({k: [v] for k, v in GOOD.items()})
    out, gateway = _run(client)
    assert all(r.source == "llm" and r.attempts == 1 for r in out.values())
    assert [c.kind.value for c in out["story"].claims] == [
        "ranking",
        "shift",
        "log_message",
    ]
    assert gateway.usage.calls == 3
    assert all("SLOT: " in p and "D:cart:latency" in p for p in client.prompts)


def test_retry_then_accept_counts_two_calls() -> None:
    client = Scripted(
        {**{k: [v] for k, v in GOOD.items()}, "story": [BAD_RANK, GOOD["story"]]}
    )
    out, gateway = _run(client)
    story = out["story"]
    assert (story.source, story.attempts, story.fallback) == ("llm", 2, False)
    assert story.rejections == ((0, "rank_mismatch"),)
    retry_prompt = [p for p in client.prompts if "SLOT: story" in p][1]
    assert "rank_mismatch" in retry_prompt
    assert gateway.usage.calls == 4


def test_two_failures_fall_back_to_template_slot() -> None:
    client = Scripted(
        {**{k: [v] for k, v in GOOD.items()}, "story": [BAD_RANK, BAD_RANK]}
    )
    out, _ = _run(client)
    story = out["story"]
    assert (story.source, story.attempts, story.fallback) == ("template", 2, True)
    assert list(story.claims) == template_slots(ENTRY, P)["story"]


def test_model_error_and_junk_fall_back() -> None:
    for answers in (
        [OllamaConnectionError("down"), OllamaConnectionError("down")],
        ["not json", json.dumps({"story": "prose"})],
        [json.dumps([{"kind": "opinion", "sentence": "x"}]), "[]"],
    ):
        client = Scripted({**{k: [v] for k, v in GOOD.items()}, "story": answers})
        out, _ = _run(client)
        assert out["story"].fallback and out["story"].source == "template", answers
        assert out["contradictions"].source == "llm"


def test_kind_not_allowed_in_slot_is_rejected() -> None:
    client = Scripted(
        {
            **{k: [v] for k, v in GOOD.items()},
            "verification": [GOOD["story"], GOOD["story"]],
        }
    )
    out, _ = _run(client)
    assert out["verification"].fallback
    assert {r for _, r in out["verification"].rejections} == {"schema"}


def test_cache_replays_retry_deterministically(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path / "c.sqlite")
    answers = {**{k: [v] for k, v in GOOD.items()}, "story": [BAD_RANK, GOOD["story"]]}
    first, g1 = _run(Scripted(answers), cache)
    second, g2 = _run(NoCalls(), cache)
    assert first == second
    assert g2.usage.calls == g1.usage.calls == 4
    assert g2.usage.prompt_tokens == g1.usage.prompt_tokens


def test_empty_slot_makes_no_call() -> None:
    entry = copy.deepcopy(ENTRY)
    next(s for s in entry["steps"] if s["id"] == "F")["disagree"] = []
    client = Scripted(
        {"story": [GOOD["story"]], "verification": [GOOD["verification"]]}
    )
    out, gateway = _run(client, entry=entry)
    assert out["contradictions"].attempts == 0 and out["contradictions"].claims == ()
    assert gateway.usage.calls == 2


def test_prompt_is_deterministic_and_marks_the_slot() -> None:
    a = render_prompt("story", ENTRY)
    assert a == render_prompt("story", copy.deepcopy(ENTRY))
    assert "SLOT: story" in a and "L:log:claim1" not in a


def test_fallback_keeps_both_attempts_reasons() -> None:
    junk = json.dumps([{"kind": "opinion", "sentence": "x"}])
    client = Scripted({**{k: [v] for k, v in GOOD.items()}, "story": [BAD_RANK, junk]})
    out, _ = _run(client)
    assert out["story"].rejections == ((0, "rank_mismatch"), (-1, "schema"))


def test_first_draft_counts() -> None:
    two = json.dumps(
        [
            {
                **SUPPORTED["ranking"].model_dump(mode="json", exclude_none=True),
                "rank": 2,
            },
            SUPPORTED["shift"].model_dump(mode="json", exclude_none=True),
        ]
    )
    client = Scripted(
        {**{k: [v] for k, v in GOOD.items()}, "story": [two, GOOD["story"]]}
    )
    out, _ = _run(client)
    assert (out["story"].drafted_first, out["story"].accepted_first) == (2, 1)
    assert (
        out["contradictions"].drafted_first,
        out["contradictions"].accepted_first,
    ) == (
        1,
        1,
    )


def test_prompt_lists_the_slot_vocabulary() -> None:
    story = render_prompt("story", ENTRY, P)
    steps = render_prompt("verification", ENTRY, P)
    assert "ALLOWED WORDS" in story
    assert "suspect" in story and "waiting" in story and "logged" in story
    assert "incoming" in steps and "query" in steps
    assert "incoming" not in story.split("ALLOWED WORDS")[1].split("\n")[0]
