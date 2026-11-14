"""FGSV lite (S4.6, design s4_4_7_tier2_design.md T-e/T-f)."""

from __future__ import annotations

import json
import socket
import subprocess
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest

from helios.actions import fgsv
from helios.schemas.ueg_c import (
    TENANT_SELF,
    EdgeType,
    NodeType,
    UEGCEdge,
    UEGCNode,
    UEGCSnapshot,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path

PARAMS = fgsv.FGSVParams(
    alpha_ks=0.05,
    sample_seconds=15,
    min_samples=8,
    coverage_min=0.75,
    blast_max=2,
    perturb_shift=1,
    provisional=False,
)


def _graph(calls: list[tuple[str, str]]) -> UEGCSnapshot:
    names = sorted({s for pair in calls for s in pair} | {"cart"})
    nodes = [
        UEGCNode(node_id=n, node_type=NodeType.SERVICE, service_name=n) for n in names
    ]
    nodes.append(
        UEGCNode(
            node_id="helios.lpipe",
            node_type=NodeType.SERVICE,
            service_name="helios.lpipe",
            tenant=TENANT_SELF,
        )
    )
    edges = [
        UEGCEdge(source=a, target=b, edge_type=EdgeType.STRUCTURAL, weight=1)
        for a, b in calls
    ]
    edges.append(
        UEGCEdge(
            source="helios.lpipe",
            target="cart",
            edge_type=EdgeType.STRUCTURAL,
            weight=1,
        )
    )
    return UEGCSnapshot(
        incident_id="i",
        variant_config_hash="h",
        nodes=nodes,
        edges=edges,
        captured_at_iso="t",
    )


# frontend -> checkout -> cart -> redis ; frontend -> ad
SHOP = _graph(
    [
        ("frontend", "checkout"),
        ("checkout", "cart"),
        ("cart", "redis"),
        ("frontend", "ad"),
    ]
)


def _samples(n: int, phase: float) -> np.ndarray:
    """Deterministic, roughly bell-shaped samples (no random generator)."""
    i = np.arange(n, dtype="float64")
    return np.sin(i * 2.3 + phase) + np.sin(i * 0.7 + 2 * phase)


def _pairs(
    shift: float = 0, n: int = 40
) -> dict[str, list[tuple[np.ndarray, np.ndarray]]]:
    counts = (np.arange(n) % 7).astype("float64")
    return {
        "metrics": [(_samples(n, 0.4) + shift, _samples(n, 0.1))],
        "logs": [(counts, np.roll(counts, 3))],
    }


# ── parameters ──────────────────────────────────────────────────────────────


def test_frozen_parameters_load_and_are_not_provisional() -> None:
    params = fgsv.load_fgsv_params()
    assert not params.provisional
    assert params.alpha_ks == pytest.approx(0.05)  # Chapter 3's value
    assert len(fgsv.fgsv_params_hash(params)) == 64


def test_parameter_file_errors(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        fgsv.load_fgsv_params(tmp_path / "absent.json")
    bad = tmp_path / "p.json"
    bad.write_text(json.dumps({"alpha_ks": 0.05}))
    with pytest.raises(ValueError, match="keys"):
        fgsv.load_fgsv_params(bad)
    raw = json.loads(fgsv.FGSV_PARAMS_PATH.read_text())
    bad.write_text(json.dumps({**raw, "alpha_ks": 2}))
    with pytest.raises(ValueError, match="alpha_ks"):
        fgsv.load_fgsv_params(bad)
    bad.write_text(json.dumps({**raw, "min_samples": 1}))
    with pytest.raises(ValueError, match="min_samples"):
        fgsv.load_fgsv_params(bad)


# ── proposal ────────────────────────────────────────────────────────────────


def test_proposals() -> None:
    assert fgsv.propose("cart", "error").as_dict() == {
        "kind": "restart",
        "target": "cart",
    }
    assert fgsv.propose("cart", "resource").kind == "scale-out"
    assert fgsv.propose("redis-cart", "error").kind == "escalate-to-human"
    assert fgsv.propose("carts-db", None).kind == "escalate-to-human"
    assert fgsv.propose("kafka", None).kind == "escalate-to-human"
    assert fgsv.propose(None, None).kind == "none"
    assert not fgsv.stateful("checkout")


# ── structure ───────────────────────────────────────────────────────────────


def test_callers_and_what_a_target_explains() -> None:
    assert fgsv.callers(SHOP, "cart") == ["checkout"]
    assert fgsv.explained_by(SHOP, "cart") == {"cart", "checkout", "frontend"}
    assert fgsv.explained_by(SHOP, "ad") == {"ad", "frontend"}
    # Self nodes are never part of the production structure.
    assert "helios.lpipe" not in fgsv.callers(SHOP, "cart")


def test_replay_coverage_and_blast_radius() -> None:
    r = fgsv.replay(SHOP, "cart", ["cart", "checkout", "frontend", "ad", "elsewhere"])
    assert r["anomalous"] == ["ad", "cart", "checkout", "frontend"]  # graph only
    assert r["coverage"] == pytest.approx(0.75)
    assert r["blast_radius"] == 1
    assert fgsv.replay(SHOP, "cart", [])["coverage"] == 1
    assert fgsv.replay(SHOP, "frontend", ["cart"])["coverage"] == 0


# ── twin and KS gate ────────────────────────────────────────────────────────


def test_split_normal_halves_and_drops_missing() -> None:
    values = np.array([1, 2, np.nan, 4, 5, 6, 7, 8, 99, 99], dtype=float)
    twin, prod = fgsv.split_normal(values, 8)
    assert twin.tolist() == [1, 2, 4]
    assert prod.tolist() == [5, 6, 7, 8]
    assert [a.size for a in fgsv.split_normal(values, 0)] == [0, 0]


def test_gate_passes_on_one_distribution_and_fails_under_a_shift() -> None:
    assert fgsv.ks_gate(_pairs(), PARAMS)["passed"] is True
    shifted = fgsv.ks_gate(_pairs(), PARAMS, shift=3)
    assert shifted["passed"] is False
    assert "metrics" in shifted["rejected"]
    assert set(shifted["pillars"]) == {"metrics", "logs"}


def test_gate_without_enough_data_decides_nothing() -> None:
    few = {"metrics": [(np.arange(3.0), np.arange(3.0))]}
    assert fgsv.ks_gate(few, PARAMS) == {"passed": None, "pillars": {}}
    flat = {"metrics": [(np.full(20, 4.0), np.full(20, 4.0))]}
    assert fgsv.ks_gate(flat, PARAMS)["passed"] is None  # constant: no signal
    assert fgsv.ks_gate({}, PARAMS)["passed"] is None


def test_holm_across_pillars() -> None:
    gate = fgsv.ks_gate(
        {"metrics": _pairs()["metrics"], "logs": _pairs(shift=4)["metrics"]}, PARAMS
    )
    assert gate["passed"] is False
    assert gate["rejected"] == ["logs"]


# ── the step ────────────────────────────────────────────────────────────────


def _validate(
    target: str, anomalous: list[str], pairs: Any, **kw: Any
) -> dict[str, Any]:
    graph = kw.pop("graph", SHOP)
    return fgsv.validate(
        fgsv.propose(target, None),
        mode="recommend",
        graph=graph,
        anomalous=anomalous,
        pairs=pairs,
        params=PARAMS,
        **kw,
    )


def test_validation_verdicts() -> None:
    ok = _validate("cart", ["cart", "checkout"], _pairs())
    assert (ok["verdict"], ok["reason"]) == ("PASS", "validated")
    assert ok["mode"] == "recommend"
    assert ok["fgsv"] is True
    assert _validate("ad", ["cart", "checkout"], _pairs())["reason"] == "coverage"
    wide = _graph([("a", "cart"), ("b", "cart"), ("c", "cart")])
    assert _validate("cart", ["cart"], _pairs(), graph=wide)["reason"] == "blast_radius"
    assert _validate("cart", ["cart"], _pairs(), graph=None)["reason"] == "no_structure"
    assert (
        _validate("cart", ["cart"], _pairs(), graph=object())["reason"]
        == "no_structure"
    )
    assert _validate("cart", ["cart"], {})["reason"] == "no_twin_data"
    assert (
        _validate("redis", ["redis"], _pairs())["reason"]
        == "not_actionable:escalate-to-human"
    )


def test_the_fidelity_break_makes_the_twin_stale() -> None:
    step = _validate("cart", ["cart"], _pairs(), shift=3)
    assert (step["verdict"], step["reason"]) == ("STALE", "ks_gate")
    assert step["perturbation"] == {"shift": 3}


def test_unvalidated_step_for_nofgsv() -> None:
    step = fgsv.unvalidated_step(fgsv.propose("cart", None), "shadow")
    assert step == {
        "id": "A",
        "mode": "shadow",
        "proposal": {"kind": "restart", "target": "cart"},
        "fgsv": False,
        "verdict": "UNVALIDATED",
        "reason": "fgsv_off",
    }


def test_anomalous_services_use_the_detector_threshold() -> None:
    z = np.array([[1, 12, 12], [1, 2, 3], [np.nan, np.nan, 15]], dtype=float)
    assert fgsv.anomalous_services(["cart", "ad", "email"], z, 1, 10) == [
        "cart",
        "email",
    ]
    assert fgsv.anomalous_services(["cart"], z[:1], 3, 10) == []


def test_validation_never_opens_a_socket_or_starts_a_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("the action path must not reach out")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(subprocess, "Popen", refuse)
    assert _validate("cart", ["cart"], _pairs())["verdict"] == "PASS"
