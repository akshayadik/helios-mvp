"""D-pipe coe_evidence (S2.7): a new output; ranking, mu, sigma and hash unchanged."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from helios.pipelines.d_pipe.params import load_dpipe_params
from helios.pipelines.d_pipe.pipeline import run_dpipe
from helios.schemas.telemetry import TelemetryWindow
from helios.schemas.verdict import PipelineVerdict
from helios.telemetry.trigger import detect, load_detector_params
from helios.vcl import (
    VCLFlag,  # noqa: F401 — flag-guard compliance
    get_variant,
    set_current_manifest,
)

REPO = Path(__file__).resolve().parents[3]

# Recorded on main before coe_evidence existed (2026-10-31): the 6th and 10th
# OTel build windows in directory order.
GOLDEN = {
    5: (
        ["shipping", "recommendation", "payment", "cart", "fraud-detection"],
        0.256321,
        0.809005,
        "8263ba0618f3ed9833dc1cda7f1cff5a2791de8afcf76c77a2e0e370f2e7355d",
    ),
    9: (
        ["cart", "checkout", "ad", "product-reviews", "currency"],
        0.757252,
        0.067625,
        "3b13ef620902cacdadd64da24123046eb9b5f9274255d472024e42615f0946ae",
    ),
}


@pytest.fixture(autouse=True)
def _manifest() -> None:
    set_current_manifest(get_variant("HELIOS-Full"))


def _run_build(index: int) -> dict[str, Any]:
    path = sorted((REPO / "data/otel/build_v3").glob("*/manifest.json"))[index]
    raw = json.loads(path.read_text())
    raw.pop("window_hash", None)
    raw.pop("snapshot_hash", None)
    window = TelemetryWindow(**raw)
    det, dp = load_detector_params(), load_dpipe_params()
    return run_dpipe(
        window=window,
        ueg_c=None,
        incident_id=window.incident_id,
        snapshot_hash="s" * 64,
        variant_config_hash="h" * 64,
        evaluation_phase=window.evaluation_phase,
        run_id="r",
        trigger=detect(window, det, root=REPO),
        evidence_ref=det.threshold,
        w_error=dp.w_error,
        w_resource=dp.w_resource,
        rho_threshold=dp.rho_threshold,
        topology_boost_factor=dp.topology_boost_factor,
    )


def test_coe_evidence_top5_fields() -> None:
    out = _run_build(9)
    services = out["coe_evidence"]["services"]
    assert [s["service"] for s in services] == out["ranked_candidates"][:5]
    for s in services:
        assert set(s) == {"service", "shift", "score", "final"}
        assert s["final"] == out["candidate_scores"][s["service"]]
        assert s["shift"] is None or isinstance(s["shift"], float)
    assert any(s["shift"] is not None for s in services)


@pytest.mark.parametrize("index", sorted(GOLDEN))
def test_ranking_mu_sigma_and_decision_hash_unchanged(index: int) -> None:
    ranked, mu, sigma, digest = GOLDEN[index]
    out = _run_build(index)
    assert out["ranked_candidates"][:5] == ranked
    assert out["mu"] == pytest.approx(mu, abs=1e-6)
    assert out["sigma"] == pytest.approx(sigma, abs=1e-6)
    verdict = PipelineVerdict.from_output({**out, "latency_ms": 1})
    assert verdict.compute_decision_hash() == digest
    bare = {k: v for k, v in out.items() if k != "coe_evidence"}
    assert (
        PipelineVerdict.from_output({**bare, "latency_ms": 1}).compute_decision_hash()
        == digest
    )


def test_abstained_has_empty_evidence(tmp_path: Path) -> None:
    import datetime as dt

    from helios.schemas.telemetry import EvaluationPhase

    window = TelemetryWindow(
        incident_id="inc-empty",
        variant_config_hash="a" * 64,
        window_start_iso=dt.datetime(2026, 1, 1, tzinfo=dt.UTC).isoformat(),
        window_end_iso=dt.datetime(2026, 1, 1, 0, 5, tzinfo=dt.UTC).isoformat(),
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        p1_metrics_path=None,
        p2_traces_path=None,
        p3_logs_path=None,
    )
    out = run_dpipe(
        window=window,
        ueg_c=None,
        incident_id="inc-empty",
        snapshot_hash="b" * 64,
        variant_config_hash="a" * 64,
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        run_id="run-001",
    )
    assert out["ranked_candidates"] == []
    assert out["coe_evidence"] == {"services": []}
