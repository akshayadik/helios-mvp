"""Tests for gpipe_config constants."""

from __future__ import annotations

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def test_gpipe_config_constants_importable() -> None:
    from helios.pipelines.g_pipe.gpipe_config import (
        DISAGREEMENT_SWEEP,
        DISAGREEMENT_THRESHOLD,
        GPIPE_PPR_ALPHA,
    )

    assert isinstance(DISAGREEMENT_THRESHOLD, float)
    assert isinstance(GPIPE_PPR_ALPHA, float)
    assert isinstance(DISAGREEMENT_SWEEP, list)
    assert len(DISAGREEMENT_SWEEP) == 5
    assert DISAGREEMENT_THRESHOLD in DISAGREEMENT_SWEEP
