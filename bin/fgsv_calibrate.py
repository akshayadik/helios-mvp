"""Calibrate FGSV lite on build data (S4.6, design s4_4_7_tier2_design.md T-e/T-f).

For every build case (otel_build_v3, rcaeval_build; the pool is refused by
``load_cases``) the frozen trigger and the runner's graph (HELIOS-Full) are
built, and **every** in-scope service of the graph is treated as a proposed
target: the labelled root cause is a correct target, every other service a
wrong one. For each target the KS gate runs on clean data and under each
fidelity-break shift, and replay gives coverage and blast radius.

The grid of (coverage_min, blast_max) is scored by Youden's J over targets
that clear the gate and are actionable: the share of correct targets that
PASS minus the share of wrong targets that PASS. Ties go to the stricter
setting (higher coverage_min, then lower blast_max). Prints the selection and
writes aggregates only (no labels, no per-case rows) to
``docs/sprints/s4-product-eval-tooling/calibration/fgsv_calibration.json``.
It never writes the frozen parameter file.

Usage:
    set -a; source .env; set +a
    poetry run python bin/fgsv_calibrate.py [--workers 8]
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bin.log_deviation import load_key
from helios.actions import fgsv
from helios.evaluation.trigger_calibration import CalibrationCase, load_cases
from helios.orchestrator.runner import incident_graph as incident_graph
from helios.telemetry.scope import in_scope, scope_key
from helios.telemetry.trigger import detect, load_detector_params, service_scores
from helios.vcl import get_variant, set_current_manifest
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT = Path("docs/sprints/s4-product-eval-tooling/calibration/fgsv_calibration.json")
CORPORA_USED = ("otel_build_v3", "rcaeval_build")
VARIANT = "HELIOS-Full"
COVERAGE_GRID = (0.25, 0.4, 0.6, 0.75, 0.9, 1)
BLAST_GRID = (0, 1, 2, 3, 4, 5, 6, 8)
SHIFTS = (1, 2, 3)
_DIGITS = 4


def _absolute(case: CalibrationCase) -> Any:
    window = case.window
    for attr in ("p1_metrics_path", "p2_traces_path", "p3_logs_path"):
        value = getattr(window, attr)
        if value is not None and not Path(value).is_absolute():
            window = window.model_copy(update={attr: str(REPO_ROOT / value)})
    return window


def _case_rows(job: tuple[str, CalibrationCase]) -> dict[str, Any]:
    """Per-target gate and replay results of one case (labels used only to
    mark a target correct; nothing label-derived leaves this script)."""
    corpus, case = job
    manifest = get_variant(VARIANT)
    set_current_manifest(manifest)
    params = fgsv.load_fgsv_params()
    detector = load_detector_params()
    window = _absolute(case)
    trigger = detect(window, detector, root=REPO_ROOT)
    graph, _ = incident_graph(
        window, manifest, manifest.compute_variant_config_hash(), trigger
    )
    out: dict[str, Any] = {"corpus": corpus, "graph": graph is not None, "rows": []}
    if graph is None or not fgsv.has_structure(graph, graph.candidate_ids()[0]):
        return out
    scores = service_scores(window, detector.bucket_seconds, root=REPO_ROOT)
    first = int((trigger.trigger_time_s - scores.start_s) // detector.bucket_seconds)
    anomalous = fgsv.anomalous_services(
        scores.services, scores.z, first, detector.threshold
    )
    truth = scope_key(case.root_cause)
    for target in graph.candidate_ids():
        if not in_scope(target):
            continue
        pairs = fgsv.twin_pairs(
            window,
            [target, *fgsv.callers(graph, target)],
            trigger.trigger_time_s,
            params,
            root=REPO_ROOT,
        )
        gate = {
            str(k): fgsv.ks_gate(pairs, params, shift=k)["passed"] for k in (0, *SHIFTS)
        }
        result = fgsv.replay(graph, target, anomalous)
        out["rows"].append(
            {
                "correct": scope_key(target) == truth,
                "stateful": fgsv.stateful(target),
                "gate": gate,
                "coverage": result["coverage"],
                "blast": result["blast_radius"],
            }
        )
    return out


def _share(num: int, den: int) -> float | None:
    return round(num / den, _DIGITS) if den else None


def summarise(cases: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [r for c in cases for r in c["rows"]]
    by_corpus = {
        corpus: {
            "cases": sum(c["corpus"] == corpus for c in cases),
            "with_structure": sum(
                c["corpus"] == corpus and bool(c["rows"]) for c in cases
            ),
        }
        for corpus in CORPORA_USED
    }
    gate_rates = {}
    for k in ("0", *map(str, SHIFTS)):
        decided = [r for r in rows if r["gate"][k] is not None]
        gate_rates[k] = {
            "tested": len(decided),
            "no_twin_data": len(rows) - len(decided),
            "stale_share": _share(sum(not r["gate"][k] for r in decided), len(decided)),
        }
    eligible = [r for r in rows if r["gate"]["0"] and not r["stateful"]]
    correct = [r for r in eligible if r["correct"]]
    wrong = [r for r in eligible if not r["correct"]]
    grid: list[dict[str, Any]] = []
    for cov in COVERAGE_GRID:
        for blast in BLAST_GRID:
            ok_c = sum(r["coverage"] >= cov and r["blast"] <= blast for r in correct)
            ok_w = sum(r["coverage"] >= cov and r["blast"] <= blast for r in wrong)
            tpr = ok_c / len(correct) if correct else 0
            fpr = ok_w / len(wrong) if wrong else 0
            grid.append(
                {
                    "coverage_min": cov,
                    "blast_max": blast,
                    "correct_pass": _share(ok_c, len(correct)),
                    "wrong_pass": _share(ok_w, len(wrong)),
                    "youden_j": round(tpr - fpr, _DIGITS),
                }
            )
    best = max(
        grid, key=lambda g: (g["youden_j"], g["coverage_min"], -int(g["blast_max"]))
    )
    return {
        "corpora": by_corpus,
        "targets": len(rows),
        "correct_targets": sum(r["correct"] for r in rows),
        "stateful_targets": sum(r["stateful"] for r in rows),
        "gate": gate_rates,
        "eligible": {"correct": len(correct), "wrong": len(wrong)},
        "grid": grid,
        "selected": best,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--report", type=Path, default=REPORT)
    args = ap.parse_args()
    key = load_key()
    jobs = [
        (corpus, case)
        for corpus in CORPORA_USED
        for case in load_cases(corpus, root=REPO_ROOT, key=key)
    ]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        cases = list(pool.map(_case_rows, jobs))
    params = fgsv.load_fgsv_params()
    summary = summarise(cases)
    report = {
        "params_used": {
            "alpha_ks": params.alpha_ks,
            "sample_seconds": params.sample_seconds,
            "min_samples": params.min_samples,
        },
        "variant": VARIANT,
        "shifts": list(SHIFTS),
        **summary,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    sel = summary["selected"]
    print(json.dumps({k: report[k] for k in ("corpora", "gate", "eligible")}, indent=1))
    print(
        f"selected coverage_min={sel['coverage_min']} blast_max={sel['blast_max']} "
        f"correct_pass={sel['correct_pass']} wrong_pass={sel['wrong_pass']} "
        f"J={sel['youden_j']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
