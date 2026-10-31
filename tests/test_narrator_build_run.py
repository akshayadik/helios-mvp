"""bin/narrator_build_run.py: dev split per round, no ground truth, final after a chosen round."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from bin import narrator_build_run as tool
from bin.mahc_build_run import CacheMissError
from helios.evaluation.lpipe_calibration import split_cases
from helios.orchestrator.runner import RunOrchestrator
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from tests.pipelines.l_pipe.test_pipeline import REPO, FakeClient
from tests.test_runner_lpipe import KEY, stage_capture

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.filterwarnings("ignore::scipy.stats.ConstantInputWarning")


def _stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Two staged build cases; the split of each; the tool pointed at them."""
    captures = tmp_path / "captures"
    sources = sorted((REPO / "data/otel/build_v3").glob("*/manifest.json"))[9:11]
    ids = [stage_capture(captures, src) for src in sources]
    missing = tmp_path / "no_ground_truth.json"  # the tool must never open it
    monkeypatch.setattr(
        tool, "CORPORA", {"otel_build_v3": (str(captures), "unused", str(missing))}
    )
    monkeypatch.setattr(tool, "BUILD_CORPORA", ("otel_build_v3",))
    monkeypatch.setattr(tool, "make_client", FakeClient)
    monkeypatch.setattr(tool, "CACHE_PATH", tmp_path / "cache.sqlite")
    monkeypatch.setattr(tool, "REPORT_DIR", tmp_path / "reports")
    monkeypatch.setattr(tool, "load_key", lambda: KEY)
    return split_cases(ids)


def _spy(monkeypatch: pytest.MonkeyPatch) -> list[set[str]]:
    seen: list[set[str]] = []
    original = RunOrchestrator.run

    def run(self: Any, corpus: Any, incidents: Any = None) -> None:
        seen.append(set(incidents))
        original(self, corpus, incidents)

    monkeypatch.setattr(RunOrchestrator, "run", run)
    return seen


def _report(tmp_path: Path, name: str) -> dict[str, Any]:
    return dict(json.loads((tmp_path / "reports" / name).read_text("utf-8")))


def test_round_uses_dev_split_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    splits = _stage(tmp_path, monkeypatch)
    seen = _spy(monkeypatch)
    assert tool.main(["--round", "1"]) == 0
    dev = {i for i, s in splits.items() if s == "dev"}
    assert seen == [dev, dev]  # HELIOS-Full, then HELIOS-noLLM
    report = _report(tmp_path, "narrator_round1.json")
    corpus = report["corpora"]["otel_build_v3"]
    assert report["split"] == "dev" and corpus["cases"] == len(dev)
    assert corpus["llm"]["narratives"] == len(dev)
    assert corpus["template"]["narratives"] == len(dev)


def test_report_written_without_ground_truth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    splits = _stage(tmp_path, monkeypatch)

    def no_labels(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("ground truth read")

    monkeypatch.setattr("helios.adapters.rcaeval.verify_ground_truth", no_labels)
    assert tool.main(["--round", "1"]) == 0
    text = (tmp_path / "reports" / "narrator_round1.json").read_text("utf-8")
    assert not any(i in text for i in splits)
    report = json.loads(text)
    from helios.narrative.params import load_narrator_params, narrator_params_hash
    from helios.narrative.prompt import NARRATOR_PROMPT_SHA

    assert report["narrator_prompt_sha"] == NARRATOR_PROMPT_SHA
    assert report["narrator_params_hash"] == narrator_params_hash(
        load_narrator_params()
    )
    assert set(report["corpora"]["otel_build_v3"]["llm"]) >= {
        "first_pass_claim_acceptance",
        "slot_fallback_rate",
        "rejections",
    }


def test_final_requires_chosen_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    splits = _stage(tmp_path, monkeypatch)
    with pytest.raises(SystemExit):
        tool.main(["--final"])  # no round chosen
    assert tool.main(["--final", "--chosen", "1"]) == 2  # round 1 never ran
    assert tool.main(["--round", "1"]) == 0
    path = tmp_path / "reports" / "narrator_round1.json"
    good = path.read_text("utf-8")
    stale = json.loads(good)
    stale["narrator_prompt_sha"] = "another prompt"
    path.write_text(json.dumps(stale), "utf-8")
    assert tool.main(["--final", "--chosen", "1"]) == 2  # prompt changed since
    path.write_text(good, "utf-8")
    seen = _spy(monkeypatch)
    assert tool.main(["--final", "--chosen", "1"]) == 0
    heldout = {i for i, s in splits.items() if s == "heldout"}
    assert seen == [heldout, heldout]
    final = _report(tmp_path, "narrator_final.json")
    assert final["split"] == "heldout" and final["chosen_round"] == 1


def test_tool_refuses_the_pool() -> None:
    assert tool.main(["--round", "1", "--corpus", "pool"]) == 2


def test_narrator_client_lets_only_narrator_prompts_reach_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # L-pipe answers must come from the cache; a call reaching the client is a miss.
    from helios.pipelines.l_pipe.ollama_client import (
        OllamaClient,
        OllamaGenerateResult,
    )

    def served(self: Any, prompt: str, timeout_s: float) -> OllamaGenerateResult:
        return OllamaGenerateResult("[]", 1, 1)

    monkeypatch.setattr(OllamaClient, "generate", served)
    client = tool._NarratorClient("http://h:1", "m")
    assert client.generate("HELIOS-NARRATOR\nSLOT: story", 1).text == "[]"
    with pytest.raises(CacheMissError):
        client.generate("worker prompt", 1)
