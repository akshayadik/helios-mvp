"""Tests for helios.vcl.disjointness — VCLFlag-compliant."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator

import pytest

from helios.vcl.disjointness import _REGISTRY, DisjointnessRegistry, register


def _unique_helios_path() -> str:
    """Return a unique helios.* qualname safe to use in _REGISTRY without pollution."""
    return f"helios.fake.fn_{uuid.uuid4().hex}"


def _unique_tests_path() -> str:
    return f"tests.fake.fn_{uuid.uuid4().hex}"


@pytest.fixture(autouse=True)
def _clean_registry() -> Generator[None, Any, None]:
    """Isolate each test: snapshot the full registry and restore it after."""
    snapshot = dict(_REGISTRY)
    yield
    _REGISTRY.clear()
    _REGISTRY.update(snapshot)


# ---------------------------------------------------------------------------
# Registry population
# ---------------------------------------------------------------------------


def test_no_helios_paths_registered_at_stage0() -> None:
    registry = DisjointnessRegistry()
    # Stage 0 has g_pipe and l_pipe null stubs decorated with @gated_by.
    # Verify known stage-0 pipeline stubs are present.
    assert "helios.pipelines.g_pipe.stub.run_gpipe" in registry._paths
    assert "helios.pipelines.l_pipe.stub.run_lpipe" in registry._paths


def test_register_increments_len() -> None:
    path = _unique_helios_path()
    before = len(DisjointnessRegistry())
    register(path, "dpipe")
    registry = DisjointnessRegistry()
    assert len(registry) == before + 1


def test_test_module_functions_filtered_out() -> None:
    tests_path = _unique_tests_path()
    before = len(DisjointnessRegistry())
    register(tests_path, "gpipe")
    registry = DisjointnessRegistry()
    assert len(registry) == before


def test_decorator_registers_helios_module_function() -> None:
    path = f"helios.pipelines.fake_{uuid.uuid4().hex}.run_gpipe"
    register(path, "gpipe")
    registry = DisjointnessRegistry()
    assert path in registry._paths


# ---------------------------------------------------------------------------
# Audit: no violations
# ---------------------------------------------------------------------------


def test_audit_returns_empty_when_all_paths_have_single_flag() -> None:
    paths = [_unique_helios_path() for _ in range(3)]
    flags = ["dpipe", "gpipe", "lpipe"]
    for p, f in zip(paths, flags, strict=False):
        register(p, f)
    assert DisjointnessRegistry().audit() == []


def test_single_flag_per_path_has_no_violations() -> None:
    path = _unique_helios_path()
    register(path, "mahc")
    assert DisjointnessRegistry().audit() == []


def test_audit_returns_empty_list_type() -> None:
    result = DisjointnessRegistry().audit()
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Audit: violations
# ---------------------------------------------------------------------------


def test_double_gating_produces_violation() -> None:
    path = _unique_helios_path()
    register(path, "dpipe")
    register(path, "gpipe")
    violations = DisjointnessRegistry().audit()
    assert len(violations) == 1


def test_violation_string_contains_path_and_flags() -> None:
    path = _unique_helios_path()
    register(path, "dpipe")
    register(path, "lpipe")
    violations = DisjointnessRegistry().audit()
    assert len(violations) == 1
    msg = violations[0]
    assert path in msg
    assert "dpipe" in msg
    assert "lpipe" in msg
