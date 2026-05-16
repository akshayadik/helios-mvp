"""Tests for helios/vcl - VCL Stage 0 (ENG03-ENG06)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from helios.integrity_gate import MetricIntegrityGate
from helios.vcl import (
    CONFIRMATORY_VARIANTS,
    EXPLORATORY_VARIANTS,
    GatedComponentInactiveError,
    VCLFlag,
    VCLManifest,
    canonical_json,
    gated_by,
    get_current_manifest,
    get_variant,
    set_current_manifest,
)
from helios.vcl.decorators import _current_manifest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def clear_manifest():
    """Reset the ContextVar before and after each decorator test."""
    token = _current_manifest.set(None)
    yield
    _current_manifest.reset(token)


@pytest.fixture()
def full_manifest() -> VCLManifest:
    return CONFIRMATORY_VARIANTS["HELIOS-Full"]


class _GateMockLedger:
    def __init__(self) -> None:
        self.entries: list[dict[str, str]] = []

    def append(self, fields: dict[str, str]) -> None:
        self.entries.append(fields)


# ---------------------------------------------------------------------------
# TestCanonicalJson
# ---------------------------------------------------------------------------


class TestCanonicalJson:
    def test_sorted_keys(self) -> None:
        result = canonical_json({"z": 1, "a": 2})
        assert result.index('"a"') < result.index('"z"')

    def test_no_whitespace(self) -> None:
        result = canonical_json({"x": 1, "y": 2})
        assert " " not in result

    def test_float_precision_6_decimals(self) -> None:
        result = canonical_json({"v": 1.123456789})
        assert "1.123457" in result

    def test_nested_objects_sorted(self) -> None:
        result = canonical_json({"b": {"z": 3, "a": 1}, "a": 2})
        assert result.startswith('{"a"')

    def test_list_values_rounded(self) -> None:
        result = canonical_json({"vals": [1.111111111, 2.999999999]})
        assert "1.111111" in result
        assert "3.0" in result

    def test_non_serialisable_raises(self) -> None:
        with pytest.raises(TypeError, match="not JSON serialisable"):
            canonical_json({"bad": object()})


# ---------------------------------------------------------------------------
# TestVCLFlag
# ---------------------------------------------------------------------------


class TestVCLFlag:
    def test_flag_count_is_14(self) -> None:
        assert len(VCLFlag) == 14

    def test_all_flags_returns_14_strings(self) -> None:
        flags = VCLFlag.all_flags()
        assert len(flags) == 14
        assert all(isinstance(f, str) for f in flags)

    def test_bool_flags_excludes_ingest_mode(self) -> None:
        bf = VCLFlag.bool_flags()
        assert VCLFlag.INGEST_MODE not in bf
        assert len(bf) == 13

    def test_flag_values_are_lowercase_strings(self) -> None:
        for flag in VCLFlag:
            assert flag.value == flag.value.lower()
            assert isinstance(flag.value, str)


# ---------------------------------------------------------------------------
# TestVCLManifest
# ---------------------------------------------------------------------------


class TestVCLManifest:
    def test_hash_is_64_char_hex(self, full_manifest: VCLManifest) -> None:
        h = full_manifest.compute_variant_config_hash()
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_is_deterministic(self, full_manifest: VCLManifest) -> None:
        assert (
            full_manifest.compute_variant_config_hash()
            == full_manifest.compute_variant_config_hash()
        )

    def test_hash_changes_on_flag_flip(self) -> None:
        m1 = VCLManifest.from_flags(lpipe=True)
        m2 = VCLManifest.from_flags(lpipe=False)
        assert m1.compute_variant_config_hash() != m2.compute_variant_config_hash()

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            VCLManifest.from_flags(nonexistent_flag=True)

    def test_frozen_raises_on_mutation(self, full_manifest: VCLManifest) -> None:
        with pytest.raises(ValidationError):
            full_manifest.lpipe = False  # type: ignore[misc]

    def test_from_flags_factory(self) -> None:
        m = VCLManifest.from_flags(dpipe=True, lpipe=True, ingest_mode="live")
        assert m.dpipe is True
        assert m.lpipe is True
        assert m.ingest_mode == "live"

    def test_ingest_mode_live_accepted(self) -> None:
        m = VCLManifest.from_flags(ingest_mode="live")
        assert m.ingest_mode == "live"

    def test_ingest_mode_invalid_raises(self) -> None:
        with pytest.raises(ValidationError):
            VCLManifest.from_flags(ingest_mode="batch")

    def test_three_mutations(self) -> None:
        """Three manifest mutations each hash-differ and are rejected by MetricIntegrityGate."""
        baseline = VCLManifest.from_flags()
        baseline_hash = baseline.compute_variant_config_hash()

        mutations = [
            VCLManifest.from_flags(lpipe=True),
            VCLManifest.from_flags(model_version="helios-llm-experimental"),
            VCLManifest.from_flags(prompt_template_id="variant-v2"),
        ]

        for mutated in mutations:
            mutated_hash = mutated.compute_variant_config_hash()
            assert mutated_hash != baseline_hash

            ledger = _GateMockLedger()
            gate = MetricIntegrityGate(
                expected_config_hash=baseline_hash,
                ledger=ledger,
                run_id="run-001",
                analytic_consequence="test",
            )
            row = {
                "variant_config_hash": mutated_hash,
                "snapshot_hash": "a" * 64,
                "run_id": "run-001",
            }
            result = gate.check(row, incident_id="INC-001")
            assert result.status == "FAIL"
            assert result.gate_check == "variant_config_hash_match"
            assert len(ledger.entries) == 1


# ---------------------------------------------------------------------------
# TestGatedBy
# ---------------------------------------------------------------------------


class TestGatedBy:
    def test_gated_passes_when_flag_true(self, clear_manifest: None) -> None:
        manifest = VCLManifest.from_flags(lpipe=True)
        set_current_manifest(manifest)

        @gated_by(VCLFlag.LPIPE)
        def run_lpipe() -> str:
            return "ok"

        assert run_lpipe() == "ok"

    def test_gated_raises_when_flag_false(self, clear_manifest: None) -> None:
        manifest = VCLManifest.from_flags(lpipe=False)
        set_current_manifest(manifest)

        @gated_by(VCLFlag.LPIPE)
        def run_lpipe() -> str:
            return "ok"

        with pytest.raises(GatedComponentInactiveError):
            run_lpipe()

    def test_missing_manifest_raises_runtime_error(self, clear_manifest: None) -> None:
        @gated_by(VCLFlag.DPIPE)
        def run_dpipe() -> str:
            return "ok"

        with pytest.raises(RuntimeError, match="not set"):
            run_dpipe()

    def test_non_bool_flag_raises_type_error_at_decoration(self) -> None:
        with pytest.raises(TypeError, match="not a boolean flag"):

            @gated_by(VCLFlag.INGEST_MODE)
            def bad_gate() -> None:
                pass

    def test_decorator_registers_gated_by_attr(self) -> None:
        @gated_by(VCLFlag.GPIPE)
        def run_gpipe() -> None:
            pass

        assert run_gpipe.__gated_by__ == "gpipe"  # type: ignore[attr-defined]

    def test_set_and_get_manifest_roundtrip(self, clear_manifest: None) -> None:
        manifest = VCLManifest.from_flags(dpipe=True)
        set_current_manifest(manifest)
        assert get_current_manifest() is manifest

    def test_error_message_contains_hash(self, clear_manifest: None) -> None:
        manifest = VCLManifest.from_flags(mahc=False)
        set_current_manifest(manifest)

        @gated_by(VCLFlag.MAHC)
        def run_mahc() -> None:
            pass

        with pytest.raises(GatedComponentInactiveError, match="variant_config_hash="):
            run_mahc()


# ---------------------------------------------------------------------------
# TestVariants
# ---------------------------------------------------------------------------


class TestVariants:
    def test_eight_variants_defined(self) -> None:
        assert len(CONFIRMATORY_VARIANTS) == 8

    def test_full_all_bool_flags_true(self) -> None:
        full = CONFIRMATORY_VARIANTS["HELIOS-Full"]
        for flag in VCLFlag.bool_flags():
            assert getattr(full, flag.value) is True, f"{flag.value} should be True"

    def test_no_router_only_router_false(self) -> None:
        no_router = CONFIRMATORY_VARIANTS["HELIOS-noRouter"]
        assert no_router.router is False
        # Every other bool flag must be True in noRouter
        for flag in VCLFlag.bool_flags():
            if flag is VCLFlag.ROUTER:
                continue
            assert (
                getattr(no_router, flag.value) is True
            ), f"{flag.value} should be True in HELIOS-noRouter"

    def test_all_variants_use_recorded_ingest_mode(self) -> None:
        for name, manifest in CONFIRMATORY_VARIANTS.items():
            assert (
                manifest.ingest_mode == "recorded"
            ), f"{name} ingest_mode should be 'recorded'"

    def test_all_variant_hashes_are_unique(self) -> None:
        hashes = [
            m.compute_variant_config_hash() for m in CONFIRMATORY_VARIANTS.values()
        ]
        assert len(hashes) == len(set(hashes)), "Two variants share the same hash"

    def test_get_variant_factory(self) -> None:
        assert get_variant("HELIOS-Full") is CONFIRMATORY_VARIANTS["HELIOS-Full"]

    def test_get_variant_unknown_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown variant"):
            get_variant("HELIOS-Unknown")


class TestExploratoryVariants:
    def test_seven_exploratory_variants_defined(self) -> None:
        assert len(EXPLORATORY_VARIANTS) == 7

    def test_exploratory_hashes_unique_within_dict(self) -> None:
        hashes = [
            m.compute_variant_config_hash() for m in EXPLORATORY_VARIANTS.values()
        ]
        assert len(hashes) == len(
            set(hashes)
        ), "Two exploratory variants share the same hash"

    def test_get_variant_resolves_exploratory_by_name(self) -> None:
        for name in EXPLORATORY_VARIANTS:
            assert get_variant(name) is EXPLORATORY_VARIANTS[name]

    def test_live_variant_uses_live_ingest_mode(self) -> None:
        assert EXPLORATORY_VARIANTS["HELIOS-live"].ingest_mode == "live"

    def test_all_non_live_exploratory_variants_use_recorded(self) -> None:
        for name, manifest in EXPLORATORY_VARIANTS.items():
            if name == "HELIOS-live":
                continue
            assert (
                manifest.ingest_mode == "recorded"
            ), f"{name} should use recorded ingest_mode"

    def test_each_single_flag_variant_differs_from_full_by_one_flag(self) -> None:
        full = CONFIRMATORY_VARIANTS["HELIOS-Full"]
        single_flag_variants = {
            "HELIOS-noP4": "p4_cognitive",
            "HELIOS-noMAHC": "mahc",
            "HELIOS-noCBR": "cbr",
            "HELIOS-noACP": "acp",
            "HELIOS-noReconcile": "reconcile",
        }
        for variant_name, disabled_flag in single_flag_variants.items():
            manifest = EXPLORATORY_VARIANTS[variant_name]
            assert (
                getattr(manifest, disabled_flag) is False
            ), f"{variant_name}: expected {disabled_flag}=False"
            for flag in VCLFlag.bool_flags():
                if flag.value == disabled_flag:
                    continue
                assert getattr(manifest, flag.value) == getattr(
                    full, flag.value
                ), f"{variant_name}: {flag.value} should match HELIOS-Full"
