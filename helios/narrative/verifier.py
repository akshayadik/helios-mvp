"""Grounding verifier (S2.8 design §5.2, §5.5; owner decisions N-b, N-c, N-f,
N-g and N-j).

``verify`` accepts a claim only if every cite is an item (or the ``F`` step) of
the run's CoE entry, the kind's rule holds against the cited items, and the
sentence is contained (N-j, closed vocabulary): one line, no brackets or
citation IDs; only the claim's own services; every other word from the frozen
word list of its kind; rank, channel, direction, edge order and pipeline name
agreeing with the claim's fields; every number from the claim's own evidence in
its own unit; times only in verification steps and inside the window. Pure and
deterministic: it reads the entry and the frozen parameters only.
"""

from __future__ import annotations

import datetime as dt
import re
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from helios.narrative.claims import Claim, ClaimKind
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from helios.narrative.params import NarratorParams

__all__ = ["Reason", "entry_services", "mentions", "verify"]


class Reason(StrEnum):
    """Why a claim was rejected (closed set, design §5.5 and N-j)."""

    MISSING_CITE = "missing_cite"
    UNKNOWN_ID = "unknown_id"
    KIND_MISMATCH = "kind_mismatch"
    WRONG_DIRECTION = "wrong_direction"
    WRONG_EDGE = "wrong_edge"
    SNIPPET_NOT_FOUND = "snippet_not_found"
    FOREIGN_SERVICE = "foreign_service"
    NUMBER_NOT_IN_EVIDENCE = "number_not_in_evidence"
    TIME_OUT_OF_WINDOW = "time_out_of_window"
    VERB_NOT_ALLOWED = "verb_not_allowed"
    MODALITY_MISMATCH = "modality_mismatch"
    RANK_MISMATCH = "rank_mismatch"
    NOT_IN_DISAGREE = "not_in_disagree"
    SCHEMA = "schema"
    WORD_NOT_ALLOWED = "word_not_allowed"
    MALFORMED_SENTENCE = "malformed_sentence"


_MODALITY_PREFIX = {"metric": "D:", "log": "L:", "edge": "G:"}
_TIME = re.compile(r"(\d{1,2}):(\d{2})(?::(\d{2}))?")
_NUMBER = re.compile(r"(\d+(?:\.\d+)?)(%|ms|s)?")
_CITE = re.compile(r"\b[DGL]:\S")
_STRIP = ".,;:!?()~\"'"
_UNIT_WORDS = {
    "%": "%",
    "ms": "ms",
    "milliseconds": "ms",
    "millisecond": "ms",
    "s": "s",
    "sec": "s",
    "secs": "s",
    "seconds": "s",
}
_PUNCT = re.compile(r"[,;:]")


def _steps(entry: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(s["id"]): s for s in entry["steps"]}


