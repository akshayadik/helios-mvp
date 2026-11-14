"""S4.1 API contract tests (design A-g, A-h) over a fixture campaign.

The fixture store has four runs: a CONFIRMED and a PROVISIONAL HELIOS-Full
run, a HELIOS-noExpl run (narrative stored but never shown) and a
confirmatory run (locked until build-freeze). Every response is checked
against the committed OpenAPI spec, and a leakage scan checks that no response
carries ground truth, a case name, an injection time or a scored metric.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

import duckdb
import pytest
from fastapi.testclient import TestClient

from bin.helios_api import (
    SPEC_PATH,
    decisions_secret,
    main,
    refuse_deviation_env,
    spec_text,
)
from helios.api import API_VERSION
from helios.api.app import ApiConfig, create_app
from helios.api.auth import ApiKey, KeyStore, add_key
from helios.api.decisions import DecisionLedger, ViewTokens, read_entries
from helios.orchestrator.coe import CoELedger
from helios.store.result_store import ResultStore
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.ed25519 import generate_private_key, public_key_pem
from helios.vcl.variants import CONFIRMATORY_VARIANTS, EXPLORATORY_VARIANTS

if TYPE_CHECKING:
    from pathlib import Path

SECRET = b"d" * 40
COE_KEY = b"c" * 40
FULL = CONFIRMATORY_VARIANTS["HELIOS-Full"].compute_variant_config_hash()
NOEXPL = EXPLORATORY_VARIANTS["HELIOS-noExpl"].compute_variant_config_hash()
SPEC = json.loads(SPEC_PATH.read_text())
FORBIDDEN = re.compile(
    r"root_cause|ground_truth|inject|hr_at|ttcd|cpr|fault|re[123](ob|ss|tt)_",
    re.IGNORECASE,
)


class Clock:
    def __init__(self) -> None:
        self.now = 1_800_000_000.0

    def __call__(self) -> float:
        return self.now


def _store(path: Path) -> None:
    ResultStore(path).close()  # creates the schema
    con = duckdb.connect(str(path))
    runs = [
        ("run-c", "inc-1", FULL, "confirmed", "exploratory"),
        ("run-p", "inc-1", FULL, "provisional", "exploratory"),
        ("run-x", "inc-2", NOEXPL, "provisional", "exploratory"),
        ("run-k", "inc-3", FULL, "provisional", "confirmatory"),
    ]
    for run, inc, vh, state, phase in runs:
        con.execute(
            "INSERT INTO fusion_row (run_id, incident_id, variant_config_hash, method, "
            "ranked_json, scores_json, confidence, fused_sigma, state, first_ms, "
            "first_ranked_json, terminal_ms, non_converged, evidence_json) VALUES "
            "(?, ?, ?, 'mahc', ?, ?, 0.88, 0.1, ?, 1200, ?, 20000, false, '{}')",
            [
                run,
                inc,
                vh,
                json.dumps(["checkout", "email", "ad", "cart"]),
                json.dumps({"checkout": 0.9, "email": 0.4}),
                state,
                json.dumps(["email", "checkout"]),
            ],
        )
        con.execute(
            "INSERT INTO result_row (run_id, incident_id, variant_config_hash, "
            "snapshot_hash, pipeline, evaluation_phase, status, ranked_candidates, "
            "candidate_scores, prompt_tokens, completion_tokens, cpu_ms, gpu_ms, "
            "latency_ms, narrative, decision_hash, schema_version) VALUES "
            "(?, ?, ?, 's', 'dpipe', ?, 'ranked', '[]', '{}', 0, 0, 1, 0, 1, '', 'h', 'v')",
            [run, inc, vh, phase],
        )
        con.execute(
            "INSERT INTO trigger_row (run_id, incident_id, variant_config_hash, "
            "trigger_time_s, suspects, context, source, detector_hash, "
            "seeds_from_trigger, handover_unix) VALUES "
            "(?, ?, ?, 1700000000, ?, '[]', 'detector', 'd', true, 1)",
            [run, inc, vh, json.dumps(["checkout"])],
        )
        con.execute(
            "INSERT INTO routing_row (run_id, incident_id, routing_json) VALUES (?, ?, ?)",
            [run, inc, json.dumps({"escalate": state != "confirmed"})],
        )
        slots = {
            "story": {
                "claims": [
                    {"kind": "ranking", "sentence": "checkout is top.", "cites": ["F"]}
                ]
            }
        }
        con.execute(
            "INSERT INTO narrative_row (run_id, incident_id, narrator, slots_json, "
            "rendered, attempts, fallbacks, prompt_tokens, completion_tokens, wall_ms) "
            "VALUES (?, ?, 'llm', ?, 'checkout is top. [F]', 1, 0, 10, 5, 3)",
            [run, inc, json.dumps(slots)],
        )
    con.close()


def _coe(directory: Path, private: Any) -> None:
    directory.mkdir()
    path = directory / "results.HELIOS-Full.coe.jsonl"
    path.touch()
    ledger = CoELedger(COE_KEY, path, ed25519_private=private)
    ledger.init_anchor()
    for run in ("run-c", "run-p", "run-k"):
        ledger.append(
            {
                "run_id": run,
                "incident_id": "inc-1",
                "variant_config_hash": FULL,
                "snapshot_hash": "s",
                "evaluation_phase": "exploratory",
                "steps": [{"step": "fusion", "state": "provisional"}],
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
    reader = add_key(keys, "obs", ["reader"])
    reviewer = add_key(keys, "R1", ["reviewer"])
    other = add_key(keys, "R2", ["reviewer"])
    blind = add_key(keys, "P1", ["reviewer"], blind=True)
    simulated = add_key(keys, "S1", ["reviewer"], simulated=True)
    assignments = tmp_path / "assignments.json"
    assignments.write_text(json.dumps({"assignments": {"P1": ["run-p", "run-x"]}}))
    frozen = {"v": False}
    clock = Clock()
    config = ApiConfig(
        store_path=tmp_path / "results.duckdb",
        coe_dir=tmp_path / "coe",
        decisions_path=tmp_path / "decisions" / "decisions.jsonl",
        keys_path=keys,
        decisions_secret=SECRET,
        public_key_path=pub,
        frozen=lambda: frozen["v"],
        clock=clock,
        assignments_path=assignments,
    )
    client = TestClient(create_app(config))
    return {
        "client": client,
        "reader": {"X-API-Key": reader},
        "reviewer": {"X-API-Key": reviewer},
        "other": {"X-API-Key": other},
        "blind": {"X-API-Key": blind},
        "simulated": {"X-API-Key": simulated},
        "frozen": frozen,
        "clock": clock,
        "config": config,
        "tmp": tmp_path,
    }


# ── the committed spec and response conformance ──────────────────────────────


def _resolve(schema: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in schema:
        schema = SPEC["components"]["schemas"][schema["$ref"].rsplit("/", 1)[1]]
    return schema


def _conforms(value: Any, schema: dict[str, Any], where: str = "$") -> None:
    schema = _resolve(schema)
    if "anyOf" in schema:
        errors = []
        for option in schema["anyOf"]:
            try:
                _conforms(value, option, where)
                return
            except AssertionError as exc:
                errors.append(str(exc))
        raise AssertionError(f"{where}: no anyOf branch matches: {errors}")
    kind = schema.get("type")
    if kind == "object" and "properties" in schema:
        assert isinstance(value, dict), where
        assert set(schema.get("required", [])) <= set(value), where
        extra = set(value) - set(schema["properties"])
        assert not extra or schema.get("additionalProperties", True), (where, extra)
        for k, v in value.items():
            if k in schema["properties"]:
                _conforms(v, schema["properties"][k], f"{where}.{k}")
    elif kind == "array":
        assert isinstance(value, list), where
        for i, v in enumerate(value):
            _conforms(v, schema.get("items", {}), f"{where}[{i}]")
    elif kind == "string":
        assert isinstance(value, str), where
        if "enum" in schema:
            assert value in schema["enum"], where
    elif kind == "integer":
        assert isinstance(value, int) and not isinstance(value, bool), where
    elif kind == "number":
        assert isinstance(value, int | float) and not isinstance(value, bool), where
    elif kind == "boolean":
        assert isinstance(value, bool), where
    elif kind == "null":
        assert value is None, where


def _check(resp: Any, method: str, template: str) -> Any:
    """The response matches the spec's schema for this path, method and status."""
    op = SPEC["paths"][template][method]
    responses = {**SPEC.get("components", {}).get("responses", {}), **op["responses"]}
    status = str(resp.status_code)
    assert status in op["responses"] or status in ("401", "403", "422"), (
        template,
        status,
    )
    body = resp.json()
    assert not FORBIDDEN.search(json.dumps(body)), (template, body)
    entry = responses.get(status)
    if entry and "content" in entry:
        media = next(iter(entry["content"].values()))
        _conforms(body, media["schema"])
    if resp.status_code >= 400:
        assert resp.headers["content-type"].startswith("application/problem+json")
        assert body["status"] == resp.status_code
    return body


