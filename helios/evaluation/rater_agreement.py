"""Rater agreement, adjudicated consensus and H_fact (S2.9 design §5.6;
owner decisions R-i, R-k, R-m; entry 65).

κ is Cohen's κ between the two raters' binary labels, over all items (planted
included, so both labels are common) and over real claims only. Consensus
follows R-i and R-m: with κ at or above the threshold, agreements stand and
disagreements take the adjudicator's label; below it (or undefined) the
adjudicator's label decides every real claim. H_fact counts real claims only;
planted claims measure each rater's attention instead.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "DETECTION_FLOOR",
    "KAPPA_THRESHOLD",
    "SITTING_GAP_S",
    "agreement_report",
    "cohen_kappa",
    "consensus",
    "detection",
    "h_fact",
    "per_rater_h_fact",
]

KAPPA_THRESHOLD = 7 / 10  # metric contract §5, OSF deposit 1
DETECTION_FLOOR = 4 / 5  # planted claims caught per sitting (design §5.2)
SITTING_GAP_S = 30 * 60  # a pause longer than this starts a new sitting
_UNSUPPORTED = "unsupported"
_LLM_ARM = "HELIOS-Full"  # blinding check: A = language model, B = fixed rules


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float | None:
    """Cohen's κ for two equal-length label lists; None when undefined."""
    n = len(a)
    if n == 0 or n != len(b):
        return None
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    cats = set(a) | set(b)
    expected = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    if expected >= 1:
        return None
    return (observed - expected) / (1 - expected)


def _raters(labels: Mapping[tuple[str, str], Mapping[str, Any]]) -> tuple[str, str]:
    people = sorted({p for _, p in labels})
    if len(people) != 2:
        raise ValueError(f"consensus needs exactly two raters, got {people}")
    return people[0], people[1]


