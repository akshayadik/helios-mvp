"""The H_fact rubric (S2.9 design §5.1): names every claim kind and error
category, and its hash is what a labelling set records."""

from __future__ import annotations

from pathlib import Path

from helios.labelling.annotations import CATEGORIES
from helios.labelling.sets import build_set, rubric_sha
from helios.narrative.claims import ClaimKind
from helios.narrative.params import load_narrator_params
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from tests.labelling.test_sets import entries

RUBRIC = Path(__file__).resolve().parents[2] / "docs/research/h_fact_rubric.md"


def test_rubric_names_every_kind_and_category() -> None:
    text = RUBRIC.read_text("utf-8")
    for kind in ClaimKind:
        assert f"`{kind.value}`" in text, kind
    for category in CATEGORIES:
        assert f"`{category}`" in text, category
    assert "never against the fault label" in text  # entry 65


def test_rubric_sha_matches_the_set_manifest() -> None:
    sha = rubric_sha(RUBRIC)
    s = build_set(
        entries(2), planted_share=1 / 4, rubric_sha=sha, params=load_narrator_params()
    )
    assert s.manifest["rubric_sha"] == sha and len(sha) == 64
