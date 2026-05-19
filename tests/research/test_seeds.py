"""Tests for helios.research.seeds — seed registry."""

from __future__ import annotations

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def test_seed_registry_has_two_entries() -> None:
    from helios.research.seeds import SEED_REGISTRY

    assert len(SEED_REGISTRY) == 2


def test_seed_registry_global_seed_value() -> None:
    from helios.research.seeds import GLOBAL_SEED

    assert GLOBAL_SEED == 42


def test_seed_registry_llama_seed_value() -> None:
    from helios.research.seeds import LLAMA_SEED

    assert LLAMA_SEED == 42


def test_seed_registry_llama_seed_matches_lpipe_config() -> None:
    from helios.pipelines.l_pipe.lpipe_config import LLAMA_SEED as LPIPE_SEED
    from helios.research.seeds import LLAMA_SEED as REG_SEED

    assert REG_SEED == LPIPE_SEED


def test_seed_registry_entries_have_required_keys() -> None:
    from helios.research.seeds import SEED_REGISTRY

    required = {"seed_id", "value", "stage", "algorithm", "context", "source_constant"}
    for entry in SEED_REGISTRY:
        assert required <= entry.keys(), f"Missing keys in {entry}"


def test_seed_registry_seed_ids_are_unique() -> None:
    from helios.research.seeds import SEED_REGISTRY

    ids = [e["seed_id"] for e in SEED_REGISTRY]
    assert len(ids) == len(set(ids))
