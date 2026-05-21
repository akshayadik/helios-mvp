"""Integration tests for fuse_verdicts.py."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import TYPE_CHECKING

import duckdb

from helios.vcl.config import VCLManifest  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path


def _create_minimal_result_db(db_path: Path, variant: str) -> None:
    """Create a minimal DuckDB result_row table with 3 pipeline rows for 1 incident."""
    conn = duckdb.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE result_row (
            incident_id VARCHAR,
            variant VARCHAR,
            pipeline VARCHAR,
            ranked_candidates VARCHAR,
            narrative VARCHAR,
            hr_at_3 DOUBLE
        )
    """
    )
    for pipe in ["d_pipe", "g_pipe", "l_pipe"]:
        conn.execute(
            "INSERT INTO result_row VALUES (?, ?, ?, ?, ?, ?)",
            ["otel-001", variant, pipe, json.dumps(["svc-a", "svc-b"]), "normal", 1],
        )
    conn.close()


def test_fuse_smoke_flag_exits_zero(tmp_path: Path) -> None:
    db_path = tmp_path / "results.duckdb"
    _create_minimal_result_db(db_path, "HELIOS-Full")
    result = subprocess.run(
        [
            sys.executable,
            "scripts/fuse_verdicts.py",
            "--db-path",
            str(db_path),
            "--smoke",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_fuse_produces_consensus_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "results.duckdb"
    _create_minimal_result_db(db_path, "HELIOS-Full")
    result = subprocess.run(
        [sys.executable, "scripts/fuse_verdicts.py", "--db-path", str(db_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    conn = duckdb.connect(str(db_path), read_only=True)
    row = conn.execute("SELECT COUNT(*) FROM consensus_verdict").fetchone()
    count = row[0] if row is not None else 0
    conn.close()
    assert count >= 1


def test_fuse_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "results.duckdb"
    _create_minimal_result_db(db_path, "HELIOS-Full")
    for _ in range(2):
        subprocess.run(
            [sys.executable, "scripts/fuse_verdicts.py", "--db-path", str(db_path)],
            capture_output=True,
            text=True,
        )
    conn = duckdb.connect(str(db_path), read_only=True)
    row = conn.execute("SELECT COUNT(*) FROM consensus_verdict").fetchone()
    count = row[0] if row is not None else 0
    conn.close()
    # Two runs must not duplicate rows (INSERT OR IGNORE semantics)
    assert count == 1
