"""Read-only accessors over the frozen variant tables.

Kept separate from variants.py because the OSF freeze fingerprints that file
by git blob SHA (variant_hashes.json `vcl_freeze_sha`); any edit to it, even
one that leaves every variant_config_hash unchanged, fails the freeze check.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from .registry import VCLFlag
from .variants import CONFIRMATORY_VARIANTS, get_variant

if TYPE_CHECKING:
    from pathlib import Path

    from .config import VCLManifest


def get_all_variants() -> dict[str, VCLManifest]:
    """Return all confirmatory variants as a fresh dict (8 entries)."""
    return dict(CONFIRMATORY_VARIANTS)


# ── Flag consumers (S4.10 O-h; also the S5.2 disjointness scan) ──────────────

_SCAN_ROOTS: tuple[str, ...] = ("helios", "bin")
_SCAN_SKIP: tuple[str, ...] = ("helios/vcl/",)


def flag_readers(repo_root: Path) -> dict[str, list[str]]:
    """Map each boolean flag to the files outside ``helios/vcl/`` that read it.

    A read is ``<anything>.<flag>`` (a manifest attribute) or ``VCLFlag.<NAME>``
    (which covers ``@gated_by``). Files are parsed, never imported.
    """
    flags = {f.value: f.name for f in VCLFlag.bool_flags()}
    by_name = {name: value for value, name in flags.items()}
    readers: dict[str, set[str]] = {value: set() for value in flags}
    for root in _SCAN_ROOTS:
        for path in sorted((repo_root / root).rglob("*.py")):
            rel = path.relative_to(repo_root).as_posix()
            if rel.startswith(_SCAN_SKIP):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Attribute):
                    continue
                if isinstance(node.value, ast.Name) and node.value.id == "VCLFlag":
                    if node.attr in by_name:
                        readers[by_name[node.attr]].add(rel)
                elif node.attr in readers:
                    readers[node.attr].add(rel)
    return {flag: sorted(files) for flag, files in readers.items()}


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
