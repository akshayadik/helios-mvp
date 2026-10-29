"""Recalibrate D-pipe on build data with the frozen detector (S2.1 Task 13).

Grid, objective and tie rule are in helios.evaluation.dpipe_calibration. Each
case is scored with the frozen trigger and the graph the runner builds
(``incident_graph``, HELIOS-Full); a window without a graph does not depend on
the propagation parameters, so it is scored once per pair of weights. Writes
``docs/sprints/s2-reasoning/s2_1_dpipe_calibration.json`` (aggregates only)
and prints the selected setting; it never writes the frozen parameter file.

Usage:
    set -a; source .env; set +a
    poetry run python bin/dpipe_calibrate.py [--workers 8]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bin.log_deviation import load_key
from helios.evaluation.dpipe_calibration import (
    MAY_PARAMS,
    change_from_may,
    dpipe_grid,
    select_dpipe,
)
from helios.evaluation.scoring import score_ranking
from helios.evaluation.trigger_calibration import (
    CORPORA,
    CalibrationCase,
    load_cases,
)
from helios.orchestrator.runner import incident_graph as incident_graph
from helios.pipelines.d_pipe.params import DPipeParams, dpipe_params_hash
from helios.pipelines.d_pipe.pipeline import run_dpipe
from helios.telemetry.trigger import (
    detect,
    detector_hash,
    load_detector_params,
)
from helios.vcl import get_variant, set_current_manifest
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance
from helios.vcl.utils import canonical_json

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT = Path("docs/sprints/s2-reasoning/s2_1_dpipe_calibration.json")
VARIANT = "HELIOS-Full"
_DIGITS = 6


def _case_hits(case: CalibrationCase) -> tuple[bool, list[int]]:
    """Whether the case has a graph, and HR@3 (0/1) for every grid setting."""
    manifest = get_variant(VARIANT)
    set_current_manifest(manifest)
    config_hash = manifest.compute_variant_config_hash()
    detector = load_detector_params()
    window = case.window
    for attr in ("p1_metrics_path", "p2_traces_path", "p3_logs_path"):
        value = getattr(window, attr)
        if value is not None and not Path(value).is_absolute():
            window = window.model_copy(update={attr: str(REPO_ROOT / value)})
    trigger = detect(window, detector, root=REPO_ROOT)
    graph, _seeds = incident_graph(window, manifest, config_hash, trigger)
    cache: dict[tuple[float, ...], int] = {}
    hits: list[int] = []
    for p in dpipe_grid():
        key: tuple[float, ...] = (p.w_error, p.w_resource)
        if graph is not None:
            key += (p.rho_threshold, p.topology_boost_factor)
        if key not in cache:
            out = run_dpipe(
                window=window,
                ueg_c=graph,
                incident_id=window.incident_id,
                snapshot_hash=window.compute_window_hash(),
                variant_config_hash=config_hash,
                evaluation_phase=window.evaluation_phase,
                run_id="dpipe-calibration",
                trigger=trigger,
                evidence_ref=detector.threshold,
                w_error=p.w_error,
                w_resource=p.w_resource,
                rho_threshold=p.rho_threshold,
                topology_boost_factor=p.topology_boost_factor,
            )
            ranked = list(out.get("ranked_candidates") or [])
            cache[key] = score_ranking(ranked, case.root_cause).hr_at_3
        hits.append(cache[key])
    return graph is not None, hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)

    detector = load_detector_params()
    if detector.provisional:
        print("[dpipe] the detector is provisional; freeze it first", file=sys.stderr)
        return 2
    key = load_key()
    cases = {c: load_cases(c, root=REPO_ROOT, key=key) for c in CORPORA}
    grid = dpipe_grid()
    hits: dict[str, list[list[int]]] = {}
    graphs: dict[str, int] = {}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for corpus, items in cases.items():
            results = list(pool.map(_case_hits, items, chunksize=2))
            graphs[corpus] = sum(g for g, _ in results)
            hits[corpus] = [h for _, h in results]
            print(
                f"[dpipe] {corpus}: {len(items)} cases, {graphs[corpus]} with a graph"
            )

    hr3: dict[DPipeParams, dict[str, float]] = {
        p: {
            corpus: round(statistics.mean(case[i] for case in rows), _DIGITS)
            for corpus, rows in hits.items()
        }
        for i, p in enumerate(grid)
    }
    selected = select_dpipe(hr3)
    best = statistics.mean(hr3[selected].values())
    ties = sum(statistics.mean(v.values()) == best for v in hr3.values())
    may = hr3.get(MAY_PARAMS)
    report: dict[str, Any] = {
        "detector_hash": detector_hash(detector),
        "variant": VARIANT,
        "cases": {c: len(v) for c, v in cases.items()},
        "cases_with_graph": graphs,
        "grid_size": len(grid),
        "results": [{**asdict(p), "hr_at_3": hr3[p]} for p in grid],
        "may_hr_at_3": may,
        "selected": {
            **asdict(selected),
            "dpipe_params_hash": dpipe_params_hash(selected),
            "hr_at_3": hr3[selected],
            "mean_hr_at_3": round(best, _DIGITS),
            "change_from_may": change_from_may(selected),
            "settings_at_best_mean": ties,
        },
    }
    text = json.dumps(json.loads(canonical_json(report)), indent=2, sort_keys=True)
    (REPO_ROOT / REPORT).write_text(text + "\n", encoding="utf-8")

    print(
        f"[dpipe] selected w_error {selected.w_error:g}, w_resource "
        f"{selected.w_resource:g}, rho {selected.rho_threshold:g}, boost "
        f"{selected.topology_boost_factor:g} ({ties} setting(s) at the best mean)"
    )
    for corpus, value in hr3[selected].items():
        base = f"; May values {may[corpus]:.3f}" if may else ""
        print(f"[dpipe]   {corpus}: HR@3 {value:.3f}{base}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
