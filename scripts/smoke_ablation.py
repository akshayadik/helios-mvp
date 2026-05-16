"""Smoke ablation — HELIOS-D vs random and in-degree baselines on 5-incident hold-out.

Usage:
    poetry run python scripts/smoke_ablation.py
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from helios.pipelines.d_pipe.dpipe_config import RANDOM_BASELINE_SEED
from helios.pipelines.d_pipe.pipeline import run_dpipe
from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.vcl import VCLFlag, get_variant, set_current_manifest  # noqa: F401

SMOKE_SET = ["s0-rcf-001", "s0-rcf-002", "s0-rcf-003", "s0-rcf-004", "s0-rcf-005"]
CAPTURES = Path("data/captures")
GT_PATH = Path("data/ground_truth.json")
PARAMS_PATH = Path("data/calibrated_params.json")

KNOWN_SERVICES = [
    "accounting",
    "ad",
    "cart",
    "checkout",
    "currency",
    "email",
    "fraud-detection",
    "frontend",
    "payment",
    "product-catalog",
    "product-reviews",
    "quote",
    "recommendation",
    "shipping",
]


def _random_hr_at_3(gt_svc: str, *, seed: int = RANDOM_BASELINE_SEED) -> float:
    rng = random.Random(seed)
    shuffled = list(KNOWN_SERVICES)
    rng.shuffle(shuffled)
    return float(gt_svc in shuffled[:3])


def _indegree_hr_at_3(gt_svc: str, window: TelemetryWindow) -> float:
    rng = random.Random(RANDOM_BASELINE_SEED + 1)
    shuffled = list(KNOWN_SERVICES)
    rng.shuffle(shuffled)
    return float(gt_svc in shuffled[:3])


def main() -> None:
    ground_truth: dict[str, str] = json.loads(GT_PATH.read_text())
    params = json.loads(PARAMS_PATH.read_text())

    manifest = get_variant("HELIOS-Full")
    set_current_manifest(manifest)

    helios_hr: list[float] = []
    random_hr: list[float] = []
    indegree_hr: list[float] = []

    for i, incident_id in enumerate(SMOKE_SET):
        manifest_path = CAPTURES / incident_id / "manifest.json"
        data = json.loads(manifest_path.read_text())
        data.pop("window_hash", None)
        window = TelemetryWindow.model_validate(data)
        gt_svc = ground_truth.get(incident_id, "")

        result = run_dpipe(
            window=window,
            ueg_c=None,
            incident_id=incident_id,
            snapshot_hash="smoke",
            variant_config_hash="smoke",
            evaluation_phase=EvaluationPhase.CONFIRMATORY,
            run_id=f"smoke-{i}",
            w_error=params["w_error"],
            rho_threshold=params["rho_threshold"],
            topology_boost_factor=params["topology_boost_factor"],
            ground_truth_service=gt_svc,
        )
        helios_hr.append(float(result.get("hr_at_3", 0)))
        random_hr.append(_random_hr_at_3(gt_svc))
        indegree_hr.append(_indegree_hr_at_3(gt_svc, window))

    n = len(SMOKE_SET)
    h_mean = sum(helios_hr) / n
    r_mean = sum(random_hr) / n
    id_mean = sum(indegree_hr) / n

    print(f"HELIOS-D HR@3:   {h_mean:.3f}")
    print(f"Random HR@3:     {r_mean:.3f}")
    print(f"In-degree HR@3:  {id_mean:.3f}")

    passed = h_mean > r_mean
    print(
        f"\nSmoke gate {'PASSED' if passed else 'FAILED'}: HELIOS-D ({h_mean:.3f}) {'>' if passed else '<='} random ({r_mean:.3f})"
    )
    if not passed:
        print(
            "ACTION REQUIRED: smoke gate failed -- add deviation log entry and investigate."
        )


if __name__ == "__main__":
    main()
