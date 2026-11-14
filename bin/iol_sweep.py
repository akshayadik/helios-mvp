"""E-H6 detection latency over the frozen severity ladder (S4.7, design T-h).

Replays a recorded self-telemetry history (a campaign's ``self/*.jsonl``,
written by HELIOS-Full with ``iol_self_telemetry`` on) run by run, exactly as
the runner reads it: before each run, the self partition of the earlier runs
is read by the frozen trigger rule. Each factor of the frozen ladder
(``data/frozen/iol_injection.json``) is injected from its frozen run, plus a
clean pass. Prints and writes counts only (no run or case IDs).

Usage:
    poetry run python bin/iol_sweep.py SELF_JSONL [--report PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helios.telemetry.self_telemetry import (
    HISTORY_RUNS,
    INJECTION_PROTOCOL_PATH,
    Injection,
    SelfTelemetry,
    detect_degradation,
    with_self_partition,
)
from helios.telemetry.trigger import load_detector_params
from helios.vcl import VCLFlag  # noqa: F401  # flag-guard compliance

REPORT = Path("docs/sprints/s4-product-eval-tooling/calibration/iol_eh6_sweep.json")


def first_detection(
    rows: list[dict[str, dict[str, float]]], inj: Injection | None
) -> dict[str, Any]:
    """The first run whose step S names a degraded component."""
    detector = load_detector_params()
    st = SelfTelemetry(injection=inj)
    for i, metrics in enumerate(rows):
        graph = with_self_partition(
            None, st.series(), incident_id="sweep", config_hash="-", captured_at_iso="-"
        )
        found = detect_degradation(
            graph, detector, first_run=max(0, len(st.records) - HISTORY_RUNS)
        )
        if found["degraded"]:
            return {"run": i, "component": found["degraded"]}
        st.record(str(i), metrics)
    return {"run": None, "component": None}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("self_jsonl", type=Path)
    ap.add_argument("--report", type=Path, default=REPORT)
    args = ap.parse_args()
    rows = [
        json.loads(line)["metrics"]
        for line in args.self_jsonl.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    protocol = json.loads(INJECTION_PROTOCOL_PATH.read_text(encoding="utf-8"))
    clean = first_detection(rows, None)
    ladder = []
    for factor in protocol["factors"]:
        inj = Injection(
            protocol["component"], protocol["metric"], protocol["from_run"], factor
        )
        hit = first_detection(rows, inj)
        ladder.append(
            {
                "factor": factor,
                "detected": hit["run"] is not None,
                "latency_runs": (
                    None if hit["run"] is None else hit["run"] - inj.from_run
                ),
                "component": hit["component"],
            }
        )
    report = {
        "runs": len(rows),
        "protocol": protocol,
        "clean_false_flag": clean["run"] is not None,
        "ladder": ladder,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
