"""MAHC build calibration: folds, nested cross-fitting, floor, report (S2.5 §5.2-5.4)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from helios.consensus.mahc import Vote
from helios.evaluation import mahc_calibration as mc
from helios.evaluation.mahc_calibration import BuildCase
from helios.telemetry.signal_type import SignalType
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    import pytest

RES, LAT = SignalType.RESOURCE, SignalType.LATENCY


def _case(i: int, corpus: str, group: str, d_right: bool, l_right: bool) -> BuildCase:
    root = f"svc-{i % 3}"
    other = "svc-x"
    d = Vote(
        "dpipe", (root, other) if d_right else (other, "svc-y", "svc-z", root), 0.3
    )
    lv = Vote("lpipe", (root,) if l_right else (other,), 0.6)
    return BuildCase(f"id{i:03d}", corpus, group, RES if i % 2 else LAT, (d, lv), root)


def _corpus() -> list[BuildCase]:
    cases = []
    for i in range(60):
        group = ["ad", "cart", "email"][i % 3] if i < 30 else ["ob", "ss"][i % 2]
        corpus = "otel_build_v3" if i < 30 else "rcaeval_build"
        cases.append(_case(i, corpus, group, d_right=i % 4 != 0, l_right=i % 5 != 0))
    return cases


def test_outer_folds_are_groups() -> None:
    folds = mc.outer_folds(_corpus())
    assert len(folds) == 5
    cases = _corpus()
    for fold in folds:
        assert len({(cases[i].corpus, cases[i].group) for i in fold}) == 1
    assert sorted(i for f in folds for i in f) == list(range(60))


def test_cross_fit_never_scores_a_case_with_a_model_that_saw_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import dataclass

    from helios.consensus.priors import PriorCase

    @dataclass(frozen=True)
    class Tagged(PriorCase):
        tag: str = ""

    cases = _corpus()
    seen: list[set[str]] = []
    real_fit, real_case = mc.fit_priors, mc.prior_case

    def tagged(case: BuildCase) -> PriorCase:
        base = real_case(case)
        return Tagged(base.signal, base.hits, case.incident_id)

    def spy(prior_cases: list[PriorCase]) -> mc.PriorTable:
        seen.append({c.tag for c in prior_cases if isinstance(c, Tagged)})
        return real_fit(prior_cases)

    monkeypatch.setattr(mc, "prior_case", tagged)
    monkeypatch.setattr(mc, "fit_priors", spy)
    result = mc.cross_fit(cases)
    assert len(result.conf) == len(result.hit) == 60
    for fold in mc.outer_folds(cases):
        held = {cases[i].incident_id for i in fold}
        scoring = [s for s in seen if not s & held]
        assert scoring, "held-out cases must be scored by priors fitted without them"
    assert all(0 <= c <= 1 for c in result.conf)


def test_floor_none_when_unreachable() -> None:
    cases = [
        _case(i, "otel_build_v3", ["ad", "cart"][i % 2], False, False)
        for i in range(20)
    ]
    report = mc.evaluate(cases)
    assert report["floor"] is None


def test_report_has_no_incident_ids_and_has_the_curve() -> None:
    report = mc.evaluate(_corpus())
    text = json.dumps(report)
    assert not any(c.incident_id in text for c in _corpus())
    assert len(report["calibration_curve"]) == 10
    per = report["by_corpus"]["otel_build_v3"]
    assert set(per) >= {
        "cases",
        "mahc_hr3",
        "vote_only_hr3",
        "pipelines_hr3",
        "confirmed",
        "hr3_confirmed",
    }


def test_report_counts_the_ambiguous_stratum() -> None:
    # Metric contract: ambiguous = at least two pipelines with a list disagree on top-1.
    cases = _corpus()
    report = mc.evaluate(cases)
    expected = sum(
        1
        for c in cases
        if c.corpus == "otel_build_v3" and len({v.ranked[0] for v in c.votes}) > 1
    )
    per = report["by_corpus"]["otel_build_v3"]
    assert per["ambiguous"] == expected > 0
    assert set(per) >= {"mahc_hr3_ambiguous", "vote_only_hr3_ambiguous"}


def test_frozen_check_reports_refit_confirmed_and_gpipe_effect() -> None:
    # PR 2 review: confirmed share under the frozen (refit) calibrator, and how
    # G-pipe's vote moves confidence and state on cases where it ran.
    from helios.consensus.calibration import Calibrator
    from helios.consensus.params import MAHCParams
    from helios.consensus.priors import fit_priors

    cases = []
    for i in range(24):
        root = f"svc-{i % 3}"
        votes = [Vote("dpipe", (root, "svc-x"), 0.3), Vote("lpipe", (root,), 0.4)]
        if i % 2:
            votes.append(Vote("gpipe", ("svc-x", root), 1))
        cases.append(
            BuildCase(f"id{i}", "otel_build_v3", "ad", RES, tuple(votes), root)
        )
    sigma_only = Calibrator(
        (0, 0, -1, 0), 0, (0,) * 4, (1,) * 4, ((-1e9, 0.5), (-0.37, 0.95))
    )
    params = MAHCParams(fit_priors([]), sigma_only, 0.9, provisional=False)
    report = mc.frozen_check(cases, params)
    otel = report["by_corpus"]["otel_build_v3"]
    assert otel["cases"] == 24 and otel["confirmed"] + otel["provisional"] == 24
    g = report["gpipe_effect"]["otel_build_v3"]
    assert g["cases_with_gpipe"] == 12
    assert (
        g["confirmed_with"] < g["confirmed_without"]
    )  # G at sigma 1 raises fused sigma
    assert g["mean_confidence_with"] < g["mean_confidence_without"]


def test_a_case_without_any_list_is_a_provisional_miss() -> None:
    # S2-BL-18, decided: a build case whose every pipeline abstained is real
    # data (a miss in every denominator), so BuildCase does not refuse it.
    from helios.consensus.params import MAHCParams
    from helios.consensus.priors import fit_priors

    params = MAHCParams(fit_priors([]), None, 0.9, provisional=False)
    empty = BuildCase("id0", "otel_build_v3", "ad", RES, (), "svc-0")
    got = mc.frozen_check([empty], params)
    entry = next(iter(got.values()))["otel_build_v3"]
    assert entry["cases"] == entry["provisional"] == 1
    assert entry["hr3_provisional"] == 0
