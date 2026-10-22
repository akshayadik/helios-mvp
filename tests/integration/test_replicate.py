"""Integration test for replicate.py — verifies the --help flag works."""

from __future__ import annotations

import subprocess
import sys

from helios.vcl.config import VCLManifest  # noqa: F401 — flag-guard compliance


def test_replicate_help_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/replicate.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--db-path" in result.stdout