def _items(entry: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {i["id"]: i for s in entry["steps"] for i in s.get("items", [])}


def _citable(entry: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Evidence items and the F step; worker claims are model output, not
    evidence (design §4)."""
    items = {k: v for k, v in _items(entry).items() if ":claim" not in k}
    items["F"] = _steps(entry)["F"]
    return items


def entry_services(entry: Mapping[str, Any]) -> set[str]:
    """Every service name the entry mentions (items, rankings, graph edges)."""
    names: set[str] = set()
    for step in entry["steps"]:
        names.update(step.get("ranked") or [])
        for item in step.get("items", []):
            if item.get("service"):
                names.add(item["service"])
            if item["id"].startswith("G:"):
                names |= _names_in(item.get("value"))
    return {n for n in names if isinstance(n, str) and n}


def _spans(text: str, names: Iterable[str]) -> list[tuple[int, int, str]]:
    """Whole-token mentions (word and hyphen boundaries), longest name first."""
    found: list[tuple[int, int, str]] = []
    taken = [False] * len(text)
    for name in sorted(set(names), key=lambda n: (-len(n), n)):
        pattern = rf"(?<![A-Za-z0-9_-]){re.escape(name)}(?![A-Za-z0-9_-])"
        for m in re.finditer(pattern, text, re.IGNORECASE):
            if not any(taken[m.start() : m.end()]):
                found.append((m.start(), m.end(), name))
                for k in range(m.start(), m.end()):
                    taken[k] = True
    return sorted(found)


def mentions(text: str, names: Iterable[str]) -> set[str]:
    """Service names in ``text`` as whole tokens, so ``cart`` is not found
    inside ``cartservice``."""
    return {name for _, _, name in _spans(text, names)}


def _names_in(value: Any) -> set[str]:
    if isinstance(value, dict):
        return {k for k in value if isinstance(k, str)}
    if isinstance(value, list):
        out: set[str] = set()
        for v in value:
            out |= _names_in(v) if isinstance(v, list) else {str(v)}
        return out
    return set()


def _edge_holds(claim: Claim, item: Mapping[str, Any]) -> bool:
    """The cited G-pipe item holds the claim's directed edge (caller → callee)."""
    value = item.get("value")
    if claim.feature == "wait" and item["id"] == f"G:{claim.callee}:wait_from":
        return isinstance(value, dict) and claim.caller in value
    if claim.feature == "lead" and item["id"] == f"G:{claim.callee}:leads":
        return isinstance(value, list) and claim.caller in value
    if claim.feature == "ghost" and item["id"].endswith(":ghost_edges"):
        return isinstance(value, list) and [claim.caller, claim.callee] in value
    return False


def _direction_of(item: Mapping[str, Any]) -> str | None:
    before, after = item.get("before"), item.get("after")
    if isinstance(before, int | float) and isinstance(after, int | float):
        return None if after == before else ("up" if after > before else "down")
    value = item.get("value")
    if isinstance(value, int | float) and value:
        return "up" if value > 0 else "down"
    return None


def _snippet_ok(snippet: str, line: str, min_chars: int) -> bool:
    """Long enough, and a whole-word run of the cited line."""
    if len(snippet) < min_chars or snippet != snippet.strip():
        return False
    for m in re.finditer(re.escape(snippet), line):
        before = line[m.start() - 1] if m.start() else " "
        after = line[m.end()] if m.end() < len(line) else " "
        if not (before.isalnum() or after.isalnum()):
            return True
    return False


def _check_kind(
    claim: Claim,
    entry: Mapping[str, Any],
    cited: list[Mapping[str, Any]],
    params: NarratorParams,
) -> Reason | None:
    steps = _steps(entry)
    fusion = steps["F"]
    if claim.kind == ClaimKind.SHIFT:
        # N-j: only the claim's own D-pipe channel item grounds a shift.
        own = [i for i in cited if i["id"] == f"D:{claim.service}:{claim.channel}"]
        if not own:
            return Reason.KIND_MISMATCH
        if all(_direction_of(i) != claim.direction for i in own):
            return Reason.WRONG_DIRECTION
        return None
    if claim.kind == ClaimKind.CALL_STRUCTURE:
        graph = [i for i in cited if i["id"].startswith("G:")]
        if not graph:
            return Reason.KIND_MISMATCH
        return None if any(_edge_holds(claim, i) for i in graph) else Reason.WRONG_EDGE
    if claim.kind == ClaimKind.LOG_MESSAGE:
        lines = [
            i
            for i in cited
            if i["id"].startswith("L:") and i.get("service") == claim.service
        ]
        if not lines:
            return Reason.KIND_MISMATCH
        snippet = str(claim.snippet or "")
        ok = any(
            _snippet_ok(snippet, str(i.get("text", "")), params.min_snippet_chars)
            for i in lines
        )
        return None if ok else Reason.SNIPPET_NOT_FOUND
    if claim.kind == ClaimKind.RANKING:
        ranked = list(fusion.get("ranked") or [])
        rank = int(claim.rank or 0)
        if not 1 <= rank <= len(ranked) or ranked[rank - 1] != claim.service:
            return Reason.RANK_MISMATCH
        return None
    if claim.kind == ClaimKind.CONTRADICTION:
        ranked = list(steps.get(f"P:{claim.pipeline}", {}).get("ranked") or [])
        if claim.pipeline not in (fusion.get("disagree") or []) or not ranked:
            return Reason.NOT_IN_DISAGREE
        if ranked[0] != claim.service:
            return Reason.NOT_IN_DISAGREE
        prefix = {"dpipe": "D:", "gpipe": "G:", "lpipe": "L:"}[str(claim.pipeline)]
        own_items = [
            i
            for i in cited
            if i["id"].startswith(prefix) and i.get("service") == claim.service
        ]
        return None if own_items else Reason.KIND_MISMATCH
    return _check_step(claim, entry, cited)


def _check_step(
    claim: Claim, entry: Mapping[str, Any], cited: list[Mapping[str, Any]]
) -> Reason | None:
    top3 = list(_steps(entry)["F"].get("ranked") or [])[:3]
    target = claim.target_service
    neighbours = {
        n
        for i in cited
        if i["id"].startswith("G:") and i.get("service") in top3
        for n in _names_in(i.get("value"))
    }
    if target not in top3 and target not in neighbours:
        return Reason.FOREIGN_SERVICE
    prefix = _MODALITY_PREFIX[str(claim.modality)]
    if not any(i["id"].startswith(prefix) for i in cited):
        return Reason.MODALITY_MISMATCH
    return None


def _allowed_services(
    claim: Claim, entry: Mapping[str, Any], cited: list[Mapping[str, Any]]
) -> set[str]:
    names = {claim.service, claim.caller, claim.callee, claim.target_service}
    if claim.kind == ClaimKind.CONTRADICTION:
        names |= set(list(_steps(entry)["F"].get("ranked") or [])[:1])
    if claim.kind == ClaimKind.VERIFICATION_STEP:
        names |= {i.get("service") for i in cited}
    return {n for n in names if n}


def _own_item(claim: Claim, cited: list[Mapping[str, Any]]) -> Mapping[str, Any]:
    return next(
        (i for i in cited if i["id"] == f"D:{claim.service}:{claim.channel}"), {}
    )


def _unit_words(claim: Claim, cited: list[Mapping[str, Any]]) -> set[str]:
    unit = str(_own_item(claim, cited).get("unit", "")) if claim.kind == "shift" else ""
    parts = {w for w in re.split(r"[\s_/-]+", unit.lower()) if w and not w.isdigit()}
    return parts | ({unit.lower()} if unit else set())


def _words(claim: Claim, params: NarratorParams, units: set[str]) -> set[str]:
    kind = claim.kind.value
    vocab = params.vocabulary
    words = set(vocab.get("common", ())) | set(vocab.get(kind, ()))
    if claim.kind in (ClaimKind.RANKING, ClaimKind.CONTRADICTION):
        words |= set(params.rank_words)
    if claim.kind == ClaimKind.SHIFT:
        words |= {w for ws in params.direction_words.values() for w in ws}
        words |= {w for ws in params.channel_words.values() for w in ws} | units
    if claim.kind == ClaimKind.VERIFICATION_STEP:
        words |= set(params.verbs) | {
            w for ws in params.channel_words.values() for w in ws
        }
    if claim.kind == ClaimKind.CONTRADICTION:
        words |= set(params.pipeline_words)
    return words


def _evidence(
    claim: Claim, entry: Mapping[str, Any], cited: list[Mapping[str, Any]]
) -> dict[str, tuple[float, str]]:
    """Named numbers the sentence may state, with their unit (N-j: only the
    claim's own evidence)."""
    if claim.kind == ClaimKind.SHIFT:
        item = _own_item(claim, cited)
        unit = str(item.get("unit", ""))
        return {
            k: (float(item[k]), unit)
            for k in ("before", "after")
            if isinstance(item.get(k), int | float)
        }
    if claim.kind == ClaimKind.CALL_STRUCTURE and claim.feature == "wait":
        item = next((i for i in cited if i["id"] == f"G:{claim.callee}:wait_from"), {})
        share = (item.get("value") or {}).get(claim.caller)
        return {"share": (float(share), "fraction")} if share is not None else {}
    if claim.kind == ClaimKind.RANKING:
        conf = _steps(entry)["F"].get("confidence")
        return {"confidence": (float(conf), "fraction")} if conf is not None else {}
    return {}


def _close(a: float, b: float, places: int, tol: float) -> bool:
    return abs(a - b) <= tol * abs(b) or round(b, places) == round(a, places)


def _match(
    value: float,
    places: int,
    unit: str | None,
    evidence: dict[str, tuple[float, str]],
    tol: float,
) -> set[str]:
    hits = set()
    for name, (e, e_unit) in evidence.items():
        if unit == "%":
            ok = 0 <= e <= 1 and _close(value, e * 100, places, tol)
        elif unit == "s":
            ok = e_unit == "ms" and _close(value * 1000, e, max(places - 3, 0), tol)
        elif unit == "ms":
            ok = e_unit == "ms" and _close(value, e, places, tol)
        else:
            ok = _close(value, e, places, tol)
        if ok:
            hits.add(name)
    return hits


def _time_ok(token: str, entry: Mapping[str, Any]) -> bool:
    m = _TIME.fullmatch(token)
    t = _steps(entry)["T"]
    if m is None or not t.get("window_start") or not t.get("window_end"):
        return False
    start = dt.datetime.fromisoformat(str(t["window_start"]))
    end = dt.datetime.fromisoformat(str(t["window_end"]))
    hh, mm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    if hh > 23 or mm > 59 or ss > 59:
        return False
    lo = start.replace(second=0, microsecond=0)
    when = start.replace(hour=hh, minute=mm, second=ss, microsecond=0)
    if when < lo:  # a window that crosses midnight
        when += dt.timedelta(days=1)
    return lo <= when <= end


def _contain(
    claim: Claim,
    entry: Mapping[str, Any],
    cited: list[Mapping[str, Any]],
    params: NarratorParams,
) -> Reason | None:
    text = claim.sentence
    if "\n" in text or "\r" in text or len(text.split()) > params.max_words:
        return Reason.MALFORMED_SENTENCE
    if claim.kind == ClaimKind.LOG_MESSAGE:
        # The quoted snippet is verified evidence (it may hold brackets or
        # arrows); everything outside the quotes is contained.
        quoted = f'"{claim.snippet}"'
        if text.count(quoted) != 1:
            return Reason.SNIPPET_NOT_FOUND
        text = text.replace(quoted, " ")
    if any(ch in text for ch in '"[]{}<>`|') or _CITE.search(text):
        return Reason.MALFORMED_SENTENCE
    services = entry_services(entry) | _allowed_services(claim, entry, cited)
    spans = _spans(text, services)
    if {n for _, _, n in spans} - _allowed_services(claim, entry, cited):
        return Reason.FOREIGN_SERVICE
    order = [n for _, _, n in spans]
    for start, end, _ in reversed(spans):
        text = text[:start] + " " + text[end:]
    words = _words(claim, params, _unit_words(claim, cited))
    seen: list[str] = []
    numbers: list[tuple[float, int, str | None]] = []
    tokens = [t.strip(_STRIP) for t in text.split()]
    tokens = [t for t in tokens if t]
    for n, token in enumerate(tokens):
        low = token.lower()
        if _TIME.fullmatch(token):
            if claim.kind != ClaimKind.VERIFICATION_STEP:
                return Reason.WORD_NOT_ALLOWED
            if not _time_ok(token, entry):
                return Reason.TIME_OUT_OF_WINDOW
            continue
        if any(ch.isdigit() for ch in token) and low not in words:
            m = _NUMBER.fullmatch(low)
            if m is None or _PUNCT.search(token):
                return Reason.WORD_NOT_ALLOWED
            unit = m.group(2)
            nxt = tokens[n + 1].lower() if n + 1 < len(tokens) else ""
            if unit is None and nxt in _UNIT_WORDS:
                unit = _UNIT_WORDS[nxt]
            raw = m.group(1)
            places = len(raw.split(".")[1]) if "." in raw else 0
            numbers.append((float(raw), places, unit))
            continue
        if low in _UNIT_WORDS:
            continue
        if low.endswith("'s"):
            low = low[:-2]
        if low not in words:
            return Reason.WORD_NOT_ALLOWED
        seen.append(low)
    if reason := _agree(claim, seen, order, params):
        return reason
    evidence = _evidence(claim, entry, cited)
    matched: list[set[str]] = []
    for value, places, unit in numbers:
        hits = _match(value, places, unit, evidence, params.rel_tolerance)
        if not hits:
            return Reason.NUMBER_NOT_IN_EVIDENCE
        matched.append(hits)
    for i, earlier in enumerate(matched):
        for later in matched[i + 1 :]:
            if earlier == {"after"} and later == {"before"}:
                return Reason.WRONG_DIRECTION
    return None


def _agree(
    claim: Claim, seen: list[str], order: list[str], params: NarratorParams
) -> Reason | None:
    """The sentence says what the claim's fields say (N-j)."""
    said = set(seen)
    if claim.kind == ClaimKind.RANKING:
        ranks = {params.rank_words[w] for w in said if w in params.rank_words}
        if ranks != {claim.rank}:
            return Reason.RANK_MISMATCH
    if claim.kind == ClaimKind.SHIFT:
        own = set(params.channel_words.get(str(claim.channel), ()))
        other = {
            w
            for c, ws in params.channel_words.items()
            if c != claim.channel
            for w in ws
        } - own
        if said & other:
            return Reason.KIND_MISMATCH
        opposite = "down" if claim.direction == "up" else "up"
        if said & set(params.direction_words.get(opposite, ())):
            return Reason.WRONG_DIRECTION
        if not said & set(params.direction_words.get(str(claim.direction), ())):
            return Reason.WRONG_DIRECTION
    if claim.kind == ClaimKind.CALL_STRUCTURE:
        first = claim.callee if claim.feature == "lead" else claim.caller
        second = claim.caller if claim.feature == "lead" else claim.callee
        if first not in order or second not in order:
            return Reason.WRONG_EDGE
        if order.index(first) > order.index(second):
            return Reason.WRONG_EDGE
    if claim.kind == ClaimKind.CONTRADICTION:
        named = {params.pipeline_words[w] for w in said if w in params.pipeline_words}
        if named != {claim.pipeline}:
            return Reason.NOT_IN_DISAGREE
    return None


def verify(
    claim: Claim, entry: Mapping[str, Any], params: NarratorParams
) -> Reason | None:
    """None if the claim is grounded in the entry; otherwise why not."""
    if not claim.cites:
        return Reason.MISSING_CITE
    citable = _citable(entry)
    if any(c not in citable for c in claim.cites):
        return Reason.UNKNOWN_ID
    cited = [citable[c] for c in claim.cites]
    if claim.kind == ClaimKind.VERIFICATION_STEP:
        words = claim.sentence.strip().split()
        verb = str(claim.action_verb or "").lower()
        if verb not in params.verbs or not words or words[0].lower() != verb:
            return Reason.VERB_NOT_ALLOWED
    if reason := _check_kind(claim, entry, cited, params):
        return reason
    return _contain(claim, entry, cited, params)
