#!/usr/bin/env python3
"""Phase A (A6): plain SVG figures from the analysis and evidence JSON.

Usage (from the repository root):
    poetry run python scripts/phase_a_figures.py --analysis analysis.json \
        --evidence evidence.json --out-dir figures/

Figures (each written only when its input is given):

- ``forest.svg`` (analysis): Family A and B effects, mean difference with
  its BCa 95% interval, one panel per measure (each with its own axis);
  a filled marker is a rejection under the binding Holm reading on a
  confirmatory run, or "below threshold (descriptive)" on any other run.
- ``forest_e.svg`` (analysis): Family E effects (exploratory, BCa only, no
  decision).
- ``reliability.svg`` (evidence): MAHC confidence against the observed HR@3
  per confidence bin, one panel per variant with a confidence.
- ``cost_accuracy.svg`` (evidence): median log-CpR against HR@3, one point
  per variant.
- ``hr_by_variant.svg`` (evidence): HR@1 and HR@3 per variant.

It reads only the JSON that ``bin/analyse.py`` and
``scripts/phase_a_evidence.py`` write: no store, no ground truth, no capture,
no case ID. It computes no statistic of its own, uses no plotting library
(the SVG is written as text, so the same input gives the same bytes), and
lives outside the frozen paths.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any
from xml.sax.saxutils import escape

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

__all__ = [
    "cost_accuracy",
    "forest",
    "forest_rows",
    "hr_by_variant",
    "main",
    "nice_ticks",
    "reliability",
]

# Light print palette (validated: two categorical slots pass every check).
SURFACE = "#ffffff"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
MUTED = "#8a8984"
GRID = "#e6e5e1"
AXIS = "#c3c2b7"
SERIES_1 = "#2a78d6"
SERIES_2 = "#eb6834"
FONT = "system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"

WIDTH = 760
FULL = "HELIOS-Full"
_PREFIX = "HELIOS-"
MERGE_PX = 6  # points closer than this (pixels) share a marker and label


# ── primitives ──────────────────────────────────────────────────────────────


def _n(x: float) -> str:
    """A coordinate with at most two decimals, trailing zeros dropped."""
    text = f"{x:.2f}".rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _text(
    x: float,
    y: float,
    s: str,
    *,
    size: int = 12,
    fill: str = TEXT,
    anchor: str = "start",
    weight: str = "normal",
) -> str:
    return (
        f'<text x="{_n(x)}" y="{_n(y)}" font-size="{size}" fill="{fill}" '
        f'text-anchor="{anchor}" font-weight="{weight}">{escape(s)}</text>'
    )


def _line(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    stroke: str = AXIS,
    width: int = 1,
    dash: str = "",
) -> str:
    extra = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<line x1="{_n(x1)}" y1="{_n(y1)}" x2="{_n(x2)}" y2="{_n(y2)}" '
        f'stroke="{stroke}" stroke-width="{width}"{extra}/>'
    )


def _dot(x: float, y: float, *, fill: str, stroke: str, tip: str, r: int = 4) -> str:
    return (
        f'<circle cx="{_n(x)}" cy="{_n(y)}" r="{r}" fill="{fill}" stroke="{stroke}" '
        f'stroke-width="2"><title>{escape(tip)}</title></circle>'
    )


def _bar(x0: float, y: float, w: float, h: float, *, fill: str, tip: str) -> str:
    """A horizontal bar anchored at x0, its data end rounded (radius 4)."""
    r = min(4.0, w / 2, h / 2)
    if w <= 0:
        return ""
    x1 = x0 + w
    d = (
        f"M{_n(x0)},{_n(y)} H{_n(x1 - r)} Q{_n(x1)},{_n(y)} {_n(x1)},{_n(y + r)} "
        f"V{_n(y + h - r)} Q{_n(x1)},{_n(y + h)} {_n(x1 - r)},{_n(y + h)} "
        f"H{_n(x0)} Z"
    )
    return f'<path d="{d}" fill="{fill}"><title>{escape(tip)}</title></path>'


def _doc(height: float, body: Iterable[str], title: str, desc: str) -> str:
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" '
            f'height="{_n(height)}" viewBox="0 0 {WIDTH} {_n(height)}" '
            f'role="img" font-family="{FONT}">',
            f"<title>{escape(title)}</title>",
            f"<desc>{escape(desc)}</desc>",
            f'<rect width="{WIDTH}" height="{_n(height)}" fill="{SURFACE}"/>',
            *body,
            "</svg>",
            "",
        ]
    )


def nice_ticks(lo: float, hi: float, count: int = 5) -> list[float]:
    """Round tick values (steps of 1, 2 or 5 times a power of ten) whose ends enclose
    [lo, hi]."""
    if hi <= lo:
        hi = lo + 1
    raw = (hi - lo) / max(count, 1)
    power = 10 ** math.floor(math.log10(raw))
    step = next(m * power for m in (1, 2, 5, 10) if m * power >= raw)
    first = math.floor(lo / step + 1e-9)
    last = math.ceil(hi / step - 1e-9)
    return [round(k * step, 10) for k in range(first, last + 1)]


def _fmt_tick(t: float) -> str:
    return f"{t:g}"


def _f3(x: float | None) -> str:
    return "—" if x is None else f"{x:.3f}"


def _fv(x: float, *, signed: bool = False) -> str:
    """A value with decimals by magnitude: three below 10, one below 1000,
    none above (a millisecond difference does not need three decimals)."""
    digits = 3 if abs(x) < 10 else (1 if abs(x) < 1000 else 0)
    return f"{x:+.{digits}f}" if signed else f"{x:.{digits}f}"


def _short(name: str) -> str:
    return name.removeprefix(_PREFIX) if name != FULL else "Full"


class _Scale:
    """Linear map from a data domain onto a pixel range."""

    def __init__(self, d0: float, d1: float, p0: float, p1: float) -> None:
        if d1 == d0:
            d1 = d0 + 1
        self.d0, self.d1, self.p0, self.p1 = d0, d1, p0, p1

    def __call__(self, v: float) -> float:
        return self.p0 + (v - self.d0) / (self.d1 - self.d0) * (self.p1 - self.p0)


def _x_axis(
    scale: _Scale, ticks: Sequence[float], top: float, bottom: float
) -> list[str]:
    out = []
    for t in ticks:
        x = scale(t)
        out.append(_line(x, top, x, bottom, stroke=GRID))
        out.append(
            _text(x, bottom + 14, _fmt_tick(t), size=10, fill=TEXT_2, anchor="middle")
        )
    return out


def _y_axis(
    scale: _Scale, ticks: Sequence[float], left: float, right: float
) -> list[str]:
    out = []
    for t in ticks:
        y = scale(t)
        out.append(_line(left, y, right, y, stroke=GRID))
        out.append(
            _text(left - 6, y + 3, _fmt_tick(t), size=10, fill=TEXT_2, anchor="end")
        )
    return out


# ── forest plots ────────────────────────────────────────────────────────────


def forest_rows(analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Family A and B rows: one per hypothesis and measure, with the decision
    under the run's label (True: rejected / below threshold)."""
    confirmatory = analysis.get("label") == "confirmatory"
    rows: list[dict[str, Any]] = []
    for key in ("family_a", "family_b"):
        fam = analysis.get(key) or {}
        holm = {r["id"]: r for r in fam.get("holm_binding", [])}
        for h in sorted(fam.get("hypotheses", []), key=lambda r: r.get("rank", 0)):
            decided = {**h, **holm.get(h["id"], {})}
            if confirmatory:
                hit = bool(decided.get("rejected"))
            else:
                hit = bool(
                    decided.get("below_threshold_descriptive", decided.get("rejected"))
                )
            for measure, m in sorted((h.get("by_measure") or {}).items()):
                rows.append(
                    {
                        "id": h["id"],
                        "comparison": str(h.get("comparison") or ""),
                        "measure": measure,
                        "diff": m.get("mean_difference"),
                        "low": m.get("bca_low"),
                        "high": m.get("bca_high"),
                        "decided": hit if h.get("p_value") is not None else None,
                    }
                )
    return rows


