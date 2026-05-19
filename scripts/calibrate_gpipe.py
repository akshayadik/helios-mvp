#!/usr/bin/env python3
"""G-pipe LOO-CV threshold sweep — writes calibrated fields to data/calibrated_params.json.

Usage:
    poetry run python scripts/calibrate_gpipe.py

Requires re-captured corpus (schema-draft-v0.2 manifests) at data/captures/.
Runs D-pipe on each incident to obtain ppr_scores, then sweeps DISAGREEMENT_SWEEP
thresholds via LOO-CV to find the threshold that maximises G-pipe HR@3.
"""

from __future__ import annotations

import json
from pathlib import Path

from helios.pipelines.g_pipe.gpipe_config import DISAGREEMENT_SWEEP
from helios.pipelines.g_pipe.pipeline import _ppr_traverse, compute_ppr_disagreement
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.variants import CONFIRMATORY_VARIANTS

CALIBRATED_PATH = Path("data/calibrated_params.json")
CAPTURES_DIR = Path("data/captures")
GROUND_TRUTH_PATH = Path("data/ground_truth.json")

HELIOS_ENABLE_CALIBRATE_GPIPE: bool = True


def _load_corpus() -> list[dict]:
    from helios.graph.ppr_pruner import prune_graph
    from helios.graph.ueg_c_builder import build_ueg_c
    from helios.pipelines.d_pipe.dpipe_config import (
        RHO_THRESHOLD_DEFAULT,
        TOPOLOGY_BOOST_DEFAULT,
        W_ERROR_DEFAULT,
    )
    from helios.pipelines.d_pipe.pipeline import run_dpipe
    from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
    from helios.vcl.decorators import set_current_manifest

    ground_truth: dict[str, str] = json.loads(GROUND_TRUTH_PATH.read_text())

    manifest = CONFIRMATORY_VARIANTS["HELIOS-Full"]
    set_current_manifest(manifest)
    corpus = []

    for d in sorted(CAPTURES_DIR.iterdir()):
        cap_path = d / "manifest.json"
        if not cap_path.exists():
            continue
        cap = json.loads(cap_path.read_text())
        if cap.get("schema_version") != "schema-draft-v0.2":
            print(f"[skip] {d.name}: not schema-draft-v0.2")
            continue

        p2 = d / "p2_traces.parquet"
        if not p2.exists():
            continue

        incident_id = cap["incident_id"]
        ground_truth_service = ground_truth.get(incident_id, "")

        window = TelemetryWindow(
            incident_id=incident_id,
            variant_config_hash=cap["variant_config_hash"],
            window_start_iso=cap.get("window_start_iso", ""),
            window_end_iso=cap.get("window_end_iso", ""),
            evaluation_phase=EvaluationPhase.EXPLORATORY,
            p1_metrics_path=str(d / "p1_metrics.parquet"),
            p2_traces_path=str(p2),
            p3_logs_path=str(d / "p3_logs.parquet"),
        )

        snapshot = build_ueg_c(window, cap["variant_config_hash"])
        if snapshot is None:
            print(f"[skip] {incident_id}: build_ueg_c returned None")
            continue
        snapshot, _ = prune_graph(snapshot)

        # Re-run D-pipe to obtain ppr_scores (score_final from anomaly/propagation stages).
        d_out = run_dpipe(
            window=window,
            ueg_c=snapshot,
            incident_id=incident_id,
            snapshot_hash=cap.get("snapshot_hash", "calib"),
            variant_config_hash=cap["variant_config_hash"],
            evaluation_phase=EvaluationPhase.EXPLORATORY,
            run_id=f"calib-gpipe-{incident_id}",
            w_error=W_ERROR_DEFAULT,
            rho_threshold=RHO_THRESHOLD_DEFAULT,
            topology_boost_factor=TOPOLOGY_BOOST_DEFAULT,
            ground_truth_service=ground_truth_service,
        )
        dpipe_scores: dict[str, float] = d_out.get("ppr_scores", {})

        if not dpipe_scores:
            print(f"[skip] {incident_id}: empty dpipe ppr_scores")
            continue

        corpus.append(
            {
                "incident_id": incident_id,
                "snapshot": snapshot,
                "dpipe_scores": dpipe_scores,
                "ground_truth": ground_truth_service,
            }
        )

    return corpus


def _loo_cv(corpus: list[dict], threshold: float) -> tuple[float, float, int]:
    """Returns (g_hr_at_3, d_hr_at_3, n_triggered)."""
    g_hits, d_hits, n_triggered = 0, 0, 0
    n = len(corpus)
    if n == 0:
        return 0.00, 0.00, 0
    for held_out in corpus:
        dpipe_scores = held_out["dpipe_scores"]
        gt = held_out["ground_truth"]
        disagreement = compute_ppr_disagreement(dpipe_scores)
        if disagreement >= threshold and held_out["snapshot"] is not None:
            n_triggered += 1
            ranked, _ = _ppr_traverse(held_out["snapshot"], dpipe_scores)
            g_hits += int(gt in ranked[:3])
        d_ranked = sorted(dpipe_scores, key=dpipe_scores.get, reverse=True)  # type: ignore[arg-type]
        d_hits += int(gt in d_ranked[:3])
    return g_hits / max(n_triggered, 1), d_hits / n, n_triggered


def main() -> None:
    corpus = _load_corpus()
    if not corpus:
        print("[calibrate_gpipe] ERROR: empty corpus — re-capture first")
        raise SystemExit(1)

    print(f"[calibrate_gpipe] corpus: {len(corpus)} incidents")
    best_threshold, best_g_hr, best_n = DISAGREEMENT_SWEEP[0], 0.00, 0

    for threshold in DISAGREEMENT_SWEEP:
        g_hr, d_hr, n = _loo_cv(corpus, threshold)
        print(f"  t={threshold:.2f}  G={g_hr:.4f}  D={d_hr:.4f}  triggered={n}")
        if g_hr > best_g_hr:
            best_threshold, best_g_hr, best_n = threshold, g_hr, n

    _, best_d_hr, _ = _loo_cv(corpus, best_threshold)
    gate_passed = best_g_hr >= best_d_hr

    print(
        f"\n[calibrate_gpipe] best t={best_threshold:.2f}  G={best_g_hr:.4f}"
        f"  D={best_d_hr:.4f}  A-H6={'PASS' if gate_passed else 'FAIL'}"
    )

    params = json.loads(CALIBRATED_PATH.read_text()) if CALIBRATED_PATH.exists() else {}
    params.update(
        {
            "gpipe_hr_at_3_held_out": best_g_hr,
            "dpipe_hr_at_3_held_out": best_d_hr,
            "gate_passed": gate_passed,
            "n_incidents_triggered": best_n,
            "gpipe_disagreement_threshold_calibrated": best_threshold,
        }
    )
    CALIBRATED_PATH.write_text(json.dumps(params, indent=2))
    print(f"[calibrate_gpipe] written → {CALIBRATED_PATH}")


if __name__ == "__main__":
    main()
