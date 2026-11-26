"""Phase A replication-bundle manifest (scripts/phase_a_bundle.py)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from phase_a_bundle import REPO_ROOT, bca_seeds, build_manifest, main, readme

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path


def _campaign(tmp_path: Path, digest: str) -> Path:
    d = tmp_path / f"camp_{digest}"
    d.mkdir()
    (d / "schedule.json").write_text(json.dumps({"digest": "s" * 12}), encoding="utf-8")
    (d / "campaign.json").write_text(
        json.dumps({"build_freeze_digest": digest, "gt_corpus": "pool"}),
        encoding="utf-8",
    )
    (d / "results.duckdb").write_bytes(b"store")
    return d


def test_bca_seeds_are_keyed_by_the_nearest_id() -> None:
    analysis = {
        "family_a": {
            "hypotheses": [
                {"id": "A-H1", "by_measure": {"hr_at_3": {"bca_seed": 11}}},
                {"id": "A-H2", "by_measure": {"hr_at_3": {"bca_seed": None}}},
            ]
        },
        "family_e": [{"id": "E-H2", "bca_seed": 12}],
    }
    assert bca_seeds(analysis) == {"A-H1": 11, "E-H2": 12}


def test_manifest_records_build_ledger_deposit_and_inputs(tmp_path: Path) -> None:
    record = json.loads((REPO_ROOT / "data/frozen/build_freeze.json").read_text())
    good = _campaign(tmp_path, str(record["frozen_paths"]["digest"])[:12])
    other = _campaign(tmp_path, "deadbeef0000")
    art = tmp_path / "analysis.json"
    art.write_text(
        json.dumps({"version": "analysis-v2", "label": "exploratory", "bca_seed": 7}),
        encoding="utf-8",
    )
    m = build_manifest(REPO_ROOT, [good, other], [art])
    # The record's own tag: it lags BUILD_FREEZE_TAG between a constant bump
    # and the new record (two PRs), so the manifest reports what the record says.
    assert m["build"]["record_tag"] == record["tag"]
    assert str(record["tag"]).startswith("build-freeze")
    assert m["build"]["frozen_paths_digest"] == record["frozen_paths"]["digest"]
    assert m["build"]["frozen_paths_count"] == record["frozen_paths"]["count"]
    assert m["deviation_log"]["entries"] >= 1
    assert "research/osf/analysis_plan.json" in m["deposit"]
    assert m["campaigns_from_another_build"] == [str(other)]
    assert set(m["campaigns"][0]["stores"]) == {"results.duckdb"}
    assert m["artefacts"][str(art)]["label"] == "exploratory"
    text = readme(m)
    assert "**Warning:**" in text and str(record["tag"]) in text


def test_main_writes_manifest_and_readme(tmp_path: Path) -> None:
    out, md = tmp_path / "bundle.json", tmp_path / "README.md"
    assert main(["--out", str(out), "--readme", str(md)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["version"] == "bundle-v1"
    assert md.read_text(encoding="utf-8").startswith("# Replication bundle")