def family_e_rows(analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": r["id"],
            "comparison": str(r.get("comparison") or ""),
            "measure": str(r.get("metric") or "metric"),
            "diff": r.get("mean_difference") if r.get("available") else None,
            "low": r.get("bca_low"),
            "high": r.get("bca_high"),
            "decided": None,
        }
        for r in analysis.get("family_e") or []
    ]


def _clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def forest(
    rows: Sequence[Mapping[str, Any]],
    *,
    title: str,
    subtitle: str,
    legend: str,
    decisions: bool = True,
) -> str:
    """Effects with BCa 95% intervals, one panel (own axis) per measure.

    With ``decisions``, a filled marker is a decision ("decided" True), a
    hollow one is not, and a grey hollow one is untestable (no p-value);
    without, every marker is filled (Family E draws no decision)."""
    row_h, label_w, value_w = 22, 300, 150
    left, right = label_w, WIDTH - value_w
    body = [
        _text(16, 26, title, size=16, weight="600"),
        _text(16, 46, subtitle, size=12, fill=TEXT_2),
    ]
    y = 70
    measures = sorted({str(r["measure"]) for r in rows})
    for measure in measures:
        group = [r for r in rows if r["measure"] == measure]
        vals = [
            float(v)
            for r in group
            for v in (r["diff"], r["low"], r["high"])
            if v is not None
        ]
        lo, hi = min([*vals, 0]), max([*vals, 0])
        pad = (hi - lo) / 20 or 1
        ticks = nice_ticks(lo - pad, hi + pad)
        scale = _Scale(ticks[0], ticks[-1], left, right)
        body.append(_text(16, y + 4, measure, size=13, weight="600"))
        top = y + 14
        bottom = top + row_h * len(group)
        if not vals:  # nothing to place on an axis: list the rows only
            for i, r in enumerate(group):
                cy = top + row_h * i + row_h / 2
                label = f"{r['id']}  {_clip(str(r['comparison']), 34)}"
                body.append(_text(16, cy + 4, label, size=11))
                body.append(_text(left, cy + 4, "untestable", size=11, fill=MUTED))
            y = bottom + 18
            continue
        body += _x_axis(scale, ticks, top, bottom)
        body.append(_line(scale(0), top, scale(0), bottom, stroke=MUTED, dash="4 3"))
        for i, r in enumerate(group):
            cy = top + row_h * i + row_h / 2
            label = f"{r['id']}  {_clip(str(r['comparison']), 34)}"
            body.append(_text(16, cy + 4, label, size=11))
            if r["diff"] is None:
                body.append(_text(left + 4, cy + 4, "untestable", size=11, fill=MUTED))
                continue
            d = float(r["diff"])
            if r["low"] is not None and r["high"] is not None:
                body.append(
                    _line(
                        scale(float(r["low"])),
                        cy,
                        scale(float(r["high"])),
                        cy,
                        stroke=SERIES_1,
                        width=2,
                    )
                )
                ci = f" [{_fv(float(r['low']))}, {_fv(float(r['high']))}]"
            else:
                ci = ""
            tip = f"{r['id']} {measure}: {_fv(d, signed=True)}{ci}"
            if decisions and r["decided"] is None:
                fill, stroke, tip = SURFACE, MUTED, tip + " (untestable)"
            elif decisions and not r["decided"]:
                fill, stroke = SURFACE, SERIES_1
            else:
                fill, stroke = SERIES_1, SERIES_1
            body.append(_dot(scale(d), cy, fill=fill, stroke=stroke, tip=tip))
            body.append(
                _text(
                    right + 12,
                    cy + 4,
                    f"{_fv(d, signed=True)}{ci}",
                    size=10,
                    fill=TEXT_2,
                )
            )
        y = bottom + 34
    body.append(_text(16, y, legend, size=11, fill=TEXT_2))
    return _doc(y + 16, body, title, subtitle)


