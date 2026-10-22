"""Tamper tests for the capture content seal (helios.telemetry.seal).

VCLFlag-compliant: the seal is always-on C1 data-integrity infrastructure.
window_hash does not cover Parquet bytes; each test names the change the seal
must catch, or the legitimate state it must accept.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import io
import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from bin import verify_captures
from helios.integrity_gate import AppendOnlyLedger
from helios.orchestrator.runner import RunOrchestrator
from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.telemetry.reader import CaptureReader
from helios.telemetry.seal import SEAL_FILENAME, check_seal, write_seal
from helios.vcl import VCLFlag, get_variant, set_current_manifest  # noqa: F401

_KEY = b"test-secret-at-least-32-chars-long!!"
_OTHER_KEY = b"another-secret-at-least-32-chars-long"


def _capture(root: Path, incident_id: str, *, seal: bool = True) -> Path:
    """Write a capture with three real Parquet streams under root/incident_id."""
    inc = root / incident_id
    inc.mkdir(parents=True)
    paths = {}
    for stream in ("p1_metrics", "p2_traces", "p3_logs"):
        path = inc / f"{stream}.parquet"
        pq.write_table(pa.table({"v": [1, 2, 3], "s": ["a", "b", "c"]}), path)
        paths[f"{stream}_path"] = str(path)
    window = TelemetryWindow(
        incident_id=incident_id,
        variant_config_hash="a" * 64,
        window_start_iso=dt.datetime(2026, 1, 1, tzinfo=dt.UTC).isoformat(),
        window_end_iso=dt.datetime(2026, 1, 1, 0, 5, tzinfo=dt.UTC).isoformat(),
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        **paths,
    )
    manifest = {**window.model_dump(), "window_hash": window.compute_window_hash()}
    manifest["snapshot_hash"] = "b" * 64
    (inc / "manifest.json").write_text(json.dumps(manifest, default=str))
    if seal:
        write_seal(inc, window, _KEY)
    return inc


def _window(inc: Path) -> TelemetryWindow:
    raw = json.loads((inc / "manifest.json").read_text())
    raw.pop("window_hash")
    raw.pop("snapshot_hash", None)
    return TelemetryWindow(**raw)


# ── Legitimate states ──────────────────────────────────────────────────────────


def test_sealed_capture_is_intact(tmp_path: Path) -> None:
    _capture(tmp_path, "inc-001")
    result = CaptureReader(tmp_path, seal_key=_KEY).read("inc-001")
    assert result.hash_matches
    assert result.seal_checked
    assert result.seal_error is None
    assert result.intact


def test_reader_without_key_never_reports_intact(tmp_path: Path) -> None:
    _capture(tmp_path, "inc-001")
    result = CaptureReader(tmp_path).read("inc-001")
    assert result.hash_matches
    assert not result.seal_checked
    assert not result.intact


# ── Content changes that window_hash cannot see ────────────────────────────────


def test_changed_parquet_value_is_detected(tmp_path: Path) -> None:
    inc = _capture(tmp_path, "inc-001")
    pq.write_table(
        pa.table({"v": [9, 2, 3], "s": ["a", "b", "c"]}), inc / "p1_metrics.parquet"
    )
    result = CaptureReader(tmp_path, seal_key=_KEY).read("inc-001")
    assert result.hash_matches  # the original blind spot
    assert result.seal_error == "content changed since sealing: p1_metrics"
    assert not result.intact


def test_changed_snapshot_hash_annotation_is_detected(tmp_path: Path) -> None:
    """snapshot_hash sits outside window_hash; the manifest bytes are sealed."""
    inc = _capture(tmp_path, "inc-001")
    manifest = json.loads((inc / "manifest.json").read_text())
    manifest["snapshot_hash"] = "c" * 64
    (inc / "manifest.json").write_text(json.dumps(manifest, default=str))
    err = check_seal(inc, _window(inc), _KEY)
    assert err == "manifest.json bytes changed since sealing"


def test_deleted_stream_file_is_detected(tmp_path: Path) -> None:
    inc = _capture(tmp_path, "inc-001")
    (inc / "p3_logs.parquet").unlink()
    err = check_seal(inc, _window(inc), _KEY)
    assert err is not None
    assert "p3_logs declared" in err


# ── Attacks on the seal itself ─────────────────────────────────────────────────


def test_recomputed_hash_without_key_is_detected(tmp_path: Path) -> None:
    """The reason the seal is signed: plain hashes can be recomputed."""
    inc = _capture(tmp_path, "inc-001")
    pq.write_table(
        pa.table({"v": [9, 2, 3], "s": ["a", "b", "c"]}), inc / "p1_metrics.parquet"
    )
    seal = json.loads((inc / SEAL_FILENAME).read_text())
    seal["pillars"]["p1_metrics"] = hashlib.sha256(
        (inc / "p1_metrics.parquet").read_bytes()
    ).hexdigest()
    (inc / SEAL_FILENAME).write_text(json.dumps(seal))
    assert (
        check_seal(inc, _window(inc), _KEY)
        == f"{SEAL_FILENAME} signature does not verify"
    )


def test_seal_signed_with_wrong_key_is_detected(tmp_path: Path) -> None:
    inc = _capture(tmp_path, "inc-001", seal=False)
    write_seal(inc, _window(inc), _OTHER_KEY)
    assert (
        check_seal(inc, _window(inc), _KEY)
        == f"{SEAL_FILENAME} signature does not verify"
    )


def test_seal_copied_from_another_incident_is_detected(tmp_path: Path) -> None:
    a = _capture(tmp_path, "inc-001")
    b = _capture(tmp_path, "inc-002")
    shutil.copy(a / SEAL_FILENAME, b / SEAL_FILENAME)
    err = check_seal(b, _window(b), _KEY)
    assert err is not None
    assert "seal belongs to 'inc-001'" in err


def test_whole_capture_copied_under_another_id_is_detected(tmp_path: Path) -> None:
    """Internally consistent copy; its manifest paths point at inc-001's data."""
    src = _capture(tmp_path, "inc-001")
    shutil.copytree(src, tmp_path / "inc-002")
    result = CaptureReader(tmp_path, seal_key=_KEY).read("inc-002")
    assert result.seal_error is not None
    assert "capture directory 'inc-002' holds incident 'inc-001'" in result.seal_error


