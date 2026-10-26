"""In-process test of bin/khop_calibrate.py on the synthetic build corpus."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from bin import khop_calibrate as cli
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from tests.graph.test_ueg_c_check_cli import _corpus

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_calibration_prints_counts_and_the_selected_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _corpus(tmp_path)
    truth = {"cases": {"aaa": {"root_cause_service": "cart"}}}
    (tmp_path / "data" / "rcaeval" / "ground_truth_build.json").write_text(
        json.dumps(truth), encoding="utf-8"
    )
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    assert cli.main(["--corpus", "build"]) == 0
    out = capsys.readouterr().out
    assert "2 windows, 1 graphs" in out
    assert "root cause is a service node: 1/1" in out
    assert "K=3 top-n=200: root cause kept 1/1" in out
    assert "selected by the rule: K=" in out
    assert "with the 50-node floor: root cause kept 1/1" in out
    for name in ("redis", "cart", "kafka", "logger", "frontend"):
        assert name not in out


def test_capture_labels_match_short_service_names() -> None:
    assert cli._key("adService") == cli._key("ad")
    assert cli._key("product-catalog") == cli._key("productCatalogService")
    assert cli._key("service") == "service"
