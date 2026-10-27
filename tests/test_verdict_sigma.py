"""sigma from score spread and evidence strength (S2.1, S2-M7-ENG09)."""

from __future__ import annotations

from helios.schemas.verdict import MU_DIGITS, sigma_from_scores
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def test_sigma_is_high_for_close_scores_and_low_for_a_clear_winner() -> None:
    strong = {"a": 12, "b": 12}
    close = sigma_from_scores({"a": 1, "b": 0.9}, strong, evidence_ref=6)
    clear = sigma_from_scores({"a": 1, "b": 0.1}, strong, evidence_ref=6)
    assert close is not None and clear is not None
    assert close > clear


def test_sigma_near_one_when_raw_evidence_is_tiny() -> None:
    sigma = sigma_from_scores({"a": 1, "b": 0.01}, {"a": 0.06}, evidence_ref=6)
    assert sigma is not None and sigma >= 0.99


def test_sigma_bounded_and_finite_for_tiny_positive_scores() -> None:
    sigma = sigma_from_scores({"a": 1e-9, "b": 0}, {"a": 1e-9}, evidence_ref=6)
    assert sigma is not None and 0 <= sigma <= 1


def test_sigma_counterexample_ch3_p157() -> None:
    # Same top-1 and top-1 score, different spread: sigma must tell them apart.
    evidence = {"a": 12}
    tight = sigma_from_scores({"a": 1, "b": 0.95, "c": 0.9}, evidence, evidence_ref=6)
    spread = sigma_from_scores({"a": 1, "b": 0.2, "c": 0.1}, evidence, evidence_ref=6)
    assert tight != spread


def test_sigma_none_without_scores() -> None:
    assert sigma_from_scores({}, {}, evidence_ref=6) is None
    assert sigma_from_scores({"a": 0}, {"a": 0}, evidence_ref=6) is None


def test_single_candidate_with_strong_evidence_is_certain() -> None:
    assert sigma_from_scores({"a": 1}, {"a": 12}, evidence_ref=6) == 0


def test_sigma_is_rounded_like_mu() -> None:
    sigma = sigma_from_scores({"a": 3, "b": 1}, {"a": 4}, evidence_ref=6)
    assert sigma == round(sigma or 0, MU_DIGITS)