def test_committed_spec_matches_the_app(tmp_path: Path) -> None:
    assert (
        spec_text(tmp_path) == SPEC_PATH.read_text()
    ), "docs/api/openapi.json is stale: run bin/helios_api.py export-spec"
    assert SPEC["info"]["version"] == API_VERSION


# ── health and authentication ────────────────────────────────────────────────


def test_health_needs_no_key_and_reports_ledgers(env: dict[str, Any]) -> None:
    body = _check(env["client"].get("/health"), "get", "/health")
    assert body["status"] == "ok" and body["incidents"] == 3
    assert body["keys_configured"] == 5 and body["build_frozen"] is False
    assert "baseline-v1" in body["schema_tags"]
    assert body["coe_ledgers"]["results.HELIOS-Full.coe.jsonl"].startswith("Verified")


def test_keys_and_roles(env: dict[str, Any]) -> None:
    c = env["client"]
    assert _check(c.get("/v1/incidents"), "get", "/v1/incidents")["status"] == 401
    bad = c.get("/v1/incidents", headers={"X-API-Key": "nope"})
    assert bad.status_code == 401
    r = c.post("/v1/verdicts/run-p/views", headers=env["reader"])
    assert _check(r, "post", "/v1/verdicts/{run_id}/views")["status"] == 403


