"""Persona Profiles: one stream per worker, registered prompts (S2.3 design §5.1)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import pyarrow.parquet as pq

from helios.pipelines.l_pipe import lpipe_config
from helios.pipelines.l_pipe.aliases import build_alias_map
from helios.pipelines.l_pipe.personas import (
    PERSONAS,
    prompt_sha,
    provisional,
    render_prompt,
)
from helios.schemas.telemetry import TelemetryWindow
from helios.telemetry.scope import in_scope
from helios.telemetry.trigger import TriggerRecord, TriggerSource, service_scores
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    import pytest

REPO = Path(__file__).resolve().parents[3]


def _otel_window() -> TelemetryWindow:
    manifest = sorted((REPO / "data/otel/build_v3").glob("*/manifest.json"))[0]
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    raw.pop("window_hash", None)
    raw.pop("snapshot_hash", None)
    return TelemetryWindow(**raw)


def _trigger(window: TelemetryWindow) -> TriggerRecord:
    start = pd.Timestamp(window.window_start_iso).timestamp()
    end = pd.Timestamp(window.window_end_iso).timestamp()
    return TriggerRecord(
        incident_id=window.incident_id,
        trigger_time_s=start + (end - start) * 3 / 5,
        suspects=(),
        context=(),
        source=TriggerSource.THRESHOLD,
        detector_hash="d",
    )


def test_personas_in_order() -> None:
    assert [(p.name, p.stream) for p in PERSONAS] == [
        ("metric", "p1"),
        ("log", "p3"),
        ("trace", "p2"),
    ]


def test_each_builder_opens_only_its_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _otel_window()
    streams = {
        "p1": window.p1_metrics_path,
        "p2": window.p2_traces_path,
        "p3": window.p3_logs_path,
    }
    opened: list[str] = []

    def spy(real: Any) -> Any:
        def inner(path: Any, *args: Any, **kwargs: Any) -> Any:
            opened.append(str(path if isinstance(path, str | Path) else path.name))
            return real(path, *args, **kwargs)

        return inner

    monkeypatch.setattr(pd, "read_parquet", spy(pd.read_parquet))
    monkeypatch.setattr(pq, "read_table", spy(pq.read_table))
    monkeypatch.setattr(pq, "read_schema", spy(pq.read_schema))
    for persona in PERSONAS:
        opened.clear()
        persona.build(window, _trigger(window), ["cart", "checkout"], root=REPO)
        own = str(REPO / str(streams[persona.stream]))
        assert opened, persona.name
        assert set(opened) == {own}, persona.name


def test_rendered_prompt_has_no_real_names_or_ids() -> None:
    window = _otel_window()
    services = service_scores(window, 60, root=REPO).services
    candidates = [s for s in services if in_scope(s)]
    components = [s for s in services if not in_scope(s)]
    alias = build_alias_map(window.incident_id, candidates, components)
    for persona in PERSONAS:
        digest = persona.build(window, _trigger(window), candidates, root=REPO)
        assert digest is not None and digest.lines, persona.name
        prompt = render_prompt(persona, digest, alias)
        alias.check(prompt)
        assert window.incident_id not in prompt
        assert "data/" not in prompt
        assert not re.search(r"\d{4}-\d{2}-\d{2}|\d{9,}", prompt)
        for name in candidates:
            assert not re.search(rf"\b{re.escape(name)}\b", prompt, re.IGNORECASE), name


def test_prompt_files_contain_contract_placeholders() -> None:
    for persona in PERSONAS:
        text = persona.prompt_path.read_text(encoding="utf-8")
        for key in ("{candidates}", "{digest}", "{max_ranked}"):
            assert key in text, (persona.name, key)
        assert len(prompt_sha(persona)) == 64


def test_frozen_prompt_shas_match_files_and_report() -> None:
    # Entry 58: the round 1 prompts and llama3.1:8b, as in the final build report.
    report = json.loads(
        (REPO / "docs/sprints/s2-reasoning/calibration/lpipe_round3.json").read_text(
            encoding="utf-8"
        )
    )
    files = {p.name: prompt_sha(p) for p in PERSONAS}
    assert lpipe_config.WORKER_PROMPT_SHAS == files == report["prompt_shas"]
    assert report["model_digest"] == lpipe_config.EXPECTED_MODEL_DIGEST
    assert report["split"] == "both"
    assert not provisional()


def test_provisional_when_a_sha_is_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    unset = {**lpipe_config.WORKER_PROMPT_SHAS, "log": None}
    monkeypatch.setattr(lpipe_config, "WORKER_PROMPT_SHAS", unset)
    assert provisional()


def test_template_words_are_not_checked_only_inserted_text(tmp_path: Path) -> None:
    # The fixed template may use a word that is also a service name ("user" in
    # Sock Shop); only the per-incident insertions can leak.
    import dataclasses

    from helios.pipelines.l_pipe.digests import Digest, DigestLine

    template = tmp_path / "t.txt"
    template.write_text(
        "user traffic {candidates} {digest} {max_ranked}", encoding="utf-8"
    )
    persona = dataclasses.replace(PERSONAS[0], prompt_path=template)
    alias = build_alias_map("x", ["user", "carts"], [])
    ok = Digest("metric", (DigestLine("M1", "carts", "carts cpu up", 3),), 0)
    assert "user traffic" in render_prompt(persona, ok, alias)
