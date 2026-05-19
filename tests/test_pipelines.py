"""Tests for gated null pipeline stubs — d_pipe, g_pipe and l_pipe (§3.6.7).

All stubs must be gated behind their respective VCL flags.
When their flag is inactive, they raise GatedComponentInactiveError; when active, they
return a minimal PipelineVerdict stub. Uses VCLManifest / VCLFlag per C1 invariants.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from helios.schemas.ueg_c import UEGCSnapshot

from helios.pipelines.d_pipe.stub import run_dpipe
from helios.pipelines.g_pipe.pipeline import run_gpipe
from helios.pipelines.l_pipe.pipeline import run_lpipe
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
# G-pipe pipeline (gated by gpipe)
# ------------------------------------------------------------------


def _make_minimal_snap() -> UEGCSnapshot:
    from helios.schemas.ueg_c import (
        EdgeType,
        NodeType,
        UEGCEdge,
        UEGCNode,
        UEGCSnapshot,
    )

    return UEGCSnapshot(
        incident_id="inc-001",
        variant_config_hash="a" * 64,
        nodes=[
            UEGCNode(node_id="A", node_type=NodeType.SERVICE, service_name="A"),
            UEGCNode(node_id="B", node_type=NodeType.SERVICE, service_name="B"),
            UEGCNode(node_id="C", node_type=NodeType.SERVICE, service_name="C"),
        ],
        edges=[
            UEGCEdge(source="A", target="B", edge_type=EdgeType.CALL, weight=0.80),
            UEGCEdge(source="B", target="C", edge_type=EdgeType.CALL, weight=0.60),
        ],
        captured_at_iso="2026-01-01T00:00:00+00:00",
    )


class TestGPipePipeline:
    def test_gpipe_active_returns_verdict(self) -> None:
        m = _manifest_with()  # HELIOS-Full has gpipe=True
        set_current_manifest(m)
        result = run_gpipe(
            incident_id="inc-001",
            snapshot=_make_minimal_snap(),
            snapshot_hash=_FAKE_SNAP,
            dpipe_scores={"A": 0.90, "B": 0.45, "C": 0.36},
            evaluation_phase="exploratory",
            run_id="run-001",
        )
        assert result["pipeline"] == "gpipe"
        assert result["incident_id"] == "inc-001"

    def test_gpipe_inactive_raises(self) -> None:
        m = _manifest_with(gpipe=False)
        set_current_manifest(m)
        with pytest.raises(GatedComponentInactiveError):
            run_gpipe(
                incident_id="inc-001",
                snapshot=_make_minimal_snap(),
                snapshot_hash=_FAKE_SNAP,
                dpipe_scores={"A": 0.90, "B": 0.45, "C": 0.36},
                evaluation_phase="exploratory",
                run_id="run-001",
            )

    def test_gpipe_has_gated_by_attribute(self) -> None:
        assert hasattr(run_gpipe, "__gated_by__")
        assert run_gpipe.__gated_by__ == VCLFlag.GPIPE


# ------------------------------------------------------------------
# L-pipe stub (gated by l2c_llm)
# ------------------------------------------------------------------


class TestLPipePipeline:
    def _make_snap(self) -> UEGCSnapshot:
        from helios.schemas.ueg_c import NodeType, UEGCNode, UEGCSnapshot

        return UEGCSnapshot(
            incident_id="inc-001",
            variant_config_hash="a" * 64,
            nodes=[UEGCNode(node_id="A", node_type=NodeType.SERVICE, service_name="A")],
            edges=[],
            captured_at_iso="2026-01-01T00:00:00+00:00",
        )

    def test_lpipe_active_returns_verdict(self) -> None:
        from unittest.mock import MagicMock, patch

        m = _manifest_with()  # HELIOS-Full has l2c_llm=True
        set_current_manifest(m)
        mock_handler_result = (
            MagicMock(ranked_candidates=["A"], narrative="A caused the issue"),
            MagicMock(prompt_tokens=10, completion_tokens=20),
        )
        with (
            patch("helios.pipelines.l_pipe.pipeline.PromptRegistry") as mock_reg_cls,
            patch("helios.pipelines.l_pipe.pipeline.OllamaClient"),
            patch(
                "helios.pipelines.l_pipe.pipeline.ResponseHandler"
            ) as mock_handler_cls,
        ):
            mock_reg = MagicMock()
            mock_reg.render.return_value = "test prompt"
            mock_reg.prompt_version = "rca_v1"
            mock_reg_cls.return_value = mock_reg
            mock_handler = MagicMock()
            mock_handler.handle.return_value = mock_handler_result
            mock_handler_cls.return_value = mock_handler
            result = run_lpipe(
                incident_id="inc-001",
                snapshot=self._make_snap(),
                snapshot_hash=_FAKE_SNAP,
                evaluation_phase="exploratory",
                run_id="run-001",
            )
        assert result["pipeline"] == "lpipe"
        assert result["incident_id"] == "inc-001"

    def test_lpipe_inactive_raises(self) -> None:
        m = _manifest_with(l2c_llm=False)
        set_current_manifest(m)
        with pytest.raises(GatedComponentInactiveError):
            run_lpipe(
                incident_id="inc-001",
                snapshot=self._make_snap(),
                snapshot_hash=_FAKE_SNAP,
                evaluation_phase="exploratory",
                run_id="run-001",
            )

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