# ── incidents and verdicts ───────────────────────────────────────────────────


def test_incidents_page_and_detail(env: dict[str, Any]) -> None:
    c, h = env["client"], env["reader"]
    page = _check(c.get("/v1/incidents?limit=2", headers=h), "get", "/v1/incidents")
    assert page["total"] == 3 and [i["incident_id"] for i in page["items"]] == [
        "inc-1",
        "inc-2",
    ]
    assert page["items"][0] == {
        "incident_id": "inc-1",
        "runs": 2,
        "confirmed": 1,
        "needs_review": 1,
    }
    t = "/v1/incidents/{incident_id}"
    detail = _check(c.get("/v1/incidents/inc-1", headers=h), "get", t)
    assert {r["run_id"]: r["needs_review"] for r in detail["runs"]} == {
        "run-c": False,
        "run-p": True,
    }
    assert detail["runs"][0]["top3"] == ["checkout", "email", "ad"]
    assert _check(c.get("/v1/incidents/zzz", headers=h), "get", t)["status"] == 404
    # The confirmatory run is hidden until build-freeze, then listed.
    assert _check(c.get("/v1/incidents/inc-3", headers=h), "get", t)["runs"] == []
    env["frozen"]["v"] = True
    assert len(c.get("/v1/incidents/inc-3", headers=h).json()["runs"]) == 1
    assert c.get("/v1/incidents?limit=0", headers=h).status_code == 422


def test_verdict_with_narrative_and_the_noexpl_condition(env: dict[str, Any]) -> None:
    c, h = env["client"], env["reader"]
    t = "/v1/verdicts/{run_id}"
    v = _check(c.get("/v1/verdicts/run-p", headers=h), "get", t)
    assert v["variant"] == "HELIOS-Full" and v["needs_review"] is True
    assert v["ranked"][0] == {"rank": 1, "service": "checkout", "score": 0.9}
    assert v["ranked"][2]["score"] is None  # no score stored for "ad"
    assert v["first_ranked"] == ["email", "checkout"] and v["escalated"] is True
    assert v["trigger"]["suspects"] == ["checkout"]
    assert v["narrative"]["claims"] == [
        {
            "slot": "story",
            "kind": "ranking",
            "sentence": "checkout is top.",
            "cites": ["F"],
        }
    ]
    x = _check(c.get("/v1/verdicts/run-x", headers=h), "get", t)
    assert x["variant"] == "HELIOS-noExpl" and x["narrative"] is None
    assert _check(c.get("/v1/verdicts/none", headers=h), "get", t)["status"] == 404
    locked = _check(c.get("/v1/verdicts/run-k", headers=h), "get", t)
    assert locked["status"] == 423
    env["frozen"]["v"] = True
    assert c.get("/v1/verdicts/run-k", headers=h).status_code == 200


