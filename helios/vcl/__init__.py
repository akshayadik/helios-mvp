"""Variant Control Layer — C1 §6.1."""

from .config import VCLManifest
from .decorators import (
    GatedComponentInactiveError,
    gated_by,
    get_current_manifest,
    set_current_manifest,
)
from .registry import VCLFlag
from .snapshot_registry import DuplicateSnapshotError, SnapshotRegistry
from .utils import canonical_json
from .variants import CONFIRMATORY_VARIANTS, EXPLORATORY_VARIANTS, get_variant

__all__ = [
    "CONFIRMATORY_VARIANTS",
    "EXPLORATORY_VARIANTS",
    "DuplicateSnapshotError",
    "GatedComponentInactiveError",
    "SnapshotRegistry",
    "VCLFlag",
    "VCLManifest",
    "canonical_json",
    "gated_by",
    "get_current_manifest",
    "get_variant",
    "set_current_manifest",
]
