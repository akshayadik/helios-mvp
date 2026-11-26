#!/usr/bin/env python3
"""Phase A (A5): evidence for C1 and the three innovations, from scored stores.

Usage (from the repository root):
    poetry run python scripts/phase_a_evidence.py \
        --db CAMPAIGN/results.duckdb [--db ...] [--campaign CAMPAIGN ...] \
        --out-json evidence.json --out-md evidence.md

Sections, all descriptive (no hypothesis test; A-H5 and E-H2 are the tests):

- **Evidence-grounded narratives:** narratives written by the model or filled
  by the template, claims drafted and rejected by the verifier, retries,
  H_struct.
- **Calibrated consensus confidence:** per MAHC variant, the confidence
  against the fused HR@3 hit (Brier, expected calibration error over equal
  bins, AUROC, reliability bins), and reliability per published state and
  its reason (CR-03 wording, ``helios.narrative.render.state_text``).
- **Cheap-first routing:** HELIOS-Full against HELIOS-noRouter on the cases
  both ran: L-pipe consulted, escalation, tokens, TTT, log-CpR, HR@1, HR@3.
- **C1 integrity (with --campaign):** exclusions by gate check, counts only.

Reads the harness-written tables (eval_run, eval_score, fusion_row,
narrative_row, result_row) and exclusion ledgers. It reads no ground truth and
no capture, prints counts and statistics only, never a case ID, and lives
outside the frozen paths.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

import duckdb
import numpy as np
from scipy.stats import rankdata

from helios.analysis.run import variant_names
from helios.narrative.render import state_text
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

__all__ = [
    "auroc",
    "brier",
    "calibration",
    "expected_calibration_error",
    "load_runs",
    "main",
    "render_markdown",
    "routing_savings",
]

N_BINS = 10
FULL = "HELIOS-Full"
UNIFORM = "HELIOS-noRouter"

_RUNS_SQL = """
select r.run_id, r.incident_id, r.variant_config_hash, r.state, r.confidence,
       r.llm_consulted, r.escalated, r.ttt_ms, r.log_cpr, r.narrative_claims,
       r.grounding_drafted, r.grounding_rejected, r.h_struct, r.h_fact,
       s.hr_at_1, s.hr_at_3, f.evidence_json
from eval_run r
join fusion_row f on f.run_id = r.run_id
join eval_score s on s.run_id = r.run_id and s.list_kind = 'fused'
     and s.source = f.method
