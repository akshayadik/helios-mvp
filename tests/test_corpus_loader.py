"""Tests for CorpusLoader — directory and JSON manifest corpus loading."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from helios.orchestrator.corpus import CorpusLoader

if TYPE_CHECKING:
    from pathlib import Path


class TestCorpusLoaderDirectory:
    def test_discovers_incident_subdirs(self, tmp_path: Path) -> None:
        for iid in ["inc-001", "inc-002"]:
            d = tmp_path / iid
            d.mkdir()
            (d / "manifest.json").write_text("{}")
        (tmp_path / "other").mkdir()  # no manifest.json — should be skipped

        loader = CorpusLoader(tmp_path)
        ids = list(loader.incident_ids())
        assert ids == ["inc-001", "inc-002"]

    def test_sorted_order(self, tmp_path: Path) -> None:
        for iid in ["inc-003", "inc-001", "inc-002"]:
            d = tmp_path / iid
            d.mkdir()
            (d / "manifest.json").write_text("{}")
        loader = CorpusLoader(tmp_path)
        assert list(loader.incident_ids()) == ["inc-001", "inc-002", "inc-003"]

    def test_empty_directory_yields_nothing(self, tmp_path: Path) -> None:
        loader = CorpusLoader(tmp_path)
        assert list(loader.incident_ids()) == []


class TestCorpusLoaderJSON:
    def test_loads_incidents_list(self, tmp_path: Path) -> None:
        manifest = tmp_path / "corpus.json"
        manifest.write_text(json.dumps({"incidents": ["inc-a", "inc-b"]}))
        loader = CorpusLoader(manifest)
        assert list(loader.incident_ids()) == ["inc-a", "inc-b"]

    def test_missing_incidents_key_raises(self, tmp_path: Path) -> None:
        manifest = tmp_path / "corpus.json"
        manifest.write_text(json.dumps({"data": []}))
        loader = CorpusLoader(manifest)
        with pytest.raises(ValueError, match="'incidents' key"):
            list(loader.incident_ids())


class TestCorpusLoaderErrors:
    def test_unsupported_extension_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "corpus.yaml"
        f.write_text("incidents: []")
        loader = CorpusLoader(f)
        with pytest.raises(ValueError, match="directory or a .json file"):
            list(loader.incident_ids())
