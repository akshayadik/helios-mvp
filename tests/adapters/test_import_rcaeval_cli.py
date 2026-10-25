"""End-to-end test of bin/import_rcaeval.py on a synthetic two-case corpus."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

import pandas as pd
import pytest

from bin import import_rcaeval as cli
from tests.adapters.test_rcaeval_adapter import T0, FakeFetcher, _raw_case

if TYPE_CHECKING:
    from pathlib import Path

    from helios.adapters.rcaeval import RemoteFile
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

CASES = ("re2ss_carts_cpu_1", "re2ss_carts_cpu_2")


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeFetcher:
    index = tmp_path / "idx" / "cases.parquet"
    index.parent.mkdir()
    pd.DataFrame(
        [
            {
                "case": c,
                "system": "ss",
                "root_cause_service": "carts",
                "fault": "cpu",
                "repetition": i + 1,
                "inject_time": T0 + 60,
                "has_logs": True,
                "has_traces": False,
            }
            for i, c in enumerate(CASES)
        ]
    ).to_parquet(index)
    files = {"cases.parquet": index.read_bytes()}
    for case in CASES:
        raw = _raw_case(tmp_path / "src" / case, traces=False)
        df = pd.read_parquet(raw / "metrics.parquet").rename(
            columns={
                "checkoutservice_cpu": "carts_cpu",
                "frontend_latency-90": "front-end_latency-90",
                "redis-cart_mem": "carts-db_mem",
            }
        )
        df.to_parquet(raw / "metrics.parquet")
        logs = pd.read_parquet(raw / "logs.parquet")
        logs["container_name"] = ["front-end", "carts"]
        logs.to_parquet(raw / "logs.parquet")
        for f in raw.iterdir():
            files[f"{case}/{f.name}"] = f.read_bytes()
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(cli, "REPO_ROOT", repo)
    monkeypatch.setattr(
        cli, "INDEX_SHA256", hashlib.sha256(files["cases.parquet"]).hexdigest()
    )
    monkeypatch.setenv("DEVIATION_HMAC_SECRET", "s" * 40)

    class CaseFetcher(FakeFetcher):
        def list_files(self, case: str) -> list[RemoteFile]:
            mine = {p: d for p, d in self.files.items() if p.startswith(case + "/")}
            return FakeFetcher(mine).list_files(case)

    return CaseFetcher(files)


def test_fetch_convert_verify_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fetcher = _fixture(tmp_path, monkeypatch)
    assert cli.main(["fetch", "--corpus", "build"], fetcher=fetcher) == 0
    assert cli.main(["convert", "--corpus", "build"]) == 0
    assert cli.main(["verify", "--corpus", "build"]) == 0
    out = capsys.readouterr().out
    assert "2/2 cases OK, 0 problem(s)" in out
    assert "re2ss" not in out and "carts" not in out  # convert prints no labels
    data = tmp_path / "repo" / "data" / "rcaeval"
    manifest = json.loads((data / "build_manifest.json").read_text())
    assert len(manifest["case_order"]) == 2
    truth = json.loads((data / "ground_truth_build.json").read_text())
    assert {c["case"] for c in truth["cases"].values()} == set(CASES)


def test_verify_detects_changed_telemetry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fetcher = _fixture(tmp_path, monkeypatch)
    cli.main(["fetch", "--corpus", "build"], fetcher=fetcher)
    cli.main(["convert", "--corpus", "build"])
    data = tmp_path / "repo" / "data" / "rcaeval"
    first = json.loads((data / "build_manifest.json").read_text())["case_order"][0]
    (data / "build" / first / "p1_metrics.parquet").write_bytes(b"tampered")
    assert cli.main(["verify", "--corpus", "build"]) == 1
    assert "content changed since sealing" in capsys.readouterr().out


def test_convert_refuses_a_non_empty_output_and_trials_write_nothing_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetcher = _fixture(tmp_path, monkeypatch)
    cli.main(["fetch", "--corpus", "build"], fetcher=fetcher)
    assert cli.main(["convert", "--corpus", "build", "--limit", "1"]) == 0
    data = tmp_path / "repo" / "data" / "rcaeval"
    assert not (data / "build_manifest.json").exists()
    assert not (data / "ground_truth_build.json").exists()
    with pytest.raises(SystemExit, match="not empty"):
        cli.main(["convert", "--corpus", "build"])


def test_convert_requires_fetched_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetcher = _fixture(tmp_path, monkeypatch)
    cli.main(["fetch", "--corpus", "build", "--limit", "1"], fetcher=fetcher)
    with pytest.raises(SystemExit, match="not fetched"):
        cli.main(["convert", "--corpus", "build"])


def test_fetch_rejects_an_index_that_is_not_the_pinned_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetcher = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "INDEX_SHA256", "0" * 64)
    with pytest.raises(SystemExit, match="pinned index"):
        cli.main(["fetch", "--corpus", "build"], fetcher=fetcher)
