"""bin/labelling_runs.py (S2.9 §5.7): signed build ledgers for Full and noLLM,
pool refused, no ground truth read."""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, Any

from bin import labelling_runs as tool
from helios.orchestrator.coe import CoELedger
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.ed25519 import generate_private_key
from tests.pipelines.l_pipe.test_pipeline import REPO, FakeClient
from tests.test_runner_lpipe import KEY, stage_capture

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_runs_refuse_pool_and_existing_dir(tmp_path: Path) -> None:
    assert tool.main(["--out", str(tmp_path / "x"), "--corpus", "pool"]) == 2
    (tmp_path / "exists").mkdir()
    assert tool.main(["--out", str(tmp_path / "exists")]) == 2


def test_runs_write_signed_ledgers_and_never_open_ground_truth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captures = tmp_path / "captures"
    stage_capture(
        captures, sorted((REPO / "data/otel/build_v3").glob("*/manifest.json"))[9]
    )
    missing = tmp_path / "no_ground_truth.json"
    monkeypatch.setattr(
        tool, "CORPORA", {"otel_build_v3": (str(captures), "x", str(missing))}
    )
    monkeypatch.setattr(tool, "BUILD_CORPORA", ("otel_build_v3",))
    monkeypatch.setattr(tool, "make_client", FakeClient)
    monkeypatch.setattr(tool, "CACHE_PATH", tmp_path / "cache.sqlite")
    monkeypatch.setattr(tool, "load_key", lambda: KEY)
    signer = generate_private_key()
    monkeypatch.setattr(tool, "load_signer", lambda: signer)
    opened: list[str] = []
    real_open = builtins.open

    def _open(file: Any, *args: Any, **kwargs: Any) -> Any:
        if "ground_truth" in str(file):
            opened.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _open)
    out = tmp_path / "build"
    assert tool.main(["--out", str(out)]) == 0
    assert opened == []
    dirs = sorted(p.name for p in out.iterdir())
    assert dirs == ["otel_build_v3-HELIOS-Full.coe", "otel_build_v3-HELIOS-noLLM.coe"]
    for d in out.iterdir():
        (path,) = d.glob("*.coe.jsonl")
        assert CoELedger(KEY, path, ed25519_public=signer.public_key()).verify()[0]
