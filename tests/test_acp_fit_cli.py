"""bin/acp_fit.py: case extraction, run-once refusal, freeze (S3.2 P-d)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from bin import acp_fit
from helios.acp.features import ACP_FEATURE_NAMES
from helios.acp.params import ACP_CLASSES, ACPParams, acp_params_hash, load_acp_params
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path

D = len(ACP_FEATURE_NAMES)


def _entry(status: str = "unfit") -> dict[str, Any]:
    return {
        "incident_id": "inc-1",
        "steps": [
            {"id": "T"},
            {
                "id": "R",
                "acp": {"status": status, "features": [1] + [0] * (D - 1)},
            },
        ],
    }


def _params() -> ACPParams:
    return ACPParams(
        feature_names=ACP_FEATURE_NAMES,
        classes=ACP_CLASSES,
        mean=(0,) * D,
        scale=(1,) * D,
        weights=((0,) * D,) * len(ACP_CLASSES),
        lam=1,
        n_cases=2,
    )


@pytest.fixture
def paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    report, frozen = tmp_path / "acp_fit.json", tmp_path / "acp_params.json"
    monkeypatch.setattr(acp_fit, "REPORT", report)
    monkeypatch.setattr(acp_fit, "ACP_PARAMS_PATH", frozen)
    return report, frozen


def test_case_from_entry_maps_the_fault() -> None:
    case = acp_fit.case_from_entry(_entry(), "rcaeval_build", {"fault": "socket"})
    assert case.label == "network"
    assert case.corpus == "rcaeval_build"
    assert len(case.x) == D


def test_case_from_entry_refuses_acp_off() -> None:
    with pytest.raises(ValueError, match="ACP features"):
        acp_fit.case_from_entry(_entry("off"), "c", {"fault": "cpu"})


def test_case_from_entry_refuses_unknown_fault() -> None:
    with pytest.raises(ValueError, match="remediation family"):
        acp_fit.case_from_entry(_entry(), "c", {"fault": "meteor"})


def test_fit_runs_once(paths: tuple[Path, Path]) -> None:
    report, _ = paths
    report.write_text("{}", encoding="utf-8")
    assert acp_fit._fit() == 2


def test_fit_refuses_when_frozen_exists(paths: tuple[Path, Path]) -> None:
    _, frozen = paths
    frozen.write_text("{}", encoding="utf-8")
    assert acp_fit._fit() == 2


def test_freeze_needs_a_report(paths: tuple[Path, Path]) -> None:
    assert acp_fit._freeze() == 2


def test_freeze_checks_the_hash_and_writes_once(paths: tuple[Path, Path]) -> None:
    report, frozen = paths
    params = _params()
    body = {"fit": params.as_dict(), "fit_hash": "bad"}
    report.write_text(json.dumps(body), encoding="utf-8")
    assert acp_fit._freeze() == 3
    body["fit_hash"] = acp_params_hash(params)
    report.write_text(json.dumps(body), encoding="utf-8")
    assert acp_fit._freeze() == 0
    assert acp_params_hash(load_acp_params(frozen)) == acp_params_hash(params)
    assert acp_fit._freeze() == 2  # never replaced


def test_main_needs_the_repository_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert acp_fit.main([]) == 2


def test_counting_ledger() -> None:
    ledger = acp_fit._CountingLedger()
    ledger.append({"a": "b"})
    assert ledger.count == 1
