"""Tests for scripts/compile_ground_truth.py — ground truth label compiler. VCLFlag-compliant."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def test_compile_ground_truth_produces_valid_json(tmp_path: Path) -> None:
    md = textwrap.dedent(
        """
        | incident_id | environment | fault_injected_service | root_cause_service | fault_type | label_source | labelled_at | evaluation_phase |
        |---|---|---|---|---|---|---|---|
        | otel-001 | otel-demo | cartservice | cartservice | latency | manual | 2026-05-15 | exploratory |
        | otel-002 | otel-demo | paymentservice | paymentservice | crash | manual | 2026-05-15 | exploratory |
    """
    ).strip()
    md_file = tmp_path / "ground_truth_labelling.md"
    md_file.write_text(md)
    out_file = tmp_path / "ground_truth.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/compile_ground_truth.py",
            "--input",
            str(md_file),
            "--output",
            str(out_file),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(out_file.read_text())
    assert len(data) == 2
    assert data["otel-001"]["root_cause_service"] == "cartservice"
    assert data["otel-002"]["root_cause_service"] == "paymentservice"


def test_compile_ground_truth_no_rows_exits_nonzero(tmp_path: Path) -> None:
    md_file = tmp_path / "empty.md"
    md_file.write_text("# No table here\n")
    out_file = tmp_path / "out.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/compile_ground_truth.py",
            "--input",
            str(md_file),
            "--output",
            str(out_file),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