def test_chain_of_evidence(env: dict[str, Any]) -> None:
    c, h = env["client"], env["reader"]
    t = "/v1/verdicts/{run_id}/coe"
    body = _check(c.get("/v1/verdicts/run-p/coe", headers=h), "get", t)
    assert body["verified"] is True and body["entry"]["run_id"] == "run-p"
    assert _check(c.get("/v1/verdicts/run-x/coe", headers=h), "get", t)["status"] == 404


def test_tampered_coe_is_reported(env: dict[str, Any]) -> None:
    path = env["tmp"] / "coe" / "results.HELIOS-Full.coe.jsonl"
    path.write_text(path.read_text().replace("provisional", "confirmed", 1))
    client = TestClient(create_app(env["config"]))
    assert client.get("/health").json()["status"] == "degraded"
    body = client.get("/v1/verdicts/run-c/coe", headers=env["reader"]).json()
    assert body["verified"] is False


# ── views, decisions and server-side timing (A-e, A-f) ───────────────────────


def test_decision_flow_and_server_timing(env: dict[str, Any]) -> None:
    c, h, clock = env["client"], env["reviewer"], env["clock"]
    tv, td = "/v1/verdicts/{run_id}/views", "/v1/verdicts/{run_id}/decisions"
    view = _check(c.post("/v1/verdicts/run-p/views", headers=h), "post", tv)
    assert view["expires_at"] - view["issued_at"] == 1800
    clock.now += 42.25
    body = {"decision": "escalate", "view_token": view["view_token"], "client_ms": 41}
    d = _check(c.post("/v1/verdicts/run-p/decisions", headers=h, json=body), "post", td)
    assert (d["decision"], d["key_id"], d["decision_ms"], d["client_ms"]) == (
        "escalate",
        "R1",
        42250,
        41,
    )
    reuse = c.post("/v1/verdicts/run-p/decisions", headers=h, json=body)
    assert _check(reuse, "post", td)["status"] == 409
    # A changed mind is a second decision; the latest counts.
    view2 = c.post("/v1/verdicts/run-p/views", headers=h).json()
    body2 = {"decision": "accept", "view_token": view2["view_token"]}
    assert c.post("/v1/verdicts/run-p/decisions", headers=h, json=body2).is_success
    listed = _check(
        c.get("/v1/verdicts/run-p/decisions", headers=env["reader"]), "get", td
    )
    assert [x["decision"] for x in listed["decisions"]] == ["escalate", "accept"]
    assert listed["latest"] == "accept"
    ledger = DecisionLedger(key=SECRET, log_path=env["config"].decisions_path)
    assert ledger.verify()[0]
    events = [e["event"] for e in read_entries(env["config"].decisions_path)]
    assert events == ["view", "decision", "view", "decision"]


def test_token_refusals(env: dict[str, Any]) -> None:
    c, h, clock = env["client"], env["reviewer"], env["clock"]
    td = "/v1/verdicts/{run_id}/decisions"
    token = c.post("/v1/verdicts/run-p/views", headers=h).json()["view_token"]
    other_key = c.post(
        "/v1/verdicts/run-p/decisions",
        headers=env["other"],
        json={"decision": "accept", "view_token": token},
    )
    assert _check(other_key, "post", td)["status"] == 400
    wrong_run = c.post(
        "/v1/verdicts/run-c/decisions",
        headers=h,
        json={"decision": "accept", "view_token": token},
    )
    assert wrong_run.status_code == 400
    forged = token[:-4] + "0000"
    r = c.post(
        "/v1/verdicts/run-p/decisions",
        headers=h,
        json={"decision": "accept", "view_token": forged},
    )
    assert r.status_code == 400
    garbage = c.post(
        "/v1/verdicts/run-p/decisions",
        headers=h,
        json={"decision": "accept", "view_token": "not-a-token-at-all!!"},
    )
    assert garbage.status_code == 400
    clock.now += 1801
    late = c.post(
        "/v1/verdicts/run-p/decisions",
        headers=h,
        json={"decision": "accept", "view_token": token},
    )
    assert _check(late, "post", td)["status"] == 410
    bad = c.post(
        "/v1/verdicts/run-p/decisions",
        headers=h,
        json={"decision": "maybe", "view_token": token},
    )
    assert _check(bad, "post", td)["status"] == 422
    locked = c.post("/v1/verdicts/run-k/views", headers=h)
    assert locked.status_code == 423


