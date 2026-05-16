"""LOO-CV calibration for D-pipe — 250-cell joint grid over 15 calibration incidents.

Usage:
    set -a; source .env; set +a
    poetry run python scripts/calibrate_dpipe.py \
        --captures data/captures \
        --ground-truth data/ground_truth.json \
        --output data/calibrated_params.json
"""

from __future__ import annotations

import argparse
import itertools
import json
import statistics
from pathlib import Path

from helios.graph.ppr_pruner import prune_graph
from helios.graph.ueg_c_builder import build_ueg_c
from helios.pipelines.d_pipe.dpipe_config import (
    INTEGRITY_RATE_GATE,
    PRUNER_EFFICACY_GATE,
    RHO_THRESHOLD_GRID,
    TOPOLOGY_BOOST_GRID,
    W_ERROR_GRID,
)
from helios.pipelines.d_pipe.pipeline import run_dpipe
from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.vcl import VCLFlag, get_variant, set_current_manifest  # noqa: F401

CALIBRATION_SET = [
    "s0-adhc-001",
    "s0-adhc-002",
    "s0-adhc-003",
    "s0-cart-001",
    "s0-cart-002",
    "s0-cart-003",
    "s0-imgsl-001",
    "s0-imgsl-002",
    "s0-imgsl-003",
    "s0-imgsl-004",
    "s0-pcat-001",
    "s0-pcat-002",
    "s0-pcat-003",
    "s0-pcat-004",
    "s0-pcat-005",
]
HR_AT_3_GATE = 0.25

# Per-grid-cell result entry: (hr_per_incident, cpr_per_incident, w_error, rho, boost)
ResultEntry = tuple[list[float], list[float], float, float, float]

# Fields written by the capture script that are not part of the schema.
_MANIFEST_EXTRA_KEYS: frozenset[str] = frozenset({"window_hash"})


def _load_window(captures: Path, incident_id: str) -> TelemetryWindow:
    manifest_path = captures / incident_id / "manifest.json"
    data = json.loads(manifest_path.read_text())
    # Strip keys not in TelemetryWindow (extra="forbid" would reject them).
    for k in _MANIFEST_EXTRA_KEYS:
        data.pop(k, None)
    return TelemetryWindow.model_validate(data)


def _evaluate_params(
    captures: Path,
    ground_truth: dict[str, str],
    w_error: float,
    rho_threshold: float,
    topology_boost_factor: float,
) -> tuple[list[float], list[float]]:
    """Return (per_incident_hr, per_incident_cpr) for the full calibration set."""
    hr_vals: list[float] = []
    cpr_vals: list[float] = []

    for i, incident_id in enumerate(CALIBRATION_SET):
        window = _load_window(captures, incident_id)
        gt_svc = ground_truth.get(incident_id)
        try:
            result = run_dpipe(
                window=window,
                ueg_c=None,
                incident_id=incident_id,
                snapshot_hash="calib",
                variant_config_hash="calib",
                evaluation_phase=EvaluationPhase.EXPLORATORY,
                run_id=f"calib-fold-{i}",
                w_error=w_error,
                rho_threshold=rho_threshold,
                topology_boost_factor=topology_boost_factor,
                ground_truth_service=gt_svc,
            )
            hr_vals.append(float(result.get("hr_at_3", 0)))
            cpr_val = result.get("cpr", 0.00)
            cpr_vals.append(float(cpr_val) if cpr_val == cpr_val else 0.00)
        except Exception:
            hr_vals.append(0.00)
            cpr_vals.append(0.00)

    return hr_vals, cpr_vals


def _fold_metrics(
    hr_vals: list[float], cpr_vals: list[float], indices: list[int]
) -> dict[str, float]:
    hr = [hr_vals[i] for i in indices]
    cpr = [cpr_vals[i] for i in indices]
    n = len(hr)
    return {
        "mean_hr": sum(hr) / n,
        "mean_cpr": sum(cpr) / n,
        "std_hr": statistics.stdev(hr) if n > 1 else 0.00,
        "min_cpr": min(cpr),
    }


def _tiebreak_key(
    m: dict[str, float], boost: float
) -> tuple[float, float, float, float, float]:
    return (-m["mean_hr"], -m["mean_cpr"], m["std_hr"], -m["min_cpr"], boost)