where r.state <> 'BASELINE'
"""
_TOKENS_SQL = """
select run_id, sum(prompt_tokens + completion_tokens) from result_row group by run_id
"""
_NARR_SQL = """
select run_id, narrator, attempts, fallbacks, prompt_tokens + completion_tokens
from narrative_row
"""
_COLS = (
    "run_id",
    "incident_id",
    "variant_config_hash",
    "state",
    "confidence",
    "llm_consulted",
    "escalated",
    "ttt_ms",
    "log_cpr",
    "narrative_claims",
    "grounding_drafted",
    "grounding_rejected",
    "h_struct",
    "h_fact",
    "hr_at_1",
    "hr_at_3",
    "evidence_json",
)


# ── statistics ──────────────────────────────────────────────────────────────


def brier(conf: Sequence[float], hit: Sequence[int]) -> float | None:
    """Mean squared gap between stated confidence and the 0/1 outcome."""
    if not conf:
        return None
    c, h = np.asarray(conf, dtype=float), np.asarray(hit, dtype=float)
    return float(np.mean((c - h) ** 2))


def _bin_index(conf: Sequence[float], n_bins: int) -> np.ndarray:
    c = np.asarray(conf, dtype=float)
    idx: np.ndarray = np.minimum((c * n_bins).astype(int), n_bins - 1)
    return idx


def expected_calibration_error(
    conf: Sequence[float], hit: Sequence[int], n_bins: int = N_BINS
) -> float | None:
    """Weighted mean |stated - observed| over equal-width confidence bins."""
    if not conf:
        return None
    c, h = np.asarray(conf, dtype=float), np.asarray(hit, dtype=float)
    idx = _bin_index(conf, n_bins)
    gaps = [
        (idx == b).sum() * abs(c[idx == b].mean() - h[idx == b].mean())
        for b in np.unique(idx)
    ]
    return float(sum(gaps) / len(c))


def auroc(conf: Sequence[float], hit: Sequence[int]) -> float | None:
    """Probability that a hit carries higher confidence than a miss (ties
    count half), by the rank-sum identity; None without both classes."""
    h = np.asarray(hit, dtype=int)
    n_pos, n_neg = int(h.sum()), int(len(h) - h.sum())
    if n_pos == 0 or n_neg == 0:
        return None
    ranks = rankdata(np.asarray(conf, dtype=float))
    return float((ranks[h == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def reliability_bins(
    conf: Sequence[float], hit: Sequence[int], n_bins: int = N_BINS
) -> list[dict[str, Any]]:
    c, h = np.asarray(conf, dtype=float), np.asarray(hit, dtype=float)
    idx = _bin_index(conf, n_bins)
    return [
        {
            "bin_low": b / n_bins,
            "bin_high": (b + 1) / n_bins,
            "n": int((idx == b).sum()),
            "mean_confidence": float(c[idx == b].mean()),
            "observed_hr_at_3": float(h[idx == b].mean()),
        }
        for b in sorted(set(idx.tolist()))
    ]


# ── loading ─────────────────────────────────────────────────────────────────


def load_runs(dbs: Iterable[Path]) -> list[dict[str, Any]]:
    """HELIOS runs with their fused hit, routing, narrative and token fields."""
    names = variant_names()  # all 15 frozen variants
    runs: list[dict[str, Any]] = []
    for db in dbs:
        con = duckdb.connect(str(db), read_only=True)
        tokens = dict(con.execute(_TOKENS_SQL).fetchall())
        narr = {r[0]: r[1:] for r in con.execute(_NARR_SQL).fetchall()}
        for row in con.execute(_RUNS_SQL).fetchall():
            r = dict(zip(_COLS, row, strict=True))
            r["variant"] = names.get(str(r["variant_config_hash"]), "unknown")
            r["detail"] = json.loads(r.pop("evidence_json") or "{}")
            r["pipeline_tokens"] = int(tokens.get(r["run_id"]) or 0)
            n = narr.get(r["run_id"])
            r["narrator"], r["narr_attempts"], r["narr_fallbacks"], r["narr_tokens"] = (
                n if n is not None else (None, 0, 0, 0)
            )
            runs.append(r)
        con.close()
    return runs


# ── sections ────────────────────────────────────────────────────────────────


def _rate(num: float, den: float) -> float | None:
    return None if den == 0 else num / den


def narratives(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Per variant with narratives: who wrote them, verifier rejections, H_struct."""
    by: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in runs:
        if r["narrator"] is not None:
            by[r["variant"]].append(r)
    out: dict[str, Any] = {}
    for name, rs in sorted(by.items()):
        drafted = sum(int(r["grounding_drafted"] or 0) for r in rs)
        rejected = sum(int(r["grounding_rejected"] or 0) for r in rs)
        model = [r for r in rs if r["narrator"] == "llm"]
        hs = [float(r["h_struct"]) for r in rs if r["h_struct"] is not None]
        out[name] = {
            "narratives": len(rs),
            "written_by_model": len(model),
            "filled_by_template": sum(r["narrator"] == "template" for r in rs),
            "claims_shown": sum(int(r["narrative_claims"] or 0) for r in rs),
            "claims_drafted": drafted,
            "claims_rejected": rejected,
            "rejection_rate": _rate(rejected, drafted),
            "model_attempts_per_narrative": _rate(
                sum(int(r["narr_attempts"] or 0) for r in model), len(model)
            ),
            "slot_fallbacks": sum(int(r["narr_fallbacks"] or 0) for r in rs),
            "mean_h_struct": statistics.fmean(hs) if hs else None,
            "h_fact_scored": sum(r["h_fact"] is not None for r in rs),
        }
    return out


