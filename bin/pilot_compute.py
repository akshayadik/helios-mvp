#!/usr/bin/env python3
"""S5.3 campaign compute on a cold cache (design s5_3_pilot_design.md Q-e 2).

    poetry run python bin/pilot_compute.py --dir data/campaigns/s5_1/otel_build_v3 \
        --out docs/sprints/s5-integration-freeze/pilot/compute_otel_build_v3.json

The S5.1 first runs were mostly response-cache hits, so their wall times
understate what phase E costs on the pool, whose cache starts empty. The S5.5
determinism reruns bypassed the cache, so on the rerun cases they show live
model times. Per rerun case, the cold-cache cost of one phase E case is:

- the noRouter rerun's wall time (it runs first in a phase E case and makes
  every worker call live; the cache then shares them with later variants);
- for every other variant with a rerun: its wall time minus its live worker
  time (in phase E its worker calls are cache hits; its narrator stays live);
- for the variants without a rerun (no model call: D, G, noLLM): their
  first-run wall time, which no cache changes;
- for each baseline phase (binding and trigger time): the first-run wall time.

Wall times come from the campaign log (``started`` to ``passed``); live worker
times from the rerun store. Reads no ground truth; changes no run.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from helios.vcl import VCLFlag  # noqa: E402, F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

HELIOS_ENABLE_PILOT_COMPUTE: bool = True
FIRST_RUN = "HELIOS-noRouter"
POOL_CASES = 240
HELIOS_PHASES = ("confirmatory", "exploratory")
BASELINE_PHASES = ("baseline", "baseline_trigger")


def run_walls(log: Iterable[Mapping[str, Any]]) -> dict[str, tuple[float, str]]:
    """key -> (seconds from started to passed, run_id), passed runs only."""
    started: dict[str, float] = {}
    out: dict[str, tuple[float, str]] = {}
    for row in log:
        key, event = str(row.get("key", "")), row.get("event")
        if event == "started" and row.get("at") is not None:
            started[key] = float(row["at"])
        elif event == "passed" and key in started and row.get("at") is not None:
            out[key] = (float(row["at"]) - started[key], str(row["run_id"]))
    return out


def live_worker_s(evidence: Mapping[str, Any] | None) -> float:
    """Seconds spent in L-pipe worker calls that went to the model."""
    workers = (evidence or {}).get("workers") or {}
    return sum(
        float(w.get("wall_ms") or 0) / 1000
        for w in workers.values()
        if not w.get("cache_hit")
    )


def cold_case_costs(
    walls: Mapping[str, tuple[float, str]],
    fetch_rerun_evidence: Callable[[str], Mapping[str, Any] | None],
) -> dict[str, dict[str, float]]:
    """Per rerun case: HELIOS and baseline seconds on a cold cache."""
    by_case: dict[str, dict[str, tuple[float, str]]] = defaultdict(dict)
    for key, value in walls.items():
        phase, case, system = key.split("/", 2)
        by_case[case][f"{phase}/{system}"] = value
    out: dict[str, dict[str, float]] = {}
    for case, runs in sorted(by_case.items()):
        reruns = {k.split("/", 1)[1]: v for k, v in runs.items() if k[:6] == "rerun/"}
        if FIRST_RUN not in reruns:
            continue
        helios = reruns[FIRST_RUN][0]
        for system, (wall, run_id) in reruns.items():
            if system != FIRST_RUN and not system.startswith("BASELINE-"):
                helios += max(wall - live_worker_s(fetch_rerun_evidence(run_id)), 0)
        for key, (wall, _) in runs.items():
            phase, system = key.split("/", 1)
            if (
                phase in HELIOS_PHASES
                and system.startswith("HELIOS-")
                and system not in reruns
            ):
                helios += wall
        baselines = sum(
            wall
            for key, (wall, _) in runs.items()
            if key.split("/", 1)[0] in BASELINE_PHASES
        )
        out[case] = {"helios_s": helios, "baselines_s": baselines}
    return out


def _summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"median": None, "mean": None, "p90": None}
    ordered = sorted(values)
    return {
        "median": round(statistics.median(ordered), 1),
        "mean": round(statistics.fmean(ordered), 1),
        "p90": round(ordered[max(math.ceil(len(ordered) * 9 / 10) - 1, 0)], 1),
    }


def compute_report(costs: Mapping[str, Mapping[str, float]]) -> dict[str, Any]:
    helios = [c["helios_s"] for c in costs.values()]
    base = [c["baselines_s"] for c in costs.values()]
    h, b = _summary(helios), _summary(base)

    def hours(s: float | None) -> float | None:
        return None if s is None else round(s * POOL_CASES / 3600, 2)

    return {
        "cases": len(costs),
        "helios_s_per_case": h,
        "baselines_s_per_case": b,
        "pool_projection_h": {
            "cases": POOL_CASES,
            "helios_e1_e3": {
                "median": hours(h["median"]),
                "p90": hours(h["p90"]),
            },
            "baselines_e2": {"median": hours(b["median"]), "p90": hours(b["p90"])},
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--dir", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    if not HELIOS_ENABLE_PILOT_COMPUTE:
        print("pilot compute disabled", file=sys.stderr)
        return 1
    from helios.store.result_store import ResultStore

    log = [
        json.loads(line)
        for line in (args.dir / "campaign_log.jsonl").read_text().splitlines()
        if line.strip()
    ]
    rerun = ResultStore(args.dir / "rerun.duckdb")
    try:
        costs = cold_case_costs(
            run_walls(log), lambda r: rerun.fetch_evidence(r, "lpipe")
        )
    finally:
        rerun.close()
    report = compute_report(costs) | {"campaign": args.dir.name}
    text = json.dumps(report, indent=1, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    p = report["pool_projection_h"]
    print(
        f"{args.dir.name}: {report['cases']} cases; HELIOS "
        f"{report['helios_s_per_case']['median']} s/case median, baselines "
        f"{report['baselines_s_per_case']['median']} s/case; pool E1+E3 "
        f"{p['helios_e1_e3']['median']} h, E2 {p['baselines_e2']['median']} h"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
