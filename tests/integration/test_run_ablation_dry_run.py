"""Integration tests for run_ablation.py --dry-run mode."""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

from helios.vcl.config import VCLManifest  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path


def test_dry_run_exits_zero(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_ablation.py",
            "--dry-run",
            "--output-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_dry_run_prints_variant_list(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_ablation.py",
            "--dry-run",
            "--output-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    # Must list all 8 confirmatory variants
    for name in ["HELIOS-Full", "HELIOS-noLLM", "HELIOS-noGraph", "HELIOS-D"]:
        assert name in result.stdout, f"{name} not in output"


def test_dry_run_prints_expected_row_count(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_ablation.py",
            "--dry-run",
            "--output-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert "480" in result.stdout, f"Expected 480 in output, got: {result.stdout}"


def test_dry_run_does_not_create_db_files(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "scripts/run_ablation.py",
            "--dry-run",
            "--output-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    db_files = list(tmp_path.glob("*.duckdb"))
    assert db_files == [], f"Unexpected DB files created: {db_files}"
