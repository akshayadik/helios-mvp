"""Phase A Markdown tables (scripts/phase_a_tables.py): label wording, formats."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from phase_a_tables import decision, fmt_p, main, render

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path


def _hypothesis(hid: str, rank: int, p: float | None) -> dict[str, Any]:
    h: dict[str, Any] = {
        "id": hid,
        "rank": rank,
        "comparison": "HELIOS-Full vs HELIOS-D",
        "metric": "HR@3",
        "test": "wilcoxon_signed_rank",
        "n_pairs": 40,
        "p_value": p,
        "by_measure": {
            "hr_at_3": {
                "n_informative": 9,
                "mean_difference": 0.125,
                "bca_low": 0.025,
                "bca_high": 0.25,
                "bca_note": None,
                "hodges_lehmann": 0,
                "cliffs_delta": 0.125,
                "cohens_h": 0.3,
            }
        },
        "exploratory_hr": {
            "hr_at_3_discordant_pairs": 9,
            "hr_at_1": {"mean_difference": 0.05, "bca_low": -0.025, "bca_high": 0.125},
            "mrr": {"mean_difference": 0.04, "bca_low": -0.01, "bca_high": 0.09},
        },
    }
    if p is None:
        h["untestable"] = "cell rule: too few cases"
    return h


def _holm(hid: str, rank: int, p: float | None, key: str, hit: bool) -> dict[str, Any]:
    return {
        "id": hid,
        "rank": rank,
        "p_value": p,
        "threshold": None if p is None else 0.00625,
        "adjusted_p": None if p is None else min(3 * p, 1),
        key: hit,
    }


def _analysis(label: str) -> dict[str, Any]:
    key = "rejected" if label == "confirmatory" else "below_threshold_descriptive"
    holm = [
        _holm("A-H3", 1, 0.00001, key, True),
        _holm("A-H1", 2, 0.2, key, False),
        _holm("A-H7", 3, None, key, False),
    ]
    return {
        "version": "analysis-v2",
        "label": label,
        "guard_reasons": [] if label == "confirmatory" else ["corpus is ['build']"],
        "systems": {"HELIOS-Full": 40, "HELIOS-D": 40},
        "cases": 40,
        "family_a": {
            "holm_reading": "data_order",
            "hypotheses": [
                _hypothesis("A-H3", 1, 0.00001),
                _hypothesis("A-H1", 2, 0.2),
                _hypothesis("A-H7", 3, None),
            ],
            "holm_binding": holm,
            "holm_other_reading": holm,
            "benjamini_hochberg": holm,
        },
        "family_e": [
            {
                "id": "E-H2",
                "comparison": "HELIOS-noRouter vs HELIOS-Full",
                "metric": "time to triage",
                "status": "exploratory",
                "available": True,
                "n_pairs": 40,
                "mean_difference": 12.5,
                "bca_low": 10.25,
                "bca_high": 14.75,
                "cliffs_delta": 0.9,
            },
            {
                "id": "E-H3",
                "comparison": "x vs y",
                "metric": "m",
                "status": "retired",
                "available": False,
            },
        ],
        "sanity_floors": {"HR@3": {"random_all_services": 0.2, "helios_d": 0.75}},
        "rerun_determinism": {
            "HELIOS-Full": {"pairs": 4, "compared": 4, "identical_share": 0.75}
        },
    }


def test_fmt_p() -> None:
    assert fmt_p(None) == "—"
    assert fmt_p(0.01234567) == "0.0123"
    assert fmt_p(0.00001) == "1.0e-05"


def test_decision_wording_follows_the_label() -> None:
    assert decision({"p_value": 0.001, "rejected": True}, True) == "rejected"
    assert decision({"p_value": 0.2, "rejected": False}, True) == "not rejected"
    desc = {"p_value": 0.001, "below_threshold_descriptive": True}
    assert decision(desc, False) == "below threshold (descriptive)"
    assert decision({"p_value": None, "untestable": "no data"}, True) == (
        "untestable: no data"
    )


def test_confirmatory_tables_say_rejected() -> None:
    text = render(_analysis("confirmatory"))
    assert "**Label:** confirmatory" in text
    assert "| A-H3 | 1 |" in text
    assert "| rejected |" in text
    assert "| not rejected |" in text
    assert "untestable: cell rule: too few cases" in text
    assert "Not confirmatory" not in text


def test_exploratory_tables_never_say_rejected() -> None:
    text = render(_analysis("exploratory"))
    assert "rejected" not in text
    assert "below threshold (descriptive)" in text
    assert "**Not confirmatory:** corpus is ['build']" in text


def test_sections_and_effects() -> None:
    text = render(_analysis("confirmatory"))
    for heading in (
        "## Family A (confirmatory ablation)",
        "robustness",
        "HR@1 and MRR beside HR@3",
        "## Family E (exploratory; BCa only, never Holm)",
        "## Sanity floors",
        "## Rerun determinism",
    ):
        assert heading in text
    assert "hr_at_3: +0.125 [0.025, 0.250]" in text
    assert "| E-H3 | x vs y | m | retired |" in text


def test_main_writes_the_file(tmp_path: Path) -> None:
    src = tmp_path / "analysis.json"
    src.write_text(json.dumps(_analysis("exploratory")), encoding="utf-8")
    out = tmp_path / "tables.md"
    assert main(["--analysis", str(src), "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("# Analysis tables")
