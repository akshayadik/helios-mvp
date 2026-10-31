"""Engine: picks the narrator, renders, and builds CoE step N (S2.8 §5.6)."""

from __future__ import annotations

from typing import Any

import pytest

from helios.narrative.engine import run_narrative
from helios.narrative.params import load_narrator_params
from helios.pipelines.l_pipe.ollama_client import OllamaConnectionError
from helios.vcl import VCLFlag, get_variant, set_current_manifest
from helios.vcl.decorators import GatedComponentInactiveError
from tests.narrative.test_llm import DIGEST, GOOD, NoCalls, Scripted
from tests.narrative.test_verifier import ENTRY

P = load_narrator_params()


@pytest.fixture(autouse=True)
def _full() -> None:
    set_current_manifest(get_variant("HELIOS-Full"))


def test_template_narrative_makes_no_call() -> None:
    n = run_narrative(ENTRY, params=P, llm=False, client=NoCalls(), cache=None)  # type: ignore[arg-type]
    assert n.narrator == "template"
    assert all(s.source == "template" for s in n.slots.values())
    assert (n.prompt_tokens, n.completion_tokens) == (0, 0)
    assert n.rendered.startswith("Top suspects: 1. cart")


def test_llm_narrative_step_n() -> None:
    client = Scripted({k: [v] for k, v in GOOD.items()})
    n = run_narrative(ENTRY, params=P, llm=True, client=client, cache=None)  # type: ignore[arg-type]
    step = n.as_step()
    assert step["id"] == "N" and step["narrator"] == "llm"
    assert step["cost"] == {"prompt_tokens": 300, "completion_tokens": 60}
    assert set(step["measured"]) == {"wall_ms"}
    assert set(step["slots"]) == {"story", "contradictions", "verification"}
    story = step["slots"]["story"]
    assert story["source"] == "llm" and story["claims"][0]["kind"] == "ranking"
    assert step["rendered"] == n.rendered


def test_unreachable_model_falls_back_without_calls() -> None:
    class Down(NoCalls):
        def model_digest(self, timeout_s: float) -> str:
            raise OllamaConnectionError("down")

    n = run_narrative(ENTRY, params=P, llm=True, client=Down(), cache=None)  # type: ignore[arg-type]
    assert n.narrator == "llm"
    assert all(s.source == "template" for s in n.slots.values() if s.claims)
    assert all(s.fallback for s in n.slots.values() if s.claims)


def test_gated_off_by_coe_narrative() -> None:
    set_current_manifest(get_variant("HELIOS-noExpl"))
    with pytest.raises(GatedComponentInactiveError):
        run_narrative(ENTRY, params=P, llm=False, client=None, cache=None)
    assert VCLFlag.COE_NARRATIVE.value == "coe_narrative"


def test_digest_passed_to_cache_key(tmp_path: Any) -> None:
    from helios.pipelines.l_pipe.cache import ResponseCache

    cache = ResponseCache(tmp_path / "c.sqlite")
    client = Scripted({k: [v] for k, v in GOOD.items()})
    run_narrative(ENTRY, params=P, llm=True, client=client, cache=cache)  # type: ignore[arg-type]
    assert cache.size() == 3
    assert client.model_digest(1) == DIGEST
