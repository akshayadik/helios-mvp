"""Labelling set: what raters may see and the sealed key they may not
(S2.9 design §5.3, owner decisions R-b, R-d, R-f, R-k, R-o).

Every displayed claim of every HELIOS-Full and HELIOS-noLLM narrative becomes
one item, with code-generated planted claims mixed in, all shuffled across
narratives and arms. ``set.json`` holds only an opaque item ID, the top-3
header, the claim kind and sentence, and its evidence cards; ``key.json``
holds the arm, run, case, slot, planted flag and category. The shuffle seed is
derived from the sorted real-claim keys and the rubric hash, so nobody chooses
it and anyone can recompute it (no new seed-register block).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from helios.labelling.cards import cards_for, displayed_claims, header_top3
from helios.labelling.planted import plant
from helios.vcl import VCLFlag, get_variant  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from helios.narrative.claims import Claim
    from helios.narrative.params import NarratorParams

__all__ = [
    "ARMS",
    "CONFIRMATORY_PLANTED_SHARE",
    "TRAINING_PLANTED_SHARE",
    "LabellingSet",
    "build_set",
    "derived_seed",
    "rater_order",
    "rubric_sha",
    "write_set",
]

ARMS: tuple[str, ...] = ("HELIOS-Full", "HELIOS-noLLM")  # A-H7
TRAINING_PLANTED_SHARE = 1 / 4
CONFIRMATORY_PLANTED_SHARE = 1 / 10
_ID_HEX = 16


@dataclass
class LabellingSet:
    items: list[dict[str, Any]]
    key: dict[str, dict[str, Any]]
    manifest: dict[str, Any]


def rubric_sha(path: Path) -> str:
    """SHA-256 of the rubric file's bytes (frozen before confirmatory labelling)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def derived_seed(item_keys: Sequence[str], rubric_sha: str) -> int:
    """The shuffle seed from the sorted item keys and the rubric hash (R-o)."""
    payload = "\n".join(sorted(item_keys)) + "\n" + rubric_sha
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big")


def rater_order(seed: int, person: str, n: int) -> list[int]:
    """Each person's own permutation of the item positions."""
    order = list(range(n))
    random.Random(f"{seed}:{person}").shuffle(order)
    return order


def _arm_of(entry: Mapping[str, Any]) -> str | None:
    by_hash = {get_variant(a).compute_variant_config_hash(): a for a in ARMS}
    return by_hash.get(str(entry.get("variant_config_hash")))


def _item(item_id: str, claim: Claim, entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "item": item_id,
        "header": header_top3(entry),
        "kind": claim.kind.value,
        "sentence": claim.sentence,
        "cards": [dataclasses.asdict(c) for c in cards_for(claim, entry)],
    }


def _opaque(seed: int, key: str) -> str:
    return hashlib.sha256(f"{seed}|{key}".encode()).hexdigest()[:_ID_HEX]


def build_set(
    entries: Sequence[Mapping[str, Any]],
    *,
    planted_share: float,
    rubric_sha: str,
    params: NarratorParams,
) -> LabellingSet:
    """Items, key and manifest for ``entries`` (odd entries skipped and counted)."""
    sources: list[tuple[str, Claim, Mapping[str, Any]]] = []
    meta: dict[str, dict[str, Any]] = {}
    skipped = 0
    for entry in entries:
        arm = _arm_of(entry)
        claims = displayed_claims(entry)
        steps = {str(s["id"]): s for s in entry["steps"]}
        if arm is None or not claims or not (steps.get("F", {}).get("ranked")):
            skipped += 1
            continue
        for slot, index, claim in claims:
            src = f"{entry['run_id']}/{slot}/{index}"
            sources.append((src, claim, entry))
            meta[src] = {
                "arm": arm,
                "run_id": entry["run_id"],
                "incident_id": entry["incident_id"],
                "slot": slot,
                "index": index,
            }
    seed = derived_seed([s for s, _, _ in sources], rubric_sha)
    rng = random.Random(seed)
    planted = plant(sources, planted_share, rng, params) if sources else []
    by_src = {s: e for s, _, e in sources}
    rows: list[tuple[str, Claim, Mapping[str, Any], dict[str, Any]]] = []
    for src, claim, entry in sources:
        rows.append(
            (
                src,
                claim,
                entry,
                {**meta[src], "planted": False, "category": "", "source": src},
            )
        )
    for n, (src, claim, category) in enumerate(planted):
        rows.append(
            (
                f"planted/{n}/{src}",
                claim,
                by_src[src],
                {**meta[src], "planted": True, "category": category, "source": src},
            )
        )
    rng.shuffle(rows)
    items, key = [], {}
    for row_key, claim, entry, k in rows:
        item_id = _opaque(seed, row_key)
        items.append(_item(item_id, claim, entry))
        key[item_id] = k
    manifest = {
        "seed": seed,
        "rubric_sha": rubric_sha,
        "planted_share": planted_share,
        "sources": sorted(meta),
        "counts": {
            "entries": len(entries),
            "skipped": skipped,
            "real": len(sources),
            "planted": len(planted),
        },
        "ledgers": [],
    }
    return LabellingSet(items, key, manifest)


def _dump(obj: Any) -> bytes:
    return (
        json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode()


def write_set(s: LabellingSet, directory: Path) -> None:
    """Write set.json, key.json and manifest.json once; refuse an existing directory."""
    directory.mkdir(parents=True, exist_ok=False)
    set_bytes, key_bytes = _dump(s.items), _dump(s.key)
    manifest = {
        **s.manifest,
        "set_sha256": hashlib.sha256(set_bytes).hexdigest(),
        "key_sha256": hashlib.sha256(key_bytes).hexdigest(),
    }
    (directory / "set.json").write_bytes(set_bytes)
    (directory / "key.json").write_bytes(key_bytes)
    (directory / "manifest.json").write_bytes(_dump(manifest))
