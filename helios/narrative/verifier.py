"""Grounding verifier (S2.8 design §5.2, §5.5; owner decisions N-b, N-c, N-f, N-g).

``verify`` accepts a claim only if every cite is an item (or the ``F`` step) of
the run's CoE entry, the kind's rule holds against the cited items, and the
sentence stays inside them: no other service named, no number the cited items
do not hold, no direction word against the claim, no time outside the window.
Pure and deterministic; it reads the entry and the frozen parameters only.
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
    """Why a claim was rejected (closed set, design §5.5)."""

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


_CHANNELS = ("error", "latency", "resource")
_MODALITY_PREFIX = {"metric": "D:", "log": "L:", "edge": "G:"}
_TIME = re.compile(r"(?<![\d:])(\d{1,2}):(\d{2})(?::(\d{2}))?(?![\d:])")
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}[T ][\d:.]+(?:Z|[+-]\d{2}:?\d{2})?")
# A number not glued to letters, '#', '-' or ':' (so p99, L12, #1, top-3 and
# citation IDs are not numbers), with an optional unit.
_NUMBER = re.compile(
    r"(?<![\w#.:-])(\d+(?:\.\d+)?)\s*(%|ms|milliseconds?|s|secs?|seconds?)?(?![\w.]*\d)"
)
_ORDINAL = re.compile(r"\b\d+(?:st|nd|rd|th)\b")
_CITE = re.compile(r"\b[DGL]:[\w.:-]+")


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
            value = item.get("value")
            if item["id"].startswith("G:"):
                if isinstance(value, dict):
                    names.update(value)
                elif isinstance(value, list):
                    for v in value:
                        names.update(v if isinstance(v, list) else [v])
    return {n for n in names if isinstance(n, str) and n}


def mentions(text: str, names: Iterable[str]) -> set[str]:
    """Service names in ``text`` as whole tokens (word and hyphen boundaries),
    longest first, so ``cart`` is not found inside ``cartservice``."""
    found: set[str] = set()
    taken = [False] * len(text)
    for name in sorted(set(names), key=lambda n: (-len(n), n)):
        pattern = rf"(?<![A-Za-z0-9_-]){re.escape(name)}(?![A-Za-z0-9_-])"
        for m in re.finditer(pattern, text, re.IGNORECASE):
            if not any(taken[m.start() : m.end()]):
                found.add(name)
                for k in range(m.start(), m.end()):
                    taken[k] = True
    return found


def _numbers(obj: Any) -> list[float]:
    if isinstance(obj, bool) or obj is None:
        return []
    if isinstance(obj, int | float):
        return [float(obj)]
    if isinstance(obj, dict):
        return [n for v in obj.values() for n in _numbers(v)]
    if isinstance(obj, list | tuple):
        return [n for v in obj for n in _numbers(v)]
    return []


def _evidence_numbers(cited: Iterable[Mapping[str, Any]]) -> list[float]:
    out: list[float] = []
    for item in cited:
        if item.get("id") == "F":
            for key in ("confidence", "fused_sigma", "scores"):
                out += _numbers(item.get(key))
        else:
            for key in ("value", "before", "after"):
                out += _numbers(item.get(key))
    return out


def _candidates(value: float, unit: str | None) -> list[float]:
    if unit == "%":
        return [value / 100, value]
    if unit and unit.startswith("s"):
        return [value * 1000, value]
    if unit and unit.startswith("m"):
        return [value, value / 1000]
    return [value]


def _matches(token: str, unit: str | None, evidence: list[float], tol: float) -> bool:
    value = float(token)
    places = len(token.split(".")[1]) if "." in token else 0
    for cand in _candidates(value, unit):
        scale = 100 if unit == "%" and cand == value else 1
        for e in evidence:
            if abs(cand - e) <= tol * abs(e) or round(e * scale, places) == value:
                return True
            if scale == 1 and round(e, places) == round(cand, places):
                return True
    return False


def _time_ok(text: str, entry: Mapping[str, Any]) -> bool:
    t = _steps(entry)["T"]
    if not t.get("window_start") or not t.get("window_end"):
        return not _TIME.search(text)
    start = dt.datetime.fromisoformat(str(t["window_start"]))
    end = dt.datetime.fromisoformat(str(t["window_end"]))
    lo = start.replace(second=0, microsecond=0)
    for m in _TIME.finditer(text):
        hh, mm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
        if hh > 23 or mm > 59:
            return False
        when = start.replace(hour=hh, minute=mm, second=ss, microsecond=0)
        if when < lo:  # a window that crosses midnight
            when += dt.timedelta(days=1)
        if not lo <= when <= end:
            return False
    return True


def _strip_non_numbers(text: str, names: Iterable[str]) -> str:
    text = _ISO.sub(" ", text)
    text = _CITE.sub(" ", text)
    text = _TIME.sub(" ", text)
    text = _ORDINAL.sub(" ", text)
    for name in names:
        text = re.sub(re.escape(name), " ", text, flags=re.IGNORECASE)
    return text


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


def _check_kind(
    claim: Claim, entry: Mapping[str, Any], cited: list[Mapping[str, Any]]
) -> Reason | None:
    steps = _steps(entry)
    fusion = steps["F"]
    if claim.kind == ClaimKind.SHIFT:
        own = [i for i in cited if i["id"] == f"D:{claim.service}:{claim.channel}"]
        logs = [
            i
            for i in cited
            if i["id"].startswith("L:") and i.get("service") == claim.service
        ]
        if own:
            return (
                None
                if any(_direction_of(i) == claim.direction for i in own)
                else Reason.WRONG_DIRECTION
            )
        return None if logs else Reason.KIND_MISMATCH
    if claim.kind == ClaimKind.CALL_STRUCTURE:
        graph = [i for i in cited if i["id"].startswith("G:")]
        if not graph:
            return Reason.KIND_MISMATCH
        if any(_edge_holds(claim, i) for i in graph):
            return None
        return Reason.WRONG_EDGE
    if claim.kind == ClaimKind.LOG_MESSAGE:
        lines = [
            i
            for i in cited
            if i["id"].startswith("L:") and i.get("service") == claim.service
        ]
        if not lines:
            return Reason.KIND_MISMATCH
        snippet = str(claim.snippet)
        # Verbatim in a cited line, and what the sentence actually quotes.
        ok = snippet in claim.sentence and any(
            snippet and snippet in str(i.get("text", "")) for i in lines
        )
        return None if ok else Reason.SNIPPET_NOT_FOUND
    if claim.kind == ClaimKind.RANKING:
        ranked = list(fusion.get("ranked") or [])
        rank = int(claim.rank or 0)
        if not 1 <= rank <= len(ranked) or ranked[rank - 1] != claim.service:
            return Reason.RANK_MISMATCH
        return None
    if claim.kind == ClaimKind.CONTRADICTION:
        step = steps.get(f"P:{claim.pipeline}", {})
        ranked = list(step.get("ranked") or [])
        if claim.pipeline not in (fusion.get("disagree") or []) or not ranked:
            return Reason.NOT_IN_DISAGREE
        if ranked[0] != claim.service:
            return Reason.NOT_IN_DISAGREE
        prefix = {"dpipe": "D:", "gpipe": "G:", "lpipe": "L:"}[str(claim.pipeline)]
        own = [
            i
            for i in cited
            if i["id"].startswith(prefix) and i.get("service") == claim.service
        ]
        return None if own else Reason.KIND_MISMATCH
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
        for n in _numbers_free_names(i.get("value"))
    }
    if target not in top3 and target not in neighbours:
        return Reason.FOREIGN_SERVICE
    prefix = _MODALITY_PREFIX[str(claim.modality)]
    if not any(i["id"].startswith(prefix) for i in cited):
        return Reason.MODALITY_MISMATCH
    return None


def _numbers_free_names(value: Any) -> set[str]:
    if isinstance(value, dict):
        return {k for k in value if isinstance(k, str)}
    if isinstance(value, list):
        out: set[str] = set()
        for v in value:
            out |= _numbers_free_names(v) if isinstance(v, list) else {str(v)}
        return out
    return set()


def _allowed(
    claim: Claim, entry: Mapping[str, Any], cited: list[Mapping[str, Any]]
) -> set[str]:
    names = {claim.service, claim.caller, claim.callee, claim.target_service}
    if claim.kind == ClaimKind.CONTRADICTION:
        ranked = list(_steps(entry)["F"].get("ranked") or [])
        names |= set(ranked[:1])
    if claim.kind == ClaimKind.VERIFICATION_STEP:
        names |= {i.get("service") for i in cited}
    return {n for n in names if n}


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
    if reason := _check_kind(claim, entry, cited):
        return reason
    services = entry_services(entry)
    # A log claim's snippet was checked verbatim against the cited line; what
    # it quotes is evidence, so only the rest of the sentence is contained.
    sentence = claim.sentence
    if claim.kind == ClaimKind.LOG_MESSAGE and claim.snippet:
        sentence = sentence.replace(claim.snippet, " ")
    if mentions(sentence, services) - _allowed(claim, entry, cited):
        return Reason.FOREIGN_SERVICE
    if claim.kind == ClaimKind.SHIFT and claim.direction:
        opposite = "down" if claim.direction == "up" else "up"
        tokens = set(re.findall(r"[a-z]+", sentence.lower()))
        if tokens & set(params.direction_words.get(opposite, ())):
            return Reason.WRONG_DIRECTION
    if not _time_ok(sentence, entry):
        return Reason.TIME_OUT_OF_WINDOW
    evidence = _evidence_numbers(cited)
    text = _strip_non_numbers(sentence, services)
    for m in _NUMBER.finditer(text):
        if not _matches(m.group(1), m.group(2), evidence, params.rel_tolerance):
            return Reason.NUMBER_NOT_IN_EVIDENCE
    return None