def test_missing_seal_is_unverified(tmp_path: Path) -> None:
    _capture(tmp_path, "inc-001", seal=False)
    result = CaptureReader(tmp_path, seal_key=_KEY).read("inc-001")
    assert result.seal_error is not None
    assert "capture content is unverified" in result.seal_error
    assert not result.intact


def test_corrupt_seal_is_detected(tmp_path: Path) -> None:
    inc = _capture(tmp_path, "inc-001")
    (inc / SEAL_FILENAME).write_text("{not json")
    assert (
        check_seal(inc, _window(inc), _KEY)
        == f"{SEAL_FILENAME} is unreadable or unsigned"
    )


def test_seal_is_write_once(tmp_path: Path) -> None:
    inc = _capture(tmp_path, "inc-001")
    with pytest.raises(FileExistsError):
        write_seal(inc, _window(inc), _KEY)


def test_short_key_is_rejected(tmp_path: Path) -> None:
    inc = _capture(tmp_path, "inc-001", seal=False)
    with pytest.raises(ValueError, match="at least 32 bytes"):
        write_seal(inc, _window(inc), b"short")


# ── Run path: an altered capture never reaches a pipeline ──────────────────────


def test_orchestrator_skips_altered_capture(tmp_path: Path) -> None:
    captures = tmp_path / "captures"
    inc = _capture(captures, "inc-001")
    pq.write_table(
        pa.table({"v": [9, 2, 3], "s": ["a", "b", "c"]}), inc / "p1_metrics.parquet"
    )
    manifest = get_variant("HELIOS-Full")
    set_current_manifest(manifest)
    orch = RunOrchestrator(
        manifest=manifest,
        captures_dir=captures,
        db_path=tmp_path / "results.duckdb",
        registry_path=tmp_path / "registry.jsonl",
        reconciliation_path=tmp_path / "reconciliation.jsonl",
        exclusion_ledger=MagicMock(spec=AppendOnlyLedger),
        hmac_key=_KEY,
    )
    orch.run(captures)
    rows = [
        json.loads(line)
        for line in (tmp_path / "reconciliation.jsonl").read_text().splitlines()
    ]
    assert [(r["outcome"], r["gate_check"]) for r in rows] == [
        ("skipped", "capture_seal_invalid")
    ]
    assert not (tmp_path / "registry.jsonl").exists()


# ── CLI bootstrap: seals only bytes proven identical to git HEAD ───────────────


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _cli(repo: Path, monkeypatch: pytest.MonkeyPatch, *args: str) -> tuple[int, str]:
    monkeypatch.setenv("DEVIATION_HMAC_SECRET", _KEY.decode())
    out = io.StringIO()
    with contextlib.chdir(repo), contextlib.redirect_stdout(out):
        rc = verify_captures.main(
            ["--captures-dir", "caps", "--incident-id", "inc-001", *args]
        )
    return rc, out.getvalue()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@h.local")
    _git(tmp_path, "config", "user.name", "Tester")
    with contextlib.chdir(tmp_path):
        _capture(Path("caps"), "inc-001", seal=False)  # repo-relative paths
    return tmp_path


def test_cli_refuses_to_seal_uncommitted_capture(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rc, out = _cli(repo, monkeypatch, "--init-seals")
    assert rc == 1
    assert "REFUSED" in out
    assert not (repo / "caps/inc-001" / SEAL_FILENAME).exists()


def test_cli_refuses_to_seal_capture_modified_after_commit(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "capture")
    pq.write_table(pa.table({"v": [9]}), repo / "caps/inc-001/p2_traces.parquet")
    rc, out = _cli(repo, monkeypatch, "--init-seals")
    assert rc == 1
    assert "not identical to git HEAD" in out


def test_cli_seals_committed_capture_then_verifies_and_detects(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "capture")
    assert _cli(repo, monkeypatch)[0] == 1  # unsealed fails
    rc, out = _cli(repo, monkeypatch, "--init-seals")
    assert rc == 0
    assert "SEALED" in out
    rc, out = _cli(repo, monkeypatch)
    assert rc == 0
    assert "[OK      ] inc-001" in out
    pq.write_table(pa.table({"v": [9]}), repo / "caps/inc-001/p1_metrics.parquet")
    rc, out = _cli(repo, monkeypatch)
    assert rc == 1
    assert "ALTERED" in out
