"""bin/router_build_run.py: pool refused, R-d stop, aggregates only, freeze (S3.1)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from bin import router_build_run as tool
from helios.consensus.mahc import Vote
from helios.consensus.router_features import FEATURE_NAMES
from helios.consensus.router_params import load_router_params, router_params_hash
from helios.evaluation.router_calibration import RouterCase
from helios.telemetry.signal_type import SignalType
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

N = len(FEATURE_NAMES)
_IND = FEATURE_NAMES.index("d_margin")


def _case(i: int, corpus: str, *, d_right: bool, ind: int) -> RouterCase:
    root = f"svc-{i % 5}"
    d = (root, "svc-x") if d_right else ("svc-x", "svc-y", "svc-z", "svc-w")
    x: list[float] = [0] * N
    x[0], x[_IND] = 1, ind
    return RouterCase(
        incident_id=f"incident{i:03d}",
        corpus=corpus,
        group=f"g{i % 3}",
        signal=SignalType.LATENCY,
        x_cheap=tuple(x),
        x_dg=None,
        graph=False,
        votes={"dpipe": Vote("dpipe", d, 0.3), "lpipe": Vote("lpipe", (root,), 0.3)},
        latency_ms={"dpipe": 200, "lpipe": 12_000},
        root=root,
    )


def _cases(*, stoppable: bool) -> list[RouterCase]:
    out = []
    for k, corpus in enumerate(("otel_build_v3", "rcaeval_build")):
        for i in range(30):
            right = stoppable and i % 2 == 0
            out.append(_case(k * 30 + i, corpus, d_right=right, ind=1 - i % 2))
    return out


def _patch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, cases: list[RouterCase]
) -> Path:
    def collect(**_kw: Any) -> tuple[list[RouterCase], dict[str, int]]:
        return cases, {"excluded": 0, "unfeatured": 0}

    params_path = tmp_path / "router_params.json"
    monkeypatch.setattr(tool, "collect_cases", collect)
    monkeypatch.setattr(tool, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(tool, "ROUTER_PARAMS_PATH", params_path)
    monkeypatch.setattr(tool, "load_key", lambda: b"k")
    monkeypatch.setattr(tool, "ALPHA", 0.05)
    return params_path


def test_tool_refuses_the_pool() -> None:
    assert tool.main(["--corpus", "pool"]) == 2


def test_fit_writes_an_aggregate_report_with_a_refit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch, tmp_path, _cases(stoppable=True))
    assert tool.main(["--run", "7"]) == 0
    text = (tmp_path / "router_run7.json").read_text()
    assert "incident0" not in text
    assert "svc-" not in text
    report = json.loads(text)
    assert report["variant"] == "HELIOS-noRouter"
    assert report["tau_acc"] is not None
    assert report["refit"]["provisional"] is False
    assert report["refit"]["tau_acc"] == report["tau_acc"] >= report["tau_held_out"]
    assert set(report["refit_in_sample"]) == {"otel_build_v3", "rcaeval_build"}


def test_unstoppable_build_data_stops_for_the_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch, tmp_path, _cases(stoppable=False))
    monkeypatch.setattr(tool, "ALPHA", 0)
    assert tool.main(["--run", "2"]) == 3
    report = json.loads((tmp_path / "router_run2.json").read_text())
    assert report["tau_acc"] is None
    assert "refit" not in report


def test_freeze_needs_a_reviewed_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    params_path = _patch(monkeypatch, tmp_path, _cases(stoppable=True))
    assert tool.main(["--freeze", "--run", "9"]) == 2
    assert not params_path.exists()


def test_freeze_writes_the_reviewed_refit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    params_path = _patch(monkeypatch, tmp_path, _cases(stoppable=True))
    assert tool.main(["--run", "3"]) == 0
    assert tool.main(["--freeze", "--run", "3"]) == 0
    report = json.loads((tmp_path / "router_run3.json").read_text())
    frozen = load_router_params(params_path)
    assert router_params_hash(frozen) == report["refit_hash"]
    assert not frozen.provisional


def test_freeze_refuses_a_tampered_refit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    params_path = _patch(monkeypatch, tmp_path, _cases(stoppable=True))
    assert tool.main(["--run", "4"]) == 0
    path = tmp_path / "router_run4.json"
    report = json.loads(path.read_text())
    report["refit"]["tau_acc"] = 0.01
    path.write_text(json.dumps(report))
    assert tool.main(["--freeze", "--run", "4"]) == 3
    assert not params_path.exists()


def test_case_from_entry_reads_the_runner_record() -> None:
    entry = {
        "incident_id": "inc",
        "steps": [
            {"id": "T", "signal": "latency"},
            {
                "id": "R",
                "ran": True,
                "features_cheap": [1] + [0] * (N - 1),
                "features": [1] * N,
            },
            {
                "id": "P:dpipe",
                "status": "ranked",
                "ranked": ["cart", "prometheus", "ad"],
                "sigma": 0.2,
                "measured": {"latency_ms": 40},
            },
            {
                "id": "P:gpipe",
                "status": "abstained",
                "ranked": [],
                "sigma": None,
                "measured": {"latency_ms": 900},
            },
            {
                "id": "P:lpipe",
                "status": "ranked",
                "ranked": ["ad"],
                "sigma": None,
                "measured": {"latency_ms": 12_000},
            },
        ],
    }
    case = tool.case_from_entry(entry, "otel_build_v3", {"root_cause_service": "cart"})
    assert case is not None
    assert case.votes["dpipe"].ranked == ("cart", "ad")  # out of scope dropped
    assert case.votes["lpipe"].sigma == 1
    assert "gpipe" not in case.votes
    assert case.x_dg is None  # G-pipe ran but ranked nothing
    assert case.graph is True
    assert case.latency_ms == {"dpipe": 40, "gpipe": 900, "lpipe": 12_000}
    assert case.group == "cart"
    assert case.signal == SignalType.LATENCY


def test_case_from_entry_skips_runs_without_features() -> None:
    entry = {"incident_id": "inc", "steps": [{"id": "R", "ran": False}]}
    assert tool.case_from_entry(entry, "c", {"root_cause_service": "x"}) is None


def test_an_existing_run_is_never_overwritten(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # OTel fix refit (entry 76): new runs take new numbers; run 1 stays.
    from bin import router_build_run

    assert router_build_run.main(["--run", "1"]) == 2
    assert "never overwritten" in capsys.readouterr().err
