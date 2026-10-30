"""Aliases for every name a prompt could recognise (S2.3 design L-i).

The benchmark systems are public, so a real service name lets the model answer
from memory of the benchmark instead of from the telemetry. Before a digest is
sent, every in-scope service becomes ``svc-NN``, every out-of-scope component
``dep-NN`` and every fault flag of the OTel demo ``flag-NN``.

- The alias order is a permutation from SHA-256(incident ID, name):
  deterministic, different per incident, and no seed.
- A name matches in any spelling a log line, URL, RPC or pod name uses
  (``checkout``, ``checkoutservice``, ``checkout-service``, ``CheckoutService``)
  on token or camelCase boundaries, so the stem ``ad`` masks ``AdService`` but
  not ``address`` or ``GetAds``. Longer names are tried first.
- ``check`` refuses text in which a real name survives; its message carries a
  count only, never the name.

Operation and message words (``PlaceOrder``, "card declined") are kept: they
are the semantics L-pipe exists to decode.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

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

_SUFFIX = r"(?:[-_]?(?:service|Service|SERVICE))?"
_LEFT = r"(?:(?<![A-Za-z0-9])|(?<=[a-z0-9])(?=[A-Z]))"


class AliasLeakError(RuntimeError):
    """A real name survived masking; the prompt must not be sent."""


def _casings(word: str) -> str:
    forms = dict.fromkeys((word.lower(), word.capitalize(), word.upper()))
    return "(?:" + "|".join(re.escape(f) for f in forms) + ")"


def _parts(name: str) -> list[str]:
    """Name split on separators and camelCase, trailing ``service`` dropped."""
    words = [
        w
        for chunk in re.split(r"[^A-Za-z0-9]+", name)
        for w in re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", chunk)
    ]
    if len(words) > 1 and words[-1].lower() == "service":
        words = words[:-1]
    return words or [name]


def _pattern(name: str, *, flag: bool) -> str:
    if flag:
        return re.escape(name)
    body = "[-_]?".join(_casings(w) for w in _parts(name))
    return body + _SUFFIX


def _order(incident_id: str, names: Sequence[str]) -> list[str]:
    def key(n: str) -> str:
        return hashlib.sha256(f"{incident_id}\x00{n}".encode()).hexdigest()

    return sorted(dict.fromkeys(names), key=lambda n: (key(n), n))


def _labels(prefix: str, names: list[str]) -> dict[str, str]:
    width = max(2, len(str(len(names))))
    return {n: f"{prefix}-{i:0{width}d}" for i, n in enumerate(names, start=1)}


@dataclass(frozen=True)
class AliasMap:
    """Real name ↔ alias for one incident."""

    forward: Mapping[str, str]
    backward: Mapping[str, str]
    _regex: re.Pattern[str]
    _groups: Mapping[str, str]

    def _hits(self, text: str) -> list[re.Match[str]]:
        return [m for m in self._regex.finditer(text) if self._real_hit(m, text)]

    @staticmethod
    def _real_hit(m: re.Match[str], text: str) -> bool:
        # An all-capitals match must not run into more capitals ("ADDRESS").
        end = m.end()
        token = m.group(0)
        return not (
            token.isupper()
            and end < len(text)
            and text[end].isalpha()
            and text[end].isupper()
        )

    def _name_of(self, m: re.Match[str]) -> str:
        assert m.lastgroup is not None
        return self._groups[m.lastgroup]

    def mask(self, text: str) -> str:
        """Every real name replaced by its alias."""
        out: list[str] = []
        pos = 0
        for m in self._hits(text):
            out.append(text[pos : m.start()])
            out.append(self.forward[self._name_of(m)])
            pos = m.end()
        out.append(text[pos:])
        return "".join(out)

    def unmask(self, alias: str) -> str:
        """The real name of an alias; KeyError for an unknown alias."""
        return self.backward[alias]

    def check(self, text: str) -> None:
        """Raise AliasLeakError if any real name survives in ``text``."""
        hits = self._hits(text)
        if hits:
            raise AliasLeakError(f"{len(hits)} real name(s) survived masking")


def _by_length(names: Mapping[str, str]) -> list[str]:
    return sorted(names, key=lambda n: (-len(n), n))


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
    names = _by_length(forward)
    alternation = "|".join(
        f"(?P<n{i}>{_pattern(n, flag=n in FEATURE_FLAG_NAMES)})"
        for i, n in enumerate(names)
    )
    regex = re.compile(f"{_LEFT}(?:{alternation})(?![a-z])")
    return AliasMap(
        forward=forward,
        backward={a: n for n, a in forward.items()},
        _regex=regex,
        _groups={f"n{i}": n for i, n in enumerate(names)},
    )
