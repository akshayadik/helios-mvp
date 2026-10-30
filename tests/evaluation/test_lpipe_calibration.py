"""L-pipe build runs: cases, dev/held-out split, report aggregates (S2.3 §5.8)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from helios.evaluation import lpipe_calibration as lc
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    import pytest

REPO = Path(__file__).resolve().parents[2]
MANIFESTS = ("data/otel/build_v3_manifest.json", "data/rcaeval/build_manifest.json")


def _ids(path: str) -> list[str]:
    return list(json.loads((REPO / path).read_text(encoding="utf-8"))["case_order"])


def test_split_alternates_in_hash_order() -> None:
    for path in MANIFESTS:
        ids = _ids(path)
        split = lc.split_cases(ids)
        assert split == lc.split_cases(list(reversed(ids)))
        dev = sum(v == "dev" for v in split.values())
        assert dev == (len(ids) + 1) // 2, path


def test_cases_count_558(monkeypatch: pytest.MonkeyPatch) -> None:
    # RCAEval case files are gitignored; stub the per-case loader and count the
    # IDs of the tracked corpus manifests.
    from helios.evaluation.trigger_calibration import CalibrationCase

    def fake(corpus: str, *, root: Path, key: bytes) -> list[CalibrationCase]:
        path = MANIFESTS[0] if corpus == "otel_build_v3" else MANIFESTS[1]
        window = MagicMock()
        return [CalibrationCase(i, window, 0, "cart", None) for i in _ids(path)]

    monkeypatch.setattr(lc, "load_cases", fake)
    cases = lc.load_lpipe_cases(root=REPO, key=b"k")
    assert len(cases) == 558
    assert [c.corpus for c in cases].count("otel_build_v3") == 63


def test_summary_counts() -> None:
    rows = [
        lc.CaseOutcome(
            "otel_build_v3",
            "dev",
            "f1",
            1,
            {"metric": 1, "log": None, "trace": 0},
            2,
            {"log": "no_digest"},
            9,
            False,
        ),
        lc.CaseOutcome(
            "otel_build_v3",
            "dev",
            "f2",
            0,
            {"metric": None, "log": None, "trace": None},
            0,
            {"metric": "schema", "log": "schema", "trace": "timeout"},
            12,
            True,
        ),
    ]
    out = lc.summarise(rows)
    group = out["otel_build_v3"]["dev"]
    assert group["cases"] == 2
    assert group["lpipe_hr3_hits"] == 1
    assert group["worker_hr3_hits"] == {"log": 0, "metric": 1, "trace": 0}
    assert group["worker_valid"] == {"log": 0, "metric": 1, "trace": 1}
    assert group["k"] == {"0": 1, "2": 1}
    assert group["drops"] == {"no_digest": 1, "schema": 2, "timeout": 1}
    assert group["mean_seconds"] == 10.5
    assert group["cache_hits"] == 1
    assert group["faults"] == {"f1": 1, "f2": 1}
