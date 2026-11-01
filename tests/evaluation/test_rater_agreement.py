"""Rater agreement and H_fact (S2.9 design §5.6, owner decisions R-i and R-m)."""

from __future__ import annotations

from typing import Any

import pytest

from helios.evaluation.rater_agreement import (
    DETECTION_FLOOR,
    KAPPA_THRESHOLD,
    agreement_report,
    cohen_kappa,
    consensus,
    detection,
    h_fact,
    per_rater_h_fact,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

S, U = "supported", "unsupported"


def _key(n_real: int, n_planted: int = 0) -> dict[str, dict[str, Any]]:
    key: dict[str, dict[str, Any]] = {}
    for i in range(n_real):
        arm = "HELIOS-Full" if i % 2 == 0 else "HELIOS-noLLM"
        key[f"r{i}"] = {
            "arm": arm,
            "incident_id": f"c{i // 2}",
            "planted": False,
            "category": "",
            "kind": "log_message" if i == 0 else "shift",
        }
    cats = ["numeric_drift", "entity_mismatch", "directional_inversion"]
    for j in range(n_planted):
        key[f"p{j}"] = {
            "arm": "HELIOS-Full",
            "incident_id": f"c{j}",
            "planted": True,
            "category": cats[j % 3],
        }
    return key


def _lab(
    verdict: str, category: str = "", ts: str = "2026-12-01T10:00:00Z"
) -> dict[str, Any]:
    if verdict == U and not category:
        category = "numeric_drift"
    return {"verdict": verdict, "category": category, "timestamp_utc": ts}


def test_kappa_matches_hand_value() -> None:
    a = [S] * 40 + [S] * 5 + [U] * 5 + [U] * 50
    b = [S] * 40 + [U] * 5 + [S] * 5 + [U] * 50
    k = cohen_kappa(a, b)
    assert k is not None and round(k, 3) == 0.798


def test_kappa_undefined_when_one_label_only() -> None:
    assert cohen_kappa([S] * 10, [S] * 10) is None
    assert cohen_kappa([], []) is None


def test_prevalence_paradox_fixture() -> None:
    a = [S] * 99 + [U]
    b = [S] * 99 + [S]
    k = cohen_kappa(a, b)
    assert k is not None and k <= 0.01  # 99% agree, kappa near zero


def _labels(pairs: dict[str, tuple[str, str]]) -> dict[tuple[str, str], dict[str, Any]]:
    out = {}
    for item, (v1, v2) in pairs.items():
        out[item, "R1"] = _lab(v1)
        out[item, "R2"] = _lab(v2)
    return out


def test_consensus_above_and_below_threshold() -> None:
    key = _key(4)
    labels = _labels({"r0": (S, S), "r1": (S, U), "r2": (U, U), "r3": (S, S)})
    adj = {("r1", "ADJ"): _lab(U, "entity_mismatch"), ("r3", "ADJ"): _lab(U)}
    above = consensus(labels, adj, key, kappa=KAPPA_THRESHOLD)
    assert above["r0"]["verdict"] == S and above["r1"]["verdict"] == U
    assert above["r3"]["verdict"] == S  # agreement stands above the threshold
    below = consensus(labels, adj, key, kappa=KAPPA_THRESHOLD - 1 / 50)
    assert below["r3"]["verdict"] == U  # the adjudicator re-labels every real claim
    assert below["r0"]["verdict"] == "pending"
    none = consensus(labels, {}, key, kappa=KAPPA_THRESHOLD)
    assert none["r1"]["verdict"] == "pending"


def test_planted_never_count_in_h_fact() -> None:
    key = _key(4, n_planted=3)
    labels = _labels({"r0": (S, S), "r1": (S, S), "r2": (U, U), "r3": (S, S)})
    labels.update(_labels({"p0": (U, U), "p1": (U, U), "p2": (U, U)}))
    cons = consensus(labels, {}, key, kappa=KAPPA_THRESHOLD)
    assert set(cons) == {"r0", "r1", "r2", "r3"}
    got = h_fact(cons, key)["per_arm"]
    assert got["HELIOS-Full"] == {"claims": 2, "unsupported": 1, "h_fact": 1 / 2}
    assert got["HELIOS-noLLM"] == {"claims": 2, "unsupported": 0, "h_fact": 0}


def test_h_fact_per_case_pairs_full_and_nollm() -> None:
    key = _key(4)
    cons = consensus(
        _labels({"r0": (U, U), "r1": (S, S), "r2": (S, S), "r3": (S, S)}),
        {},
        key,
        kappa=KAPPA_THRESHOLD,
    )
    per_case = h_fact(cons, key)["per_case"]
    assert per_case["c0"]["HELIOS-Full"]["h_fact"] == 1
    assert per_case["c0"]["HELIOS-noLLM"]["h_fact"] == 0
    assert set(per_case["c1"]) == {"HELIOS-Full", "HELIOS-noLLM"}


def test_per_rater_h_fact() -> None:
    key = _key(2)
    got = per_rater_h_fact(_labels({"r0": (U, S), "r1": (S, S)}), key)
    assert got["R1"]["HELIOS-Full"]["h_fact"] == 1
    assert got["R2"]["HELIOS-Full"]["h_fact"] == 0


def test_detection_floor_flags_a_sitting() -> None:
    key = _key(2, n_planted=10)
    labels: dict[tuple[str, str], dict[str, Any]] = {}
    for j in range(5):  # sitting 1: 5 of 5 caught
        labels[f"p{j}", "R1"] = _lab(U, ts=f"2026-12-01T10:0{j}:00Z")
    for j in range(5, 10):  # sitting 2, two hours later: 3 of 5 caught
        verdict = U if j < 8 else S
        labels[f"p{j}", "R1"] = _lab(verdict, ts=f"2026-12-01T12:0{j - 5}:00Z")
    labels["r0", "R1"] = _lab(U, ts="2026-12-01T12:09:00Z")  # a false alarm
    labels["r1", "R1"] = _lab(S, ts="2026-12-01T12:09:30Z")
    got = detection(labels, key)["R1"]
    assert [s["below_floor"] for s in got["sittings"]] == [False, True]
    assert got["sittings"][1]["caught"] == 3 and got["sittings"][1]["planted"] == 5
    assert got["false_alarm"] == 1 / 2
    assert DETECTION_FLOOR == 4 / 5


def test_category_disagreement_does_not_change_h_fact() -> None:
    key = _key(2)
    labels = {
        ("r0", "R1"): _lab(U, "numeric_drift"),
        ("r0", "R2"): _lab(U, "entity_mismatch"),
        ("r1", "R1"): _lab(S),
        ("r1", "R2"): _lab(S),
    }
    without = consensus(labels, {}, key, kappa=KAPPA_THRESHOLD)
    with_adj = consensus(
        labels, {("r0", "ADJ"): _lab(U, "entity_mismatch")}, key, kappa=KAPPA_THRESHOLD
    )
    assert without["r0"]["verdict"] == with_adj["r0"]["verdict"] == U
    assert with_adj["r0"]["category"] == "entity_mismatch"
    assert h_fact(without, key) == h_fact(with_adj, key)


def test_blinding_hit_rate_and_report() -> None:
    key = _key(4, n_planted=2)
    labels = _labels({"r0": (S, S), "r1": (S, U), "r2": (U, U), "r3": (S, S)})
    labels.update(_labels({"p0": (U, U), "p1": (U, S)}))
    guesses = {
        ("r0", "R1"): {"verdict": "A"},  # r0 is Full; A is the language model: a hit
        ("r1", "R1"): {"verdict": "A"},  # r1 is noLLM: a miss
        ("r2", "R2"): {"verdict": "unsure"},
    }
    rep = agreement_report(labels, {("r1", "ADJ"): _lab(U)}, guesses, key)
    assert rep["blinding"]["all"] == {
        "answered": 2,
        "hits": 1,
        "unsure": 1,
        "hit_rate": 1 / 2,
    }
    # Review C2: leak kinds (Full only) apart from shared kinds.
    assert rep["blinding"]["leak_kinds"]["hits"] == 1  # r0 is a log claim
    assert rep["blinding"]["shared_kinds"]["answered"] == 1
    assert rep["blinding"]["shared_kinds"]["hits"] == 0
    assert rep["kappa_all"] is not None and rep["kappa_real"] is not None
    # kappa 1/3 here: R-m sends every real claim to the adjudicator, who
    # decided one of four, so three stay pending.
    assert rep["kappa_threshold_met"] is False and rep["counts"]["pending"] == 3
    assert set(rep) >= {"h_fact", "per_rater", "detection", "category_agreement"}


def test_consensus_needs_two_raters() -> None:
    with pytest.raises(ValueError, match="two raters"):
        consensus({("r0", "R1"): _lab(S)}, {}, _key(1), kappa=KAPPA_THRESHOLD)
