"""Per-system service-name normalisation (S0.1 finding F4, D11 §3).

RCAEval names one service differently per modality (e.g. ``frontendservice``
in traces, ``frontend`` in metrics). Every name is mapped to one canonical
service name before it reaches a pipeline, so the graph has one node per
service and the ground-truth root cause can be matched against the ranking.

Known aliases are listed explicitly. Any other pair of names that collapse to
the same stem once a ``service`` suffix is removed is treated as an
*unresolved alias*: sealing fails until the table says whether they are the
same service. Nothing is merged silently.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "ALIASES",
    "DISTINCT",
    "SYSTEMS",
    "UnresolvedAliasError",
    "candidate_set",
    "canonical",
    "unresolved_aliases",
]

HELIOS_ENABLE_RCAEVAL_ADAPTER: bool = True

# System code in RCAEval case names: re2ob_..., re2tt_..., re1ss_...
SYSTEMS: dict[str, str] = {
    "ob": "Online Boutique",
    "tt": "Train-Ticket",
    "ss": "Sock Shop",
}

# raw name (lower case) -> canonical name, per system. Append-only: a new
# entry changes the candidate set of affected cases, so it is added before
# sealing and never after.
ALIASES: dict[str, dict[str, str]] = {
    "ob": {"frontendservice": "frontend"},
    "tt": {},
    "ss": {},
}

# Name pairs that look like aliases but are different services, per system,
# with the reason. Same append-only rule as ALIASES.
DISTINCT: dict[str, dict[frozenset[str], str]] = {
    "ob": {},
    "tt": {},
    "ss": {
        frozenset({"payment", "paymentservice"}): (
            "Sock Shop `payment` vs Online Boutique `paymentservice`: build case "
            "re3ss_carts_f1_3 also holds sparse Online Boutique series (co-located "
            "deployment); kept as recorded, not merged"
        ),
        frozenset({"shipping", "shippingservice"}): (
            "Sock Shop `shipping` vs Online Boutique `shippingservice`: same case "
            "and reason as payment / paymentservice"
        ),
    },
}

_SUFFIX = re.compile(r"[-_]?service$")


def canonical(system: str, raw: str) -> str:
    """Canonical service name for ``raw`` in ``system``."""
    if system not in ALIASES:
        raise ValueError(f"unknown system {system!r}")
    name = raw.strip().lower()
    return ALIASES[system].get(name, name)


def _stem(name: str) -> str:
    return _SUFFIX.sub("", name)


def unresolved_aliases(system: str, names: Iterable[str]) -> list[tuple[str, str]]:
    """Pairs of distinct canonical names that look like one service."""
    by_stem: dict[str, set[str]] = {}
    for raw in names:
        name = canonical(system, raw)
        by_stem.setdefault(_stem(name), set()).add(name)
    pairs: list[tuple[str, str]] = []
    for group in by_stem.values():
        ordered = sorted(group)
        pairs.extend(
            (a, b)
            for i, a in enumerate(ordered)
            for b in ordered[i + 1 :]
            if frozenset({a, b}) not in DISTINCT[system]
        )
    return pairs


class UnresolvedAliasError(ValueError):
    """Two service names may denote one service and ALIASES does not say."""


def candidate_set(system: str, *modalities: Iterable[str]) -> list[str]:
    """Sorted union of canonical service names over every modality (F5).

    Raises UnresolvedAliasError when the union holds a likely alias pair.
    """
    union = sorted({canonical(system, n) for names in modalities for n in names if n})
    pairs = unresolved_aliases(system, union)
    if pairs:
        raise UnresolvedAliasError(
            f"{SYSTEMS[system]}: unresolved service-name aliases {pairs}; "
            "add them to helios.adapters.names.ALIASES before sealing"
        )
    return union
