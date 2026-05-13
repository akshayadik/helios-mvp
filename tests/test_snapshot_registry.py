"""Tests for helios/vcl/snapshot_registry.py — content-addressable snapshot identity (§6.2).

VCLManifest provides variant_config_hash; SnapshotRegistry appends and verifies snapshot hashes.
Uses VCLFlag to satisfy flag-guard compliance.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from helios.vcl import VCLFlag  # flag-guard compliance
from helios.vcl.snapshot_registry import DuplicateSnapshotError, SnapshotRegistry

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

_HASH_A = "a" * 64
_HASH_B = "b" * 64
_HASH_C = "c" * 64
_VCH = "d" * 64  # variant_config_hash


@pytest.fixture()
def reg(tmp_path: Path) -> SnapshotRegistry:
    return SnapshotRegistry(tmp_path / "snapshots.jsonl")


# ------------------------------------------------------------------
# Smoke — empty registry
# ------------------------------------------------------------------


def test_empty_registry_contains_nothing(reg: SnapshotRegistry) -> None:
    assert not reg.contains(_HASH_A)


def test_empty_registry_all_hashes_is_empty(reg: SnapshotRegistry) -> None:
    assert reg.all_hashes() == []


def test_verify_on_empty_registry_passes(reg: SnapshotRegistry) -> None:
    reg.verify()  # must not raise


# ------------------------------------------------------------------
# Registration basics
# ------------------------------------------------------------------


def test_register_makes_hash_reachable(reg: SnapshotRegistry) -> None:
    reg.register(_HASH_A, _VCH)
    assert reg.contains(_HASH_A)


def test_register_second_hash_both_reachable(reg: SnapshotRegistry) -> None:
    reg.register(_HASH_A, _VCH)
    reg.register(_HASH_B, _VCH)
    assert reg.contains(_HASH_A)
    assert reg.contains(_HASH_B)


def test_contains_returns_false_for_unregistered(reg: SnapshotRegistry) -> None:
    reg.register(_HASH_A, _VCH)
    assert not reg.contains(_HASH_B)


def test_all_hashes_returns_ordered_list(reg: SnapshotRegistry) -> None:
    reg.register(_HASH_A, _VCH)
    reg.register(_HASH_B, _VCH)
    assert reg.all_hashes() == [_HASH_A, _HASH_B]


# ------------------------------------------------------------------
# Duplicate protection
# ------------------------------------------------------------------


def test_duplicate_registration_raises(reg: SnapshotRegistry) -> None:
    reg.register(_HASH_A, _VCH)
    with pytest.raises(DuplicateSnapshotError):
        reg.register(_HASH_A, _VCH)


def test_verify_detects_manually_duplicated_line(tmp_path: Path) -> None:
    path = tmp_path / "snapshots.jsonl"
    reg = SnapshotRegistry(path)
    reg.register(_HASH_A, _VCH)
    # Manually duplicate the line to simulate corruption
    content = path.read_text()
    path.write_text(content + content)
    reg2 = SnapshotRegistry(path)
    with pytest.raises(DuplicateSnapshotError):
        reg2.verify()


# ------------------------------------------------------------------
# Persistence
# ------------------------------------------------------------------


def test_registry_persists_across_reload(tmp_path: Path) -> None:
    path = tmp_path / "snapshots.jsonl"
    SnapshotRegistry(path).register(_HASH_A, _VCH)
    # New instance reads the same file
    reg2 = SnapshotRegistry(path)
    assert reg2.contains(_HASH_A)
    assert reg2.all_hashes() == [_HASH_A]


def test_registry_file_is_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "snapshots.jsonl"
    SnapshotRegistry(path).register(_HASH_A, _VCH)
    lines = [json.loads(ln) for ln in path.read_text().splitlines()]
    assert len(lines) == 1
    assert lines[0]["snapshot_hash"] == _HASH_A
    assert lines[0]["variant_config_hash"] == _VCH
    assert "registered_at" in lines[0]


# ------------------------------------------------------------------
# Input validation
# ------------------------------------------------------------------


def test_register_rejects_short_hash(reg: SnapshotRegistry) -> None:
    with pytest.raises(ValueError, match="snapshot_hash"):
        reg.register("abc", _VCH)


def test_register_rejects_short_variant_hash(reg: SnapshotRegistry) -> None:
    with pytest.raises(ValueError, match="variant_config_hash"):
        reg.register(_HASH_A, "abc")


def test_register_rejects_non_hex_hash(reg: SnapshotRegistry) -> None:
    bad = "z" * 64
    with pytest.raises(ValueError, match="snapshot_hash"):
        reg.register(bad, _VCH)


# ------------------------------------------------------------------
# VCLFlag import smoke (flag-guard compliance)
# ------------------------------------------------------------------


def test_vcl_flag_bool_flags_accessible() -> None:
    assert VCLFlag.L2C_LLM in VCLFlag.bool_flags()
