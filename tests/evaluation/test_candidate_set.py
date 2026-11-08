"""Candidate parameter sets for a chain refit (entries 76, 78)."""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from helios.consensus.params import load_mahc_params, mahc_params_hash
from helios.evaluation.candidate_set import CANDIDATE_ROOT, load_chain
from helios.pipelines.d_pipe.params import dpipe_params_hash, load_dpipe_params
from helios.pipelines.g_pipe.params import gpipe_params_hash, load_gpipe_params
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path


def test_without_a_candidate_the_chain_is_the_frozen_one() -> None:
    chain = load_chain()
    assert chain.sources == {"dpipe": "frozen", "gpipe": "frozen", "mahc": "frozen"}
    assert chain.hashes() == {
        "dpipe": dpipe_params_hash(load_dpipe_params()),
        "gpipe": gpipe_params_hash(load_gpipe_params()),
        "mahc": mahc_params_hash(load_mahc_params()),
    }


def test_a_stage_in_the_candidate_directory_replaces_only_that_stage(
    tmp_path: Path,
) -> None:
    shutil.copy(CANDIDATE_ROOT / "otel_fix" / "gpipe_params.json", tmp_path)
    chain = load_chain(tmp_path)
    assert chain.sources == {"dpipe": "frozen", "gpipe": "candidate", "mahc": "frozen"}
    assert chain.gpipe.model is not None
    assert "error_origin_shift" in chain.gpipe.model.columns
    assert chain.hashes()["dpipe"] == dpipe_params_hash(load_dpipe_params())


def test_the_otel_fix_gpipe_candidate_is_the_entry_78_refit() -> None:
    chain = load_chain(CANDIDATE_ROOT / "otel_fix")
    assert chain.hashes()["gpipe"] == (
        "6987f666f53f9b420946e7cab79f01487d038afa382a7ba890d9cd70195999a5"
    )


def test_a_missing_candidate_directory_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="candidate"):
        load_chain(tmp_path / "typo")


def test_the_otel_fix_mahc_candidate_is_the_entry_79_refit() -> None:
    chain = load_chain(CANDIDATE_ROOT / "otel_fix")
    assert chain.sources["mahc"] == "candidate"
    assert chain.hashes()["mahc"] == (
        "eb5b6adcf817b5705f72ecd635ed04da73702e4b395d66a7a5dd35e62f6318ba"
    )
