"""run_lpipe over the three workers (S2.3 design §5; L-a to L-g)."""

from __future__ import annotations

import ast
import dataclasses
import json
import re
from pathlib import Path
from typing import Any

import pytest

from helios.pipelines.l_pipe import personas as personas_module
from helios.pipelines.l_pipe.cache import ResponseCache
from helios.pipelines.l_pipe.ollama_client import OllamaGenerateResult
from helios.pipelines.l_pipe.pipeline import ProvisionalPromptError, run_lpipe
from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.telemetry.trigger import TriggerRecord, detect, load_detector_params
from helios.vcl import VCLFlag, get_variant, set_current_manifest  # noqa: F401

REPO = Path(__file__).resolve().parents[3]
L_PIPE = REPO / "helios/pipelines/l_pipe"
_LINE = re.compile(r"^([MLT]\d+) (svc-\d+)\b", re.MULTILINE)
_USAGE = (50, 10, 90)  # prompt tokens, completion tokens, compute ms per fake call


def _window(manifest: Path, **update: Any) -> TelemetryWindow:
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    raw.pop("window_hash", None)
    raw.pop("snapshot_hash", None)
    return TelemetryWindow(**raw).model_copy(update=update)


OTEL = sorted((REPO / "data/otel/build_v3").glob("*/manifest.json"))[9]  # all 3 digests
RCAEVAL = REPO / "data/rcaeval/build/07cd12b1da55c799672f5c85336eb8ea/manifest.json"


def _trigger(window: TelemetryWindow) -> TriggerRecord:
    return detect(window, load_detector_params(), root=REPO)


class FakeClient:
    """Ranks the service of the digest's first line, citing that line."""

    def __init__(self, answer: str | None = None) -> None:
        self.answer = answer
        self.calls = 0
        self.in_flight = 0
        self.max_in_flight = 0

    def model_digest(self, timeout_s: float) -> str:
        return "fake-digest"

    def generate(self, prompt: str, timeout_s: float) -> OllamaGenerateResult:
        self.calls += 1
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if self.answer is not None:
                return OllamaGenerateResult(self.answer, *_USAGE)
            line_id, svc = _LINE.findall(prompt)[0]
            text = json.dumps(
                {
                    "ranked": [
                        {"service": svc, "claims": [{"text": "x", "cites": [line_id]}]}
                    ]
                }
            )
            return OllamaGenerateResult(text, *_USAGE)
        finally:
            self.in_flight -= 1


def _run(window: TelemetryWindow, client: FakeClient, **kw: Any) -> dict[str, Any]:
    set_current_manifest(get_variant("HELIOS-Full"))
    return run_lpipe(
        incident_id=window.incident_id,
        snapshot_hash="s" * 64,
        evaluation_phase=window.evaluation_phase.value,
        run_id="r",
        window=window,
        trigger=_trigger(window),
        root=REPO,
        client=client,  # type: ignore[arg-type]
        **kw,
    )


def test_ranked_verdict_with_mu_sigma() -> None:
    window = _window(OTEL)
    client = FakeClient()
    out = _run(window, client)
    assert out["status"] == "ranked"
    assert out["ranked_candidates"]
    assert out["mu"] is not None and out["sigma"] is not None
    assert out["evidence"]["k"] == 3
    assert client.calls == 3
    assert out["llm_calls"] == 3
    assert all(not s.startswith("svc-") for s in out["ranked_candidates"])
    assert set(out["evidence"]["workers"]) == {"metric", "log", "trace"}


def test_all_workers_invalid_abstains_with_reasons() -> None:
    out = _run(_window(OTEL), FakeClient('{"ranked": []}'))
    assert out["status"] == "abstained"
    assert out["ranked_candidates"] == []
    assert out["mu"] is None and out["sigma"] is None
    reasons = {w["dropped"] for w in out["evidence"]["workers"].values()}
    assert reasons == {"no_valid_claim"}


def test_rcaeval_window_runs_two_workers() -> None:
    client = FakeClient()
    out = _run(_window(RCAEVAL), client)
    assert client.calls == 2
    assert out["evidence"]["workers"]["trace"]["dropped"] == "no_digest"
    assert out["evidence"]["k"] == 2


def test_digest_crash_is_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_k: Any) -> None:
        raise ValueError("bad parquet")

    crashing = dataclasses.replace(personas_module.PERSONAS[0], build=boom)
    monkeypatch.setattr(
        personas_module, "PERSONAS", (crashing, *personas_module.PERSONAS[1:])
    )
    out = _run(_window(OTEL), FakeClient())
    assert out["status"] == "failed"
    assert out["ranked_candidates"] == []


def test_confirmatory_refuses_provisional_prompts() -> None:
    window = _window(OTEL, evaluation_phase=EvaluationPhase.CONFIRMATORY)
    client = FakeClient()
    set_current_manifest(get_variant("HELIOS-Full"))
    with pytest.raises(ProvisionalPromptError):
        run_lpipe(
            incident_id=window.incident_id,
            snapshot_hash="s" * 64,
            evaluation_phase="confirmatory",
            run_id="r",
            window=window,
            trigger=_trigger(_window(OTEL)),
            root=REPO,
            client=client,  # type: ignore[arg-type]
        )
    assert client.calls == 0


def test_calls_are_sequential() -> None:
    client = FakeClient()
    _run(_window(OTEL), client)
    assert client.max_in_flight == 1


def test_cache_hit_reports_replayed_time(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path / "c.sqlite")
    first = _run(_window(OTEL), FakeClient(), cache=cache)
    client = FakeClient()
    second = _run(_window(OTEL), client, cache=cache)
    assert client.calls == 0
    assert second["cache_hit"] is True and first["cache_hit"] is False
    assert second["replayed_ms"] == pytest.approx(
        sum(w["wall_ms"] for w in first["evidence"]["workers"].values())
    )
    assert second["ranked_candidates"] == first["ranked_candidates"]
    assert second["llm_calls"] == first["llm_calls"]


def test_never_reads_dpipe_or_gpipe() -> None:
    banned = (
        "helios.pipelines.d_pipe",
        "helios.pipelines.g_pipe",
        "helios.graph.ueg_c_builder",
        "helios.schemas.ueg_c",
    )
    for path in L_PIPE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(banned), (path.name, node.module)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(banned), (path.name, alias.name)
