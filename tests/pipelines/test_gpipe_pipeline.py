"""Tests for helios.pipelines.g_pipe.pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from helios.vcl import VCLFlag, get_variant, set_current_manifest  # noqa: F401

if TYPE_CHECKING:
    from collections.abc import Generator

    from helios.schemas.ueg_c import UEGCSnapshot


@pytest.fixture(autouse=True)
def _reset_manifest() -> Generator[None, Any, None]:
    yield
    from helios.vcl.decorators import _current_manifest

    _current_manifest.set(None)


class TestComputePprDisagreement:
    def test_below_threshold_returns_low_value(self) -> None:
        from helios.pipelines.g_pipe.pipeline import compute_ppr_disagreement

        scores = {"a": 0.60, "b": 0.25, "c": 0.15}
        # 3rd/top = 0.15/0.60 = 0.25 — below default threshold
        assert compute_ppr_disagreement(scores) == pytest.approx(0.25)

    def test_at_threshold_returns_exact(self) -> None:
        from helios.pipelines.g_pipe.pipeline import compute_ppr_disagreement

        # 3rd/top = 0.27/0.90 = 0.30 (exactly at threshold)
        scores = {"a": 0.90, "b": 0.45, "c": 0.27}
        assert compute_ppr_disagreement(scores) == pytest.approx(0.30)

    def test_above_threshold(self) -> None:
        from helios.pipelines.g_pipe.pipeline import compute_ppr_disagreement

        scores = {"a": 0.90, "b": 0.60, "c": 0.31}
        assert compute_ppr_disagreement(scores) > 0.30

    def test_uniform_scores_return_near_one(self) -> None:
        from helios.pipelines.g_pipe.pipeline import compute_ppr_disagreement

        scores = {"a": 0.33, "b": 0.33, "c": 0.33}
        assert compute_ppr_disagreement(scores) == pytest.approx(1, abs=0.01)

    def test_fewer_than_three_candidates_returns_zero(self) -> None:
        from helios.pipelines.g_pipe.pipeline import compute_ppr_disagreement

        assert compute_ppr_disagreement({"a": 0.80, "b": 0.20}) == 0.00
        assert compute_ppr_disagreement({}) == 0.00

    def test_negative_score_raises_value_error(self) -> None:
        from helios.pipelines.g_pipe.pipeline import compute_ppr_disagreement

        with pytest.raises(ValueError, match="negative"):
            compute_ppr_disagreement({"a": 0.80, "b": -0.10, "c": 0.30})

    def test_all_zero_scores_returns_zero(self) -> None:
        from helios.pipelines.g_pipe.pipeline import compute_ppr_disagreement

        assert compute_ppr_disagreement({"a": 0.00, "b": 0.00, "c": 0.00}) == 0.00


class TestShouldRunGpipe:
    def _dpipe_dict(self, scores: dict) -> dict:
        return {"ppr_scores": scores, "pipeline": "dpipe"}

    def test_gpipe_flag_off_returns_false(self) -> None:
        from helios.pipelines.g_pipe.pipeline import should_run_gpipe

        manifest = get_variant("HELIOS-noGraph")
        result = should_run_gpipe(
            self._dpipe_dict({"a": 0.34, "b": 0.33, "c": 0.33}), manifest
        )
        assert result is False

    def test_l2b_graph_flag_off_returns_false(self) -> None:
        from unittest.mock import MagicMock

        from helios.pipelines.g_pipe.pipeline import should_run_gpipe

        m = MagicMock()
        m.gpipe = True
        m.l2b_graph = False
        result = should_run_gpipe(
            self._dpipe_dict({"a": 0.34, "b": 0.33, "c": 0.33}), m
        )
        assert result is False

    def test_disagreement_below_threshold_returns_false(self) -> None:
        from helios.pipelines.g_pipe.pipeline import should_run_gpipe

        manifest = get_variant("HELIOS-Full")
        set_current_manifest(manifest)
        # 3rd/top = 0.10/0.80 = 0.125 → below 0.30
        result = should_run_gpipe(
            self._dpipe_dict({"a": 0.80, "b": 0.10, "c": 0.10}), manifest
        )
        assert result is False

    def test_disagreement_at_threshold_returns_true(self) -> None:
        from helios.pipelines.g_pipe.pipeline import should_run_gpipe

        manifest = get_variant("HELIOS-Full")
        set_current_manifest(manifest)
        # 3rd/top = 0.27/0.90 = 0.30 → at threshold
        result = should_run_gpipe(
            self._dpipe_dict({"a": 0.90, "b": 0.45, "c": 0.27}), manifest
        )
        assert result is True


def _make_snap() -> UEGCSnapshot:
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


class TestPprTraverse:
    def test_returns_ranked_list_and_scores(self) -> None:
        from helios.pipelines.g_pipe.pipeline import _ppr_traverse

        ranked, scores = _ppr_traverse(
            _make_snap(), seed_weights={"A": 0.80, "B": 0.20}
        )
        assert set(ranked) == {"A", "B", "C"}
        assert all(isinstance(v, float) for v in scores.values())

    def test_deterministic_on_same_input(self) -> None:
        from helios.pipelines.g_pipe.pipeline import _ppr_traverse

        seeds = {"A": 0.70, "B": 0.30}
        ranked_a, scores_a = _ppr_traverse(_make_snap(), seed_weights=seeds)
        ranked_b, scores_b = _ppr_traverse(_make_snap(), seed_weights=seeds)
        assert ranked_a == ranked_b
        assert scores_a == scores_b

    def test_zero_sum_personalization_no_error(self) -> None:
        from helios.pipelines.g_pipe.pipeline import _ppr_traverse

        # All matched node scores are zero — falls back to uniform, no ZeroDivisionError
        ranked, _ = _ppr_traverse(
            _make_snap(), seed_weights={"A": 0.00, "B": 0.00, "C": 0.00}
        )
        assert len(ranked) == 3

    def test_unknown_seed_nodes_filtered(self) -> None:
        from helios.pipelines.g_pipe.pipeline import _ppr_traverse

        ranked, _ = _ppr_traverse(
            _make_snap(), seed_weights={"A": 0.80, "PHANTOM": 0.20}
        )
        assert "PHANTOM" not in ranked


class TestRunGpipe:
    def test_sentinel_when_below_threshold(self) -> None:
        from helios.pipelines.g_pipe.pipeline import run_gpipe

        manifest = get_variant("HELIOS-Full")
        set_current_manifest(manifest)
        result = run_gpipe(
            incident_id="inc-001",
            snapshot=_make_snap(),
            snapshot_hash="b" * 64,
            dpipe_scores={"A": 0.80, "B": 0.15, "C": 0.05},
            evaluation_phase="exploratory",
            run_id="run-001",
        )
        # 3rd/top = 0.05/0.80 = 0.0625 — below threshold
        assert result["narrative"] == "gpipe-gated-or-skipped"
        assert result["ranked_candidates"] == []

    def test_full_result_when_above_threshold(self) -> None:
        from helios.pipelines.g_pipe.pipeline import run_gpipe

        manifest = get_variant("HELIOS-Full")
        set_current_manifest(manifest)
        result = run_gpipe(
            incident_id="inc-001",
            snapshot=_make_snap(),
            snapshot_hash="b" * 64,
            dpipe_scores={"A": 0.90, "B": 0.45, "C": 0.36},
            evaluation_phase="exploratory",
            run_id="run-001",
        )
        # 3rd/top = 0.36/0.90 = 0.40 — above threshold
        assert result["narrative"] != "gpipe-gated-or-skipped"
        assert len(result["ranked_candidates"]) > 0

    def test_sentinel_has_all_required_fields(self) -> None:
        from helios.pipelines.g_pipe.pipeline import run_gpipe

        manifest = get_variant("HELIOS-Full")
        set_current_manifest(manifest)
        result = run_gpipe(
            incident_id="inc-001",
            snapshot=_make_snap(),
            snapshot_hash="b" * 64,
            dpipe_scores={"A": 0.90, "B": 0.08, "C": 0.02},
            evaluation_phase="confirmatory",
            run_id="run-xyz",
        )
        for field in (
            "pipeline",
            "incident_id",
            "run_id",
            "variant_config_hash",
            "snapshot_hash",
            "ranked_candidates",
            "ppr_scores",
            "hr_at_3",
            "cpr",
            "latency_ms",
            "token_count",
            "narrative",
            "evaluation_phase",
            "schema_version",
        ):
            assert field in result, f"missing field: {field}"
        assert result["evaluation_phase"] == "confirmatory"
        assert result["run_id"] == "run-xyz"

    def test_raises_when_gpipe_flag_off(self) -> None:
        from helios.pipelines.g_pipe.pipeline import run_gpipe
        from helios.vcl import GatedComponentInactiveError

        manifest = get_variant("HELIOS-noGraph")
        set_current_manifest(manifest)
        with pytest.raises(GatedComponentInactiveError):
            run_gpipe(
                incident_id="inc-001",
                snapshot=_make_snap(),
                snapshot_hash="b" * 64,
                dpipe_scores={"A": 0.90, "B": 0.45, "C": 0.36},
                evaluation_phase="exploratory",
                run_id="run-001",
            )
