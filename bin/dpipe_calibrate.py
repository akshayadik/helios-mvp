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
    poetry run python bin/dpipe_calibrate.py --memory --report PATH

``--memory`` (OTel fix refit, entry 77) adds the w_memory settings and
reports the no-loss check against the current frozen setting: if the
selected setting has w_memory, its HR@3 on rcaeval_build and its hits on the
otel_build_v3 cases outside ``MEMORY_FAULT`` must be at least the current
setting's, or fix B is dropped. ``--report`` refuses to overwrite an existing
file other than the S2.1 report.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

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
from helios.pipelines.d_pipe.params import (
    DPipeParams,
    dpipe_params_hash,
    load_dpipe_params,
)
from helios.pipelines.d_pipe.pipeline import run_dpipe
from helios.pipelines.d_pipe.stages import b_anomaly_scorer
from helios.telemetry.trigger import (
    detect,
    detector_hash,
    load_detector_params,
)
from helios.vcl import get_variant, set_current_manifest
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance
from helios.vcl.utils import canonical_json

if TYPE_CHECKING:
    from collections.abc import Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT = Path("docs/sprints/s2-reasoning/s2_1_dpipe_calibration.json")
VARIANT = "HELIOS-Full"
MEMORY_FAULT = "emailMemoryLeak"
OTEL = "otel_build_v3"
RCAEVAL = "rcaeval_build"
_DIGITS = 6
_TREND = b_anomaly_scorer.memory_trend


def _memoised_trend() -> Callable[[list[float], np.ndarray], float]:
    """``memory_trend`` cached by series and split for one case: the trend does
    not depend on the weights, so the grid computes it once per series, not
    once per setting. Same values; running time only."""
    seen: dict[tuple[bytes, bytes], float] = {}

    def trend(series: list[float], before: np.ndarray) -> float:
        key = (np.asarray(series, dtype="float64").tobytes(), before.tobytes())
        if key not in seen:
            seen[key] = _TREND(series, before)
        return seen[key]

    return trend


def _case_hits(case: CalibrationCase, memory: bool = False) -> tuple[bool, list[int]]:
    """Whether the case has a graph, and HR@3 (0/1) for every grid setting."""
    # This worker, this case; the cached function has the same signature.
    b_anomaly_scorer.memory_trend = _memoised_trend()  # type: ignore[assignment]
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
    for p in dpipe_grid(memory=memory):
        # w_memory None (memory in the resource channel) is keyed as -1.
        mem = -1 if p.w_memory is None else p.w_memory
        key: tuple[float, ...] = (p.w_error, p.w_resource, mem)
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
                w_memory=p.w_memory,
                rho_threshold=p.rho_threshold,
                topology_boost_factor=p.topology_boost_factor,
            )
            ranked = list(out.get("ranked_candidates") or [])
            cache[key] = score_ranking(ranked, case.root_cause).hr_at_3
        hits.append(cache[key])
    return graph is not None, hits


def _otel_hits_by_fault(
    rows: list[list[int]], faults: list[str | None], i: int
) -> dict[str, int]:
    out: dict[str, int] = {}
    for row, fault in zip(rows, faults, strict=True):
        key = fault or "unknown"
        out[key] = out.get(key, 0) + row[i]
    return dict(sorted(out.items()))


def memory_check(
    grid: list[DPipeParams],
    hr3: dict[DPipeParams, dict[str, float]],
    hits: dict[str, list[list[int]]],
    selected: DPipeParams,
    current: DPipeParams,
    cases: dict[str, list[CalibrationCase]],
) -> dict[str, Any]:
    """The no-loss half of fix B's gate and the outcome (entry 77 (4)-(5))."""
    if current not in grid:
        raise ValueError("the current frozen setting is not in the grid")
    faults = [c.fault for c in cases[OTEL]]
    by_fault = {
        name: _otel_hits_by_fault(hits[OTEL], faults, grid.index(p))
        for name, p in (("selected", selected), ("current", current))
    }

    def outside(name: str) -> int:
        return sum(v for f, v in by_fault[name].items() if f != MEMORY_FAULT)

    no_loss = hr3[selected][RCAEVAL] >= hr3[current][RCAEVAL] and outside(
        "selected"
    ) >= outside("current")
    return {
        "current": {
            **current.as_dict(),
            "dpipe_params_hash": dpipe_params_hash(current),
            "hr_at_3": hr3[current],
        },
        "otel_hits_by_fault": by_fault,
        "otel_hits_outside_memory_fault": {
            "selected": outside("selected"),
            "current": outside("current"),
        },
        "selected_has_w_memory": selected.w_memory is not None,
        "no_loss": no_loss,
        "adopted": selected.w_memory is not None and no_loss,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--memory", action="store_true")
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args(argv)
    report_path = REPO_ROOT / args.report
    if args.memory and args.report == REPORT:
        print("[dpipe] --memory needs its own --report (S2.1's stays)", file=sys.stderr)
        return 2
    if args.report != REPORT and report_path.exists():
        print(f"[dpipe] {args.report} exists; refusing to overwrite", file=sys.stderr)
        return 2

    detector = load_detector_params()
    if detector.provisional:
        print("[dpipe] the detector is provisional; freeze it first", file=sys.stderr)
        return 2
    key = load_key()
    cases = {c: load_cases(c, root=REPO_ROOT, key=key) for c in CORPORA}
    grid = dpipe_grid(memory=args.memory)
    hits: dict[str, list[list[int]]] = {}
    graphs: dict[str, int] = {}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for corpus, items in cases.items():
            results = list(
                pool.map(_case_hits, items, [args.memory] * len(items), chunksize=2)
            )
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
        "results": [{**p.as_dict(), "hr_at_3": hr3[p]} for p in grid],
        "may_hr_at_3": may,
        "selected": {
            **selected.as_dict(),
            "dpipe_params_hash": dpipe_params_hash(selected),
            "hr_at_3": hr3[selected],
            "mean_hr_at_3": round(best, _DIGITS),
            "change_from_may": change_from_may(selected),
            "settings_at_best_mean": ties,
        },
    }
    if args.memory:
        report["memory_refit"] = memory_check(
            grid, hr3, hits, selected, load_dpipe_params(), cases
        )
    text = json.dumps(json.loads(canonical_json(report)), indent=2, sort_keys=True)
    report_path.write_text(text + "\n", encoding="utf-8")

    print(
        f"[dpipe] selected w_error {selected.w_error:g}, w_resource "
        f"{selected.w_resource:g}, rho {selected.rho_threshold:g}, boost "
        f"{selected.topology_boost_factor:g} ({ties} setting(s) at the best mean)"
    )
    for corpus, value in hr3[selected].items():
        base = f"; May values {may[corpus]:.3f}" if may else ""
        print(f"[dpipe]   {corpus}: HR@3 {value:.3f}{base}")
    if args.memory:
        check = report["memory_refit"]
        print(
            f"[dpipe] current setting: {check['current']['hr_at_3']}; "
            f"no-loss check {check['no_loss']}; fix B adopted: {check['adopted']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
