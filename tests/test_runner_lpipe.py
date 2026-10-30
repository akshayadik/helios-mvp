"""The runner with the S2.3 L-pipe: evidence, LLM-only, cache replay, reruns."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from helios.integrity_gate import AppendOnlyLedger
from helios.orchestrator.runner import RunOrchestrator
from helios.pipelines.l_pipe.cache import ResponseCache
from helios.schemas.telemetry import TelemetryWindow
from helios.store.result_store import ResultStore
from helios.telemetry.seal import write_seal
from helios.vcl import VCLFlag, get_variant, set_current_manifest  # noqa: F401
from tests.pipelines.l_pipe.test_pipeline import OTEL, FakeClient

REPO = Path(__file__).resolve().parents[1]
KEY = b"test-secret-at-least-32-chars-long!!"
_STREAMS = ("p1_metrics_path", "p2_traces_path", "p3_logs_path")

# The frozen D-pipe warns (scipy ConstantInputWarning) on some real windows; the
# build tools run without the error filter, so only these tests silence it.
pytestmark = pytest.mark.filterwarnings("ignore::scipy.stats.ConstantInputWarning")


def stage_capture(captures: Path, manifest: Path = OTEL) -> str:
    """A sealed copy of a build case whose stream paths point at the repo files."""
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    raw.pop("window_hash", None)
    raw.pop("snapshot_hash", None)
    for attr in _STREAMS:
        if raw.get(attr):
            raw[attr] = str(REPO / raw[attr])
    window = TelemetryWindow(**raw)
    inc_dir = captures / window.incident_id
    inc_dir.mkdir(parents=True)
    out = window.model_dump(mode="json")
    out["window_hash"] = window.compute_window_hash()
    (inc_dir / "manifest.json").write_text(json.dumps(out), encoding="utf-8")
    write_seal(inc_dir, window, KEY)
    return window.incident_id


def run_variant(
    tmp_path: Path,
    variant: str,
    client: FakeClient,
    cache: ResponseCache | None = None,
    name: str = "r",
) -> ResultStore:
    captures = tmp_path / "captures"
    if not captures.exists():
        stage_capture(captures)
    manifest = get_variant(variant)
    set_current_manifest(manifest)
    db = tmp_path / f"{name}.duckdb"
    RunOrchestrator(
        manifest=manifest,
        captures_dir=captures,
        db_path=db,
        registry_path=tmp_path / f"{name}.registry.jsonl",
        reconciliation_path=tmp_path / f"{name}.reconciliation.jsonl",
        exclusion_ledger=MagicMock(spec=AppendOnlyLedger),
        hmac_key=KEY,
        lpipe_client=client,  # type: ignore[arg-type]
        lpipe_cache=cache,
    ).run(captures)
    return ResultStore(db)


def _lpipe_row(store: ResultStore) -> dict[str, Any]:
    rows = [r for r in store.fetch_all() if r["pipeline"] == "lpipe"]
    assert len(rows) == 1
    return rows[0]


def test_runner_stores_lpipe_evidence(tmp_path: Path) -> None:
    store = run_variant(tmp_path, "HELIOS-Full", FakeClient())
    row = _lpipe_row(store)
    assert row["status"] == "ranked"
    evidence = store.fetch_evidence(str(row["run_id"]), "lpipe")
    assert evidence is not None
    assert evidence["k"] == 3
    assert set(evidence["workers"]) == {"metric", "log", "trace"}


def test_llm_only_variant_runs_lpipe_without_graph(tmp_path: Path) -> None:
    store = run_variant(tmp_path, "HELIOS-LLM-only", FakeClient())
    assert _lpipe_row(store)["status"] == "ranked"
    gpipe = [r for r in store.fetch_all() if r["pipeline"] == "gpipe"]
    assert [r["status"] for r in gpipe] == ["skipped"]


def test_cached_run_replays_wall_time(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.sqlite"
    run_variant(tmp_path, "HELIOS-Full", FakeClient(), ResponseCache(cache_path), "a")
    with sqlite3.connect(cache_path) as db:
        db.execute("UPDATE calls SET wall_ms = 5000")
    client = FakeClient()
    store = run_variant(tmp_path, "HELIOS-Full", client, ResponseCache(cache_path), "b")
    assert client.calls == 0
    assert float(_lpipe_row(store)["latency_ms"]) >= 3 * 5000


def test_rerun_gives_equal_lpipe_decisions(tmp_path: Path) -> None:
    first = _lpipe_row(run_variant(tmp_path, "HELIOS-Full", FakeClient(), name="a"))
    second = _lpipe_row(run_variant(tmp_path, "HELIOS-Full", FakeClient(), name="b"))
    for key in ("status", "ranked_candidates", "candidate_scores", "mu", "sigma"):
        assert first[key] == second[key], key
