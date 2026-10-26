"""bin/score_runs.py — the scoring CLI prints counts and means only."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

import bin.score_runs as cli
from helios.schemas.telemetry import EvaluationPhase
from helios.schemas.verdict import PipelineName, PipelineVerdict, VerdictStatus
from helios.store.result_store import ResultStore
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path


def _db(tmp_path: Path, phase: EvaluationPhase) -> Path:
    db = tmp_path / "results.duckdb"
    store = ResultStore(db)
    for run_id, ranked in (("r1", ["cart", "ad"]), ("r2", ["ad", "cart"])):
        store.insert(
            PipelineVerdict(
                run_id=run_id,
                incident_id=f"s0-{run_id}",
                variant_config_hash="a" * 64,
                snapshot_hash="b" * 64,
                pipeline=PipelineName.DPIPE,
                evaluation_phase=phase,
                status=VerdictStatus.RANKED,
                ranked_candidates=ranked,
                latency_ms=1,
            )
        )
    store.close()
    return db


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "repo"
    truth = root / "data" / "ground_truth.json"
    truth.parent.mkdir(parents=True)
    labels = {"s0-r1": {"root_cause_service": "cartService"}}
    labels["s0-r2"] = {"root_cause_service": "cartService"}
    truth.write_text(json.dumps(labels))
    monkeypatch.setattr(cli, "REPO_ROOT", root)
    return root


def test_scores_captures_and_prints_counts_only(
    tmp_path: Path, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = _db(tmp_path, EvaluationPhase.EXPLORATORY)
    assert cli.main(["--db", str(db), "--corpus", "captures"]) == 0
    out = capsys.readouterr().out
    assert "2 lists scored" in out
    assert "pipeline dpipe: n=2 " in out
    assert "hr_at_3=1.000" in out
    assert "mrr=0.750" in out  # (1 + 1/2) / 2
    for secret in ("cart", "s0-r1", "s0-r2"):
        assert secret not in out
    assert len(ResultStore(db).fetch_scores()) == 2


def test_confirmatory_runs_are_refused_before_build_freeze(
    tmp_path: Path, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = _db(tmp_path, EvaluationPhase.CONFIRMATORY)
    assert cli.main(["--db", str(db), "--corpus", "captures"]) == 3
    assert "build-freeze" in capsys.readouterr().out


def test_missing_database(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--db", str(tmp_path / "none.duckdb"), "--corpus", "build"]) == 2
    assert "no results database" in capsys.readouterr().out