# ── evidence figures ────────────────────────────────────────────────────────


def reliability(calibration: Mapping[str, Mapping[str, Any]]) -> str | None:
    """Observed HR@3 against mean confidence per bin, a panel per variant."""
    variants = [(k, v) for k, v in calibration.items() if v.get("bins")]
    if not variants:
        return None
    cols, size, gap = 3, 250, 34
    panel_w = (WIDTH - 2 * 40 - gap * (cols - 1)) / cols
    title = "Calibrated consensus confidence: reliability"
    sub = "Mean MAHC confidence against observed HR@3, per confidence bin; dashed: perfect calibration."
    body = [
        _text(16, 26, title, size=16, weight="600"),
        _text(16, 46, sub, size=12, fill=TEXT_2),
    ]
    ticks = nice_ticks(0, 1)
    for i, (name, v) in enumerate(variants):
        col, row = i % cols, i // cols
        x0 = 56 + col * (panel_w + gap)
        y0 = 80 + row * (size + 24)
        sx = _Scale(0, 1, x0, x0 + panel_w - 12)
        sy = _Scale(0, 1, y0 + size - 40, y0 + 24)
        body.append(_text(x0 - 30, y0, name, size=11, weight="600"))
        body.append(
            _text(
                x0 - 30,
                y0 + 14,
                f"ECE {_f3(v.get('ece'))} · Brier {_f3(v.get('brier'))}"
                f" · n {v.get('with_confidence', 0)}",
                size=10,
                fill=TEXT_2,
            )
        )
        body += _y_axis(sy, ticks, sx(0), sx(1))
        body += _x_axis(sx, ticks, sy(1), sy(0))
        body.append(_line(sx(0), sy(0), sx(1), sy(1), stroke=MUTED, dash="4 3"))
        pts = [
            (float(b["mean_confidence"]), float(b["observed_hr_at_3"]), int(b["n"]))
            for b in v["bins"]
        ]
        path = " ".join(f"{_n(sx(c))},{_n(sy(o))}" for c, o, _ in pts)
        body.append(
            f'<polyline points="{path}" fill="none" stroke="{SERIES_1}" stroke-width="2"/>'
        )
        for c, o, n in pts:
            body.append(
                _dot(
                    sx(c),
                    sy(o),
                    fill=SERIES_1,
                    stroke=SURFACE,
                    tip=f"confidence {c:.3f}, HR@3 {o:.3f}, n {n}",
                )
            )
        body.append(
            _text(
                (sx(0) + sx(1)) / 2,
                sy(0) + 30,
                "Mean confidence",
                size=10,
                fill=TEXT_2,
                anchor="middle",
            )
        )
    rows = math.ceil(len(variants) / cols)
    height = 80 + rows * (size + 24)
    return _doc(height, body, title, sub)


