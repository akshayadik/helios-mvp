"""API v1.2 (S4.5-S4.7): the proposal as a recommendation, the control-plane
state, and shadow mode (responders see a run only after its incident is
decided; admin keys always)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from helios.api.app import ApiConfig, create_app
from helios.api.auth import add_key
from helios.orchestrator.coe import CoELedger
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.ed25519 import generate_private_key, public_key_pem
from tests.api.test_api import COE_KEY, FULL, NOEXPL, SECRET, Clock, _check, _store

if TYPE_CHECKING:
    from pathlib import Path


def _action(mode: str, verdict: str = "PASS") -> dict[str, Any]:
    return {
        "id": "A",
        "mode": mode,
        "proposal": {"kind": "restart", "target": "checkout"},
        "fgsv": True,
        "verdict": verdict,
        "reason": "validated" if verdict == "PASS" else "ks_gate",
    }


def _coe(directory: Path, private: Any) -> None:
    directory.mkdir()
    path = directory / "results.tier2.coe.jsonl"
    path.touch()
    ledger = CoELedger(COE_KEY, path, ed25519_private=private)
    ledger.init_anchor()
    rows = [
        (
            "run-p",
            "inc-1",
            FULL,
            [
                _action("recommend"),
                {"id": "S", "measured": {"degraded": "helios.model"}},
            ],
        ),
        ("run-x", "inc-2", NOEXPL, [_action("shadow", "STALE")]),
    ]
    for run, inc, vh, steps in rows:
        ledger.append(
            {
                "run_id": run,
                "incident_id": inc,
                "variant_config_hash": vh,
                "snapshot_hash": "s",
                "evaluation_phase": "exploratory",
                "steps": [{"id": "F", "ranked": ["checkout"]}, *steps],
            }
        )


@pytest.fixture
def env(tmp_path: Path) -> dict[str, Any]:
    private = generate_private_key()
    pub = tmp_path / "pub.pem"
    pub.write_bytes(public_key_pem(private))
    _store(tmp_path / "results.duckdb")
    _coe(tmp_path / "coe", private)
    keys = tmp_path / "keys.json"
    heads = {
        name: {"X-API-Key": add_key(keys, name, roles, blind=blind)}
        for name, roles, blind in (
            ("obs", ["reader"], False),
            ("R1", ["reviewer"], False),
            ("A1", ["admin"], False),
            ("P1", ["reviewer"], True),
        )
    }
    assignments = tmp_path / "assignments.json"
    assignments.write_text('{"assignments": {"P1": ["run-p"]}}')
    config = ApiConfig(
        store_path=tmp_path / "results.duckdb",
        coe_dir=tmp_path / "coe",
        decisions_path=tmp_path / "decisions" / "decisions.jsonl",
        keys_path=keys,
        decisions_secret=SECRET,
        public_key_path=pub,
        frozen=lambda: False,
        clock=Clock(),
        assignments_path=assignments,
    )
    return {"client": TestClient(create_app(config)), **heads}


def test_the_proposal_and_control_plane_state_are_on_the_verdict(
    env: dict[str, Any],
) -> None:
    c = env["client"]
    body = _check(
        c.get("/v1/verdicts/run-p", headers=env["obs"]), "get", "/v1/verdicts/{run_id}"
    )
    assert body["action"] == {
        "kind": "restart",
        "target": "checkout",
        "mode": "recommend",
        "validation": "PASS",
        "reason": "validated",
    }
    assert body["control_plane_degraded"] == "helios.model"


def test_a_run_without_steps_a_or_s_has_neither(env: dict[str, Any]) -> None:
    body = env["client"].get("/v1/verdicts/run-c", headers=env["obs"]).json()
    assert body["action"] is None
    assert body["control_plane_degraded"] is None


def test_a_blind_key_sees_neither(env: dict[str, Any]) -> None:
    body = env["client"].get("/v1/verdicts/run-p", headers=env["P1"]).json()
    assert body["action"] is None
    assert body["control_plane_degraded"] is None


def test_shadow_runs_are_hidden_until_the_incident_is_decided(
    env: dict[str, Any],
) -> None:
    c = env["client"]
    for who in ("obs", "R1"):
        assert c.get("/v1/verdicts/run-x", headers=env[who]).status_code == 404
        assert c.get("/v1/incidents/inc-2", headers=env[who]).json()["runs"] == []
    assert c.post("/v1/verdicts/run-x/views", headers=env["R1"]).status_code == 404
    # An admin sees it and records the human answer.
    admin = c.get("/v1/verdicts/run-x", headers=env["A1"]).json()
    assert admin["action"]["mode"] == "shadow"
    view = c.post("/v1/verdicts/run-x/views", headers=env["A1"]).json()
    resp = c.post(
        "/v1/verdicts/run-x/decisions",
        headers=env["A1"],
        json={
            "view_token": view["view_token"],
            "decision": "reject",
            "chosen_service": "email",
        },
    )
    assert resp.status_code == 201
    for who in ("obs", "R1"):
        assert c.get("/v1/verdicts/run-x", headers=env[who]).status_code == 200
        assert [
            r["run_id"]
            for r in c.get("/v1/incidents/inc-2", headers=env[who]).json()["runs"]
        ] == ["run-x"]


def test_recommend_runs_are_visible_to_everyone(env: dict[str, Any]) -> None:
    c = env["client"]
    for who in ("obs", "R1", "A1"):
        assert c.get("/v1/verdicts/run-p", headers=env[who]).status_code == 200
