"""Read-only accessors over the frozen variant tables.

Kept separate from variants.py because the OSF freeze fingerprints that file
by git blob SHA (variant_hashes.json `vcl_freeze_sha`); any edit to it, even
one that leaves every variant_config_hash unchanged, fails the freeze check.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .registry import VCLFlag
from .variants import CONFIRMATORY_VARIANTS, get_variant

if TYPE_CHECKING:
    from pathlib import Path

    from .config import VCLManifest


def get_all_variants() -> dict[str, VCLManifest]:
    """Return all confirmatory variants as a fresh dict (8 entries)."""
    return dict(CONFIRMATORY_VARIANTS)


# ── Flag consumers (S4.10 O-h; S5.2 disjointness scanner) ───────────────────


def flag_readers(repo_root: Path) -> dict[str, list[str]]:
    """Map each boolean flag to the runtime files (``helios/`` outside
    ``helios/vcl/``) that read it.

    Delegates to the S5.2 disjointness scanner: a read is ``VCLFlag.<NAME>``
    (which covers ``@gated_by``) or an attribute read on a manifest
    (``manifest.x``, ``self._manifest.x``). Build tools in ``bin/`` do not
    count: they never run in an incident. Files are parsed, never imported.
    """
    from .disjointness import runtime_readers

    return runtime_readers(repo_root)


def flags_off_versus_full(name: str) -> list[str]:
    """Boolean flags that ``name`` sets differently from HELIOS-Full."""
    full = CONFIRMATORY_VARIANTS["HELIOS-Full"]
    manifest = get_variant(name)
    return [
        f.value
        for f in VCLFlag.bool_flags()
        if getattr(manifest, f.value) != getattr(full, f.value)
    ]


def unconsumed_variants(
    names: list[str], readers: dict[str, list[str]]
) -> dict[str, str]:
    """Variants whose changed flags nothing reads: they run as HELIOS-Full."""
    refused: dict[str, str] = {}
    for name in names:
        dead = [f for f in flags_off_versus_full(name) if not readers.get(f)]
        if dead:
            refused[name] = "no reader of " + ", ".join(dead) + " outside helios/vcl"
    return refused
