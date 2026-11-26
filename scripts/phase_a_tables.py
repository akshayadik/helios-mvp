#!/usr/bin/env python3
"""Phase A (A6): Markdown result tables from one analysis JSON (S4.11 T-j).

Usage (from the repository root):
    poetry run python scripts/phase_a_tables.py --analysis analysis.json \
        --out tables.md

Reads only the output of ``bin/analyse.py``; it reads no store, no ground
truth and no capture, and prints nothing about cases. It lives outside the
frozen paths, so it can change during phase A without a new freeze: it
formats numbers the frozen analysis computed and computes none of its own.

Wording follows the run's label (T-i): a confirmatory run says "rejected" or
"not rejected"; any other run says "below threshold (descriptive)" and never
"rejected".
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

__all__ = ["decision", "fmt_p", "main", "render"]

_SMALL_P = 1e-4
_DASH = "—"


def fmt_p(p: float | None) -> str:
    """A p-value: four decimals, or scientific below 1e-4; a dash if absent."""
    if p is None:
        return _DASH
    return f"{p:.1e}" if p < _SMALL_P else f"{p:.4f}"


def _num(x: float | None, digits: int = 3, *, signed: bool = False) -> str:
    if x is None:
        return _DASH
    return f"{x:+.{digits}f}" if signed else f"{x:.{digits}f}"


def _cell(text: Any) -> str:
    return str(text).replace("|", "/").replace("\n", " ")


def _table(header: Sequence[str], rows: Iterable[Sequence[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(header) + " |",
        "|" + "|".join("---" for _ in header) + "|",
    ]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return lines


def decision(row: Mapping[str, Any], confirmatory: bool) -> str:
    """The wording for one Holm, BH or sensitivity row under the run's label."""
    if row.get("untestable"):
        return f"untestable: {row['untestable']}"
    if row.get("p_value") is None and "untestable" not in row:
        return "untestable"
    if confirmatory:
        return "rejected" if row.get("rejected") else "not rejected"
    hit = row.get("below_threshold_descriptive", row.get("rejected"))
    return (
        "below threshold (descriptive)" if hit else "not below threshold (descriptive)"
    )


def _effect(m: Mapping[str, Any]) -> str:
    text = (
        f"{_num(m.get('mean_difference'), signed=True)} "
        f"[{_num(m.get('bca_low'))}, {_num(m.get('bca_high'))}]"
    )
    return text + (f" ({m['bca_note']})" if m.get("bca_note") else "")


