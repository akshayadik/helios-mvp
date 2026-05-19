"""L-pipe pipeline entry-point tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from helios.schemas.ueg_c import NodeType, UEGCNode, UEGCSnapshot
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.decorators import set_current_manifest
from helios.vcl.variants import get_variant

_HASH = "a" * 64
_AT = "2026-01-01T00:00:00+00:00"


def _make_snapshot(service_names: list[str]) -> UEGCSnapshot:
    nodes = [
        UEGCNode(node_id=s, node_type=NodeType.SERVICE, service_name=s)
        for s in service_names
    ]
    return UEGCSnapshot(
        incident_id="inc-001",
        variant_config_hash=_HASH,
        nodes=nodes,
        edges=[],
        captured_at_iso=_AT,
    )


def _setup_manifest() -> None:
    set_current_manifest(get_variant("HELIOS-Full"))


def test_run_lpipe_returns_dict_with_required_fields() -> None:
    _setup_manifest()
    from helios.pipelines.l_pipe.pipeline import run_lpipe

    snapshot = _make_snapshot(["svcA", "svcB"])
    mock_handler_result = (
        MagicMock(
            ranked_candidates=["svcA"],
            narrative="svcA caused the issue",
        ),
        MagicMock(prompt_tokens=25, completion_tokens=75),
    )
    with (
        patch("helios.pipelines.l_pipe.pipeline.PromptRegistry") as mock_reg_cls,
        patch("helios.pipelines.l_pipe.pipeline.OllamaClient"),
        patch("helios.pipelines.l_pipe.pipeline.ResponseHandler") as mock_handler_cls,
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
            snapshot=snapshot,
            snapshot_hash=_HASH,
            evaluation_phase="exploratory",
            run_id="run-abc",
        )

    assert result["pipeline"] == "lpipe"
    assert result["run_id"] == "run-abc"
    assert result["ranked_candidates"] == ["svcA"]
    assert result["prompt_version"] == "rca_v1"
    assert "token_count" in result
    assert "latency_ms" in result
    assert "schema_version" in result


def test_connectivity_error_returns_failure_dict() -> None:
    _setup_manifest()
    from helios.pipelines.l_pipe.ollama_client import OllamaConnectionError
    from helios.pipelines.l_pipe.pipeline import run_lpipe

    snapshot = _make_snapshot(["svcA"])
    with (
        patch("helios.pipelines.l_pipe.pipeline.PromptRegistry") as mock_reg_cls,
        patch("helios.pipelines.l_pipe.pipeline.OllamaClient"),
        patch("helios.pipelines.l_pipe.pipeline.ResponseHandler") as mock_handler_cls,
    ):
        mock_reg = MagicMock()
        mock_reg.render.return_value = "test prompt"
        mock_reg.prompt_version = "rca_v1"
        mock_reg_cls.return_value = mock_reg
        mock_handler = MagicMock()
        mock_handler.handle.side_effect = OllamaConnectionError("connection refused")
        mock_handler_cls.return_value = mock_handler

        result = run_lpipe(
            incident_id="inc-001",
            snapshot=snapshot,
            snapshot_hash=_HASH,
            evaluation_phase="exploratory",
            run_id="run-abc",
        )

    assert result["pipeline"] == "lpipe"
    assert result["ranked_candidates"] == ["l-pipe-connectivity-error"]
    assert "l-pipe-connectivity-error" in result["narrative"]


def test_expected_prompt_sha_matches_registry() -> None:
    from helios.pipelines.l_pipe.lpipe_config import EXPECTED_PROMPT_SHA
    from helios.pipelines.l_pipe.prompt_registry import PROMPT_PATH, PromptRegistry

    registry = PromptRegistry(PROMPT_PATH)
    if EXPECTED_PROMPT_SHA is None:
        pytest.skip(
            f"EXPECTED_PROMPT_SHA not frozen — bootstrap value: {registry.prompt_sha}"
        )
    assert (
        registry.prompt_sha == EXPECTED_PROMPT_SHA
    ), f"Prompt SHA mismatch: live={registry.prompt_sha!r} frozen={EXPECTED_PROMPT_SHA!r}"


def test_service_list_from_snapshot() -> None:
    from helios.pipelines.l_pipe.pipeline import _service_list_from_snapshot

    snapshot = _make_snapshot(["svcC", "svcA", "svcB"])
    result = _service_list_from_snapshot(snapshot)
    assert result == ["svcA", "svcB", "svcC"]  # sorted


def test_anomaly_summary_format() -> None:
    from helios.pipelines.l_pipe.pipeline import _anomaly_summary

    snapshot = _make_snapshot(["svcA", "svcB"])
    result = _anomaly_summary(snapshot)
    assert result == "Anomalies detected across 2 services: svcA, svcB"
