"""OTel fix B gate: does the memory trend rank email better? (entry 76, design O-c).

For each ``emailMemoryLeak`` case of OTel build v3, with the frozen trigger:
email's rank among the in-scope services by (a) the current resource channel
(memory inside it) and (b) the memory trend. Rank = 1 + the number of services
with a strictly larger value; last when email's value is zero. The channel
passes if (b) is strictly better than (a) in at least ``PASS_CASES`` of the
cases. Build data only; the rule was fixed before this tool first ran.

Writes ``docs/sprints/s3-routing/calibration/memory_gate.json`` (aggregates and
ranks by case position, no incident ID) and refuses to overwrite it: the gate
runs once.

Usage:
    set -a; source .env; set +a
    poetry run python bin/dpipe_memory_gate.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bin.log_deviation import load_key
from helios.evaluation.trigger_calibration import load_cases
from helios.pipelines.d_pipe.stages.a_metrics_parser import MetricsParser
from helios.pipelines.d_pipe.stages.b_anomaly_scorer import AnomalyScorer
from helios.telemetry.scope import in_scope
from helios.telemetry.trigger import detect, detector_hash, load_detector_params
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance
from helios.vcl.utils import canonical_json

if TYPE_CHECKING:
    from helios.evaluation.trigger_calibration import CalibrationCase

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT = Path("docs/sprints/s3-routing/calibration/memory_gate.json")
CORPUS = "otel_build_v3"
FAULT = "emailMemoryLeak"
ROOT = "email"
PASS_CASES = 5


def rank_of(values: dict[str, float], service: str) -> int:
    """1 + services strictly above; last when the service's value is zero."""
    own = values.get(service, 0)
    if own <= 0:
        return len(values)
    return 1 + sum(v > own for s, v in values.items() if s != service)


def case_ranks(case: CalibrationCase) -> dict[str, Any]:
    """Email's rank by the resource channel and by the memory trend."""
    detector = load_detector_params()
    window = case.window
    for attr in ("p1_metrics_path", "p2_traces_path", "p3_logs_path"):
        value = getattr(window, attr)
        if value is not None and not Path(value).is_absolute():
            window = window.model_copy(update={attr: str(REPO_ROOT / value)})
    trigger = detect(window, detector, root=REPO_ROOT)
    assert window.p1_metrics_path is not None
    parsed = MetricsParser().parse(pd.read_parquet(window.p1_metrics_path))
    scored = AnomalyScorer(w_error=0, w_resource=0, w_memory=0).score_split(
        parsed, split_s=trigger.trigger_time_s
    )
    legacy = AnomalyScorer(w_error=0, w_resource=0).score_split(
        parsed, split_s=trigger.trigger_time_s
    )
    scope = [s for s in parsed.p1_services if in_scope(s)]
    resource = {s: legacy.channels[s]["resource"] for s in scope}
    memory = {s: scored.channels[s]["memory"] for s in scope}
    a, b = rank_of(resource, ROOT), rank_of(memory, ROOT)
    return {
        "trigger_source": str(trigger.source),
        "services": len(scope),
        "resource_rank": a,
        "memory_rank": b,
        "memory_better": b < a,
    }


def main(argv: list[str] | None = None) -> int:
    del argv
    path = REPO_ROOT / REPORT
    if path.exists():
        print(f"[gate] {REPORT} exists; the gate runs once", file=sys.stderr)
        return 2
    detector = load_detector_params()
    if detector.provisional:
        print("[gate] the detector is provisional", file=sys.stderr)
        return 2
    cases = [
        c
        for c in load_cases(CORPUS, root=REPO_ROOT, key=load_key())
        if c.fault == FAULT
    ]
    rows = [case_ranks(c) for c in cases]
    better = sum(r["memory_better"] for r in rows)
    report = {
        "corpus": CORPUS,
        "fault": FAULT,
        "detector_hash": detector_hash(detector),
        "rule": f"memory rank strictly better in >= {PASS_CASES} of {len(rows)}",
        "cases": rows,
        "memory_better": better,
        "passes": len(rows) == 7 and better >= PASS_CASES,
    }
    text = json.dumps(json.loads(canonical_json(report)), indent=2, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8")
    for i, r in enumerate(rows, start=1):
        print(
            f"[gate] case {i}: resource rank {r['resource_rank']}, memory rank "
            f"{r['memory_rank']} of {r['services']} ({r['trigger_source']})"
        )
    print(
        f"[gate] memory better in {better}/{len(rows)}: {'PASS' if report['passes'] else 'FAIL'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
