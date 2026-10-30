"""bin/mahc_build_run.py: pool refused, stop on an unreachable floor, aggregates only."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from bin import mahc_build_run as tool
from helios.consensus.mahc import Vote
from helios.evaluation.mahc_calibration import BuildCase
from helios.telemetry.signal_type import SignalType
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path


def _cases(right: bool) -> list[BuildCase]:
    out = []
    for i in range(40):
        root = f"svc-{i % 4}"
        ranked = (root, "svc-x") if right else ("svc-x", "svc-y", "svc-z", root)
        corpus = "otel_build_v3" if i < 20 else "rcaeval_build"
        group = ["ad", "cart"][i % 2] if i < 20 else ["ob", "ss"][i % 2]
        out.append(
            BuildCase(
                f"incident{i:03d}",
                corpus,
                group,
                SignalType.RESOURCE,
                (Vote("dpipe", ranked, 0.3), Vote("lpipe", ranked[:1], 0.6)),
                root,
            )
        )
    return out


def _patch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, cases: list[BuildCase]
) -> None:
    def collect(**_kw: Any) -> tuple[list[BuildCase], dict[str, int]]:
        return cases, {"excluded": 0}

    monkeypatch.setattr(tool, "collect_cases", collect)
    monkeypatch.setattr(tool, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(tool, "load_key", lambda: b"k")


def test_tool_refuses_the_pool() -> None:
    assert tool.main(["--corpus", "pool"]) == 2


def test_report_has_no_incident_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = _cases(right=True)
    _patch(monkeypatch, tmp_path, cases)
    assert tool.main([]) == 0
    text = (tmp_path / "mahc_run1.json").read_text(encoding="utf-8")
    assert not any(c.incident_id in text for c in cases)
    report = json.loads(text)
    assert report["floor"] is not None
    assert report["refit"]["provisional"] is False
    assert len(report["refit_hash"]) == 64


def test_unreachable_floor_exits_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch, tmp_path, _cases(right=False))
    assert tool.main([]) == 3
    assert (
        json.loads((tmp_path / "mahc_run1.json").read_text(encoding="utf-8"))["floor"]
        is None
    )


def test_cases_from_store_reads_votes_signal_and_group(tmp_path: Path) -> None:
    from helios.consensus.calibration import State
    from helios.consensus.mahc import FusedVerdict
    from helios.consensus.timing import Schedule
    from helios.schemas.verdict import PipelineName, PipelineVerdict, VerdictStatus
    from helios.store.result_store import ResultStore

    store = ResultStore(tmp_path / "s.duckdb")

    def verdict(
        p: PipelineName, ranked: list[str], status: VerdictStatus
    ) -> PipelineVerdict:
        return PipelineVerdict(
            run_id="run-1",
            incident_id="inc-1",
            variant_config_hash="h",
            snapshot_hash="s",
            pipeline=p,
            evaluation_phase="exploratory",
            status=status,
            ranked_candidates=ranked,
            sigma=0.3 if ranked else None,
            mu=1 if ranked else None,
            latency_ms=1,
        )

    store.insert(
        verdict(
            PipelineName.DPIPE, ["cartservice", "jaeger", "redis"], VerdictStatus.RANKED
        )
    )
    store.insert(verdict(PipelineName.GPIPE, [], VerdictStatus.SKIPPED))
    store.insert(verdict(PipelineName.LPIPE, ["cartservice"], VerdictStatus.RANKED))
    store.insert_fusion(
        "run-1",
        "inc-1",
        "h",
        FusedVerdict(
            "mahc",
            ("cartservice",),
            {"cartservice": 1},
            None,
            0.3,
            State.PROVISIONAL,
            Schedule(1, (), 1, False),
            (),
            {"signal": "latency"},
        ),
    )
    labels = {"inc-1": {"root_cause_service": "cartservice", "system": "ob"}}
    (case,) = tool._cases_from_store(store, "rcaeval_build", labels)
    assert case.group == "ob" and case.root == "cartservice"
    assert case.signal == SignalType.LATENCY
    assert [v.pipeline for v in case.votes] == ["dpipe", "lpipe"]
    assert case.votes[0].ranked == ("cartservice", "redis")  # jaeger is out of scope


def test_cache_only_client_never_contacts_the_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Review I2: the build run must not depend on a live model server.
    import requests

    from helios.pipelines.l_pipe import lpipe_config

    def no_network(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("no server call allowed")

    monkeypatch.setattr(requests, "get", no_network)
    monkeypatch.setattr(requests, "post", no_network)
    client = tool._CacheOnlyClient("http://h:1", "m")
    assert client.model_digest(timeout_s=1) == lpipe_config.EXPECTED_MODEL_DIGEST
    with pytest.raises(tool.CacheMissError):
        client.generate("p", 1)


def _store_with(tmp_path: Path, runs: list[tuple[str, str, str]]) -> Any:
    from helios.consensus.calibration import State
    from helios.consensus.mahc import FusedVerdict
    from helios.consensus.timing import Schedule
    from helios.schemas.verdict import PipelineName, PipelineVerdict, VerdictStatus
    from helios.store.result_store import ResultStore

    store = ResultStore(tmp_path / "s.duckdb")
    for run_id, incident, lstatus in runs:
        for p, status in (
            (PipelineName.DPIPE, "ranked"),
            (PipelineName.LPIPE, lstatus),
        ):
            ranked = ["cartservice"] if status == "ranked" else []
            store.insert(
                PipelineVerdict(
                    run_id=run_id,
                    incident_id=incident,
                    variant_config_hash="h",
                    snapshot_hash="s",
                    pipeline=p,
                    evaluation_phase="exploratory",
                    status=VerdictStatus(status),
                    ranked_candidates=ranked,
                    sigma=0.3 if ranked else None,
                    mu=1 if ranked else None,
                    latency_ms=1,
                )
            )
        store.insert_fusion(
            run_id,
            incident,
            "h",
            FusedVerdict(
                "mahc",
                (),
                {},
                None,
                None,
                State.PROVISIONAL,
                Schedule(1, (), 1, False),
                (),
                {"signal": "error"},
            ),
        )
    return store


def test_failed_lpipe_aborts_the_build(tmp_path: Path) -> None:
    store = _store_with(tmp_path, [("run-1", "inc-1", "failed")])
    labels = {"inc-1": {"root_cause_service": "cartservice", "system": "ob"}}
    with pytest.raises(tool.LPipeFailedError):
        tool._cases_from_store(store, "rcaeval_build", labels)


def test_cases_are_ordered_by_incident(tmp_path: Path) -> None:
    store = _store_with(
        tmp_path, [("run-a", "inc-2", "ranked"), ("run-b", "inc-1", "ranked")]
    )
    labels = {
        i: {"root_cause_service": "cartservice", "system": "ob"}
        for i in ("inc-1", "inc-2")
    }
    assert [
        c.incident_id for c in tool._cases_from_store(store, "rcaeval_build", labels)
    ] == [
        "inc-1",
        "inc-2",
    ]


def test_run_number_names_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch, tmp_path, _cases(right=True))
    assert tool.main(["--run", "2"]) == 0
    assert (tmp_path / "mahc_run2.json").is_file()
    assert not (tmp_path / "mahc_run1.json").exists()
