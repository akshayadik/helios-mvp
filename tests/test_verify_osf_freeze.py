"""Tests for verify_osf_freeze helper functions."""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.utils import canonical_json


def _write_json(path: Path, data: dict) -> None:
    path.write_bytes((canonical_json(data) + "\n").encode("utf-8"))


def test_fault_class_parses_incident_id() -> None:
    sys.path.insert(0, str(Path("bin")))
    from verify_osf_freeze import _fault_class

    assert _fault_class("s0-adhc-001") == "adhc"
    assert _fault_class("s0-cpuload-005") == "cpuload"
    assert _fault_class("nohyphen") == "unknown"


def test_verify_artefact_injects_timestamp_and_matches() -> None:
    sys.path.insert(0, str(Path("bin")))
    from verify_osf_freeze import _verify_artefact

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "seeds.json"
        data = {
            "schema_version": "v1",
            "generated_at_iso": "2026-05-18T12:00:00+00:00",
            "seeds": [],
        }
        _write_json(path, data)
        # Different timestamp — verify must inject on-disk ts before comparing
        regen = {
            "schema_version": "v1",
            "generated_at_iso": "2099-01-01T00:00:00+00:00",
            "seeds": [],
        }
        assert _verify_artefact(path, regen) is True


def test_verify_artefact_detects_content_mismatch() -> None:
    sys.path.insert(0, str(Path("bin")))
    from verify_osf_freeze import _verify_artefact

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "seeds.json"
        data = {
            "schema_version": "v1",
            "generated_at_iso": "2026-05-18T12:00:00+00:00",
            "seeds": [{"x": 1}],
        }
        _write_json(path, data)
        regen = {
            "schema_version": "v1",
            "generated_at_iso": "any",
            "seeds": [{"x": 2}],
        }
        assert _verify_artefact(path, regen) is False


def test_generate_manifest_sig_excludes_itself() -> None:
    sys.path.insert(0, str(Path("bin")))
    from verify_osf_freeze import _generate_manifest_sig

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        a = tmp / "aaa.json"
        b = tmp / "bbb.json"
        a.write_bytes(b'{"x":1}\n')
        b.write_bytes(b'{"y":2}\n')
        _generate_manifest_sig(tmp)
        sig_path = tmp / "manifest_sig.txt"
        assert sig_path.exists()
        # manifest_sig.txt itself is excluded — only .json files concatenated
        expected = hashlib.sha256(b'{"x":1}\n' + b'{"y":2}\n').hexdigest()
        assert sig_path.read_text().strip() == expected


def test_preflight_fails_when_expected_sha_is_none(tmp_path: Path) -> None:
    sys.path.insert(0, str(Path("bin")))
    from verify_osf_freeze import _preflight_generate

    captures = tmp_path / "captures"
    captures.mkdir()
    params = tmp_path / "calibrated_params.json"
    params.write_bytes(
        b'{"gpipe_hr_at_3_held_out":0.6,"dpipe_hr_at_3_held_out":0.55,'
        b'"gate_passed":true,"n_incidents_triggered":8}'
    )

    with (
        patch("verify_osf_freeze.EXPECTED_PROMPT_SHA", None),
        patch("verify_osf_freeze.PROMPT_PATH", tmp_path / "no_prompt.txt"),
        patch("verify_osf_freeze._REGISTRY_PATH", tmp_path / "no_reg.md"),
        pytest.raises(SystemExit) as exc_info,
    ):
        _preflight_generate(captures, params)
    assert exc_info.value.code != 0


def test_preflight_fails_when_gpipe_fields_missing(tmp_path: Path) -> None:
    sys.path.insert(0, str(Path("bin")))
    from verify_osf_freeze import _preflight_generate

    captures = tmp_path / "captures"
    captures.mkdir()
    params = tmp_path / "calibrated_params.json"
    # Missing the G-pipe LOO-CV fields — only has D-pipe fields
    params.write_bytes(b'{"w_error":0.3,"rho_threshold":0.2}')

    with (
        patch("verify_osf_freeze.EXPECTED_PROMPT_SHA", "a" * 64),
        patch("verify_osf_freeze.PROMPT_PATH", tmp_path / "no_prompt.txt"),
        patch("verify_osf_freeze._REGISTRY_PATH", tmp_path / "no_reg.md"),
        pytest.raises(SystemExit),
    ):
        _preflight_generate(captures, params)


def test_vcl_freeze_sha_returns_nonempty_string() -> None:
    sys.path.insert(0, str(Path("bin")))
    from verify_osf_freeze import _vcl_freeze_sha

    result = _vcl_freeze_sha()
    assert isinstance(result, str)
    assert len(result) > 0
