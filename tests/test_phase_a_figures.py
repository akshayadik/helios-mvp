"""Phase A SVG figures (scripts/phase_a_figures.py)."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Any

import pytest
from phase_a_figures import (
    cost_accuracy,
    figures,
    forest_rows,
    hr_by_variant,
    main,
    nice_ticks,
    reliability,
)

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path

SVG = "{http://www.w3.org/2000/svg}"


def _analysis(label: str) -> dict[str, Any]:
    def hyp(hid: str, rank: int, p: float | None) -> dict[str, Any]:
        return {
            "id": hid,
            "rank": rank,
            "comparison": "HELIOS-Full vs HELIOS-D",
            "p_value": p,
            "by_measure": {
                "hr_at_3": {"mean_difference": 0.12, "bca_low": 0.04, "bca_high": 0.2}
            },
            "below_threshold_descriptive": p is not None and p < 0.01,
        }

    return {
        "label": label,
        "family_a": {
            "hypotheses": [hyp("A-H2", 2, 0.3), hyp("A-H1", 1, 0.001)],
            "holm_binding": [
                {"id": "A-H1", "rejected": True},
                {"id": "A-H2", "rejected": False},
            ],
        },
        "family_b": {"hypotheses": [hyp("B-H1", 1, None)], "holm_binding": []},
        "family_e": [
            {
                "id": "E-H2",
                "available": True,
                "comparison": "x vs y",
                "metric": "ece",
                "mean_difference": -0.03,
                "bca_low": -0.06,
                "bca_high": -0.01,
            },
            {"id": "E-H4", "available": False, "metric": "hr_at_3"},
        ],
    }


EVIDENCE: dict[str, Any] = {
    "calibration": {
        "HELIOS-Full": {
            "with_confidence": 40,
            "ece": 0.05,
            "brier": 0.18,
            "bins": [
                {"mean_confidence": 0.3, "observed_hr_at_3": 0.25, "n": 10},
                {"mean_confidence": 0.9, "observed_hr_at_3": 0.85, "n": 30},
            ],
        },
        "HELIOS-D": {"with_confidence": 0},  # no confidence: no panel
    },
    "variants": {
        "HELIOS-Full": {"hr_at_1": 0.6, "hr_at_3": 0.8, "median_log_cpr": 3.2},
        "HELIOS-D": {"hr_at_1": 0.4, "hr_at_3": 0.7, "median_log_cpr": 0.9},
        "HELIOS-G": {"hr_at_1": 0.3, "hr_at_3": 0.45, "median_log_cpr": None},
    },
}


def _parse(svg: str) -> ET.Element:
    root = ET.fromstring(svg)
    assert root.tag == f"{SVG}svg"
    assert root.find(f"{SVG}title") is not None
    return root


def test_nice_ticks_cover_the_range() -> None:
    assert nice_ticks(0, 1) == [0, 0.2, 0.4, 0.6, 0.8, 1]
    ticks = nice_ticks(-0.07, 0.23)
    assert ticks[0] <= -0.07 and ticks[-1] >= 0.23
    assert nice_ticks(2, 2)  # empty range widened, not an error


def test_forest_rows_follow_the_label() -> None:
    conf = forest_rows(_analysis("confirmatory"))
    assert [r["id"] for r in conf] == ["A-H1", "A-H2", "B-H1"]
    assert [r["decided"] for r in conf] == [True, False, None]
    desc = forest_rows(_analysis("exploratory"))
    assert [r["decided"] for r in desc] == [True, False, None]


def test_forest_marks_decisions_and_untestable() -> None:
    out = figures(_analysis("confirmatory"), None)
    root = _parse(out["forest.svg"])
    dots = root.findall(f"{SVG}circle")
    assert len(dots) == 3  # B-H1: a difference but no p-value, grey and hollow
    styles = sorted((d.get("fill") or "", d.get("stroke") or "") for d in dots)
    assert styles == [
        ("#2a78d6", "#2a78d6"),  # A-H1 rejected
        ("#ffffff", "#2a78d6"),  # A-H2 not rejected
        ("#ffffff", "#8a8984"),  # B-H1 untestable
    ]
    assert "rejected under the binding Holm" in out["forest.svg"]
    e = _parse(out["forest_e.svg"])
    assert "untestable" in out["forest_e.svg"]
    assert len(e.findall(f"{SVG}circle")) == 1


def test_non_confirmatory_forest_never_says_rejected_as_a_decision() -> None:
    svg = figures(_analysis("exploratory"), None)["forest.svg"]
    assert "never rejected" in svg
    assert "rejected under the binding Holm" not in svg


def test_reliability_panels_only_for_variants_with_bins() -> None:
    svg = reliability(EVIDENCE["calibration"])
    assert svg is not None
    root = _parse(svg)
    assert len(root.findall(f"{SVG}polyline")) == 1
    assert "HELIOS-D" not in svg
    assert reliability({"HELIOS-D": {"with_confidence": 0}}) is None


def test_reliability_tolerates_missing_scores() -> None:
    cal = {"HELIOS-Full": {**EVIDENCE["calibration"]["HELIOS-Full"], "ece": None}}
    svg = reliability(cal)
    assert svg is not None
    assert "ECE —" in svg


def test_cost_accuracy_skips_variants_without_cost() -> None:
    svg = cost_accuracy(EVIDENCE["variants"])
    assert svg is not None
    root = _parse(svg)
    dots = root.findall(f"{SVG}circle")
    assert len(dots) == 2
    assert {d.get("fill") for d in dots} == {"#eb6834", "#2a78d6"}
    assert cost_accuracy({}) is None


def test_cost_accuracy_merges_coincident_points() -> None:
    variants = {
        "HELIOS-Full": {"hr_at_3": 0.97, "median_log_cpr": 3.6123},
        "HELIOS-noACP": {"hr_at_3": 0.97, "median_log_cpr": 3.6141},
        "HELIOS-noRouter": {"hr_at_3": 0.98, "median_log_cpr": 6.8},
    }
    svg = cost_accuracy(variants)
    assert svg is not None
    dots = _parse(svg).findall(f"{SVG}circle")
    assert len(dots) == 2
    assert ">Full, noACP<" in svg
    merged = next(d for d in dots if d.get("fill") == "#eb6834")
    tip = merged.find(f"{SVG}title")
    assert tip is not None and "3.612" in (tip.text or "")
    assert "3.614" in (tip.text or "")


def test_hr_by_variant_sorted_by_hr_at_3() -> None:
    svg = hr_by_variant(EVIDENCE["variants"])
    assert svg is not None
    root = _parse(svg)
    assert len(root.findall(f"{SVG}path")) == 6
    assert svg.index(">Full<") < svg.index(">D<") < svg.index(">G<")
    assert hr_by_variant({}) is None


def test_output_is_deterministic() -> None:
    a = figures(_analysis("confirmatory"), EVIDENCE)
    b = figures(_analysis("confirmatory"), EVIDENCE)
    assert a == b
    assert set(a) == {
        "forest.svg",
        "forest_e.svg",
        "reliability.svg",
        "cost_accuracy.svg",
        "hr_by_variant.svg",
    }


def test_main_writes_files(tmp_path: Path) -> None:
    an, ev = tmp_path / "a.json", tmp_path / "e.json"
    an.write_text(json.dumps(_analysis("confirmatory")), encoding="utf-8")
    ev.write_text(json.dumps(EVIDENCE), encoding="utf-8")
    out = tmp_path / "fig"
    argv = ["--analysis", str(an), "--evidence", str(ev), "--out-dir", str(out)]
    assert main(argv) == 0
    assert sorted(p.name for p in out.iterdir()) == [
        "cost_accuracy.svg",
        "forest.svg",
        "forest_e.svg",
        "hr_by_variant.svg",
        "reliability.svg",
    ]
    assert main(["--evidence", str(ev), "--out-dir", str(tmp_path / "e")]) == 0
    assert len(list((tmp_path / "e").iterdir())) == 3
    with pytest.raises(SystemExit):
        main(["--out-dir", str(out)])