def _spread(ys: list[float], gap: float) -> list[float]:
    """Nudge label positions apart (sorted order kept) so no two are closer
    than gap pixels."""
    order = sorted(range(len(ys)), key=lambda i: ys[i])
    out = list(ys)
    for a, b in itertools.pairwise(order):
        if out[b] - out[a] < gap:
            out[b] = out[a] + gap
    return out


def cost_accuracy(variants: Mapping[str, Mapping[str, Any]]) -> str | None:
    """Median log-CpR (cost) against HR@3 (accuracy), one point per variant.

    Variants whose points would sit within MERGE_PX pixels of each other are
    drawn as one point with one label (each member's exact values stay in
    the point's tooltip); the point holding HELIOS-Full is orange and drawn
    last, on top."""
    raw = sorted(
        (name, float(v["median_log_cpr"]), float(v["hr_at_3"]))
        for name, v in variants.items()
        if v.get("median_log_cpr") is not None
    )
    if not raw:
        return None
    title = "Cost against accuracy by variant"
    sub = (
        "Median log-CpR (lower is cheaper) against HR@3 (higher is better);"
        " orange: the point holding HELIOS-Full."
    )
    left, right, top, bottom = 70, WIDTH - 190, 70, 430
    xt = nice_ticks(min(r[1] for r in raw), max(r[1] for r in raw))
    yt = nice_ticks(max(0, min(r[2] for r in raw) - 0.05), 1)
    sx = _Scale(xt[0], xt[-1], left, right)
    sy = _Scale(yt[0], yt[-1], bottom, top)
    clusters: list[dict[str, Any]] = []
    for name, c, hr in raw:
        px, py = sx(c), sy(hr)
        home = next(
            (
                k
                for k in clusters
                if abs(k["x"] - px) <= MERGE_PX and abs(k["y"] - py) <= MERGE_PX
            ),
            None,
        )
        tip = f"{name}: log-CpR {c:.3f}, HR@3 {hr:.3f}"
        if home is None:
            clusters.append({"x": px, "y": py, "names": [name], "tips": [tip]})
        else:
            home["names"].append(name)
            home["tips"].append(tip)
    clusters.sort(key=lambda k: (FULL in k["names"], k["y"]))
    body = [
        _text(16, 26, title, size=16, weight="600"),
        _text(16, 46, sub, size=12, fill=TEXT_2),
    ]
    body += _y_axis(sy, yt, left, right)
    body += _x_axis(sx, xt, top, bottom)
    body.append(
        _text(
            (left + right) / 2,
            bottom + 34,
            "Median log-CpR",
            size=11,
            fill=TEXT_2,
            anchor="middle",
        )
    )
    body.append(_text(16, (top + bottom) / 2, "HR@3", size=11, fill=TEXT_2))
    line_h = 13
    blocks = [_wrap([_short(n) for n in k["names"]], 26) for k in clusters]
    label_y = [k["y"] + 4 for k in clusters]
    order = sorted(range(len(clusters)), key=lambda i: label_y[i])
    for a, b in itertools.pairwise(order):
        label_y[b] = max(label_y[b], label_y[a] + line_h * len(blocks[a]))
    for k, lines, ly in zip(clusters, blocks, label_y, strict=True):
        colour = SERIES_2 if FULL in k["names"] else SERIES_1
        body.append(
            _dot(
                k["x"],
                k["y"],
                fill=colour,
                stroke=SURFACE,
                r=5,
                tip="; ".join(k["tips"]),
            )
        )
        for j, line in enumerate(lines):
            body.append(_text(k["x"] + 9, ly + line_h * j, line, size=11))
    height = max(
        bottom + 50,
        max(ly + line_h * len(b) for ly, b in zip(label_y, blocks, strict=True)) + 10,
    )
    return _doc(height, body, title, sub)


