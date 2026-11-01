"""Planted claims: known-wrong copies of real claims (S2.9 design §5.2, R-f).

Each corruption tries its candidate edits in a seeded order and keeps the first
one the S2.8 verifier rejects for the category's expected reason, so a planted
claim is always wrong for the reason its category names, and reads like a real
claim of its kind (same fields, one line, about the same length). Planted
claims never count in H_fact; they give κ both labels to agree on and measure
whether a rater catches errors.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from helios.labelling.annotations import CATEGORIES
from helios.narrative.claims import Claim, ClaimKind
from helios.narrative.verifier import Reason, entry_services, verify
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    import random
    from collections.abc import Iterator, Mapping, Sequence

    from helios.narrative.params import NarratorParams

__all__ = ["CATEGORIES", "EXPECTED_REASON", "corrupt", "plant"]

EXPECTED_REASON: dict[str, set[Reason]] = {
    "numeric_drift": {Reason.NUMBER_NOT_IN_EVIDENCE},
    "entity_mismatch": {
        Reason.FOREIGN_SERVICE,
        Reason.WRONG_EDGE,
        Reason.KIND_MISMATCH,
        Reason.RANK_MISMATCH,
        Reason.NOT_IN_DISAGREE,
    },
    "directional_inversion": {Reason.WRONG_DIRECTION},
    "log_quote_mismatch": {Reason.SNIPPET_NOT_FOUND},
    "missing_citation": {Reason.UNKNOWN_ID},
}

# Numbers outside quotes; not part of a word (p99), a time (14:50) or an ID.
_NUMBER = re.compile(r"(?<![\w.:<])\d+(?:\.\d+)?(?![\w:])")
_FACTORS = (3 / 5, 8 / 5)  # far outside any rounding tolerance
_QUOTE_WORDS = ("timeout", "refused", "dropped", "closed", "rejected")
_SERVICE_FIELD = {
    ClaimKind.RANKING: "service",
    ClaimKind.SHIFT: "service",
    ClaimKind.LOG_MESSAGE: "service",
    ClaimKind.CONTRADICTION: "service",
    ClaimKind.VERIFICATION_STEP: "target_service",
}


def _name(name: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])")


def _outside_quote(sentence: str) -> tuple[int, int]:
    """The span of the quoted snippet, or an empty span."""
    m = re.search(r'"[^"]*"', sentence)
    return (m.start(), m.end()) if m else (-1, -1)


def _numeric(claim: Claim, rng: random.Random) -> Iterator[Claim]:
    q0, q1 = _outside_quote(claim.sentence)
    spots = [m for m in _NUMBER.finditer(claim.sentence) if not q0 <= m.start() < q1]
    rng.shuffle(spots)
    for m in spots:
        text = m.group()
        places = len(text.split(".")[1]) if "." in text else 0
        for factor in rng.sample(_FACTORS, len(_FACTORS)):
            new = f"{float(text) * factor:.{places}f}"
            if new != text:
                s = claim.sentence
                yield claim.model_copy(
                    update={"sentence": s[: m.start()] + new + s[m.end() :]}
                )


def _entity(
    claim: Claim, entry: Mapping[str, Any], rng: random.Random
) -> Iterator[Claim]:
    if claim.kind == ClaimKind.CALL_STRUCTURE:
        caller, callee = str(claim.caller), str(claim.callee)
        swapped = _name(caller).sub("\0", claim.sentence)
        swapped = _name(callee).sub(caller, swapped).replace("\0", callee)
        yield claim.model_copy(
            update={"sentence": swapped, "caller": callee, "callee": caller}
        )
        return
    field = _SERVICE_FIELD.get(claim.kind)
    old = getattr(claim, field) if field else None
    if field is None or not old:
        return
    others = sorted(entry_services(entry) - {old})
    rng.shuffle(others)
    for new in others:
        sentence = _name(old).sub(new, claim.sentence)
        if sentence != claim.sentence:
            yield claim.model_copy(update={"sentence": sentence, field: new})


def _direction(claim: Claim, params: NarratorParams) -> Iterator[Claim]:
    if claim.kind != ClaimKind.SHIFT or claim.direction is None:
        return
    opposite = "down" if claim.direction == "up" else "up"
    words = claim.sentence.split(" ")
    for i, word in enumerate(words):
        if word.lower() in params.direction_words.get(claim.direction, ()):
            flipped = [*words[:i], params.direction_words[opposite][0], *words[i + 1 :]]
            yield claim.model_copy(
                update={"sentence": " ".join(flipped), "direction": opposite}
            )


def _quote(claim: Claim, rng: random.Random) -> Iterator[Claim]:
    if claim.kind != ClaimKind.LOG_MESSAGE or not claim.snippet:
        return
    words = claim.snippet.split(" ")
    spots = [i for i, w in enumerate(words) if w.isalpha() and len(w) >= 3]
    rng.shuffle(spots)
    for i in spots:
        for repl in rng.sample(_QUOTE_WORDS, len(_QUOTE_WORDS)):
            if repl != words[i].lower():
                snippet = " ".join([*words[:i], repl, *words[i + 1 :]])
                sentence = claim.sentence.replace(f'"{claim.snippet}"', f'"{snippet}"')
                yield claim.model_copy(
                    update={"sentence": sentence, "snippet": snippet}
                )


def _citation(
    claim: Claim, entry: Mapping[str, Any], rng: random.Random
) -> Iterator[Claim]:
    known = {str(i["id"]) for s in entry["steps"] for i in s.get("items", [])}
    known |= {str(s["id"]) for s in entry["steps"]}
    order = list(range(len(claim.cites)))
    rng.shuffle(order)
    for k in order:
        cite = claim.cites[k]
        prefix = cite.rsplit(":", 1)[0] + ":" if ":" in cite else cite
        for n in range(1, 10):
            fake = f"{prefix}x{n}" if ":" in cite else f"{prefix}{n}"
            if fake not in known:
                cites = (*claim.cites[:k], fake, *claim.cites[k + 1 :])
                yield claim.model_copy(update={"cites": cites})
                break


def corrupt(
    claim: Claim,
    entry: Mapping[str, Any],
    category: str,
    rng: random.Random,
    params: NarratorParams,
) -> Claim | None:
    """A planted copy of ``claim`` wrong for ``category``, or None when the
    category cannot apply to it."""
    candidates = {
        "numeric_drift": lambda: _numeric(claim, rng),
        "entity_mismatch": lambda: _entity(claim, entry, rng),
        "directional_inversion": lambda: _direction(claim, params),
        "log_quote_mismatch": lambda: _quote(claim, rng),
        "missing_citation": lambda: _citation(claim, entry, rng),
    }[category]()
    for planted in candidates:
        if verify(planted, entry, params) in EXPECTED_REASON[category]:
            return planted
    return None


def plant(
    sources: Sequence[tuple[str, Claim, Mapping[str, Any]]],
    share: float,
    rng: random.Random,
    params: NarratorParams,
    *,
    n_real: int | None = None,
) -> list[tuple[str, Claim, str]]:
    """(source key, planted claim, category) so that planted claims make up
    ``share`` of all claims shown beside ``n_real`` real ones (default: as
    many as ``sources``). Each source is used at most once, so planted claims
    follow the sources' kind mix; categories stay balanced; a planted claim
    whose sentence and cites repeat an earlier one is not used (review C1)."""
    real = len(sources) if n_real is None else n_real
    want = round(share * real / (1 - share))
    order = list(range(len(sources)))
    rng.shuffle(order)
    count = dict.fromkeys(CATEGORIES, 0)
    seen: set[tuple[str, tuple[str, ...]]] = set()
    out: list[tuple[str, Claim, str]] = []
    for idx in order:
        if len(out) >= want:
            break
        key, claim, entry = sources[idx]
        turn = len(out) % len(CATEGORIES)
        ranked = sorted(
            CATEGORIES,
            key=lambda c: (count[c], (CATEGORIES.index(c) - turn) % len(CATEGORIES)),
        )
        for category in ranked:
            planted = corrupt(claim, entry, category, rng, params)
            if planted is None or (planted.sentence, planted.cites) in seen:
                continue
            seen.add((planted.sentence, planted.cites))
            count[category] += 1
            out.append((key, planted, category))
            break
    return out
