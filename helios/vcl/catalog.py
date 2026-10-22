"""Read-only accessors over the frozen variant tables.

Kept separate from variants.py because the OSF freeze fingerprints that file
by git blob SHA (variant_hashes.json `vcl_freeze_sha`); any edit to it, even
one that leaves every variant_config_hash unchanged, fails the freeze check.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .variants import CONFIRMATORY_VARIANTS

if TYPE_CHECKING:
    from .config import VCLManifest


def get_all_variants() -> dict[str, VCLManifest]:
    """Return all confirmatory variants as a fresh dict (8 entries)."""
    return dict(CONFIRMATORY_VARIANTS)