def _wrap(words: Sequence[str], width: int) -> list[str]:
    """Join names with commas, breaking lines at about width characters."""
    lines: list[str] = []
    cur = ""
    for i, w in enumerate(words):
        piece = w + ("," if i < len(words) - 1 else "")
        if cur and len(cur) + 1 + len(piece) > width:
            lines.append(cur)
            cur = piece
        else:
            cur = f"{cur} {piece}".strip()
    if cur:
        lines.append(cur)
    return lines


def hr_by_variant(variants: Mapping[str, Mapping[str, Any]]) -> str | None:
    """HR@1 and HR@3 per variant, sorted by HR@3."""
    items = sorted(variants.items(), key=lambda kv: -float(kv[1]["hr_at_3"]))
    if not items:
        return None
    title = "Hit rate by variant"
    sub = "Share of runs with the root cause ranked first (HR@1) or in the top three (HR@3)."
    left, right, top = 150, WIDTH - 60, 86
    bar_h, inner, row_h = 9, 2, 30
    sx = _Scale(0, 1, left, right)
    bottom = top + row_h * len(items)
    body = [
        _text(16, 26, title, size=16, weight="600"),
        _text(16, 46, sub, size=12, fill=TEXT_2),
    ]
    for i, (label, colour) in enumerate((("HR@1", SERIES_1), ("HR@3", SERIES_2))):
        lx = left + i * 80
        body.append(
            f'<rect x="{lx}" y="58" width="10" height="10" rx="2" fill="{colour}"/>'
        )
        body.append(_text(lx + 16, 67, label, size=11))
    body += _x_axis(sx, nice_ticks(0, 1), top - 6, bottom)
    for i, (name, v) in enumerate(items):
        y = top + row_h * i + (row_h - 2 * bar_h - inner) / 2
        body.append(_text(left - 8, y + bar_h + 4, _short(name), size=11, anchor="end"))
        h1, h3 = float(v["hr_at_1"]), float(v["hr_at_3"])
        body.append(
            _bar(
                left,
                y,
                sx(h1) - left,
                bar_h,
                fill=SERIES_1,
                tip=f"{name} HR@1 {h1:.3f}",
            )
        )
        body.append(
            _bar(
                left,
                y + bar_h + inner,
                sx(h3) - left,
                bar_h,
                fill=SERIES_2,
                tip=f"{name} HR@3 {h3:.3f}",
            )
        )
        body.append(
            _text(sx(h3) + 6, y + 2 * bar_h + inner, f"{h3:.3f}", size=10, fill=TEXT_2)
        )
    return _doc(bottom + 30, body, title, sub)


