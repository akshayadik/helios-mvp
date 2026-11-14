"""What PII redaction would change on build data (S4.4, design T-c).

Renders every L-pipe worker prompt of every build case exactly as a run does
(frozen trigger, the window's services, aliases, digests) and runs the
redactor over it. Build corpora only (``otel_build_v3``, ``rcaeval_build``):
the pool is never read. No label is read. Prints and writes counts per rule
and per corpus, never a value or a case ID.

Usage:
    poetry run python bin/pii_scan.py [--workers 8] [--report PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helios.evaluation.trigger_calibration import CORPORA
from helios.pipelines.l_pipe import personas
from helios.pipelines.l_pipe.aliases import build_alias_map
from helios.privacy.redact import RULESET_ID, redact
from helios.schemas.telemetry import TelemetryWindow
from helios.telemetry.log_templates import read_window_logs
from helios.telemetry.scope import in_scope
from helios.telemetry.trigger import detect, load_detector_params, service_scores
from helios.vcl import VCLFlag  # noqa: F401  # flag-guard compliance

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT = Path("docs/sprints/s4-product-eval-tooling/calibration/pii_scan.json")
CORPORA_USED = ("otel_build_v3", "rcaeval_build")


def _windows(corpus: str) -> list[TelemetryWindow]:
    captures, manifest, _truth = (REPO_ROOT / p for p in CORPORA[corpus])
    order = json.loads(manifest.read_text(encoding="utf-8"))["case_order"]
    out = []
    for incident_id in order:
        raw = json.loads((captures / incident_id / "manifest.json").read_text())
        raw.pop("window_hash", None)
        raw.pop("snapshot_hash", None)
        out.append(TelemetryWindow(**raw))
    return out


def _scan(window: TelemetryWindow) -> dict[str, Any]:
    detector = load_detector_params()
    trigger = detect(window, detector, root=REPO_ROOT)
    services = service_scores(window, detector.bucket_seconds, root=REPO_ROOT).services
    candidates = [s for s in services if in_scope(s)]
    components = [s for s in services if not in_scope(s)]
    alias = build_alias_map(window.incident_id, candidates, components)
    counts: Counter[str] = Counter()
    prompts = changed = 0
    for persona in personas.PERSONAS:
        digest = persona.build(window, trigger, candidates, root=REPO_ROOT)
        if digest is None:
            continue
        prompt = personas.render_prompt(persona, digest, alias)
        result = redact(prompt, protected=services)
        prompts += 1
        changed += result.text != prompt
        counts.update(result.counts)
    # The raw log lines, for contrast: what the digests' templating removes
    # before a prompt is built.
    raw: Counter[str] = Counter()
    logs = read_window_logs(window, REPO_ROOT)
    if logs is not None:
        for body in logs["body"].astype(str):
            raw.update(redact(body, protected=services).counts)
    return {
        "prompts": prompts,
        "changed": changed,
        "counts": dict(counts),
        "raw_log_counts": dict(raw),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--report", type=Path, default=REPORT)
    args = ap.parse_args()
    report: dict[str, Any] = {"ruleset": RULESET_ID, "corpora": {}}
    for corpus in CORPORA_USED:
        windows = _windows(corpus)
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            rows = list(pool.map(_scan, windows))
        total: Counter[str] = Counter()
        raw: Counter[str] = Counter()
        for r in rows:
            total.update(r["counts"])
            raw.update(r["raw_log_counts"])
        report["corpora"][corpus] = {
            "cases": len(rows),
            "cases_changed": sum(r["changed"] > 0 for r in rows),
            "prompts": sum(r["prompts"] for r in rows),
            "prompts_changed": sum(r["changed"] for r in rows),
            "redactions_by_rule": dict(sorted(total.items())),
            "raw_log_matches_by_rule": dict(sorted(raw.items())),
            "cases_with_raw_matches": sum(bool(r["raw_log_counts"]) for r in rows),
        }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
