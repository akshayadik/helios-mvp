"""Aliases for every name a prompt could recognise (S2.3 design L-i).

The benchmark systems are public, so a real service name lets the model answer
from memory of the benchmark instead of from the telemetry. Before a digest is
sent, every in-scope service becomes ``svc-NN``, every out-of-scope component
``dep-NN`` and every fault flag of the OTel demo ``flag-NN``.

- The alias order is a permutation from SHA-256(incident ID, name):
  deterministic, different per incident, and no seed.
- Matching is on tokens (alphanumeric runs split at camelCase and digits): a
  run of tokens joined by nothing, ``-``, ``_``, ``.`` or a space that spells
  a name's scope-key stem, with or without ``service``, is that name
  (``checkoutservice``, ``CheckoutService``, ``product-catalog``,
  ``ProductCatalog``). So the stem ``ad`` masks ``AdService`` but not
  ``address`` or ``GetAds``. Longest run first, so ``ts-order-mongo`` keeps
  its own alias rather than ``ts-order``'s; a run inside an unknown
  hyphenated name is left for ``check`` to refuse, never half-masked.
- ``check`` is independent of ``mask``'s boundary rules and refuses text in
  which a real name survives; its message carries a count only.

Operation and message words (``PlaceOrder``, "card declined") are kept: they
are the semantics L-pipe exists to decode.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from helios.telemetry.scope import scope_key
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "FEATURE_FLAG_NAMES",
    "AliasLeakError",
    "AliasMap",
    "build_alias_map",
]

HELIOS_ENABLE_LPIPE_ALIASES: bool = True

# The OTel demo's flagd fault flags (otel_campaign.FAULTS); a test keeps them equal.
FEATURE_FLAG_NAMES: frozenset[str] = frozenset(
    {
        "adFailure",
        "adHighCpu",
        "adManualGc",
        "cartFailure",
        "emailMemoryLeak",
        "paymentFailure",
        "paymentUnreachable",
        "productCatalogFailure",
        "recommendationCacheFailure",
    }
)

_SUFFIX = "service"
_MAX_RUN = 6  # tokens one name can span (ts-order-other-service is 4)
_JOINS = frozenset({"", "-", "_", ".", " "})
_TOKEN = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|[0-9]+")
_CHUNK = re.compile(r"[A-Za-z0-9]+")


class AliasLeakError(RuntimeError):
    """A real name survived masking; the prompt must not be sent."""


def _tokens(text: str) -> list[tuple[int, int, str]]:
    """(start, end, lowercase token): alphanumeric runs split at camelCase and digits."""
    out = []
    for chunk in _CHUNK.finditer(text):
        for t in _TOKEN.finditer(chunk.group(0)):
            out.append(
                (chunk.start() + t.start(), chunk.start() + t.end(), t.group(0).lower())
            )
    return out


def _stem(name: str, *, flag: bool) -> str:
    return name.lower() if flag else scope_key(name)


def _order(incident_id: str, names: Sequence[str]) -> list[str]:
    def key(n: str) -> str:
        return hashlib.sha256(f"{incident_id}\x00{n}".encode()).hexdigest()

    return sorted(dict.fromkeys(names), key=lambda n: (key(n), n))


def _labels(prefix: str, names: list[str]) -> dict[str, str]:
    width = max(2, len(str(len(names))))
    return {n: f"{prefix}-{i:0{width}d}" for i, n in enumerate(names, start=1)}


def _runs(text: str, toks: list[tuple[int, int, str]], i: int) -> list[tuple[int, str]]:
    """(last index, concatenation) of token runs from i, longest first."""
    out = []
    joined = toks[i][2]
    runs = [(i, joined)]
    for j in range(i + 1, min(i + _MAX_RUN, len(toks))):
        if text[toks[j - 1][1] : toks[j][0]] not in _JOINS:
            break
        joined += toks[j][2]
        runs.append((j, joined))
    out.extend(reversed(runs))
    return out


def _hyphen_word(
    text: str, toks: list[tuple[int, int, str]], k: int, side: int
) -> bool:
    """A letter token joined by '-' just before (side -1) or after (+1) the run."""
    n = k + side
    if not 0 <= n < len(toks):
        return False
    gap = text[toks[n][1] : toks[k][0]] if side < 0 else text[toks[k][1] : toks[n][0]]
    return gap == "-" and toks[n][2][0].isalpha()


@dataclass(frozen=True)
class AliasMap:
    """Real name ↔ alias for one incident."""

    forward: Mapping[str, str]
    backward: Mapping[str, str]
    _stems: Mapping[str, str]

    def _name(self, joined: str) -> str | None:
        if joined in self._stems:
            return self._stems[joined]
        if joined.endswith(_SUFFIX) and joined[: -len(_SUFFIX)] in self._stems:
            return self._stems[joined[: -len(_SUFFIX)]]
        return None

    def mask(self, text: str) -> str:
        """Every real name replaced by its alias.

        Longest token run first; a run inside an unknown hyphenated name
        (``ts-order-mongo`` when only ``ts-order-service`` is known) is left
        alone rather than half-masked — ``check`` then refuses the text.
        """
        toks = _tokens(text)
        out: list[str] = []
        pos = i = 0
        while i < len(toks):
            for j, joined in _runs(text, toks, i):
                name = self._name(joined)
                if name is None:
                    continue
                if _hyphen_word(text, toks, i, -1) or _hyphen_word(text, toks, j, 1):
                    continue
                out.append(text[pos : toks[i][0]])
                out.append(self.forward[name])
                pos = toks[j][1]
                i = j
                break
            i += 1
        out.append(text[pos:])
        return "".join(out)

    def unmask(self, alias: str) -> str:
        """The real name of an alias; KeyError for an unknown alias."""
        return self.backward[alias]

    def check(self, text: str) -> None:
        """Raise AliasLeakError if any real name survives in ``text``.

        Independent of ``mask``'s boundary rules: any token run spelling a
        name's stem (with or without ``service``), or any token that starts
        with stem + ``service``, is a leak.
        """
        toks = _tokens(text)
        hits = 0
        for i in range(len(toks)):
            if any(self._name(joined) for _, joined in _runs(text, toks, i)) or any(
                toks[i][2].startswith(stem + _SUFFIX) for stem in self._stems
            ):
                hits += 1
        if hits:
            raise AliasLeakError(f"{hits} real name(s) survived masking")


def build_alias_map(
    incident_id: str, candidates: Sequence[str], components: Sequence[str]
) -> AliasMap:
    """Aliases for the window's candidates, components and the demo's fault flags."""
    services = _order(incident_id, candidates)
    deps = _order(incident_id, [c for c in components if c not in set(candidates)])
    flags = _order(incident_id, sorted(FEATURE_FLAG_NAMES))
    forward = {
        **_labels("svc", services),
        **_labels("dep", deps),
        **_labels("flag", flags),
    }
    stems: dict[str, str] = {}
    for name in sorted(forward):
        stems.setdefault(_stem(name, flag=name in FEATURE_FLAG_NAMES), name)
    return AliasMap(
        forward=forward, backward={a: n for n, a in forward.items()}, _stems=stems
    )