# ── auth module, tokens and the CLI ──────────────────────────────────────────


def test_key_store_rules(tmp_path: Path) -> None:
    path = tmp_path / "k.json"
    key = add_key(path, "A", ["admin"])
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert key not in path.read_text()  # only the digest is stored
    store = KeyStore(path)
    found = store.lookup(key)
    assert found == ApiKey("A", ("admin",)) and found.allows("reviewer")
    assert store.lookup(None) is None and store.lookup("") is None
    assert not ApiKey("B", ("reader",)).allows("reviewer")
    with pytest.raises(ValueError, match="exists"):
        add_key(path, "A", ["reader"])
    with pytest.raises(ValueError, match="unknown roles"):
        add_key(path, "C", ["root"])
    path.write_text(
        json.dumps({"keys": [{"id": "x", "sha256": "y", "roles": ["god"]}]})
    )
    with pytest.raises(ValueError, match="unknown roles"):
        KeyStore(path)
    assert len(KeyStore(tmp_path / "absent.json")) == 0


def test_view_tokens_need_a_long_secret() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        ViewTokens(b"short")


def test_cli_guards_and_commands(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit, match="DEVIATION_HMAC_SECRET"):
        refuse_deviation_env({"DEVIATION_HMAC_SECRET": "x", "PATH": "/bin"})
    refuse_deviation_env({"PATH": "/bin"})
    with pytest.raises(SystemExit, match="shorter than 32"):
        decisions_secret({"HELIOS_DECISIONS_HMAC_SECRET": "short"})
    assert decisions_secret({"HELIOS_DECISIONS_HMAC_SECRET": "z" * 40}) == b"z" * 40
    assert main(["secret"]) == 0
    assert capsys.readouterr().out.startswith("HELIOS_DECISIONS_HMAC_SECRET=")
    keys = tmp_path / "keys.json"
    assert main(["keygen", "--keys", str(keys), "--id", "R9", "--role", "reader"]) == 0
    printed = capsys.readouterr().out.strip()
    assert KeyStore(keys).lookup(printed) == ApiKey("R9", ("reader",))
    out = tmp_path / "spec.json"
    assert main(["export-spec", "--output", str(out)]) == 0
    assert out.read_text() == SPEC_PATH.read_text()