def _check_graph_gates(captures: Path, calibration_set: list[str]) -> None:
    """Check pruner efficacy and structural integrity gates for each calibration incident."""
    efficacy_pass = 0
    efficacy_fail = 0
    efficacy_skip = 0
    integrity_pass = 0
    integrity_fail = 0
    integrity_skip = 0

    for incident_id in calibration_set:
        window = _load_window(captures, incident_id)
        if window.p2_traces_path is None:
            efficacy_skip += 1
            integrity_skip += 1
            continue
        ueg_c = build_ueg_c(window, "calib")
        if ueg_c is None:
            efficacy_skip += 1
            integrity_skip += 1
            continue
        _pruned, prune_result = prune_graph(ueg_c)
        if prune_result.nodes_before == 0:
            efficacy_skip += 1
            integrity_skip += 1
            continue
        reduction = (
            prune_result.nodes_before - prune_result.nodes_after
        ) / prune_result.nodes_before
        if reduction >= PRUNER_EFFICACY_GATE:
            efficacy_pass += 1
        else:
            efficacy_fail += 1
            print(
                f"WARNING [{incident_id}]: pruner efficacy {reduction:.3f}"
                f" < gate {PRUNER_EFFICACY_GATE} -- deviation log entry may be required"
            )
        if prune_result.integrity_rate >= INTEGRITY_RATE_GATE:
            integrity_pass += 1
        else:
            integrity_fail += 1
            print(
                f"WARNING [{incident_id}]: integrity_rate {prune_result.integrity_rate:.3f}"
                f" < gate {INTEGRITY_RATE_GATE} -- deviation log entry may be required"
            )

    print(
        f"Graph gates summary — "
        f"efficacy: {efficacy_pass} PASS / {efficacy_fail} FAIL / {efficacy_skip} SKIP; "
        f"integrity: {integrity_pass} PASS / {integrity_fail} FAIL / {integrity_skip} SKIP"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--captures", type=Path, default=Path("data/captures"))
    parser.add_argument(
        "--ground-truth", type=Path, default=Path("data/ground_truth.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("data/calibrated_params.json")
    )
    args = parser.parse_args()

    ground_truth: dict[str, str] = json.loads(args.ground_truth.read_text())

    manifest = get_variant("HELIOS-Full")
    set_current_manifest(manifest)

    _check_graph_gates(args.captures, CALIBRATION_SET)

    grid = list(
        itertools.product(W_ERROR_GRID, RHO_THRESHOLD_GRID, TOPOLOGY_BOOST_GRID)
    )
    print(
        f"Evaluating {len(grid)} parameter combinations x {len(CALIBRATION_SET)} LOO folds ..."
    )

    # Build results matrix: for each (w, rho, boost), store per-incident (hr, cpr) lists.
    all_results: list[ResultEntry] = []
    for w_err, rho, boost in grid:
        hr_per, cpr_per = _evaluate_params(
            args.captures, ground_truth, w_err, rho, boost
        )
        all_results.append((hr_per, cpr_per, w_err, rho, boost))

    n_folds = len(CALIBRATION_SET)
    all_indices = list(range(n_folds))

    # In-sample selection: best cell on all 15 incidents (params to freeze for confirmatory study).
    best_entry = min(
        all_results,
        key=lambda e: _tiebreak_key(_fold_metrics(e[0], e[1], all_indices), e[4]),
    )
    best_hr_per, _, best_w, best_rho, best_boost = best_entry

    print(
        f"Best params: w_error={best_w}, rho_threshold={best_rho}, topology_boost={best_boost}"
    )

    # True LOO-CV: for each fold k, select best params on 14 training incidents, evaluate on k.
    loo_hr_vals: list[float] = []
    loo_cpr_vals: list[float] = []
    for k in all_indices:
        train_idx = [j for j in all_indices if j != k]

        def _train_key(
            e: ResultEntry, ti: list[int] = train_idx
        ) -> tuple[float, float, float, float, float]:
            return _tiebreak_key(_fold_metrics(e[0], e[1], ti), e[4])

        best_train = min(all_results, key=_train_key)
        loo_hr_vals.append(best_train[0][k])
        loo_cpr_vals.append(best_train[1][k])

    loo_mean_hr = sum(loo_hr_vals) / n_folds
    loo_mean_cpr = sum(loo_cpr_vals) / n_folds

    print(
        f"LOO-CV HR@3={loo_mean_hr:.4f},"
        f" In-sample HR@3={sum(best_hr_per) / n_folds:.4f}"
    )

    if loo_mean_hr < HR_AT_3_GATE:
        print(
            f"WARNING: LOO-CV HR@3 {loo_mean_hr:.4f} < gate {HR_AT_3_GATE}"
            " -- deviation log entry required"
        )

    calibrated = {
        "w_error": best_w,
        "rho_threshold": best_rho,
        "topology_boost_factor": best_boost,
        "loo_cv_mean_hr_at_3": loo_mean_hr,
        "loo_cv_mean_cpr": loo_mean_cpr,
        "in_sample_mean_hr_at_3": sum(best_hr_per) / n_folds,
        "grid_cells_evaluated": len(grid),
        "n_calibration_incidents": n_folds,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(calibrated, indent=2))
    print(f"Calibrated params written to {args.output}")


if __name__ == "__main__":
    main()
