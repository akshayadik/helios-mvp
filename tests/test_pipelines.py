"""Tests for gated null pipeline stubs — d_pipe, g_pipe and l_pipe (§3.6.7).

All stubs must be gated behind their respective VCL flags.
When their flag is inactive, they raise GatedComponentInactiveError; when active, they
return a minimal PipelineVerdict stub. Uses VCLManifest / VCLFlag per C1 invariants.
"""

from __future__ import annotations

import pytest

from helios.pipelines.d_pipe.stub import run_dpipe
from helios.pipelines.g_pipe.stub import run_gpipe
from helios.pipelines.l_pipe.stub import run_lpipe
from helios.vcl import (
    GatedComponentInactiveError,
    VCLFlag,
    VCLManifest,
    get_variant,
    set_current_manifest,
)

# ------------------------------------------------------------------
# Shared helpers
# ------------------------------------------------------------------

_FAKE_VCH = "a" * 64
_FAKE_SNAP = "b" * 64


def _manifest_with(**overrides: bool) -> VCLManifest:
    """Return a new VCLManifest based on HELIOS-Full with selective flag overrides."""
    base = get_variant("HELIOS-Full")
    return base.model_copy(update=overrides)


# ------------------------------------------------------------------
# D-pipe stub (gated by dpipe)
# ------------------------------------------------------------------


class TestDPipeStub:
    def test_dpipe_active_returns_verdict(self) -> None:
        m = _manifest_with()  # HELIOS-Full has dpipe=True
        set_current_manifest(m)
        result = run_dpipe(incident_id="inc-001", snapshot_hash=_FAKE_SNAP)
        assert result["pipeline"] == "dpipe"
        assert result["incident_id"] == "inc-001"
        assert result["ranked_candidates"] == []
        assert result["narrative"] == "stub"

    def test_dpipe_inactive_raises(self) -> None:
        m = _manifest_with(dpipe=False)
        set_current_manifest(m)
        with pytest.raises(GatedComponentInactiveError):
            run_dpipe(incident_id="inc-001", snapshot_hash=_FAKE_SNAP)

    def test_dpipe_has_gated_by_attribute(self) -> None:
        assert hasattr(run_dpipe, "__gated_by__")
        assert run_dpipe.__gated_by__ == VCLFlag.DPIPE


# ------------------------------------------------------------------
# G-pipe stub (gated by l2b_graph)
# ------------------------------------------------------------------


class TestGPipeStub:
    def test_gpipe_active_returns_verdict(self) -> None:
        m = _manifest_with()  # HELIOS-Full has l2b_graph=True
        set_current_manifest(m)
        result = run_gpipe(incident_id="inc-001", snapshot_hash=_FAKE_SNAP)
        assert result["pipeline"] == "gpipe"
        assert result["incident_id"] == "inc-001"

    def test_gpipe_inactive_raises(self) -> None:
        m = _manifest_with(l2b_graph=False)
        set_current_manifest(m)
        with pytest.raises(GatedComponentInactiveError):
            run_gpipe(incident_id="inc-001", snapshot_hash=_FAKE_SNAP)

    def test_gpipe_has_gated_by_attribute(self) -> None:
        assert hasattr(run_gpipe, "__gated_by__")
        assert run_gpipe.__gated_by__ == VCLFlag.L2B_GRAPH


# ------------------------------------------------------------------
# L-pipe stub (gated by l2c_llm)
# ------------------------------------------------------------------


class TestLPipeStub:
    def test_lpipe_active_returns_verdict(self) -> None:
        m = _manifest_with()  # HELIOS-Full has l2c_llm=True
        set_current_manifest(m)
        result = run_lpipe(incident_id="inc-001", snapshot_hash=_FAKE_SNAP)
        assert result["pipeline"] == "lpipe"
        assert result["incident_id"] == "inc-001"

    def test_lpipe_inactive_raises(self) -> None:
        m = _manifest_with(l2c_llm=False)
        set_current_manifest(m)
        with pytest.raises(GatedComponentInactiveError):
            run_lpipe(incident_id="inc-001", snapshot_hash=_FAKE_SNAP)

    def test_lpipe_has_gated_by_attribute(self) -> None:
        assert hasattr(run_lpipe, "__gated_by__")
        assert run_lpipe.__gated_by__ == VCLFlag.L2C_LLM


# ------------------------------------------------------------------
# VCLFlag smoke (flag-guard compliance)
# ------------------------------------------------------------------


def test_l2b_graph_and_l2c_llm_are_bool_flags() -> None:
    bools = VCLFlag.bool_flags()
    assert VCLFlag.L2B_GRAPH in bools
    assert VCLFlag.L2C_LLM in bools
