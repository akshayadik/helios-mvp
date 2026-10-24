"""Tests for verify_osf_freeze helper functions."""

from __future__ import annotations

import hashlib
import json
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
        _generate_manifest_sig(tmp, tmp / "no_prereg.md", tmp / "no_contract.md")
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


def test_variants_py_matches_frozen_vcl_sha() -> None:
    """variants.py must stay byte-identical to the blob recorded at OSF freeze.

    The freeze fingerprints the whole file, so even a non-semantic edit fails
    `verify_osf_freeze.py --verify`. Put new variant helpers in catalog.py.
    """
    import json

    frozen = json.loads(Path("research/osf/variant_hashes.json").read_text())
    content = Path("helios/vcl/variants.py").read_bytes()
    # git blob id (not a security hash): sha1 over "blob <len>\0<content>"
    blob_sha = hashlib.sha1(
        b"blob " + str(len(content)).encode() + b"\0" + content
    ).hexdigest()
    assert blob_sha == frozen["vcl_freeze_sha"]


def test_manifest_sig_covers_prereg_text_but_not_sha_marker_values(
    tmp_path: Path,
) -> None:
    """Audit step E: editing the pre-registration changes manifest_sig."""
    sys.path.insert(0, str(Path("bin")))
    from verify_osf_freeze import _manifest_digest

    (tmp_path / "a.json").write_bytes(b'{"x":1}\n')
    prereg = tmp_path / "preregistration.md"
    marker = "| `a.json` | <!-- SHA:a.json -->"
    prereg.write_text(f"# Plan\nH1 one-sided.\n{marker}`{'a' * 64}` |\n")
    base = _manifest_digest(tmp_path, prereg)

    prereg.write_text(f"# Plan\nH1 one-sided.\n{marker}`{'b' * 64}` |\n")
    assert _manifest_digest(tmp_path, prereg) == base

    prereg.write_text(f"# Plan\nH1 two-sided.\n{marker}`{'b' * 64}` |\n")
    assert _manifest_digest(tmp_path, prereg) != base


def test_corpus_manifest_hashes_every_file_of_a_case(tmp_path: Path) -> None:
    sys.path.insert(0, str(Path("bin")))
    from verify_osf_freeze import _instance_file_hashes

    (tmp_path / "manifest.json").write_bytes(b"{}")
    (tmp_path / "p1_metrics.parquet").write_bytes(b"pq")
    (tmp_path / ".DS_Store").write_bytes(b"junk")
    hashes = _instance_file_hashes(tmp_path)
    assert hashes == {
        "manifest.json": hashlib.sha256(b"{}").hexdigest(),
        "p1_metrics.parquet": hashlib.sha256(b"pq").hexdigest(),
    }


def test_committed_corpus_manifest_lists_case_file_hashes() -> None:
    manifest = json.loads(Path("research/osf/corpus_manifest.json").read_bytes())
    incidents = manifest["exploratory"]["incidents"]
    assert manifest["schema_version"] == "v2"
    for inc in incidents:
        assert {"manifest.json", "content_seal.json"} <= inc["files"].keys()
        assert len(inc["instance_sha256"]) == 64


def test_manifest_sig_covers_the_metric_contract(tmp_path: Path) -> None:
    sys.path.insert(0, str(Path("bin")))
    from verify_osf_freeze import _manifest_digest

    (tmp_path / "a.json").write_bytes(b'{"x":1}\n')
    contract = tmp_path / "metric_contract.md"
    contract.write_text("HR@3 on the fused list\n")
    base = _manifest_digest(tmp_path, tmp_path / "none.md", contract)
    contract.write_text("HR@3 on the D-pipe list\n")
    assert _manifest_digest(tmp_path, tmp_path / "none.md", contract) != base


def test_preregistration_tables_match_the_frozen_plan_and_variants() -> None:
    """The pre-registration text cannot drift from analysis_plan.py or variants.py."""
    from helios.research.analysis_plan import (
        FAMILY_A_HYPOTHESES,
        FAMILY_B_HYPOTHESES,
        FAMILY_E_HYPOTHESES,
    )
    from helios.vcl import CONFIRMATORY_VARIANTS, EXPLORATORY_VARIANTS

    text = Path("research/osf/preregistration.md").read_text(encoding="utf-8")
    for h in (*FAMILY_A_HYPOTHESES, *FAMILY_B_HYPOTHESES):
        row = (
            f"| {h['id']} | {h['rank']} | {h['alpha']} | {h['comparison']} "
            f"| {h['primary_metric']} | {h['test']} |"
        )
        assert row in text, h["id"]
    for h in FAMILY_E_HYPOTHESES:
        assert f"| {h['id']} | {h['comparison']} | {h['primary_metric']} |" in text
    for name, manifest in {**CONFIRMATORY_VARIANTS, **EXPLORATORY_VARIANTS}.items():
        assert f"| {name} |" in text
        assert f"`{manifest.compute_variant_config_hash()[:16]}`" in text, name
