"""LLM narrator: the model picks and orders code-written candidate claims, one
call per slot, one retry, then the template slot (S2.8 design §5.4, owner
decisions N-d and (b) of 2026-11-01)."""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any

from helios.narrative.llm import llm_slots, pick_schema, render_prompt
from helios.narrative.params import load_narrator_params
from helios.narrative.template import candidate_claims, template_slots
from helios.pipelines.l_pipe.cache import ResponseCache
from helios.pipelines.l_pipe.gateway import LLMGateway
from helios.pipelines.l_pipe.ollama_client import (
    OllamaConnectionError,
    OllamaGenerateResult,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from tests.narrative.test_verifier import ENTRY

if TYPE_CHECKING:
    from pathlib import Path

P = load_narrator_params()
DIGEST = "d" * 64
CANDS = candidate_claims(ENTRY, P)
_USAGE = (120, 20, 5)  # prompt tokens, completion tokens, compute ms


def _picks(*ids: str) -> str:
    return json.dumps({"claims": list(ids)})


GOOD = {
    "story": _picks("C3", "C1"),
    "contradictions": _picks("C1"),
    "verification": _picks("C2", "C1"),
}


class Scripted:
    """Answers per slot from a queue; an exception in the queue is raised."""

    def __init__(self, answers: dict[str, list[Any]]) -> None:
        self.answers = {k: list(v) for k, v in answers.items()}
        self.prompts: list[str] = []
        self.schemas: list[dict[str, Any] | None] = []

    def model_digest(self, timeout_s: float) -> str:
        return DIGEST

    def generate(
        self, prompt: str, timeout_s: float, schema: dict[str, Any] | None = None
    ) -> OllamaGenerateResult:
        self.prompts.append(prompt)
        self.schemas.append(schema)
        slot = next(s for s in self.answers if f"SLOT: {s}" in prompt)
        answer = self.answers[slot].pop(0)
        if isinstance(answer, Exception):
            raise answer
        return OllamaGenerateResult(answer, *_USAGE)


class NoCalls:
    def model_digest(self, timeout_s: float) -> str:
        return DIGEST

    def generate(
        self, prompt: str, timeout_s: float, schema: dict[str, Any] | None = None
    ) -> OllamaGenerateResult:
        raise AssertionError("no model call expected")


def _run(client: Any, cache: ResponseCache | None = None, entry: Any = ENTRY) -> Any:
    gateway = LLMGateway(client)
    out = llm_slots(entry, P, gateway=gateway, cache=cache, model_digest=DIGEST)
    return out, gateway


def _with(slot: str, *answers: Any) -> dict[str, list[Any]]:
    return {**{k: [v] for k, v in GOOD.items()}, slot: list(answers)}


def test_picks_are_shown_in_the_models_order() -> None:
    out, gateway = _run(Scripted({k: [v] for k, v in GOOD.items()}))
    assert all(r.source == "llm" and r.attempts == 1 for r in out.values())
    assert list(out["story"].claims) == [CANDS["story"][2], CANDS["story"][0]]
    assert list(out["verification"].claims) == [
        CANDS["verification"][1],
        CANDS["verification"][0],
    ]
    assert gateway.usage.calls == 3


def test_prompt_lists_candidates_not_evidence_ids_or_worker_claims() -> None:
    a = render_prompt("story", ENTRY, P)
    assert a == render_prompt("story", copy.deepcopy(ENTRY), P)
    assert "SLOT: story" in a
    for n, claim in enumerate(CANDS["story"], start=1):
        assert f"C{n} | {claim.kind.value} | {claim.sentence}" in a
    assert "pool exhausted" not in a.replace("connection pool exhausted", "")


def test_unknown_pick_retry_then_accept() -> None:
    client = Scripted(_with("story", _picks("C1", "C999"), _picks("C1")))
    out, gateway = _run(client)
    story = out["story"]
    assert (story.source, story.attempts, story.fallback) == ("llm", 2, False)
    assert story.rejections == ((1, "unknown_id"),)
    assert "unknown_id" in [p for p in client.prompts if "SLOT: story" in p][1]
    assert gateway.usage.calls == 4


def test_two_failures_fall_back_to_template_slot() -> None:
    out, _ = _run(Scripted(_with("story", _picks("C999"), _picks("C998"))))
    story = out["story"]
    assert (story.source, story.attempts, story.fallback) == ("template", 2, True)
    assert list(story.claims) == template_slots(ENTRY, P)["story"]


def test_bad_answers_are_schema_rejections() -> None:
    too_many = _picks(*(f"C{n}" for n in range(1, 8)))
    for bad in (
        "not json",
        json.dumps({"story": "prose"}),
        _picks(),
        _picks("C1", "C1"),
        too_many,
        json.dumps({"claims": [{"kind": "ranking"}]}),
    ):
        out, _ = _run(Scripted(_with("story", bad, bad)))
        assert out["story"].fallback, bad
        assert {r for _, r in out["story"].rejections} == {"schema"}, bad
        assert out["contradictions"].source == "llm"


def test_model_error_falls_back() -> None:
    down = OllamaConnectionError("down")
    out, _ = _run(Scripted(_with("story", down, down)))
    assert out["story"].fallback
    assert out["story"].rejections == ((-1, "model_error"), (-1, "model_error"))


def test_cache_replays_retry_deterministically(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path / "c.sqlite")
    first, g1 = _run(Scripted(_with("story", _picks("C999"), _picks("C1"))), cache)
    second, g2 = _run(NoCalls(), cache)
    assert first == second
    assert g2.usage.calls == g1.usage.calls == 4


def test_empty_slot_makes_no_call() -> None:
    entry = copy.deepcopy(ENTRY)
    next(s for s in entry["steps"] if s["id"] == "F")["disagree"] = []
    client = Scripted(
        {"story": [GOOD["story"]], "verification": [GOOD["verification"]]}
    )
    out, gateway = _run(client, entry=entry)
    assert out["contradictions"].attempts == 0 and out["contradictions"].claims == ()
    assert gateway.usage.calls == 2


def test_first_draft_counts() -> None:
    out, _ = _run(Scripted(_with("story", _picks("C1", "C999"), _picks("C1"))))
    assert (out["story"].drafted_first, out["story"].accepted_first) == (2, 1)
    assert (
        out["verification"].drafted_first,
        out["verification"].accepted_first,
    ) == (2, 2)


def test_each_slot_call_sends_its_pick_schema() -> None:
    client = Scripted({k: [v] for k, v in GOOD.items()})
    _run(client)
    slots = [next(s for s in GOOD if f"SLOT: {s}" in p) for p in client.prompts]
    assert client.schemas == [pick_schema(s, CANDS[s], P) for s in slots]
    claims = pick_schema("story", CANDS["story"], P)["properties"]["claims"]
    ids = [f"C{n}" for n in range(1, len(CANDS["story"]) + 1)]
    assert claims["items"]["enum"] == ids
    steps = pick_schema("verification", CANDS["verification"], P)
    assert steps["properties"]["claims"]["maxItems"] == P.max_steps


def test_cache_key_covers_the_schema(tmp_path: Path, monkeypatch: Any) -> None:
    # A schema change must never replay an answer drafted under another schema.
    from helios.narrative import llm

    cache = ResponseCache(tmp_path / "c.sqlite")
    _run(Scripted({k: [v] for k, v in GOOD.items()}), cache)
    monkeypatch.setattr(llm, "pick_schema", lambda *_a: {"type": "object"})
    client = Scripted({k: [v] for k, v in GOOD.items()})
    _run(client, cache)
    assert len(client.prompts) == 3
