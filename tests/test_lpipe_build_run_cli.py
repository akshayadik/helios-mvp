"""bin/lpipe_build_run.py: refuses the pool, writes aggregates only (S2.3 §5.8)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from bin import lpipe_build_run as tool
from helios.evaluation.lpipe_calibration import LPipeCase
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from tests.pipelines.l_pipe.test_pipeline import OTEL, RCAEVAL, FakeClient, _window

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any

pytestmark = pytest.mark.filterwarnings("ignore::scipy.stats.ConstantInputWarning")


def test_tool_refuses_the_pool() -> None:
    assert tool.main(["--round", "1", "--corpus", "pool"]) == 2


def test_report_has_no_incident_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = [
        LPipeCase(
            _window(OTEL).incident_id,
            "otel_build_v3",
            _window(OTEL),
            "cart",
            "cartFailure",
        ),
        LPipeCase(
            _window(RCAEVAL).incident_id,
            "rcaeval_build",
            _window(RCAEVAL),
            "carts",
            None,
        ),
    ]

    def fake_cases(**_kw: Any) -> list[LPipeCase]:
        return cases

    monkeypatch.setattr(tool, "load_lpipe_cases", fake_cases)
    monkeypatch.setattr(tool, "load_key", lambda: b"k")
    monkeypatch.setattr(tool, "make_client", FakeClient)
    monkeypatch.setattr(tool, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(tool, "CACHE_PATH", tmp_path / "cache.sqlite")
    assert tool.main(["--round", "0", "--split", "both", "--final"]) == 0
    text = (tmp_path / "lpipe_round0.json").read_text(encoding="utf-8")
    for case in cases:
        assert case.incident_id not in text
    report = json.loads(text)
    assert report["round"] == 0
    total = sum(
        g["cases"] for corpus in report["summary"].values() for g in corpus.values()
    )
    assert total == 2
    assert report["model_digest"] == "fake-digest"
    assert set(report["prompt_shas"]) == {"metric", "log", "trace"}


def test_heldout_needs_the_final_flag() -> None:
    for split in ("heldout", "both"):
        with pytest.raises(SystemExit):
            tool.parse_args(["--round", "1", "--split", split])
        assert (
            tool.parse_args(["--round", "3", "--split", split, "--final"]).split
            == split
        )


def test_split_defaults_to_dev() -> None:
    assert tool.parse_args(["--round", "1"]).split == "dev"
