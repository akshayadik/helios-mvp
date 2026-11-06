"""The runner routes cheap-first (cbr_routing ON) or uniformly (OFF) (S3.1 §5)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from helios.consensus.router_features import FEATURE_NAMES
from helios.consensus.router_params import (
    SELECTABLE,
    Arm,
    ArmModel,
    RouterParams,
)
from helios.evaluation.cost import load_price_book
from helios.integrity_gate import AppendOnlyLedger
from helios.orchestrator import runner as runner_module
from helios.orchestrator.runner import RouterParamsMismatchError, RunOrchestrator
from helios.telemetry.trigger import ProvisionalParametersError
from helios.vcl import VCLFlag, get_variant, set_current_manifest  # noqa: F401
from tests.test_orchestrator_runner import _KEY, _make_capture
from tests.test_runner_coe import _entries, _step

if TYPE_CHECKING:
    from pathlib import Path

N = len(FEATURE_NAMES)
MEDIANS: dict[str, float] = {"dpipe": 200, "gpipe": 900, "lpipe": 15_000}
# D alone infeasible, D+G feasible: G-pipe runs, then stop or escalate.
P_STOP = {Arm.D: 0.6, Arm.D_G: 0.92, Arm.D_L: 0.93, Arm.FULL: 0.95}


def _params(p: dict[Arm, float], *, digest: str | None = None) -> RouterParams:
    tiny = tuple(tuple(1e-6 if i == j else 0 for j in range(N)) for i in range(N))
    return RouterParams(
        feature_names=FEATURE_NAMES,
        arms={
            a: ArmModel(a_inv=tiny, theta=(p[a],) + (0,) * (N - 1), n=60)
            for a in SELECTABLE
        },
        lam=1,
        alpha=1,
        tau_acc=0.8,
        stage_median_ms=MEDIANS,
        price_book_digest=digest or load_price_book().digest,
        provisional=False,
    )


def _fake(pipeline: str, ranked: list[str], calls: list[str]) -> Any:
    def run(**kw: Any) -> dict[str, Any]:
        calls.append(pipeline)
        out = {
            "pipeline": pipeline,
            "incident_id": kw["incident_id"],
            "run_id": kw["run_id"],
            "variant_config_hash": "x",
            "snapshot_hash": kw["snapshot_hash"],
            "evaluation_phase": kw["evaluation_phase"],
            "status": "ranked",
            "ranked_candidates": ranked,
            "candidate_scores": (
                {"cart": 0.6, "ad": 0.3, "email": 0.1} if pipeline == "dpipe" else {}
            ),
            "mu": 0.6,
            "sigma": 0.2,
            "narrative": "",
        }
        if pipeline == "lpipe":
            out["h_struct"] = {"outputs": 1, "failed": 0}
        return out

    return run


def _run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    variant: str,
    *,
    g_top: str = "cart",
    params: RouterParams | None = None,
    name: str = "r",
) -> tuple[dict[str, Any], list[str]]:
    manifest = get_variant(variant)
    hash_ = manifest.compute_variant_config_hash()
    calls: list[str] = []

    def stamped(fn: Any) -> Any:
        return lambda **kw: {**fn(**kw), "variant_config_hash": hash_}

    g_ranked = [g_top, "email"] if g_top == "cart" else [g_top, "cart"]
    monkeypatch.setattr(
        runner_module,
        "run_dpipe",
        stamped(_fake("dpipe", ["cart", "ad", "email"], calls)),
    )
    monkeypatch.setattr(
        runner_module, "run_gpipe", stamped(_fake("gpipe", g_ranked, calls))
    )
    monkeypatch.setattr(
        runner_module, "run_lpipe", stamped(_fake("lpipe", ["ad", "cart"], calls))
    )
    # A graph exists (its content is irrelevant: G-pipe is faked).
    monkeypatch.setattr(runner_module, "incident_graph", lambda *_a: (object(), []))
    captures = tmp_path / "captures"
    if not captures.exists():
        _make_capture(captures, "inc-001")
    set_current_manifest(manifest)
    orch = RunOrchestrator(
        manifest=manifest,
        captures_dir=captures,
        db_path=tmp_path / f"{name}.duckdb",
        registry_path=tmp_path / f"{name}.registry.jsonl",
        reconciliation_path=tmp_path / f"{name}.reconciliation.jsonl",
        exclusion_ledger=MagicMock(spec=AppendOnlyLedger),
        hmac_key=_KEY,
        router_params=params or _params(P_STOP),
    )
    orch.run(captures)
    (entry,) = _entries(orch.coe_path)
    return entry, calls


_DECISION_KEYS = (
    "mode",
    "ran",
    "g_decision",
    "stage1_arm",
    "terminal_arm",
    "escalate",
    "escalation_reason",
    "wanted",
    "features",
    "estimates",
)


def test_agreeing_cheap_arm_stops_before_the_lpipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry, calls = _run(tmp_path, monkeypatch, "HELIOS-Full")
    r = _step(entry, "R")
    assert calls == ["dpipe", "gpipe"]
    assert r["mode"] == "routed"
    assert r["stage1_arm"] == r["terminal_arm"] == "D+G"
    assert r["escalate"] is False
    assert r["escalation_reason"] == "none"
    assert r["stage1_ms"] == r["terminal_ms"]
    assert _step(entry, "P:lpipe")["status"] == "skipped"
    assert _step(entry, "F")["ranked"][0] == "cart"


def test_disagreement_escalates_to_full(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry, calls = _run(tmp_path, monkeypatch, "HELIOS-Full", g_top="ad")
    r = _step(entry, "R")
    assert calls == ["dpipe", "gpipe", "lpipe"]
    assert r["escalation_reason"] == "disagreement"
    assert r["terminal_arm"] == "Full"
    assert r["terminal_ms"] >= r["stage1_ms"]


def test_no_consensus_routes_exactly_like_full(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The router never reads the fusion, so A-H4's pairs see the same arms.
    for g_top in ("cart", "ad"):
        full, _ = _run(
            tmp_path, monkeypatch, "HELIOS-Full", g_top=g_top, name=f"f{g_top}"
        )
        plain, _ = _run(
            tmp_path, monkeypatch, "HELIOS-noConsensus", g_top=g_top, name=f"n{g_top}"
        )
        for key in _DECISION_KEYS:
            assert _step(full, "R")[key] == _step(plain, "R")[key], key


def test_no_llm_records_llm_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry, calls = _run(tmp_path, monkeypatch, "HELIOS-noLLM", g_top="ad")
    r = _step(entry, "R")
    assert "lpipe" not in calls
    assert r["escalation_reason"] == "llm_off"
    assert r["wanted"] == "disagreement"
    assert r["terminal_arm"] == "D+G"


def test_uniform_runs_every_pipeline_with_g_ungated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry, calls = _run(tmp_path, monkeypatch, "HELIOS-noRouter")
    r = _step(entry, "R")
    assert sorted(calls) == ["dpipe", "gpipe", "lpipe"]
    assert r["mode"] == "uniform"
    assert r["reason"] == "uniform"
    assert "stage1_arm" not in r
    assert r["features"][FEATURE_NAMES.index("g_ran")] == 1
    assert r["features_cheap"][FEATURE_NAMES.index("g_ran")] == 0
    assert "router" not in entry["parameter_hashes"]


def test_full_and_no_router_differ_on_the_same_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    full, full_calls = _run(tmp_path, monkeypatch, "HELIOS-Full", name="f")
    uniform, uniform_calls = _run(tmp_path, monkeypatch, "HELIOS-noRouter", name="u")
    assert full_calls != sorted(uniform_calls)
    assert _step(full, "R")["mode"] != _step(uniform, "R")["mode"]


def test_router_hash_in_the_coe_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from helios.consensus.router_params import router_params_hash

    params = _params(P_STOP)
    entry, _ = _run(tmp_path, monkeypatch, "HELIOS-Full", params=params)
    assert entry["parameter_hashes"]["router"] == router_params_hash(params)


def test_routing_decision_is_rerun_equal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a, _ = _run(tmp_path, monkeypatch, "HELIOS-Full", g_top="ad", name="a")
    b, _ = _run(tmp_path, monkeypatch, "HELIOS-Full", g_top="ad", name="b")
    for key in _DECISION_KEYS:
        assert _step(a, "R")[key] == _step(b, "R")[key], key
    assert _step(a, "F")["ranked"] == _step(b, "F")["ranked"]


def _confirmatory_orch(tmp_path: Path, params: RouterParams) -> RunOrchestrator:
    from tests.test_orchestrator_runner import _make_orchestrator

    orch = _make_orchestrator(tmp_path, tmp_path / "captures")
    orch._router = params
    for attr in ("_detector", "_dpipe", "_gpipe", "_mahc", "_narrator"):
        setattr(orch, attr, MagicMock(provisional=False))
    orch._coe_signer = MagicMock()
    orch._price_book_digest = load_price_book().digest
    return orch


def test_confirmatory_run_refuses_provisional_router(tmp_path: Path) -> None:
    from helios.consensus.router_params import provisional_router_params

    orch = _confirmatory_orch(
        tmp_path, provisional_router_params(stage_median_ms=MEDIANS)
    )
    with pytest.raises(ProvisionalParametersError, match="router"):
        orch._trigger_for(MagicMock(evaluation_phase="confirmatory"))


def test_confirmatory_run_refuses_a_router_from_another_price_book(
    tmp_path: Path,
) -> None:
    orch = _confirmatory_orch(tmp_path, _params(P_STOP, digest="e" * 64))
    with pytest.raises(RouterParamsMismatchError):
        orch._trigger_for(MagicMock(evaluation_phase="confirmatory"))


def test_confirmatory_routed_run_needs_the_price_book_digest(tmp_path: Path) -> None:
    orch = _confirmatory_orch(tmp_path, _params(P_STOP))
    orch._price_book_digest = None
    with pytest.raises(RouterParamsMismatchError, match="no price book digest"):
        orch._trigger_for(MagicMock(evaluation_phase="confirmatory"))
