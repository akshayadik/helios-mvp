#!/usr/bin/env python3
"""S5.3 per-system readings of a scored campaign (design s5_3_pilot_design.md §4).

    poetry run python bin/pilot_metrics.py --dir data/campaigns/s5_1/otel_build_v3 \
        --out docs/sprints/s5-integration-freeze/pilot/metrics_otel_build_v3.json

Per system (HELIOS variant or baseline, first runs only; reruns are S5.5's):
HR@1 and HR@3 of the fused list, median CpR (total and log), TTT, time to
narrative, and the determinism covariate (Q-d). Per narrating variant (L7):
how many narratives the model wrote or the template filled, and their tokens.
Reads the scored store only (eval_score, eval_run, narrative_row); calls no
model and changes nothing. Labelled exploratory build data.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from helios.vcl import VCLFlag  # noqa: E402, F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Sequence

HELIOS_ENABLE_PILOT_METRICS: bool = True
FIRST_RUN_PHASES = ("confirmatory", "exploratory", "baseline", "baseline_trigger")


def run_systems(log_lines: list[dict[str, Any]]) -> dict[str, str]:
    """run_id -> system for passed first runs (trigger-time baselines keep
    their own name, as the analysis does)."""
    out: dict[str, str] = {}
    for r in log_lines:
        if r.get("event") != "passed":
            continue
        phase, _, system = str(r.get("key", "")).split("/", 2)
        if phase not in FIRST_RUN_PHASES:
            continue
        out[str(r["run_id"])] = system + (
            " [trigger]" if phase == FIRST_RUN_PHASES[3] else ""
        )
    return out


def _med(values: Sequence[float | None]) -> float | None:
    v = [x for x in values if x is not None and not math.isnan(x)]
    return round(statistics.median(v), 3) if v else None


def _p90(values: Sequence[float | None]) -> float | None:
    v = sorted(x for x in values if x is not None)
    return round(v[max(math.ceil(len(v) * 9 / 10) - 1, 0)], 1) if v else None


def _mean(values: Sequence[float | None]) -> float | None:
    v = [x for x in values if x is not None]
    return round(statistics.fmean(v), 3) if v else None


def readings(
    systems: dict[str, str],
    scores: Sequence[tuple[str, float | None, float | None]],
    runs: list[tuple[Any, ...]],
    narratives: list[tuple[str, str, int, int]],
) -> dict[str, Any]:
    """scores: (run_id, hr_at_1, hr_at_3) of fused lists; runs: (run_id,
    cpr_total, log_cpr, ttt_ms, time_to_narrative_ms, nondeterministic);
    narratives: (run_id, narrator, prompt_tokens, completion_tokens)."""
    per: dict[str, dict[str, list[Any]]] = defaultdict(lambda: defaultdict(list))
    for run_id, h1, h3 in scores:
        if run_id in systems:
            per[systems[run_id]]["hr1"].append(h1)
            per[systems[run_id]]["hr3"].append(h3)
    nd: dict[str, Counter[str]] = defaultdict(Counter)
    for run_id, cpr, log_cpr, ttt, ttn, flag in runs:
        if run_id not in systems:
            continue
        s = per[systems[run_id]]
        s["cpr"].append(cpr)
        s["log_cpr"].append(log_cpr)
        s["ttt"].append(ttt)
        s["ttn"].append(ttn)
        nd[systems[run_id]][{True: "true", False: "false"}.get(flag, "null")] += 1
    table = {
        name: {
            "runs": len(v["hr3"]) or len(v["cpr"]),
            "hr_at_1": _mean(v["hr1"]),
            "hr_at_3": _mean(v["hr3"]),
            "cpr_total_median": _med(v["cpr"]),
            "log_cpr_median": _med(v["log_cpr"]),
            "ttt_ms_median": _med(v["ttt"]),
            "time_to_narrative_ms_median": _med(v["ttn"]),
            "nondeterministic": dict(nd[name]),
        }
        for name, v in sorted(per.items())
    }
    narr: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for run_id, narrator, pt, ct in narratives:
        if run_id in systems:
            narr[systems[run_id]][narrator].append(int(pt or 0) + int(ct or 0))
            if narrator == "llm":
                narr[systems[run_id]]["prompt"].append(int(pt or 0))
                narr[systems[run_id]]["completion"].append(int(ct or 0))
    l7 = {
        name: {
            "llm_narratives": len(v["llm"]),
            "template_narratives": len(v["template"]),
            "prompt_tokens_median": _med(v["prompt"]),
            "completion_tokens_median": _med(v["completion"]),
            "tokens_per_llm_narrative_p90": _p90(v["llm"]),
            "tokens_llm_total": sum(v["llm"]),
        }
        for name, v in sorted(narr.items())
    }
    return {"systems": table, "l7_narratives": l7}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--dir", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    if not HELIOS_ENABLE_PILOT_METRICS:
        print("pilot metrics disabled", file=sys.stderr)
        return 1
    import duckdb

    log = [
        json.loads(x)
        for x in (args.dir / "campaign_log.jsonl").read_text().splitlines()
        if x.strip()
    ]
    con = duckdb.connect(str(args.dir / "results.duckdb"), read_only=True)
    try:
        scores = con.execute(
            "select run_id, hr_at_1, hr_at_3 from eval_score where list_kind = 'fused'"
        ).fetchall()
        runs = con.execute(
            "select run_id, cpr_total, log_cpr, ttt_ms, time_to_narrative_ms,"
            " nondeterministic from eval_run"
        ).fetchall()
        narratives = con.execute(
            "select run_id, narrator, prompt_tokens, completion_tokens"
            " from narrative_row"
        ).fetchall()
    finally:
        con.close()
    report = readings(run_systems(log), scores, runs, narratives) | {
        "campaign": args.dir.name,
        "label": "exploratory build data",
    }
    text = json.dumps(report, indent=1, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(f"{args.dir.name}: {len(report['systems'])} systems")
    return 0


if __name__ == "__main__":
    sys.exit(main())
