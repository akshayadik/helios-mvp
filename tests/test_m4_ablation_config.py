"""Tests for M4 ablation config constants and VCL get_all_variants() — VCLFlag-compliant."""

from __future__ import annotations

from helios.vcl import VCLManifest, get_all_variants


def test_get_all_variants_returns_eight_entries() -> None:
    variants = get_all_variants()
    assert len(variants) == 8


def test_get_all_variants_keys_match_confirmatory() -> None:
    from helios.vcl.variants import CONFIRMATORY_VARIANTS

    assert set(get_all_variants().keys()) == set(CONFIRMATORY_VARIANTS.keys())


def test_get_all_variants_returns_vcl_manifests() -> None:
    variants = get_all_variants()
    for v in variants.values():
        assert isinstance(v, VCLManifest)


def test_get_all_variants_returns_copy() -> None:
    v1 = get_all_variants()
    v2 = get_all_variants()
    assert v1 is not v2


def test_m4_expected_pipeline_row_count() -> None:
    from helios.config.m4_ablation import (
        EXPECTED_PIPELINE_ROW_COUNT,
        NUM_INCIDENTS,
        NUM_PIPELINES,
        NUM_VARIANTS,
    )

    assert NUM_INCIDENTS == 20
    assert NUM_PIPELINES == 3
    assert NUM_VARIANTS == 8
    assert EXPECTED_PIPELINE_ROW_COUNT == NUM_INCIDENTS * NUM_VARIANTS * NUM_PIPELINES


def test_hr_at_3_floor_is_positive_fraction() -> None:
    from helios.config.m4_ablation import HR_AT_3_FLOOR

    assert HR_AT_3_FLOOR > 0
    assert HR_AT_3_FLOOR < 1


def test_min_wilcoxon_pairs_is_positive_int() -> None:
    from helios.config.m4_ablation import MIN_WILCOXON_PAIRS

    assert isinstance(MIN_WILCOXON_PAIRS, int)
    assert MIN_WILCOXON_PAIRS > 0