# ── command line ────────────────────────────────────────────────────────────


def figures(
    analysis: Mapping[str, Any] | None, evidence: Mapping[str, Any] | None
) -> dict[str, str]:
    """File name to SVG text, for every figure its input allows."""
    out: dict[str, str] = {}
    if analysis is not None:
        label = str(analysis.get("label", "exploratory"))
        if label == "confirmatory":
            legend = (
                "Filled: rejected under the binding Holm reading. Hollow: not"
                " rejected. Grey: untestable."
            )
        else:
            legend = (
                f"Run labelled {label}: filled means below threshold (descriptive),"
                " never rejected. Grey: untestable."
            )
        rows = forest_rows(analysis)
        if rows:
            out["forest.svg"] = forest(
                rows,
                title="Families A and B: effects",
                subtitle=f"Mean difference with BCa 95% interval, one axis per measure; label {label}.",
                legend=legend,
            )
        erows = family_e_rows(analysis)
        if erows:
            out["forest_e.svg"] = forest(
                erows,
                title="Family E: exploratory effects",
                subtitle="Mean difference with BCa 95% interval; exploratory, never Holm.",
                legend="Exploratory: no decision is drawn.",
                decisions=False,
            )
    if evidence is not None:
        for name, svg in (
            ("reliability.svg", reliability(evidence.get("calibration") or {})),
            ("cost_accuracy.svg", cost_accuracy(evidence.get("variants") or {})),
            ("hr_by_variant.svg", hr_by_variant(evidence.get("variants") or {})),
        ):
            if svg is not None:
                out[name] = svg
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--analysis", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.analysis is None and args.evidence is None:
        parser.error("give --analysis, --evidence or both")
    analysis = (
        json.loads(args.analysis.read_text(encoding="utf-8")) if args.analysis else None
    )
    evidence = (
        json.loads(args.evidence.read_text(encoding="utf-8")) if args.evidence else None
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = figures(analysis, evidence)
    for name, svg in out.items():
        (args.out_dir / name).write_text(svg, encoding="utf-8")
    print(f"[figures] {len(out)} written to {args.out_dir}: {', '.join(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
