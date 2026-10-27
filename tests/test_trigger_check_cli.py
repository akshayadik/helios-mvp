"""bin/trigger_check.py (S2.1): rerun equality across separate processes."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

REPO = Path(__file__).resolve().parents[1]
T0 = 1_790_000_000


def _case(root: Path) -> Path:
    case = root / "opaque-case"
    case.mkdir()
    rows = [
        (T0 + b * 30 + 10 * k, 80 if 12 <= b < 16 else 40 + b % 3)
        for b in range(30)
        for k in range(3)
    ]
    pq.write_table(
        pa.table(
            {
                "timestamp": [float(t) for t, _ in rows],
                "metric_name": ["latency"] * len(rows),
                "value": [float(v) for _, v in rows],
                "labels": [json.dumps({"service_name": "cart"})] * len(rows),
            }
        ),
        case / "p1_metrics.parquet",
    )
    window = TelemetryWindow(
        incident_id="opaque-case",
        variant_config_hash="h" * 64,
        window_start_iso=datetime.fromtimestamp(T0, UTC).isoformat(),
        window_end_iso=datetime.fromtimestamp(T0 + 30 * 30, UTC).isoformat(),
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        p1_metrics_path=str(case / "p1_metrics.parquet"),
    )
    manifest = window.model_dump(mode="json")
    manifest["window_hash"] = window.compute_window_hash()
    (case / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return case


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "bin/trigger_check.py", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )


def test_two_processes_give_identical_bytes(tmp_path: Path) -> None:
    case = _case(tmp_path)
    first = _run("--window", str(case), "--json")
    second = _run("--window", str(case), "--json")
    assert first.returncode == 0, first.stderr
    assert first.stdout
    assert first.stdout == second.stdout
    record = json.loads(first.stdout.splitlines()[0])
    assert record["suspects"] == ["cart"]
    assert record["source"] == "threshold"


def test_cli_refuses_pool() -> None:
    result = _run("--corpus", "pool")
    assert result.returncode != 0
    assert "pool" in result.stderr


def test_counts_mode_prints_only_counts_and_a_digest(tmp_path: Path) -> None:
    case = _case(tmp_path)
    out = _run("--window", str(case)).stdout
    assert "opaque-case" not in out
    assert "digest" in out