def calibration(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Per variant: calibration of P(root cause in top 3) where a confidence
    exists, and reliability per published state and reason (CR-03)."""
    by: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in runs:
        by[r["variant"]].append(r)
    out: dict[str, Any] = {}
    for name, rs in sorted(by.items()):
        scored = [r for r in rs if r["confidence"] is not None]
        states: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for r in rs:
            states[state_text(r)].append(r)
        entry: dict[str, Any] = {
            "runs": len(rs),
            "with_confidence": len(scored),
            "by_state": {
                k: {
                    "n": len(v),
                    "hr_at_1": statistics.fmean(int(x["hr_at_1"]) for x in v),
                    "hr_at_3": statistics.fmean(int(x["hr_at_3"]) for x in v),
                }
                for k, v in sorted(states.items())
            },
        }
        if scored:
            conf = [float(r["confidence"]) for r in scored]
            hit = [int(r["hr_at_3"]) for r in scored]
            entry.update(
                {
                    "mean_confidence": statistics.fmean(conf),
                    "observed_hr_at_3": statistics.fmean(hit),
                    "brier": brier(conf, hit),
                    "ece": expected_calibration_error(conf, hit),
                    "auroc": auroc(conf, hit),
                    "bins": reliability_bins(conf, hit),
                }
            )
        out[name] = entry
    return out


def _median(xs: Sequence[float]) -> float | None:
    return statistics.median(xs) if xs else None


def _side(rs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "llm_consulted_share": statistics.fmean(bool(r["llm_consulted"]) for r in rs),
        "escalated_share": statistics.fmean(bool(r["escalated"]) for r in rs),
        "pipeline_tokens": sum(int(r["pipeline_tokens"]) for r in rs),
        "median_ttt_ms": _median(
            [float(r["ttt_ms"]) for r in rs if r["ttt_ms"] is not None]
        ),
        "median_log_cpr": _median(
            [float(r["log_cpr"]) for r in rs if r["log_cpr"] is not None]
        ),
        "hr_at_1": statistics.fmean(int(r["hr_at_1"]) for r in rs),
        "hr_at_3": statistics.fmean(int(r["hr_at_3"]) for r in rs),
    }


def routing_savings(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """HELIOS-Full (cheap-first routing) against HELIOS-noRouter (uniform) on
    the cases both ran."""
    full = {r["incident_id"]: r for r in runs if r["variant"] == FULL}
    uni = {r["incident_id"]: r for r in runs if r["variant"] == UNIFORM}
    cases = sorted(full.keys() & uni.keys())
    if not cases:
        return {"cases": 0}
    a = _side([full[c] for c in cases])
    b = _side([uni[c] for c in cases])
    return {
        "cases": len(cases),
        FULL: a,
        UNIFORM: b,
        "tokens_saved_share": _rate(
            b["pipeline_tokens"] - a["pipeline_tokens"], b["pipeline_tokens"]
        ),
        "hr_at_1_change": a["hr_at_1"] - b["hr_at_1"],
        "hr_at_3_change": a["hr_at_3"] - b["hr_at_3"],
    }


def integrity(campaigns: Iterable[Path]) -> dict[str, Any]:
    """Exclusions per campaign (counts only): the final event of each run key
    in ``campaign_log.jsonl`` by gate check (a run carried from an earlier
    campaign keeps its exclusion there), and the entries of the campaign's
    own exclusion ledger."""
    counts: Counter[str] = Counter()
    ledger_entries = 0
    keys = 0
    for d in campaigns:
        last: dict[str, Mapping[str, Any]] = {}
        log = d / "campaign_log.jsonl"
        if log.exists():
            for line in log.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    event = json.loads(line)
                    if event.get("event") != "started":
                        last[str(event.get("key"))] = event
        keys += len(last)
        for event in last.values():
            if event.get("event") == "excluded":
                counts[str(event.get("gate_check", "unknown"))] += 1
        ledger = d / "exclusion_ledger.jsonl"
        if ledger.exists():
            ledger_entries += sum(
                1 for x in ledger.read_text(encoding="utf-8").splitlines() if x.strip()
            )
    return {
        "run_keys": keys,
        "exclusions": sum(counts.values()),
        "by_gate_check": dict(sorted(counts.items())),
        "ledger_entries_in_these_campaigns": ledger_entries,
    }


# ── output ──────────────────────────────────────────────────────────────────


def _f(x: Any, digits: int = 3) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:.{digits}f}"
    return str(x)


def _pct(x: Any) -> str:
    return "—" if x is None else f"{float(x):.1%}"


def _table(header: Sequence[str], rows: Iterable[Sequence[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(header) + " |",
        "|" + "|".join("---" for _ in header) + "|",
    ]
    return lines + ["| " + " | ".join(_f(c) for c in row) + " |" for row in rows]


def _narrative_lines(ev: Mapping[str, Any]) -> list[str]:
    return _table(
        [
            "Variant",
            "Narratives",
            "By model",
            "By template",
            "Claims drafted",
            "Rejected",
            "Rejection rate",
            "Model attempts / narrative",
            "Slot fallbacks",
            "Mean H_struct",
        ],
        [
            [
                k,
                v["narratives"],
                v["written_by_model"],
                v["filled_by_template"],
                v["claims_drafted"],
                v["claims_rejected"],
                _pct(v["rejection_rate"]),
                v["model_attempts_per_narrative"],
                v["slot_fallbacks"],
                v["mean_h_struct"],
            ]
            for k, v in ev["narratives"].items()
        ],
    )


def _calibration_lines(ev: Mapping[str, Any]) -> list[str]:
    cal = {k: v for k, v in ev["calibration"].items() if v["with_confidence"]}
    lines = _table(
        [
            "Variant",
            "Runs",
            "Mean confidence",
            "Observed HR@3",
            "Brier",
            "ECE",
            "AUROC",
        ],
        [
            [
                k,
                v["with_confidence"],
                v.get("mean_confidence"),
                v.get("observed_hr_at_3"),
                v.get("brier"),
                v.get("ece"),
                v.get("auroc"),
            ]
            for k, v in cal.items()
        ],
    )
    if FULL in cal:
        lines += ["", f"**{FULL}: reliability bins**", ""]
        lines += _table(
            ["Confidence bin", "n", "Mean confidence", "Observed HR@3"],
            [
                [
                    f"{b['bin_low']:.1f} to {b['bin_high']:.1f}",
                    b["n"],
                    b["mean_confidence"],
                    b["observed_hr_at_3"],
                ]
                for b in cal[FULL]["bins"]
            ],
        )
    lines += ["", "**Reliability by published state and reason (CR-03)**", ""]
    lines += _table(
        ["Variant", "State (reader wording)", "n", "HR@1", "HR@3"],
        [
            [k, s, d["n"], d["hr_at_1"], d["hr_at_3"]]
            for k, v in ev["calibration"].items()
            for s, d in v["by_state"].items()
        ],
    )
    return lines


def _routing_lines(rs: Mapping[str, Any]) -> list[str]:
    if not rs.get("cases"):
        return ["HELIOS-Full and HELIOS-noRouter share no case."]
    keys: list[tuple[str, str, Callable[[Any], str]]] = [
        ("llm_consulted_share", "L-pipe consulted", _pct),
        ("escalated_share", "Escalated", _pct),
        ("pipeline_tokens", "Pipeline tokens", _f),
        ("median_ttt_ms", "Median TTT (ms)", _f),
        ("median_log_cpr", "Median log-CpR", _f),
        ("hr_at_1", "HR@1", _f),
        ("hr_at_3", "HR@3", _f),
    ]
    lines = [f"Paired cases: {rs['cases']}.", ""]
    lines += _table(
        ["Measure", FULL, UNIFORM],
        [[label, fn(rs[FULL][k]), fn(rs[UNIFORM][k])] for k, label, fn in keys],
    )
    return [
        *lines,
        "",
        f"Tokens saved by routing: {_pct(rs['tokens_saved_share'])}; "
        f"HR@1 change {rs['hr_at_1_change']:+.3f}; "
        f"HR@3 change {rs['hr_at_3_change']:+.3f}.",
    ]


def render_markdown(ev: Mapping[str, Any]) -> str:
    lines = [
        "# Innovation and C1 evidence (A5)",
        "",
        "Descriptive only: no test and no Holm decision here. "
        f"Source: {', '.join(ev['sources'])}.",
        "",
        "## Evidence-grounded narratives",
        "",
        *_narrative_lines(ev),
        "",
        "## Calibrated consensus confidence",
        "",
        *_calibration_lines(ev),
        "",
        "## Cheap-first routing",
        "",
        *_routing_lines(ev["routing"]),
    ]
    it = ev.get("integrity")
    if it is not None:
        lines += [
            "",
            "## C1 integrity: exclusions",
            "",
            f"Run keys: {it['run_keys']}; excluded: {it['exclusions']}; ledger "
            f"entries in these campaigns: {it['ledger_entries_in_these_campaigns']}.",
            "",
        ]
        lines += _table(["Gate check", "Exclusions"], it["by_gate_check"].items())
    return "\n".join(lines).rstrip() + "\n"


def evidence(dbs: Sequence[Path], campaigns: Sequence[Path]) -> dict[str, Any]:
    runs = load_runs(dbs)
    return {
        "version": "evidence-v1",
        "label": "descriptive",
        "sources": [str(p) for p in dbs],
        "runs": len(runs),
        "narratives": narratives(runs),
        "calibration": calibration(runs),
        "routing": routing_savings(runs),
        "integrity": integrity(campaigns) if campaigns else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, action="append", required=True)
    parser.add_argument("--campaign", type=Path, action="append", default=[])
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, required=True)
    args = parser.parse_args(argv)
    ev = evidence(args.db, args.campaign)
    args.out_json.write_text(json.dumps(ev, indent=2) + "\n", encoding="utf-8")
    args.out_md.write_text(render_markdown(ev), encoding="utf-8")
    print(f"[evidence] {ev['runs']} HELIOS runs → {args.out_json}, {args.out_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
