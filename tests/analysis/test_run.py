"""S4.11 analysis runner: guard, pairing, families and floors on hand-built tables."""

from __future__ import annotations

from typing import Any

import pytest

from helios.analysis.run import (
    analyse,
    build_case_table,
    confirmatory_guard,
    e_h5_forms,
    sanity_floors,
    variant_names,
)
from helios.evaluation.run_metrics import METRICS_VERSION
from helios.evaluation.scoring import SCORING_VERSION
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.variants import CONFIRMATORY_VARIANTS

N = 10
CASES = [f"c{i:02d}" for i in range(N)]


def _hash(name: str) -> str:
    return CONFIRMATORY_VARIANTS[name].compute_variant_config_hash()


def _rows(
    name: str,
    hr3: list[int],
    *,
    corpus: str = "build",
    cases: list[str] = CASES,
    **run_fields: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    scores, runs = [], []
    for i, case in enumerate(cases):
        run_id = f"{name}-{case}"
        scores.append(
            {
                "run_id": run_id,
                "incident_id": case,
                "variant_config_hash": _hash(name),
                "list_kind": "fused",
                "source": "mahc",
                "hr_at_1": hr3[i],
                "hr_at_3": hr3[i],
                "hr_at_10": hr3[i],
                "avg_at_5": float(hr3[i]),
                "mrr": float(hr3[i]),
                "corpus": corpus,
                "scoring_version": SCORING_VERSION,
            }
        )
        run = {
            "run_id": run_id,
            "incident_id": case,
            "variant_config_hash": _hash(name),
            "corpus": corpus,
            "metrics_version": METRICS_VERSION,
            "ttcd_s": 30,
        }
        run.update({k: v[i] for k, v in run_fields.items()})
        runs.append(run)
    return scores, runs


def _merge(
    *parts: tuple[list[dict[str, Any]], list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    scores: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    for s, r in parts:
        scores += s
        runs += r
    return scores, runs


def test_variant_names_cover_all_fifteen() -> None:
    names = variant_names()
    assert len(names) == 15
    assert names[_hash("HELIOS-Full")] == "HELIOS-Full"


def test_case_table_joins_scores_and_runs_and_refuses_duplicates() -> None:
    scores, runs = _rows("HELIOS-Full", [1] * N, log_cpr=[2] * N)
    table = build_case_table(scores, runs, variant_names())
    row = table["HELIOS-Full"]["c00"]
    assert (row["hr_at_3"], row["log_cpr"]) == (1, 2)
    assert row["log_ttcd"] == pytest.approx(3.4012, abs=1e-4)  # ln 30
    with pytest.raises(ValueError, match="two runs"):
        build_case_table(scores + scores[:1], runs, variant_names())
    bad = [dict(scores[0], variant_config_hash="feedface")]
    with pytest.raises(ValueError, match="unknown variant"):
        build_case_table(bad, runs, variant_names())


def test_guard_labels_build_data_exploratory() -> None:
    scores, runs = _rows("HELIOS-Full", [1] * N)
    guard = confirmatory_guard(scores, runs, frozen=lambda: False)
    assert guard.confirmatory is False
    assert any("pool" in r for r in guard.reasons)
    assert any("build-freeze" in r for r in guard.reasons)


def test_guard_passes_only_with_pool_freeze_hashes_and_versions() -> None:
    scores, runs = _rows("HELIOS-Full", [1] * N, corpus="pool")
    assert confirmatory_guard(scores, runs, frozen=lambda: True).confirmatory
    stale = [dict(r, metrics_version="run-metrics-v0") for r in runs]
    assert not confirmatory_guard(scores, stale, frozen=lambda: True).confirmatory
    old = [dict(s, scoring_version="scoring-v1") for s in scores]
    assert not confirmatory_guard(old, runs, frozen=lambda: True).confirmatory
    alien = [dict(r, variant_config_hash="feedface") for r in runs]
    assert not confirmatory_guard(scores, alien, frozen=lambda: True).confirmatory


def _family_a_fixture() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    # Full hits every case; HELIOS-D misses every case -> A-H3 p = 2^-10.
    # noLLM hits 7 of 10 -> A-H1: 3 positive differences of 3 -> p = 1/8.
    # A-H7: Full H_fact 0.2 on 6 cases (else 0), noLLM 0 -> sign test 6 of 6;
    #       Full H_struct 0.1 on 4 cases, noLLM structural zero -> 4 of 4.
    # A-H5: noRouter log-CpR 9, Full 5 on hits; matched on HR@3 by construction.
    h_fact = [0.2] * 6 + [0] * 4
    h_struct = [0.1] * 4 + [0] * 6
    return _merge(
        _rows(
            "HELIOS-Full",
            [1] * N,
            h_fact=h_fact,
            h_struct=h_struct,
            log_cpr=[5] * N,
            escalated=[True] * 5 + [False] * 5,
            ambiguous=[True] * N,
        ),
        _rows("HELIOS-D", [0] * N),
        _rows("HELIOS-noLLM", [1] * 7 + [0] * 3, h_fact=[0] * N, h_struct=[0] * N),
        _rows("HELIOS-noRouter", [1] * N, log_cpr=[9] * N),
    )


def _by_id(family: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {h["id"]: h for h in family["hypotheses"]}


def test_family_a_on_build_data_is_exploratory_and_hand_computed() -> None:
    scores, runs = _family_a_fixture()
    groups = {c: f"g{i % 5}" for i, c in enumerate(CASES)}
    out = analyse(
        scores,
        runs,
        expected_cases=N,
        groups=groups,
        n_services=dict.fromkeys(CASES, 10),
        frozen=lambda: False,
    )
    assert out["label"] == "exploratory"
    a = _by_id(out["family_a"])
    assert a["A-H3"]["p_value"] == pytest.approx(2**-10)
    assert "sign test" in a["A-H3"]["note"]
    assert a["A-H1"]["p_value"] == pytest.approx(1 / 8)
    # IUT: the larger of the two sign-test p-values: max(2^-6, 2^-4).
    assert a["A-H7"]["p_value"] == pytest.approx(2**-4)
    assert set(a["A-H7"]["by_measure"]) == {"h_fact", "h_struct"}
    # A-H5: 10 matched cases, every difference +4 -> p = 2^-10.
    assert a["A-H5"]["n_matched"] == N
    assert a["A-H5"]["matched_share"] == 1
    assert a["A-H5"]["p_value"] == pytest.approx(2**-10)
    assert a["A-H5"]["sensitivity"]["all_cases"]["n_pairs"] == N
    assert a["A-H5"]["splits"]["by_stage"]["escalated"]["n"] == 5
    # No runs for LLM-only, G, noConsensus, noStructural: untestable, kept.
    for hid in ("A-H2", "A-H6", "A-H4", "A-H8"):
        assert a[hid]["p_value"] is None
    assert a["A-H4"]["reading"].startswith("inconclusive")
    holm = {r["id"]: r for r in out["family_a"]["holm_binding"]}
    assert len(holm) == 8
    assert holm["A-H3"]["below_threshold_descriptive"] is True
    assert "rejected" not in holm["A-H3"]
    assert holm["A-H1"]["below_threshold_descriptive"] is False
    assert out["family_a"]["holm_reading"] == "data_order"
    # Family B: no baselines yet -> all eight untestable, none below threshold.
    assert all(h["p_value"] is None for h in out["family_b"]["hypotheses"])
    e = {h["id"]: h for h in out["family_e"]}
    assert e["E-H2"]["available"] is False  # no ttt_ms in the fixture
    assert e["E-H3"]["available"] is False  # retired


def test_a_h7_modes_and_holm_reading_switch() -> None:
    scores, runs = _family_a_fixture()
    kwargs: dict[str, Any] = {
        "expected_cases": N,
        "groups": {},
        "n_services": {},
        "frozen": lambda: False,
    }
    only = _by_id(analyse(scores, runs, a_h7_mode="h_fact_only", **kwargs)["family_a"])
    assert only["A-H7"]["p_value"] == pytest.approx(2**-6)
    summed = _by_id(analyse(scores, runs, a_h7_mode="sum", **kwargs)["family_a"])
    assert summed["A-H7"]["p_value"] == pytest.approx(2**-6)
    fixed = analyse(scores, runs, holm="fixed_sequence", **kwargs)["family_a"]
    assert fixed["holm_reading"] == "fixed_sequence"
    with pytest.raises(ValueError, match="holm"):
        analyse(scores, runs, holm="other", **kwargs)
    with pytest.raises(ValueError, match="a_h7_mode"):
        analyse(scores, runs, a_h7_mode="other", **kwargs)


def test_cell_rule_makes_a_short_pair_set_untestable() -> None:
    # Seven of ten cases paired: 7/10 < 4/5 -> untestable, counted, never dropped.
    scores, runs = _merge(
        _rows("HELIOS-Full", [1] * N),
        _rows("HELIOS-D", [0] * 7, cases=CASES[:7]),
    )
    out = analyse(
        scores, runs, expected_cases=N, groups={}, n_services={}, frozen=lambda: False
    )
    a3 = _by_id(out["family_a"])["A-H3"]
    assert a3["p_value"] is None
    assert "cell rule" in a3["untestable"]


def test_confirmatory_label_uses_rejected_wording() -> None:
    scores, runs = _merge(
        _rows("HELIOS-Full", [1] * N, corpus="pool"),
        _rows("HELIOS-D", [0] * N, corpus="pool"),
    )
    out = analyse(
        scores, runs, expected_cases=N, groups={}, n_services={}, frozen=lambda: True
    )
    assert out["label"] == "confirmatory"
    holm = {r["id"]: r for r in out["family_a"]["holm_binding"]}
    assert holm["A-H3"]["rejected"] is True


def test_sanity_floors() -> None:
    # Random: per case min(k, n) / n; c1 n = 10, c2 n = 2 -> HR@3 = (3/10 + 1) / 2.
    scores, runs = _rows("HELIOS-D", [1, 0], cases=["c1", "c2"])
    table = build_case_table(scores, runs, variant_names())
    floors = sanity_floors(table, {"c1": 10, "c2": 2})
    assert floors["HR@3"]["random_all_services"] == pytest.approx(0.65)
    assert floors["HR@3"]["prior_only"] == pytest.approx(3 / 5)
    assert floors["HR@1"]["prior_only"] == pytest.approx(1 / 5)
    assert floors["HR@10"]["random_all_services"] == 1
    assert floors["HR@3"]["helios_d"] == pytest.approx(1 / 2)


def test_e_h5_both_forms() -> None:
    # Registered form: own case sets, mean(noReconcile) - mean(Full) = 3 - 1.
    # Same-case form: shared cases a, b: differences 2 and 2.
    out = e_h5_forms({"a": 1, "b": 1}, {"a": 3, "b": 3, "c": 3})
    assert out["registered_form"]["mean_difference"] == pytest.approx(2)
    assert out["same_case_form"]["n"] == 2
    assert out["same_case_form"]["mean_difference"] == pytest.approx(2)
    assert e_h5_forms({"a": 1}, {"b": 2})["same_case_form"] is None
