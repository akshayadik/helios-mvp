"""API v1 application factory (S4.1 design A-a to A-i; S4.2 K-e to K-g).

``create_app(ApiConfig(...))`` builds the FastAPI app over one campaign:
its store (read-only), its CoE ledgers (verified with the public key alone)
and its decisions ledger. Errors are RFC 9457 problem details.

S4.2 adds the review queue (``GET /v1/queue``, from an admin-written
assignments file), blind keys (RQ4 participants: only their assigned cases,
never a variant name, a CoE entry reduced to its citable evidence, only their
own decisions) and three decision fields (``chosen_service``,
``client_hidden_ms``, ``simulated``).
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from helios.actions.modes import ActionMode
from helios.api import API_VERSION, HELIOS_ENABLE_CONSOLE
from helios.api.auth import ApiKey, KeyStore
from helios.api.decisions import (
    TOKEN_TTL_S,
    DecisionLedger,
    TokenError,
    ViewTokens,
    read_entries,
)
from helios.api.models import (
    ActionOut,
    Claim,
    CoEOut,
    DecisionIn,
    DecisionOut,
    DecisionsOut,
    Health,
    IncidentDetail,
    IncidentPage,
    IncidentSummary,
    Narrative,
    Problem,
    QueueItem,
    QueueOut,
    RankedService,
    RunSummary,
    TriggerOut,
    Verdict,
    ViewOut,
)
from helios.api.reader import StoreReader
from helios.telemetry.pool_lock import BUILD_FREEZE_TAG, build_frozen
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.ed25519 import load_public_key
from helios.vcl.hmac_chain import verify_public

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

__all__ = ["ApiConfig", "create_app"]

_HUMAN_STATES = frozenset({"provisional", "non_converged"})
NONE_OF_THESE = "none"  # a reject whose root cause is not in the ranked list
_PROBLEM = "application/problem+json"
_ROUND = 3


@dataclass
class ApiConfig:
    store_path: Path
    coe_dir: Path | None
    decisions_path: Path
    keys_path: Path
    decisions_secret: bytes
    public_key_path: Path
    frozen: Callable[[], bool] = build_frozen
    clock: Callable[[], float] = time.time
    token_ttl_s: float = TOKEN_TTL_S
    assignments_path: Path | None = None
    console: bool = HELIOS_ENABLE_CONSOLE
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


def _problem(status: int, title: str, detail: str | None = None) -> JSONResponse:
    body = Problem(title=title, status=status, detail=detail).model_dump()
    return JSONResponse(body, status_code=status, media_type=_PROBLEM)


def _json_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = json.loads(value) if value.startswith("[") else [value]
    return [str(v) for v in value]


class _CoEIndex:
    """run_id -> (ledger file, entry), each file verified once (public key)."""

    def __init__(self, coe_dir: Path | None, public_key_path: Path) -> None:
        self.entries: dict[str, tuple[str, dict[str, Any]]] = {}
        self.status: dict[str, tuple[bool, str]] = {}
        if coe_dir is None or not coe_dir.is_dir():
            return
        public = load_public_key(public_key_path)
        for path in sorted(coe_dir.glob("*.coe.jsonl")):
            anchor = path.with_name(f"{path.stem}.anchor.json")
            ok, msg = verify_public(
                path, anchor, public, from_entry=None, log_kind="coe"
            )
            self.status[path.name] = (ok, msg)
            for entry in read_entries(path):
                self.entries[str(entry["run_id"])] = (path.name, entry)


def load_assignments(path: Path | None) -> dict[str, list[str]]:
    """Key ID -> ordered run IDs (``{"assignments": {...}}``); none if absent."""
    if path is None or not path.is_file():
        return {}
    body = json.loads(path.read_text()).get("assignments", {})
    return {str(k): [str(r) for r in runs] for k, runs in body.items()}


def blind_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """A CoE entry reduced to what citations resolve to (the evidence items
    and the F step), without the variant hash or parameter hashes (K-e)."""
    steps = [
        {"id": s.get("id"), "items": s["items"]}
        for s in entry["steps"]
        if s.get("items")
    ]
    steps += [
        {"id": "F", "ranked": s.get("ranked"), "confidence": s.get("confidence")}
        for s in entry["steps"]
        if s.get("id") == "F"
    ]
    return {"run_id": entry["run_id"], "steps": steps}


def _key_of(request: Request, x_api_key: str | None) -> ApiKey:
    key = request.app.state.keys.lookup(x_api_key)
    if key is None:
        raise HTTPException(401, "missing or unknown API key")
    return key  # type: ignore[no-any-return]


def _reader(
    request: Request, x_api_key: Annotated[str | None, Header()] = None
) -> ApiKey:
    return _key_of(request, x_api_key)


def _reviewer(
    request: Request, x_api_key: Annotated[str | None, Header()] = None
) -> ApiKey:
    key = _key_of(request, x_api_key)
    if not key.allows("reviewer"):
        raise HTTPException(403, "this key lacks the reviewer role")
    return key


ReaderKey = Annotated[ApiKey, Depends(_reader)]
ReviewerKey = Annotated[ApiKey, Depends(_reviewer)]
Limit = Annotated[int, Query(ge=1, le=500)]
Offset = Annotated[int, Query(ge=0)]


def create_app(config: ApiConfig) -> FastAPI:
    reader = StoreReader(config.store_path)
    keys = KeyStore(config.keys_path)
    tokens = ViewTokens(config.decisions_secret, ttl_s=config.token_ttl_s)
    ledger = DecisionLedger(key=config.decisions_secret, log_path=config.decisions_path)
    if not ledger.anchor_path.exists() and not config.decisions_path.exists():
        config.decisions_path.parent.mkdir(parents=True, exist_ok=True)
        config.decisions_path.touch()
        ledger.init_anchor()
    coe = _CoEIndex(config.coe_dir, config.public_key_path)
    assignments = load_assignments(config.assignments_path)

    app = FastAPI(
        title="HELIOS API",
        version=API_VERSION,
        description=(
            "Stored HELIOS verdicts and the human decisions on them (S4.1). "
            "Never returns ground truth or metrics derived from it."
        ),
        responses={
            401: {"model": Problem, "description": "No or unknown API key"},
            403: {"model": Problem, "description": "The key lacks the role"},
            422: {"model": Problem, "description": "Invalid request"},
        },
    )

    @app.exception_handler(HTTPException)
    def _http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return _problem(exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    def _invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _problem(422, "invalid request", json.dumps(exc.errors(), default=str))

    app.state.keys = keys

    def run_or_404(run_id: str) -> dict[str, Any]:
        fusion = reader.fusion(run_id)
        if fusion is None:
            raise HTTPException(404, "no such run")
        if reader.phase(run_id) == "confirmatory" and not config.frozen():
            raise HTTPException(
                423, f"confirmatory runs are locked until tag {BUILD_FREEZE_TAG!r}"
            )
        return fusion

    def coe_step(run_id: str, step_id: str) -> dict[str, Any] | None:
        found = coe.entries.get(run_id)
        if found is None:
            return None
        return next((s for s in found[1]["steps"] if s.get("id") == step_id), None)

    def shadow_hidden(run_id: str, incident_id: str, key: ApiKey) -> bool:
        """S4.5 shadow mode: responders see a run only once a person has
        decided on its incident; admin keys always see it."""
        action = coe_step(run_id, "A")
        if action is None or action.get("mode") != ActionMode.SHADOW.value:
            return False
        if key.allows("admin"):
            return False
        return not any(
            e["event"] == "decision" and e["incident_id"] == incident_id
            for e in read_entries(config.decisions_path)
        )

    def visible_run(run_id: str, key: ApiKey) -> dict[str, Any]:
        """The run for this key: a blind key sees only its assigned cases, a
        shadow run is hidden from responders until its incident is decided,
        and any other run is reported as absent."""
        if key.blind and run_id not in assignments.get(key.id, []):
            raise HTTPException(404, "no such run")
        fusion = run_or_404(run_id)
        if shadow_hidden(run_id, str(fusion["incident_id"]), key):
            raise HTTPException(404, "no such run")
        return fusion

    def action_of(run_id: str) -> ActionOut | None:
        step = coe_step(run_id, "A")
        if step is None:
            return None
        proposal = step.get("proposal", {})
        return ActionOut(
            kind=str(proposal.get("kind", "none")),
            target=proposal.get("target"),
            mode=str(step.get("mode", ActionMode.RECOMMEND.value)),
            validation=str(step.get("verdict", "")),
            reason=str(step.get("reason", "")),
        )

    def degraded_of(run_id: str) -> str | None:
        step = coe_step(run_id, "S")
        if step is None:
            return None
        value = step.get("measured", {}).get("degraded")
        return None if value is None else str(value)

    def not_blind(key: ApiKey) -> None:
        if key.blind:
            raise HTTPException(403, "a participant key sees only its queue")

    def summary(row: dict[str, Any]) -> RunSummary:
        state = str(row["state"])
        return RunSummary(
            run_id=str(row["run_id"]),
            variant=reader.variant(str(row["variant_config_hash"])).name,
            state=state,
            needs_review=state in _HUMAN_STATES,
            confidence=row["confidence"],
            top3=_json_list(row["ranked_json"])[:3],
        )

    def decisions_of(run_id: str) -> Iterator[dict[str, Any]]:
        for e in read_entries(config.decisions_path):
            if e["event"] == "decision" and e["run_id"] == run_id:
                yield e

    def decision_out(e: dict[str, Any]) -> DecisionOut:
        return DecisionOut(
            run_id=e["run_id"],
            incident_id=e["incident_id"],
            key_id=e["key_id"],
            decision=e["decision"],
            note=e.get("note") or None,
            shown_at=float(e["shown_at"]),
            decided_at=float(e["decided_at"]),
            decision_ms=float(e["decision_ms"]),
            client_ms=None if e.get("client_ms") is None else float(e["client_ms"]),
            client_hidden_ms=(
                None
                if e.get("client_hidden_ms") is None
                else float(e["client_hidden_ms"])
            ),
            chosen_service=e.get("chosen_service"),
            simulated=bool(e.get("simulated", False)),
            signature=e["signature"],
        )

    @app.get("/health", response_model=Health, tags=["health"])
    def health() -> Health:
        ok, msg = ledger.verify()
        coe_status = {k: v[1] for k, v in coe.status.items()}
        degraded = not ok or not all(v[0] for v in coe.status.values())
        return Health(
            status="degraded" if degraded else "ok",
            api_version=API_VERSION,
            schema_tags=reader.schema_tags(),
            build_frozen=config.frozen(),
            incidents=reader.count_incidents(),
            keys_configured=len(keys),
            decisions_ledger=msg,
            coe_ledgers=coe_status,
        )

    @app.get("/v1/incidents", response_model=IncidentPage, tags=["incidents"])
    def incidents(
        key: ReaderKey,
        limit: Limit = 50,
        offset: Offset = 0,
    ) -> IncidentPage:
        not_blind(key)
        items = [IncidentSummary(**r) for r in reader.incidents(limit, offset)]
        return IncidentPage(
            items=items, total=reader.count_incidents(), limit=limit, offset=offset
        )

    @app.get(
        "/v1/incidents/{incident_id}",
        response_model=IncidentDetail,
        responses={404: {"model": Problem}},
        tags=["incidents"],
    )
    def incident(incident_id: str, key: ReaderKey) -> IncidentDetail:
        not_blind(key)
        rows = reader.runs_of(incident_id)
        if not rows:
            raise HTTPException(404, "no such incident")
        runs = [
            summary(r)
            for r in rows
            if (reader.phase(str(r["run_id"])) != "confirmatory" or config.frozen())
            and not shadow_hidden(str(r["run_id"]), incident_id, key)
        ]
        return IncidentDetail(incident_id=incident_id, runs=runs)

    @app.get(
        "/v1/verdicts/{run_id}",
        response_model=Verdict,
        responses={404: {"model": Problem}, 423: {"model": Problem}},
        tags=["verdicts"],
    )
    def verdict(run_id: str, key: ReaderKey) -> Verdict:
        f = visible_run(run_id, key)
        variant = reader.variant(str(f["variant_config_hash"]))
        scores = json.loads(f["scores_json"] or "{}")
        ranked = _json_list(f["ranked_json"])
        trig = reader.trigger(run_id)
        routing = reader.routing(run_id) or {}
        narrative = None
        stored = reader.narrative(run_id) if variant.narrative else None
        if stored is not None:
            slots = json.loads(stored["slots_json"] or "{}")
            narrative = Narrative(
                narrator=str(stored["narrator"]),
                rendered=str(stored["rendered"]),
                claims=[
                    Claim(
                        slot=slot,
                        kind=str(c.get("kind", "")),
                        sentence=str(c.get("sentence", "")),
                        cites=[str(x) for x in c.get("cites", [])],
                    )
                    for slot, body in slots.items()
                    for c in body.get("claims", [])
                ],
                template_fallbacks=int(stored["fallbacks"]),
            )
        state = str(f["state"])
        return Verdict(
            run_id=run_id,
            incident_id=str(f["incident_id"]),
            variant=None if key.blind else variant.name,
            state=state,
            needs_review=state in _HUMAN_STATES,
            non_converged=bool(f["non_converged"]),
            confidence=f["confidence"],
            ranked=[
                RankedService(rank=i + 1, service=s, score=scores.get(s))
                for i, s in enumerate(ranked)
            ],
            first_ranked=_json_list(f["first_ranked_json"]),
            first_published_ms=f["first_ms"],
            terminal_published_ms=f["terminal_ms"],
            escalated=bool(routing["escalate"]) if "escalate" in routing else None,
            trigger=(
                None
                if trig is None
                else TriggerOut(
                    time_s=float(trig["trigger_time_s"]),
                    suspects=_json_list(trig["suspects"]),
                    source=str(trig["source"]),
                )
            ),
            narrative=narrative,
            action=None if key.blind else action_of(run_id),
            control_plane_degraded=None if key.blind else degraded_of(run_id),
        )

    @app.get(
        "/v1/verdicts/{run_id}/coe",
        response_model=CoEOut,
        responses={404: {"model": Problem}, 423: {"model": Problem}},
        tags=["verdicts"],
    )
    def chain_of_evidence(run_id: str, key: ReaderKey) -> CoEOut:
        visible_run(run_id, key)
        if run_id not in coe.entries:
            raise HTTPException(404, "no CoE entry for this run")
        name, entry = coe.entries[run_id]
        ok, msg = coe.status[name]
        return CoEOut(
            run_id=run_id,
            ledger="" if key.blind else name,
            verified=ok,
            verification=msg,
            entry=blind_entry(entry) if key.blind else entry,
        )

    @app.post(
        "/v1/verdicts/{run_id}/views",
        response_model=ViewOut,
        status_code=201,
        responses={404: {"model": Problem}, 423: {"model": Problem}},
        tags=["decisions"],
    )
    def open_view(run_id: str, key: ReviewerKey) -> ViewOut:
        f = visible_run(run_id, key)
        now = config.clock()
        text, token = tokens.issue(run_id, key.id, now)
        with config._lock:
            ledger.append(
                {
                    "event": "view",
                    "run_id": run_id,
                    "incident_id": str(f["incident_id"]),
                    "key_id": key.id,
                    "token_digest": token.digest,
                    "shown_at": round(now, _ROUND),
                    "simulated": key.simulated,
                }
            )
        return ViewOut(
            run_id=run_id,
            view_token=text,
            issued_at=now,
            expires_at=now + config.token_ttl_s,
        )

    @app.post(
        "/v1/verdicts/{run_id}/decisions",
        response_model=DecisionOut,
        status_code=201,
        responses={
            400: {"model": Problem},
            404: {"model": Problem},
            409: {"model": Problem, "description": "View token already used"},
            410: {"model": Problem, "description": "View token expired"},
            423: {"model": Problem},
        },
        tags=["decisions"],
    )
    def decide(run_id: str, body: DecisionIn, key: ReviewerKey) -> DecisionOut:
        f = visible_run(run_id, key)
        chosen = chosen_service(body, _json_list(f["ranked_json"]))
        now = config.clock()
        try:
            token = tokens.check(body.view_token, run_id=run_id, key_id=key.id, now=now)
        except TokenError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        with config._lock:
            if any(e.get("token_digest") == token.digest for e in decisions_of(run_id)):
                raise HTTPException(409, "this view token was already used")
            entry = ledger.append(
                {
                    "event": "decision",
                    "run_id": run_id,
                    "incident_id": str(f["incident_id"]),
                    "variant_config_hash": str(f["variant_config_hash"]),
                    "key_id": key.id,
                    "decision": body.decision,
                    "note": body.note or "",
                    "token_digest": token.digest,
                    "shown_at": round(token.issued_at, _ROUND),
                    "decided_at": round(now, _ROUND),
                    "decision_ms": round(tokens.decision_ms(token, now), _ROUND),
                    "client_ms": body.client_ms,
                    "client_hidden_ms": body.client_hidden_ms,
                    "chosen_service": chosen,
                    "simulated": key.simulated,
                }
            )
        return decision_out(entry)

    @app.get(
        "/v1/verdicts/{run_id}/decisions",
        response_model=DecisionsOut,
        responses={404: {"model": Problem}, 423: {"model": Problem}},
        tags=["decisions"],
    )
    def decisions(run_id: str, key: ReaderKey) -> DecisionsOut:
        visible_run(run_id, key)
        out = [
            decision_out(e)
            for e in decisions_of(run_id)
            if not key.blind or e["key_id"] == key.id
        ]
        return DecisionsOut(
            run_id=run_id, decisions=out, latest=out[-1].decision if out else None
        )

    @app.get(
        "/v1/queue",
        response_model=QueueOut,
        responses={404: {"model": Problem}},
        tags=["decisions"],
    )
    def queue(key: ReviewerKey) -> QueueOut:
        if not config.console:
            raise HTTPException(404, "the approval console is disabled")
        decided = {
            e["run_id"]
            for e in read_entries(config.decisions_path)
            if e["event"] == "decision" and e["key_id"] == key.id
        }
        items = [
            QueueItem(position=i + 1, run_id=r, decided=r in decided)
            for i, r in enumerate(assignments.get(key.id, []))
        ]
        pending = [q.position for q in items if not q.decided]
        return QueueOut(
            key_id=key.id, items=items, next_position=pending[0] if pending else None
        )

    return app


def chosen_service(body: DecisionIn, ranked: list[str]) -> str | None:
    """The service a decision names (K-e): the top-ranked one on accept,
    nothing on escalate, and on reject an optional pick from the ranked list
    (not the top one) or ``none``. Anything else is a 400."""
    pick = body.chosen_service
    top = ranked[0] if ranked else None
    if body.decision == "accept":
        if pick is not None and pick != top:
            raise HTTPException(400, "accept names the top-ranked service only")
        return top
    if body.decision == "escalate":
        if pick is not None:
            raise HTTPException(400, "escalate does not name a service")
        return None
    if pick is None:
        return None
    if pick != NONE_OF_THESE and (pick not in ranked or pick == top):
        raise HTTPException(
            400, "reject names a lower-ranked service from the list, or 'none'"
        )
    return pick
