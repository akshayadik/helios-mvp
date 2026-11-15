"""S5.5 per-call token equality (design s5_5_determinism_design.md P-c, P-d)."""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any

from bin import determinism_report as dr
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _evidence(**raw: str | None) -> dict[str, Any]:
    return {
        "prompt_shas": {w: f"sha-{w}" for w in dr.WORKERS},
        "workers": {w: {"raw": raw.get(w), "wall_ms": 7} for w in dr.WORKERS},
    }


BASE = _evidence(log=None, metric="m-out", trace="t-out")


def test_identical_calls_are_equal_and_silent_workers_are_skipped() -> None:
    again = copy.deepcopy(BASE)
    again["workers"]["metric"]["wall_ms"] = 99  # operational, never compared
    assert dr.compare_calls(BASE, again) == {"equal": ["metric", "trace"]}


def test_planted_differences_are_classified() -> None:
    again = copy.deepcopy(BASE)
    again["workers"]["metric"]["raw"] = "m-other"
    again["prompt_shas"]["trace"] = "sha-changed"
    again["workers"]["log"]["raw"] = "l-out"
    assert dr.compare_calls(BASE, again) == {
        "unequal": ["metric"],
        "prompt_differs": ["trace"],
        "one_sided": ["log"],
    }
    assert dr.compare_calls(None, None) == {}


def _rows() -> list[dict[str, Any]]:
    return [
        {
            "run_id": "a1",
            "rerun_id": "b1",
            "system": "HELIOS-Full",
            "nondeterministic": False,
            "differs": [],
            "not_comparable": [],
        },
        {
            "run_id": "a2",
            "rerun_id": "b2",
            "system": "HELIOS-Full",
            "nondeterministic": True,
            "differs": ["lpipe"],
            "not_comparable": ["narrative"],  # a fallback slot on one side
        },
        {
            "run_id": "a3",
            "rerun_id": "b3",
            "system": "BASELINE-BARO",
            "nondeterministic": False,
            "differs": [],
            "not_comparable": [],
        },
    ]


def _stores() -> tuple[dict[str, Any], dict[str, Any]]:
    changed = copy.deepcopy(BASE)
    changed["workers"]["trace"]["raw"] = "t-other"
    first = {"a1": BASE, "a2": BASE}
    again = {"b1": copy.deepcopy(BASE), "b2": changed}
    return first, again


def test_report_counts_calls_and_runs_per_system() -> None:
    first, again = _stores()
    report = dr.determinism_report(_rows(), first.get, again.get)
    assert report["calls"]["all"] == {
        "calls_compared": 4,
        "equal": 3,
        "unequal": 1,
        "prompt_differs": 0,
        "one_sided": 0,
        "token_equality_rate": 0.75,
    }
    assert "BASELINE-BARO" not in report["calls"]  # no model calls
    assert report["runs"]["BASELINE-BARO"] == {"pairs": 1, "nondeterministic": 0}
    assert report["runs"]["HELIOS-Full"] == {
        "pairs": 2,
        "nondeterministic": 1,
        "differs_lpipe": 1,
        "not_comparable_narrative": 1,
    }
    assert report["calls_not_equal"] == [
        {
            "run_id": "a2",
            "system": "HELIOS-Full",
            "equal": ["metric"],
            "unequal": ["trace"],
        }
    ]


def test_no_compared_calls_gives_no_rate() -> None:
    assert dr._rate({})["token_equality_rate"] is None


def test_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from helios.store import result_store

    first, again = _stores()

    class FakeStore:
        def __init__(self, path: Path) -> None:
            self.data = first if path.name == "results.duckdb" else again

        def fetch_evidence(self, run_id: str, pipeline: str) -> Any:
            assert pipeline == "lpipe"
            return self.data.get(run_id)

        def close(self) -> None:
            pass

    monkeypatch.setattr(result_store, "ResultStore", FakeStore)
    camp = tmp_path / "camp"
    camp.mkdir()
    (camp / "determinism.json").write_text(json.dumps(_rows()))
    out = tmp_path / "out.json"
    assert dr.main(["--dir", str(camp), "--out", str(out)]) == 0
    report = json.loads(out.read_text())
    assert report["campaign"] == "camp"
    assert report["calls"]["all"]["unequal"] == 1
