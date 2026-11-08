"""S3.2 ACP fit: fault map, seed-free folds, fit, cross-fit and scores."""

from __future__ import annotations

from collections import Counter

import pytest

from helios.acp.features import ACP_FEATURE_NAMES
from helios.acp.params import ACP_CLASSES
from helios.evaluation.acp_fit import (
    FAULT_CLASS,
    ACPCase,
    cross_fit,
    fit_params,
    folds,
    scores,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

D = len(ACP_FEATURE_NAMES)
# A separable toy set: class i lights feature column i + 1.
_COL = {c: i + 1 for i, c in enumerate(ACP_CLASSES)}


def _case(i: int, label: str, corpus: str = "a") -> ACPCase:
    x: list[float] = [1, *([0] * (D - 1))]
    x[_COL[label]] = 1
    x[-1] = (i % 3) / 3  # a nuisance column
    return ACPCase(incident_id=f"inc-{i}", corpus=corpus, x=tuple(x), label=label)


def _cases(n_per: int = 10) -> list[ACPCase]:
    out = []
    for j, label in enumerate(ACP_CLASSES):
        for i in range(n_per):
            out.append(_case(j * n_per + i, label, corpus="a" if i % 2 else "b"))
    return out


def test_fault_map_targets_known_classes() -> None:
    assert set(FAULT_CLASS.values()) == set(ACP_CLASSES)
    for fault in ("cpu", "mem", "disk", "delay", "loss", "socket", "f1", "f5"):
        assert fault in FAULT_CLASS
    assert FAULT_CLASS["recommendationCacheFailure"] == "config"
    assert FAULT_CLASS["emailMemoryLeak"] == "resource"


def test_folds_are_deterministic_and_stratified() -> None:
    cases = _cases()
    a, b = folds(cases, 5), folds(list(reversed(cases)), 5)
    assert a == list(reversed(b))  # order of input does not matter
    per = Counter((c.corpus, c.label, f) for c, f in zip(cases, a, strict=True))
    for corpus in ("a", "b"):
        for label in ACP_CLASSES:
            counts = [per[corpus, label, f] for f in range(5)]
            assert max(counts) - min(counts) <= 1


def test_fit_separates_a_separable_set() -> None:
    cases = _cases()
    params = fit_params(cases, lam=1)
    assert params.n_cases == len(cases)
    assert params.scale[0] == 1 and params.mean[0] == 0
    for c in cases:
        probs = params.probabilities(c.x)
        assert max(probs, key=probs.__getitem__) == c.label


def test_fit_is_reproducible() -> None:
    cases = _cases()
    assert fit_params(cases, lam=1) == fit_params(cases, lam=1)


def test_fit_refuses_no_cases() -> None:
    with pytest.raises(ValueError, match="no cases"):
        fit_params([], lam=1)


def test_constant_columns_get_unit_scale() -> None:
    params = fit_params(_cases(), lam=1)
    # Column D-2 is zero in every case.
    assert params.scale[D - 2] == 1


def test_cross_fit_and_scores() -> None:
    cases = _cases()
    held = cross_fit(cases, lam=1, k=5)
    assert all(set(p) == set(ACP_CLASSES) for p in held)
    s = scores(cases, held)
    assert s["cases"] == len(cases)
    assert s["accuracy"] == 1
    assert s["macro_f1"] == 1
    assert s["log_loss"] > 0
    assert sum(sum(row.values()) for row in s["confusion"].values()) == len(cases)


def test_scores_skip_absent_classes_and_count_errors() -> None:
    cases = [_case(0, "resource"), _case(1, "network")]
    leaning_network = {"resource": 0.1, "network": 0.7, "config": 0.1, "code": 0.1}
    s = scores(cases, [leaning_network, leaning_network])
    assert s["accuracy"] == round(1 / 2, 6)
    assert s["confusion"]["resource"]["network"] == 1
    # resource F1 = 0, network F1 = 2/3; config and code absent
    assert s["macro_f1"] == round((0 + 2 / 3) / 2, 6)


def test_scores_empty() -> None:
    s = scores([], [])
    assert s["accuracy"] is None and s["macro_f1"] is None and s["log_loss"] is None
