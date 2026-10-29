"""Out-of-scope services: never a trigger source, suspect, seed or ranked candidate.

Owner decision D-f (S2.1, 2026-10-27; deviation entry 47): the OTel testbed's
test harness (load generator, flag service) and observability stack
(Prometheus, Jaeger, OpenSearch, Grafana, the collector) are excluded from
every system's ranking and from the shared detection trigger. Their telemetry
stays in the graph and in every pipeline's input as context. One global list:
none of these names occurs among the RCAEval build services (checked
2026-10-27); the pool's names are checked at build-freeze.

Names match loosely, by the same stem rule as scoring (``service_key``):
lower-case, alphanumerics only, a trailing ``service`` dropped.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "OUT_OF_SCOPE_SERVICES",
    "filter_in_scope",
    "in_scope",
    "scope_digest",
    "scope_key",
]

HELIOS_ENABLE_SCOPE: bool = True

OUT_OF_SCOPE_SERVICES: frozenset[str] = frozenset(
    {
        # test harness
        "load-generator",
        "flagd",
        "flagd-ui",
        # observability stack
        "prometheus",
        "jaeger",
        "opensearch",
        "grafana",
        "otel-collector",
        "otelcol-contrib",  # the collector under its own log service name
    }
)


def scope_key(name: str) -> str:
    """Stem used to compare names (the scoring rule: ``adService`` ~ ``ad``)."""
    key = "".join(ch for ch in name.lower() if ch.isalnum())
    return key.removesuffix("service") or key


_OUT_KEYS = frozenset(scope_key(s) for s in OUT_OF_SCOPE_SERVICES)


def in_scope(service: str) -> bool:
    """True unless ``service`` is on the out-of-scope list."""
    return scope_key(service) not in _OUT_KEYS


def filter_in_scope(ranked: Sequence[str]) -> list[str]:
    """``ranked`` without out-of-scope services, order kept."""
    return [s for s in ranked if in_scope(s)]


def scope_digest() -> str:
    """SHA-256 of the sorted list (canonical JSON); recorded with every trigger."""
    text = json.dumps(sorted(OUT_OF_SCOPE_SERVICES), separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
