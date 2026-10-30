"""L-pipe build runs: cases, dev/held-out split, report aggregates (S2.3 §5.8)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
    from helios.evaluation import trigger_calibration as tc

    def fake(_path: Any, _key: Any) -> dict[str, dict[str, Any]]:
        ids = _ids(MANIFESTS[0]) + _ids(MANIFESTS[1])
        return {
            i: {
                "inject_time": 1_790_000_000,
                "root_cause_service": "cart",
                "fault": "f",
            }
            for i in ids
        }

    monkeypatch.setattr(tc, "verify_ground_truth", fake)
    cases = lc.load_lpipe_cases(root=REPO, key=b"k")
    assert len(cases) == 558
    assert {c.corpus for c in cases} == {"otel_build_v3", "rcaeval_build"}


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
