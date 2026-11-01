"""Training rounds and onboarding (S2.9 design §5.7, owner decision R-j).

Training rounds take HELIOS-Full and HELIOS-noLLM narratives of the same build
cases, stratified so every claim kind present in the build ledgers appears
(call-structure claims come almost only from the OTel captures); a case never
repeats across rounds. Onboarding is a short pre-scored set: a few real claims
of every kind and planted claims of every category, with answers shown after
each label.
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from helios.labelling.annotations import CATEGORIES
from helios.labelling.cards import displayed_claims
from helios.labelling.planted import corrupt
from helios.labelling.sets import ARMS, LabellingSet, assemble, derived_seed
from helios.vcl import VCLFlag, get_variant  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from helios.narrative.params import NarratorParams

__all__ = [
    "ONBOARDING_PLANTED_PER_CATEGORY",
    "ONBOARDING_SUPPORTED_PER_KIND",
    "onboarding_set",
    "select_training",
]

ONBOARDING_SUPPORTED_PER_KIND = 3
ONBOARDING_PLANTED_PER_CATEGORY = 4


def _arm(entry: Mapping[str, Any]) -> str | None:
    by_hash = {get_variant(a).compute_variant_config_hash(): a for a in ARMS}
    return by_hash.get(str(entry.get("variant_config_hash")))


def _kinds(entries: Sequence[Mapping[str, Any]]) -> set[str]:
    return {c.kind.value for e in entries for _, _, c in displayed_claims(e)}


def select_training(
    entries: Sequence[Mapping[str, Any]],
    *,
    n_per_arm: int,
    seed: int,
    exclude_cases: set[str],
) -> list[Mapping[str, Any]]:
    """Up to ``n_per_arm`` narratives per arm, Full and noLLM of the same case
    where possible, covering every claim kind the candidates have."""
    by_case: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for e in entries:
        arm = _arm(e)
        case = str(e["incident_id"])
        if arm and case not in exclude_cases and displayed_claims(e):
            by_case[case].setdefault(arm, e)
    cases = sorted(by_case)
    random.Random(seed).shuffle(cases)
    paired = [c for c in cases if len(by_case[c]) == len(ARMS)]
    single = [c for c in cases if len(by_case[c]) < len(ARMS)]
    wanted = _kinds([e for c in cases for e in by_case[c].values()])
    chosen: list[str] = []
    covered: set[str] = set()
    # Paired cases first: those that add a claim kind not yet covered, then
    # the rest; each arm is then topped up from unpaired cases.
    for c in paired:
        if len(chosen) < n_per_arm and _kinds(list(by_case[c].values())) - covered:
            chosen.append(c)
            covered |= _kinds(list(by_case[c].values()))
        if covered >= wanted:
            break
    for c in paired:
        if len(chosen) >= n_per_arm:
            break
        if c not in chosen:
            chosen.append(c)
    out: list[Mapping[str, Any]] = []
    for arm in ARMS:
        picked = [by_case[c][arm] for c in chosen]
        picked += [by_case[c][arm] for c in single if arm in by_case[c]]
        out += picked[:n_per_arm]
    return out


def onboarding_set(
    entries: Sequence[Mapping[str, Any]], *, seed: int, params: NarratorParams
) -> LabellingSet:
    """A pre-scored onboarding set: real claims of every kind and planted
    claims of every category; answers in the key (shown in onboarding mode)."""
    rng = random.Random(seed)
    real: dict[str, list[tuple[str, Any, Mapping[str, Any], str]]] = defaultdict(list)
    for e in entries:
        arm = _arm(e)
        if arm is None:
            continue
        for slot, index, claim in displayed_claims(e):
            real[claim.kind.value].append(
                (f"{e['run_id']}/{slot}/{index}", claim, e, arm)
            )
    rows = []
    for kind in sorted(real):
        pool = real[kind]
        for src, claim, e, arm in rng.sample(
            pool, min(ONBOARDING_SUPPORTED_PER_KIND, len(pool))
        ):
            info = {"arm": arm, "run_id": e["run_id"], "incident_id": e["incident_id"]}
            rows.append(
                (
                    src,
                    claim,
                    e,
                    {**info, "planted": False, "category": "", "source": src},
                )
            )
    sources = [s for kind in sorted(real) for s in real[kind]]
    for category in CATEGORIES:
        made = 0
        for src, claim, e, arm in rng.sample(sources, len(sources)):
            planted = corrupt(claim, e, category, rng, params)
            if planted is None:
                continue
            info = {"arm": arm, "run_id": e["run_id"], "incident_id": e["incident_id"]}
            rows.append(
                (
                    f"planted/{category}/{made}/{src}",
                    planted,
                    e,
                    {**info, "planted": True, "category": category, "source": src},
                )
            )
            made += 1
            if made == ONBOARDING_PLANTED_PER_CATEGORY:
                break
    rng.shuffle(rows)
    set_seed = derived_seed([r[0] for r in rows], "onboarding")
    return assemble(
        rows,
        set_seed,
        {
            "purpose": "onboarding",
            "rubric_sha": "",
            "counts": {
                "real": sum(not r[3]["planted"] for r in rows),
                "planted": sum(bool(r[3]["planted"]) for r in rows),
            },
            "ledgers": [],
        },
    )
