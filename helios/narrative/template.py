"""Template narrator: deterministic, no model (S2.8 design §5.3, owner N-a).

noLLM, HELIOS-D and HELIOS-G narrate only from this code; the LLM narrator
falls back to it slot by slot. It emits the same typed claims and sentence
shapes the LLM prompt asks for, so both pass one verifier and one renderer.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from helios.narrative.claims import SLOTS, Claim, ClaimKind
from helios.narrative.verifier import LOG_PREFIX, log_template_text, verify
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping

    from helios.narrative.params import NarratorParams

__all__ = ["candidate_claims", "template_slots"]

_ORDINALS = ("top", "second", "third")
_PIPELINES = {"dpipe": "D-pipe", "gpipe": "G-pipe", "lpipe": "L-pipe"}
_CHANNEL_LABEL = {"error": "errors", "latency": "latency", "resource": "resource use"}
_SNIPPET_CHARS = 120


def _steps(entry: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(s["id"]): s for s in entry["steps"]}


def _items(entry: Mapping[str, Any], prefix: str, service: str) -> list[dict[str, Any]]:
    return [
        i
        for s in entry["steps"]
        for i in s.get("items", [])
        if i["id"].startswith(prefix)
        and i.get("service") == service
        and ":claim" not in i["id"]
    ]


def _fmt(x: float) -> str:
    """A number as the sentence states it (the verifier accepts it at that
    precision)."""
    if abs(x) >= 100:
        return f"{x:.0f}"
    if abs(x) >= 1:
        return f"{x:.1f}"
    return f"{x:.3f}"


def _unit_text(unit: str) -> str:
    return {"ms": " ms", "errors/step": " per step"}.get(unit, "")


def _strongest_shift(entry: Mapping[str, Any], svc: str) -> dict[str, Any] | None:
    channels = [
        i
        for i in _items(entry, f"D:{svc}:", svc)
        if i["id"].split(":")[-1] in _CHANNEL_LABEL
        and isinstance(i.get("value"), int | float)
        and i["value"] > 0
    ]
    return max(channels, key=lambda i: (i["value"], i["id"]), default=None)


def _shift_claim(item: Mapping[str, Any], svc: str) -> Claim:
    channel = item["id"].split(":")[-1]
    unit = str(item.get("unit", ""))
    label = _CHANNEL_LABEL[channel]
    if channel == "resource" and unit and unit not in ("ms", "errors/step"):
        label = f"{unit} use"
    before, after = item.get("before"), item.get("after")
    if isinstance(before, int | float) and isinstance(after, int | float):
        direction = "up" if after > before else "down"
        verb = "rose" if direction == "up" else "fell"
        u = _unit_text(unit)
        sentence = f"{svc} {label} {verb} from {_fmt(before)}{u} to {_fmt(after)}{u}."
    else:
        direction = "up"
        sentence = f"{svc} {label} rose sharply after the trigger."
    return Claim(
        kind=ClaimKind.SHIFT,
        sentence=sentence,
        cites=(item["id"],),
        service=svc,
        channel=channel,
        direction=direction,
    )


def _percent(share: float) -> str:
    return f"{share * 100:.0f}"


def _shares(value: Any) -> dict[str, float]:
    """Wait shares worth stating: those that do not round to 0% (review M1)."""
    if not isinstance(value, dict):
        return {}
    return {k: v for k, v in value.items() if _percent(v) != "0"}


def _graph_claim(entry: Mapping[str, Any], svc: str) -> Claim | None:
    items = {i["id"]: i for i in _items(entry, f"G:{svc}:", svc)}
    wait = items.get(f"G:{svc}:wait_from")
    if wait and _shares(wait.get("value")):
        shares = _shares(wait.get("value"))
        caller, share = max(shares.items(), key=lambda kv: (kv[1], kv[0]))
        return Claim(
            kind=ClaimKind.CALL_STRUCTURE,
            sentence=f"{caller} spent {_percent(share)}% of its time waiting on {svc}.",
            cites=(wait["id"],),
            caller=caller,
            callee=svc,
            feature="wait",
        )
    leads = items.get(f"G:{svc}:leads")
    if leads and isinstance(leads.get("value"), list) and leads["value"]:
        caller = sorted(leads["value"])[0]
        return Claim(
            kind=ClaimKind.CALL_STRUCTURE,
            sentence=f"{svc} moved before its caller {caller}.",
            cites=(leads["id"],),
            caller=caller,
            callee=svc,
            feature="lead",
        )
    ghosts = items.get(f"G:{svc}:ghost_edges")
    if ghosts and isinstance(ghosts.get("value"), list) and ghosts["value"]:
        caller, callee = sorted(ghosts["value"])[0]
        return Claim(
            kind=ClaimKind.CALL_STRUCTURE,
            sentence=f"{caller} started calling {callee} after the trigger.",
            cites=(ghosts["id"],),
            caller=caller,
            callee=callee,
            feature="ghost",
        )
    return None


def _graph_claims(entry: Mapping[str, Any], svc: str) -> list[Claim]:
    """Every call-graph claim about ``svc`` (the template keeps only the first)."""
    items = {i["id"]: i for i in _items(entry, f"G:{svc}:", svc)}
    out = []
    wait = items.get(f"G:{svc}:wait_from")
    if wait:
        for caller, share in sorted(
            _shares(wait.get("value")).items(), key=lambda kv: (-kv[1], kv[0])
        ):
            out.append(
                Claim(
                    kind=ClaimKind.CALL_STRUCTURE,
                    sentence=(
                        f"{caller} spent {_percent(share)}% of its time waiting on "
                        f"{svc}."
                    ),
                    cites=(wait["id"],),
                    caller=caller,
                    callee=svc,
                    feature="wait",
                )
            )
    leads = items.get(f"G:{svc}:leads")
    if leads and isinstance(leads.get("value"), list):
        for caller in sorted(leads["value"]):
            out.append(
                Claim(
                    kind=ClaimKind.CALL_STRUCTURE,
                    sentence=f"{svc} moved before its caller {caller}.",
                    cites=(leads["id"],),
                    caller=caller,
                    callee=svc,
                    feature="lead",
                )
            )
    ghosts = items.get(f"G:{svc}:ghost_edges")
    if ghosts and isinstance(ghosts.get("value"), list):
        for caller, callee in sorted(ghosts["value"]):
            out.append(
                Claim(
                    kind=ClaimKind.CALL_STRUCTURE,
                    sentence=f"{caller} started calling {callee} after the trigger.",
                    cites=(ghosts["id"],),
                    caller=caller,
                    callee=callee,
                    feature="ghost",
                )
            )
    return out


def _snippet(text: str, params: NarratorParams) -> str | None:
    """The first words of a log line, cut at a word boundary, as long as the
    verifier requires (N-j); None when the line is too short or multi-line."""
    raw = text.strip()
    if "\n" in raw or '"' in raw:
        return None
    if len(raw) > _SNIPPET_CHARS:
        cut = raw[:_SNIPPET_CHARS]
        raw = cut[: cut.rfind(" ")] if " " in cut else ""
        raw = raw.strip()
    return raw if len(raw) >= params.min_snippet_chars else None


def _log_claims(
    entry: Mapping[str, Any], svc: str, params: NarratorParams
) -> list[Claim]:
    out = []
    for item in _items(entry, LOG_PREFIX, svc):
        logged = log_template_text(str(item.get("text", "")))
        snippet = None if logged is None else _snippet(logged, params)
        if snippet is not None:
            out.append(
                Claim(
                    kind=ClaimKind.LOG_MESSAGE,
                    sentence=f'{svc} logged "{snippet}".',
                    cites=(item["id"],),
                    service=svc,
                    snippet=snippet,
                )
            )
    return out


def _log_claim(
    entry: Mapping[str, Any], svc: str, params: NarratorParams
) -> Claim | None:
    return next(iter(_log_claims(entry, svc, params)), None)


def _story(
    entry: Mapping[str, Any], ranked: list[str], params: NarratorParams
) -> list[Claim]:
    claims: list[Claim] = []
    for rank, svc in enumerate(ranked[:3], start=1):
        claims.append(
            Claim(
                kind=ClaimKind.RANKING,
                sentence=f"{svc} is the {_ORDINALS[rank - 1]} suspect.",
                cites=("F",),
                service=svc,
                rank=rank,
            )
        )
        if shift := _strongest_shift(entry, svc):
            claims.append(_shift_claim(shift, svc))
        if graph := _graph_claim(entry, svc):
            claims.append(graph)
        if log := _log_claim(entry, svc, params):
            claims.append(log)
    return claims


def _contradictions(entry: Mapping[str, Any], top: str) -> list[Claim]:
    steps = _steps(entry)
    claims = []
    for pipeline in steps["F"].get("disagree") or []:
        ranked = list(steps.get(f"P:{pipeline}", {}).get("ranked") or [])
        if not ranked:
            continue
        svc = ranked[0]
        prefix = {"dpipe": "D:", "gpipe": "G:", "lpipe": "L:"}[pipeline]
        own = _items(entry, prefix, svc)
        if not own:
            continue
        name = _PIPELINES[pipeline]
        claims.append(
            Claim(
                kind=ClaimKind.CONTRADICTION,
                sentence=(
                    f"{name} ranks {svc} first, while the fused verdict ranks "
                    f"{top} first."
                ),
                cites=(own[0]["id"],),
                pipeline=pipeline,
                service=svc,
            )
        )
    return claims


def _clock(iso: str) -> str:
    return dt.datetime.fromisoformat(iso).strftime("%H:%M")


def _verification(
    entry: Mapping[str, Any], top: str, params: NarratorParams
) -> list[Claim]:
    return _checks(entry, top)[: params.max_steps]


def _checks(entry: Mapping[str, Any], top: str) -> list[Claim]:
    """Read-only checks on one service: its strongest metric, logs, calls."""
    t = _steps(entry)["T"]
    if not t.get("window_start") or not t.get("window_end"):
        return []
    span = (
        f"between {_clock(str(t['window_start']))} and {_clock(str(t['window_end']))}"
    )
    steps: list[Claim] = []
    shift = _strongest_shift(entry, top)
    if shift:
        label = _CHANNEL_LABEL[shift["id"].split(":")[-1]]
        steps.append(
            Claim(
                kind=ClaimKind.VERIFICATION_STEP,
                sentence=f"Query {top} {label} {span}.",
                cites=(shift["id"],),
                target_service=top,
                action_verb="query",
                modality="metric",
            )
        )
    logs = _items(entry, LOG_PREFIX, top)
    if logs:
        steps.append(
            Claim(
                kind=ClaimKind.VERIFICATION_STEP,
                sentence=f"Filter {top} logs {span}.",
                cites=(logs[0]["id"],),
                target_service=top,
                action_verb="filter",
                modality="log",
            )
        )
    graph = _items(entry, "G:", top)
    if graph:
        steps.append(
            Claim(
                kind=ClaimKind.VERIFICATION_STEP,
                sentence=f"Inspect {top} incoming calls {span}.",
                cites=(graph[0]["id"],),
                target_service=top,
                action_verb="inspect",
                modality="edge",
            )
        )
    return steps


def template_slots(
    entry: Mapping[str, Any], params: NarratorParams
) -> dict[str, list[Claim]]:
    """Story, contradictions and verification steps from the entry alone."""
    ranked = list(_steps(entry)["F"].get("ranked") or [])
    if not ranked:
        return {slot: [] for slot in SLOTS}
    return {
        "story": _story(entry, ranked, params),
        "contradictions": _contradictions(entry, ranked[0]),
        "verification": _verification(entry, ranked[0], params),
    }


def _ranking(ranked: list[str]) -> list[Claim]:
    return [
        Claim(
            kind=ClaimKind.RANKING,
            sentence=f"{svc} is the {_ORDINALS[rank - 1]} suspect.",
            cites=("F",),
            service=svc,
            rank=rank,
        )
        for rank, svc in enumerate(ranked[:3], start=1)
    ]


def candidate_claims(
    entry: Mapping[str, Any], params: NarratorParams
) -> dict[str, list[Claim]]:
    """Every claim per slot the entry supports, in the template's wording
    (owner decision (b), 2026-11-01): the LLM narrator picks and orders from
    these. Only claims the verifier accepts are offered; a superset of the
    template's own slots."""
    ranked = list(_steps(entry)["F"].get("ranked") or [])
    if not ranked:
        return {slot: [] for slot in SLOTS}
    story: list[Claim] = []
    steps: list[Claim] = []
    for svc in ranked[:3]:
        story += [
            _shift_claim(i, svc)
            for i in _items(entry, f"D:{svc}:", svc)
            if i["id"].split(":")[-1] in _CHANNEL_LABEL
            and isinstance(i.get("value"), int | float)
            and i["value"] > 0
        ]
        story += _graph_claims(entry, svc) + _log_claims(entry, svc, params)
        steps += _checks(entry, svc)
    out = {
        "story": _ranking(ranked) + story,
        "contradictions": _contradictions(entry, ranked[0]),
        "verification": steps,
    }
    return {slot: _unique(claims, entry, params) for slot, claims in out.items()}


def _unique(
    claims: list[Claim], entry: Mapping[str, Any], params: NarratorParams
) -> list[Claim]:
    """Verified claims, each sentence once (review I2: a ghost edge between two
    top-3 services is in both services' items)."""
    seen: set[tuple[str, str]] = set()
    out = []
    for c in claims:
        key = (c.kind.value, c.sentence)
        if key not in seen and verify(c, entry, params) is None:
            seen.add(key)
            out.append(c)
    return out