def _measures(h: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    return sorted((h.get("by_measure") or {}).items())


def _join(parts: Iterable[str]) -> str:
    out = "; ".join(p for p in parts if p)
    return out or _DASH


def family_table(family: Mapping[str, Any], confirmatory: bool) -> list[str]:
    """One row per hypothesis: test, n, p, Holm threshold and decision, effects."""
    holm = {r["id"]: r for r in family.get("holm_binding", [])}
    rows = []
    for h in sorted(family.get("hypotheses", []), key=lambda r: r.get("rank", 0)):
        ms = _measures(h)
        rows.append(
            [
                h["id"],
                h.get("rank", _DASH),
                h.get("comparison", _DASH),
                h.get("metric", _DASH),
                h.get("test", _DASH),
                h.get("n_pairs", 0),
                _join(str(m.get("n_informative", _DASH)) for _, m in ms),
                fmt_p(h.get("p_value")),
                _num(holm.get(h["id"], {}).get("threshold"), 5),
                fmt_p(holm.get(h["id"], {}).get("adjusted_p")),
                decision({**h, **holm.get(h["id"], {})}, confirmatory),
                _join(f"{k}: {_effect(m)}" for k, m in ms),
                _join(_num(m.get("hodges_lehmann"), signed=True) for _, m in ms),
                _join(_num(m.get("cliffs_delta"), signed=True) for _, m in ms),
                _join(
                    _num(m["cohens_h"], signed=True)
                    for _, m in ms
                    if m.get("cohens_h") is not None
                ),
            ]
        )
    return _table(
        [
            "ID",
            "Rank",
            "Comparison",
            "Metric",
            "Test",
            "n pairs",
            "n informative",
            "p",
            "Holm threshold",
            "Holm adjusted p",
            "Decision (binding Holm)",
            "Mean difference [BCa 95%]",
            "Hodges-Lehmann",
            "Cliff's δ",
            "Cohen's h",
        ],
        rows,
    )


def robustness_table(family: Mapping[str, Any], confirmatory: bool) -> list[str]:
    """Other Holm reading, BH, group-level, rank mixed model, missing data, timing."""
    other = {r["id"]: r for r in family.get("holm_other_reading", [])}
    bh = {r["id"]: r for r in family.get("benjamini_hochberg", [])}
    rows = []
    for h in sorted(family.get("hypotheses", []), key=lambda r: r.get("rank", 0)):
        s = h.get("sensitivity") or {}
        group = s.get("group_level_wilcoxon") or {}
        mixed = s.get("rank_mixed_model") or {}
        missing = s.get("missing_data") or {}
        timing = h.get("timing") or {}
        rows.append(
            [
                h["id"],
                decision(other.get(h["id"], {}), confirmatory),
                decision(bh.get(h["id"], {}), confirmatory),
                f"{fmt_p(group.get('p_value'))} (groups {group.get('n_groups', _DASH)})",
                (
                    f"{fmt_p(mixed.get('p_value'))}, ICC {_num(mixed.get('icc'))}"
                    + ("" if mixed.get("converged", True) else ", not converged")
                    if mixed
                    else _DASH
                ),
                _join(
                    [
                        (missing.get("mcar") or {}).get("status", ""),
                        (missing.get("ipw") or {}).get("status", ""),
                    ]
                ),
                (
                    _DASH
                    if not timing
                    else (
                        "sensitive to timing noise"
                        if timing.get("sensitive_to_timing_noise")
                        else "not sensitive"
                    )
                    + (
                        "; crosses the threshold with reruns"
                        if timing.get("crosses_threshold_with_reruns")
                        else ""
                    )
                ),
            ]
        )
    return _table(
        [
            "ID",
            "Other Holm reading",
            "Benjamini-Hochberg",
            "Group-level Wilcoxon p",
            "Rank mixed model",
            "Missing data (MCAR / IPW)",
            "Timing (entry 94)",
        ],
        rows,
    )


def exploratory_hr_table(family: Mapping[str, Any]) -> list[str]:
    """HR@1 and MRR beside each HR@3 test (entry 95): exploratory, descriptive."""
    rows = []
    for h in sorted(family.get("hypotheses", []), key=lambda r: r.get("rank", 0)):
        e = h.get("exploratory_hr")
        if not e:
            continue
        rows.append(
            [
                h["id"],
                e.get("hr_at_3_discordant_pairs", _DASH),
                _effect(e.get("hr_at_1") or {}),
                _effect(e.get("mrr") or {}),
            ]
        )
    if not rows:
        return ["No HR@3 test in this family."]
    return _table(
        [
            "ID",
            "HR@3 discordant pairs",
            "HR@1 difference [BCa 95%]",
            "MRR difference [BCa 95%]",
        ],
        rows,
    )


def family_b_sensitivity_lines(
    sens: Mapping[str, Any], confirmatory: bool
) -> list[str]:
    """Trigger-time baselines (B-b), no human time, and the chase anchor."""
    lines: list[str] = []
    for key, title in (
        ("trigger_time", "Baselines at HELIOS's detection-trigger time (B-b)"),
        ("no_human_time", "CpR without the human-time term"),
    ):
        rows = [
            [
                r["id"],
                f"{r.get('a', _DASH)} vs {r.get('b', _DASH)}",
                r.get("n_pairs", 0),
                fmt_p(r.get("p_value")),
                decision(r, confirmatory),
            ]
            for r in sens.get(key, [])
        ]
        if rows:
            lines += ["", f"**{title}**", ""]
            lines += _table(["ID", "Comparison", "n pairs", "p", "Decision"], rows)
    anchor = sens.get("chase_anchor")
    if anchor:
        lines += [
            "",
            "**Chase anchor**",
            "",
            f"Anchor HR@3 {_num(anchor.get('hr_at_3'))}, sensitivity band "
            f"{_num(anchor.get('sensitivity_band'))}.",
            "",
        ]
        lines += _table(
            ["Baseline", "HR@3"],
            [
                [k, _num(v)]
                for k, v in sorted((anchor.get("baselines_hr_at_3") or {}).items())
            ],
        )
    return lines


def family_e_table(rows_in: Sequence[Mapping[str, Any]]) -> list[str]:
    """Family E: exploratory, BCa only, never Holm."""
    rows = []
    for r in rows_in:
        if not r.get("available"):
            state = r.get("untestable") or (
                "retired" if r.get("status") == "retired" else "not available"
            )
            rows.append(
                [r["id"], r.get("comparison"), r.get("metric"), state, _DASH, _DASH]
            )
            continue
        rows.append(
            [
                r["id"],
                r.get("comparison"),
                r.get("metric"),
                f"n = {r.get('n_pairs', 0)}",
                _effect(r),
                _num(r.get("cliffs_delta"), signed=True),
            ]
        )
    return _table(
        [
            "ID",
            "Comparison",
            "Metric",
            "Status",
            "Mean difference [BCa 95%]",
            "Cliff's δ",
        ],
        rows,
    )


def floors_table(floors: Mapping[str, Mapping[str, float]]) -> list[str]:
    names = sorted({k for row in floors.values() for k in row})
    return _table(
        ["Measure", *names],
        [[m, *(_num(row.get(n)) for n in names)] for m, row in floors.items()],
    )


def determinism_table(det: Mapping[str, Mapping[str, Any]]) -> list[str]:
    rows = [
        [
            name,
            d.get("pairs", _DASH),
            d.get("compared", _DASH),
            _num(d.get("identical_share")),
        ]
        for name, d in sorted(det.items())
    ]
    return _table(["System", "Rerun pairs", "Compared", "Identical share"], rows)


def render(analysis: Mapping[str, Any], *, source: str = "") -> str:
    """The whole Markdown report for one analysis JSON."""
    label = str(analysis.get("label", "exploratory"))
    confirmatory = label == "confirmatory"
    lines = [
        "# Analysis tables",
        "",
        f"**Label:** {label} · **Version:** {analysis.get('version', _DASH)} · "
        f"**Cases:** {analysis.get('cases', _DASH)}"
        + (f" · **Source:** `{source}`" if source else ""),
        "",
    ]
    reasons = analysis.get("guard_reasons") or []
    if reasons:
        lines += [
            "**Not confirmatory:** " + "; ".join(reasons) + ". "
            "Every p-value below is descriptive.",
            "",
        ]
    systems = analysis.get("systems") or {}
    if systems:
        lines += ["## Systems", ""]
        lines += _table(["System", "Cases with a run"], sorted(systems.items()))
        lines.append("")
    coverage = analysis.get("trace_coverage") or {}
    if coverage:
        lines += ["## Trace coverage (entry 93)", ""]
        lines += _table(
            ["System", "Cases", "With traces", "Capture not read"],
            [
                [k, v.get("cases"), v.get("with_traces"), v.get("capture_missing")]
                for k, v in sorted(coverage.items())
            ],
        )
        lines.append("")
    for key, title in (
        ("family_a", "Family A (confirmatory ablation)"),
        ("family_b", "Family B (baselines)"),
    ):
        fam = analysis.get(key)
        if not fam:
            continue
        lines += [
            f"## {title}",
            "",
            f"Holm reading: `{fam.get('holm_reading', _DASH)}`.",
            "",
        ]
        lines += family_table(fam, confirmatory)
        lines += ["", f"### {title}: robustness", ""]
        lines += robustness_table(fam, confirmatory)
        lines += [
            "",
            f"### {title}: HR@1 and MRR beside HR@3 (entry 95, exploratory)",
            "",
        ]
        lines += exploratory_hr_table(fam)
        lines.append("")
    sens = analysis.get("family_b_sensitivity")
    if sens:
        lines += ["## Family B sensitivity", ""]
        lines += family_b_sensitivity_lines(sens, confirmatory)
        lines.append("")
    if analysis.get("family_e"):
        lines += ["## Family E (exploratory; BCa only, never Holm)", ""]
        lines += family_e_table(analysis["family_e"])
        lines.append("")
    if analysis.get("sanity_floors"):
        lines += ["## Sanity floors", ""]
        lines += floors_table(analysis["sanity_floors"])
        lines.append("")
    if analysis.get("rerun_determinism"):
        lines += ["## Rerun determinism (entries 94, 96)", ""]
        lines += determinism_table(analysis["rerun_determinism"])
        lines.append("")
    if analysis.get("timing_noise_statement"):
        lines += ["## Timing noise (entry 94)", "", analysis["timing_noise_statement"]]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    analysis = json.loads(args.analysis.read_text(encoding="utf-8"))
    args.out.write_text(render(analysis, source=args.analysis.name), encoding="utf-8")
    print(f"[tables] {analysis.get('label')} → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