def test_verify_ledgers_checks_the_decisions_ledger(
    env: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    from bin.verify_ledgers import verify_decisions

    c, h = env["client"], env["reviewer"]
    token = c.post("/v1/verdicts/run-p/views", headers=h).json()["view_token"]
    c.post(
        "/v1/verdicts/run-p/decisions",
        headers=h,
        json={"decision": "reject", "view_token": token},
    )
    path = env["config"].decisions_path
    assert verify_decisions(path, SECRET) == 0
    assert verify_decisions(env["tmp"] / "none.jsonl", SECRET) == 0
    assert verify_decisions(path, None) == 0  # no secret loaded: reported, skipped
    assert "not checked" in capsys.readouterr().out
    path.write_text(path.read_text().replace("reject", "accept"))
    assert verify_decisions(path, SECRET) == 1


# ── S4.2: review queue, blind keys, decision fields (design K-e to K-g) ──────


def _decide(
    env: dict[str, Any], who: str, run: str, **body: Any
) -> tuple[int, dict[str, Any]]:
    c, h = env["client"], env[who]
    view = c.post(f"/v1/verdicts/{run}/views", headers=h).json()
    resp = c.post(
        f"/v1/verdicts/{run}/decisions",
        headers=h,
        json={"view_token": view["view_token"], **body},
    )
    return resp.status_code, _check(resp, "post", "/v1/verdicts/{run_id}/decisions")


def test_queue_lists_assigned_cases_in_order(env: dict[str, Any]) -> None:
    c = env["client"]
    q = _check(c.get("/v1/queue", headers=env["blind"]), "get", "/v1/queue")
    assert [(i["position"], i["run_id"], i["decided"]) for i in q["items"]] == [
        (1, "run-p", False),
        (2, "run-x", False),
    ]
    assert q["next_position"] == 1
    assert _decide(env, "blind", "run-p", decision="escalate")[0] == 201
    q = c.get("/v1/queue", headers=env["blind"]).json()
    assert [i["decided"] for i in q["items"]] == [True, False]
    assert q["next_position"] == 2
    assert _decide(env, "blind", "run-x", decision="accept")[0] == 201
    assert c.get("/v1/queue", headers=env["blind"]).json()["next_position"] is None
    unassigned = c.get("/v1/queue", headers=env["reviewer"]).json()
    assert unassigned == {"key_id": "R1", "items": [], "next_position": None}
    assert c.get("/v1/queue", headers=env["reader"]).status_code == 403


def test_queue_is_removed_when_the_console_is_off(env: dict[str, Any]) -> None:
    env["config"].console = False
    resp = env["client"].get("/v1/queue", headers=env["blind"])
    assert _check(resp, "get", "/v1/queue")["status"] == 404


def test_blind_key_sees_only_its_cases_and_no_variant(env: dict[str, Any]) -> None:
    c, h = env["client"], env["blind"]
    full = _check(
        c.get("/v1/verdicts/run-p", headers=h), "get", "/v1/verdicts/{run_id}"
    )
    noexpl = c.get("/v1/verdicts/run-x", headers=h).json()
    assert full["variant"] is None and noexpl["variant"] is None
    assert full["narrative"] is not None and noexpl["narrative"] is None
    assert "HELIOS" not in json.dumps([full, noexpl])
    assert c.get("/v1/verdicts/run-c", headers=h).status_code == 404  # not assigned
    assert c.post("/v1/verdicts/run-c/views", headers=h).status_code == 404
    assert c.get("/v1/incidents", headers=h).status_code == 403
    assert c.get("/v1/incidents/inc-1", headers=h).status_code == 403
    coe = _check(
        c.get("/v1/verdicts/run-p/coe", headers=h), "get", "/v1/verdicts/{run_id}/coe"
    )
    assert set(coe["entry"]) == {"run_id", "steps"} and coe["ledger"] == ""
    assert coe["verified"] is True
    assert FULL not in json.dumps(coe)
    seen = c.get("/v1/verdicts/run-p", headers=env["reviewer"]).json()
    assert seen["variant"] == "HELIOS-Full"


def test_blind_key_sees_only_its_own_decisions(env: dict[str, Any]) -> None:
    assert _decide(env, "reviewer", "run-p", decision="escalate")[0] == 201
    assert _decide(env, "blind", "run-p", decision="reject")[0] == 201
    c = env["client"]
    mine = c.get("/v1/verdicts/run-p/decisions", headers=env["blind"]).json()
    assert [d["key_id"] for d in mine["decisions"]] == ["P1"]
    everyone = c.get("/v1/verdicts/run-p/decisions", headers=env["reader"]).json()
    assert [d["key_id"] for d in everyone["decisions"]] == ["R1", "P1"]


def test_chosen_service_rules(env: dict[str, Any]) -> None:
    # Ranked list in the fixture: checkout, email, ad, cart.
    status, d = _decide(env, "reviewer", "run-p", decision="accept")
    assert (status, d["chosen_service"]) == (201, "checkout")
    status, d = _decide(
        env, "reviewer", "run-p", decision="reject", chosen_service="ad"
    )
    assert (status, d["chosen_service"]) == (201, "ad")
    status, d = _decide(
        env, "reviewer", "run-p", decision="reject", chosen_service="none"
    )
    assert (status, d["chosen_service"]) == (201, "none")
    status, d = _decide(env, "reviewer", "run-p", decision="reject")
    assert (status, d["chosen_service"]) == (201, None)
    status, d = _decide(env, "reviewer", "run-p", decision="escalate")
    assert (status, d["chosen_service"]) == (201, None)
    for bad in (
        {"decision": "accept", "chosen_service": "email"},
        {"decision": "escalate", "chosen_service": "email"},
        {"decision": "reject", "chosen_service": "checkout"},
        {"decision": "reject", "chosen_service": "frontend"},
    ):
        assert _decide(env, "reviewer", "run-p", **bad)[0] == 400, bad


def test_hidden_time_and_simulated_tag_are_recorded(env: dict[str, Any]) -> None:
    status, d = _decide(
        env,
        "simulated",
        "run-p",
        decision="escalate",
        client_ms=1200,
        client_hidden_ms=350,
    )
    assert status == 201
    assert (d["simulated"], d["client_ms"], d["client_hidden_ms"]) == (True, 1200, 350)
    status, human = _decide(env, "reviewer", "run-p", decision="escalate")
    assert human["simulated"] is False and human["client_hidden_ms"] is None
    entries = read_entries(env["config"].decisions_path)
    assert [e["simulated"] for e in entries] == [True, True, False, False]
    assert DecisionLedger(key=SECRET, log_path=env["config"].decisions_path).verify()[0]
    bad = env["client"].post(
        "/v1/verdicts/run-p/decisions",
        headers=env["reviewer"],
        json={"decision": "accept", "view_token": "x" * 20, "client_hidden_ms": -1},
    )
    assert bad.status_code == 422


def test_key_attributes_round_trip(tmp_path: Path) -> None:
    keys = tmp_path / "k.json"
    add_key(keys, "P9", ["reviewer"], blind=True)
    add_key(keys, "S9", ["reviewer"], simulated=True)
    add_key(keys, "R9", ["reviewer"])
    stored = {k["id"]: k for k in json.loads(keys.read_text())["keys"]}
    assert stored["P9"]["blind"] is True and "simulated" not in stored["P9"]
    assert stored["S9"]["simulated"] is True and "blind" not in stored["S9"]
    assert set(stored["R9"]) == {"id", "sha256", "roles"}


def test_simulated_hitl_decides_every_review_run_once(env: dict[str, Any]) -> None:
    from bin import simulate_hitl as sim

    c, key = env["client"], env["simulated"]["X-API-Key"]
    counts = sim.simulate(c, "", key, "S1", sim.Policy("accept"), think_ms=900000)
    # run-p and run-x need review; run-c is confirmed; run-k is locked (423).
    assert counts == {"accept": 2}
    again = sim.simulate(c, "", key, "S1", sim.Policy("accept"), think_ms=900000)
    assert again == {"skipped": 2}
    entries = [
        e
        for e in read_entries(env["config"].decisions_path)
        if e["event"] == "decision"
    ]
    assert {e["run_id"] for e in entries} == {"run-p", "run-x"}
    assert all(e["simulated"] and e["client_ms"] == 900000 for e in entries)
    assert all(e["chosen_service"] == "checkout" for e in entries)


def test_simulated_hitl_policies_and_guards(env: dict[str, Any]) -> None:
    from bin import simulate_hitl as sim

    assert sim.Policy("escalate").decide({"confidence": 0.99}) == "escalate"
    gate = sim.Policy("confidence", threshold=0.9)
    assert gate.decide({"confidence": 0.95}) == "accept"
    assert gate.decide({"confidence": 0.85}) == "escalate"
    assert gate.decide({"confidence": None}) == "escalate"
    with pytest.raises(ValueError, match="threshold"):
        sim.Policy("confidence")
    with pytest.raises(ValueError, match="unknown"):
        sim.Policy("random")
    human = env["reviewer"]["X-API-Key"]
    with pytest.raises(sim.ApiError, match="not a simulated key"):
        sim.simulate(env["client"], "", human, "R1", sim.Policy("accept"), think_ms=1)
    with pytest.raises(sim.ApiError, match="HTTP 401"):
        sim.simulate(env["client"], "", "wrong", "R1", sim.Policy("accept"), think_ms=1)


def test_simulated_hitl_cli(
    env: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    import requests

    from bin import simulate_hitl as sim

    class Session:
        def __init__(self) -> None:
            self.client = env["client"]

        def __enter__(self) -> Any:
            return self.client

        def __exit__(self, *exc: object) -> None:
            return None

    monkeypatch.setattr(requests, "Session", Session)
    key_file = env["tmp"] / "sim.key"
    key_file.write_text(env["simulated"]["X-API-Key"] + "\n")
    argv = ["--api", "", "--key-file", str(key_file), "--key-id", "S1"]
    assert sim.main([*argv, "--policy", "escalate", "--limit", "1"]) == 0
    assert "{'escalate': 1}" in capsys.readouterr().out