def _by_item(
    entries: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    return {item: e for (item, _), e in entries.items()}


def consensus(
    labels: Mapping[tuple[str, str], Mapping[str, Any]],
    adjudications: Mapping[tuple[str, str], Mapping[str, Any]],
    key: Mapping[str, Mapping[str, Any]],
    *,
    kappa: float | None,
) -> dict[str, dict[str, Any]]:
    """The final label of every real claim: verdict, category and its source
    (``agreement``, ``adjudication`` or ``pending``)."""
    r1, r2 = _raters(labels)
    adj = _by_item(adjudications)
    above = kappa is not None and kappa >= KAPPA_THRESHOLD
    out: dict[str, dict[str, Any]] = {}
    for item, k in key.items():
        if k.get("planted"):
            continue
        a, b, j = labels.get((item, r1)), labels.get((item, r2)), adj.get(item)
        if above and a and b and a["verdict"] == b["verdict"]:
            category = (j or a)["category"] if a["verdict"] == _UNSUPPORTED else ""
            out[item] = {
                "verdict": a["verdict"],
                "category": category,
                "source": "agreement",
            }
        elif j is not None:
            out[item] = {
                "verdict": j["verdict"],
                "category": j.get("category", ""),
                "source": "adjudication",
            }
        else:
            out[item] = {"verdict": "pending", "category": "", "source": "pending"}
    return out


def _rate(claims: int, unsupported: int) -> dict[str, Any]:
    return {
        "claims": claims,
        "unsupported": unsupported,
        "h_fact": unsupported / claims if claims else None,
    }


def _per_arm(
    verdicts: Mapping[str, str], key: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for item, verdict in verdicts.items():
        c = counts[str(key[item]["arm"])]
        c[0] += 1
        c[1] += verdict == _UNSUPPORTED
    return {arm: _rate(*c) for arm, c in sorted(counts.items())}


def h_fact(
    cons: Mapping[str, Mapping[str, Any]], key: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    """H_fact per arm and per case (for A-H7's paired sign test); pending
    claims are left out and counted."""
    decided = {
        i: str(c["verdict"]) for i, c in cons.items() if c["verdict"] != "pending"
    }
    cases: dict[str, dict[str, str]] = defaultdict(dict)
    for item, verdict in decided.items():
        cases[str(key[item]["incident_id"])][item] = verdict
    return {
        "per_arm": _per_arm(decided, key),
        "per_case": {case: _per_arm(v, key) for case, v in sorted(cases.items())},
        "pending": len(cons) - len(decided),
    }


def per_rater_h_fact(
    labels: Mapping[tuple[str, str], Mapping[str, Any]],
    key: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Each rater's own H_fact per arm (sensitivity table, R-i)."""
    out = {}
    for person in sorted({p for _, p in labels}):
        mine = {
            item: str(e["verdict"])
            for (item, p), e in labels.items()
            if p == person and not key[item].get("planted")
        }
        out[person] = _per_arm(mine, key)
    return out


def _when(entry: Mapping[str, Any]) -> dt.datetime:
    return dt.datetime.fromisoformat(str(entry["timestamp_utc"]).replace("Z", "+00:00"))


def detection(
    labels: Mapping[tuple[str, str], Mapping[str, Any]],
    key: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Per person: planted claims caught per category, false alarms on real
    claims, and each sitting's catch rate against the floor."""
    out: dict[str, Any] = {}
    for person in sorted({p for _, p in labels}):
        mine = sorted(
            ((item, e) for (item, p), e in labels.items() if p == person),
            key=lambda ie: _when(ie[1]),
        )
        per_cat: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        real = [e for item, e in mine if not key[item].get("planted")]
        sittings: list[list[tuple[str, Mapping[str, Any]]]] = []
        for item, e in mine:
            if (
                not sittings
                or (_when(e) - _when(sittings[-1][-1][1])).total_seconds()
                > SITTING_GAP_S
            ):
                sittings.append([])
            sittings[-1].append((item, e))
            if key[item].get("planted"):
                c = per_cat[str(key[item]["category"])]
                c[0] += 1
                c[1] += e["verdict"] == _UNSUPPORTED
        rows = []
        for sitting in sittings:
            planted = [e for item, e in sitting if key[item].get("planted")]
            caught = sum(e["verdict"] == _UNSUPPORTED for e in planted)
            share = caught / len(planted) if planted else None
            rows.append(
                {
                    "start": str(sitting[0][1]["timestamp_utc"]),
                    "planted": len(planted),
                    "caught": caught,
                    "share": share,
                    "below_floor": share is not None and share < DETECTION_FLOOR,
                }
            )
        out[person] = {
            "per_category": {cat: c[1] / c[0] for cat, c in sorted(per_cat.items())},
            "false_alarm": (
                sum(e["verdict"] == _UNSUPPORTED for e in real) / len(real)
                if real
                else None
            ),
            "sittings": rows,
        }
    return out


def _blinding(
    guesses: Mapping[tuple[str, str], Mapping[str, Any]],
    key: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    answered = hits = unsure = 0
    for (item, _), g in guesses.items():
        if g["verdict"] == "unsure":
            unsure += 1
            continue
        answered += 1
        hits += (g["verdict"] == "A") == (key[item]["arm"] == _LLM_ARM)
    return {
        "answered": answered,
        "hits": hits,
        "unsure": unsure,
        "hit_rate": hits / answered if answered else None,
    }


def agreement_report(
    labels: Mapping[tuple[str, str], Mapping[str, Any]],
    adjudications: Mapping[tuple[str, str], Mapping[str, Any]],
    guesses: Mapping[tuple[str, str], Mapping[str, Any]],
    key: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """κ (all items and real only), consensus counts, H_fact, per-rater
    tables, planted-claim detection and the blinding check."""
    r1, r2 = _raters(labels)
    both = sorted(item for item in key if (item, r1) in labels and (item, r2) in labels)
    real = [i for i in both if not key[i].get("planted")]

    def verdicts(items: list[str], person: str) -> list[str]:
        return [str(labels[i, person]["verdict"]) for i in items]

    kappa_all = cohen_kappa(verdicts(both, r1), verdicts(both, r2))
    kappa_real = cohen_kappa(verdicts(real, r1), verdicts(real, r2))
    both_u = [
        i
        for i in both
        if labels[i, r1]["verdict"] == labels[i, r2]["verdict"] == _UNSUPPORTED
    ]
    same_cat = sum(
        labels[i, r1]["category"] == labels[i, r2]["category"] for i in both_u
    )
    cons = consensus(labels, adjudications, key, kappa=kappa_all)
    facts = h_fact(cons, key)
    return {
        "kappa_all": kappa_all,
        "kappa_real": kappa_real,
        "kappa_threshold_met": kappa_all is not None and kappa_all >= KAPPA_THRESHOLD,
        "category_agreement": same_cat / len(both_u) if both_u else None,
        "counts": {
            "labelled_by_both": len(both),
            "real": sum(not k.get("planted") for k in key.values()),
            "planted": sum(bool(k.get("planted")) for k in key.values()),
            "pending": facts["pending"],
        },
        "h_fact": facts,
        "per_rater": per_rater_h_fact(labels, key),
        "detection": detection(labels, key),
        "blinding": _blinding(guesses, key),
    }
