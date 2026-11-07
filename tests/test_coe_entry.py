"""CoE entry builder (S2.7 design §5.1-5.2): steps, IDs, soft cap, refs."""

from __future__ import annotations

import copy
import hashlib
from typing import Any

import pytest

from helios.consensus.calibration import State
from helios.consensus.mahc import FusedVerdict
from helios.consensus.timing import Schedule
from helios.orchestrator.coe import ITEM_CAP, build_coe_entry, fusion_record, row_ref
from helios.schemas.telemetry import EvaluationPhase
from helios.schemas.verdict import PipelineName, PipelineVerdict, VerdictStatus
from helios.telemetry.trigger import TriggerRecord, TriggerSource
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.utils import canonical_json

STEP_ORDER = ["T", "R", "P:dpipe", "P:gpipe", "P:lpipe", "F", "G"]


def _verdict(
    pipeline: PipelineName, ranked: list[str], status: VerdictStatus | None = None
) -> PipelineVerdict:
    return PipelineVerdict(
        run_id="run-1",
        incident_id="inc-1",
        variant_config_hash="h" * 64,
        snapshot_hash="s" * 64,
        pipeline=pipeline,
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        status=status or (VerdictStatus.RANKED if ranked else VerdictStatus.ABSTAINED),
        ranked_candidates=ranked,
        candidate_scores={s: 1 / (i + 2) for i, s in enumerate(ranked)},
        mu=0.4 if ranked else None,
        sigma=0.3 if ranked else None,
        latency_ms=12.5,
    )


def _dpipe_evidence() -> dict[str, Any]:
    return {
        "services": [
            {
                "service": "cart",
                "error": 4.2,
                "latency": 1.5,
                "resource": 0.3,
                "score": 0.8,
                "final": 0.9,
                "levels": {
                    "latency": {"before": 120.0, "after": 900.0, "unit": "ms"},
                },
            },
            {
                "service": "ad",
                "error": None,
                "latency": None,
                "resource": None,
                "score": 0.1,
                "final": 0.1,
            },
        ]
    }


def _gpipe_evidence() -> dict[str, Any]:
    return {
        "ranker": "learned",
        "features": True,
        "suspects": [
            {
                "service": "cart",
                "wait_from": {"frontend": 0.7},
                "leads": ["checkout"],
                "ghost_edges": [],
                "self_shift": 1.5,
            }
        ],
    }


def _lpipe_evidence(n_lines: int = 3, cite: str = "L2") -> dict[str, Any]:
    lines = [[f"L{i}", "cart", f"error line {i}"] for i in range(1, n_lines + 1)]
    return {
        "k": 1,
        "digests": {"log": {"lines": lines, "cut": False}, "metric": None},
        "workers": {
            "log": {
                "ranked": ["cart"],
                "claims": {"cart": [["errors rise after trigger", [cite]]]},
                "dropped": None,
                "raw": "RAW MODEL TEXT",
                "cache_hit": True,
                "wall_ms": 900.0,
                "produced_output": True,
                "invalid_output": False,
            },
            "metric": {
                "ranked": [],
                "claims": {},
                "dropped": "no_digest",
                "raw": None,
                "cache_hit": False,
                "wall_ms": 0.0,
                "produced_output": False,
                "invalid_output": False,
            },
        },
    }


def _fused(ranked: tuple[str, ...] = ("cart", "ad")) -> FusedVerdict:
    return FusedVerdict(
        method="mahc",
        ranked=ranked,
        scores={s: 0.5 / (i + 1) for i, s in enumerate(ranked)},
        confidence=0.91 if ranked else None,
        fused_sigma=0.2 if ranked else None,
        state=State.CONFIRMED if ranked else State.PROVISIONAL,
        schedule=Schedule(
            first_ms=30000.0,
            first_pipelines=("dpipe",),
            terminal_ms=41000.0,
            non_converged=False,
        ),
        first_ranked=ranked,
        evidence={"signal": "error", "weights": {"dpipe": 0.6}},
    )


def _build(**over: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "run_id": "run-1",
        "incident_id": "inc-1",
        "variant_config_hash": "h" * 64,
        "snapshot_hash": "s" * 64,
        "evaluation_phase": "exploratory",
        "parameter_hashes": {"detector": "d" * 64, "mahc": "m" * 64},
        "trigger": TriggerRecord(
            incident_id="inc-1",
            trigger_time_s=120.0,
            suspects=("cart",),
            context=("frontend",),
            source=TriggerSource.THRESHOLD,
            detector_hash="d" * 64,
        ),
        "signal": "error",
        "window_start": "2026-10-28T14:42:23+00:00",
        "window_end": "2026-10-28T14:56:23+00:00",
        "routing": {"ran": True, "gate_value": 0.31, "threshold": 0.2},
        "verdicts": [
            _verdict(PipelineName.DPIPE, ["cart", "ad"]),
            _verdict(PipelineName.GPIPE, ["cart"]),
            _verdict(PipelineName.LPIPE, ["ad", "cart"]),
        ],
        "evidence": {
            "dpipe": _dpipe_evidence(),
            "gpipe": _gpipe_evidence(),
            "lpipe": _lpipe_evidence(),
        },
        "h_struct": {"outputs": 1, "failed": 0, "structural_zero": False},
        "fused": _fused(),
        "gate_outcome": "PASS",
    }
    kwargs.update(over)
    return build_coe_entry(**kwargs)


def _items(entry: dict[str, Any]) -> list[dict[str, Any]]:
    return [i for step in entry["steps"] for i in step.get("items", [])]


def _strip_measured(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_measured(v) for k, v in obj.items() if k != "measured"}
    if isinstance(obj, list):
        return [_strip_measured(v) for v in obj]
    return obj


def test_steps_in_order_with_unique_ids() -> None:
    entry = _build()
    assert [s["id"] for s in entry["steps"]] == STEP_ORDER
    ids = [i["id"] for i in _items(entry)]
    assert len(ids) == len(set(ids))
    d_cart = {f"D:cart:{k}" for k in ("error", "latency", "resource", "propagation")}
    assert d_cart | {"D:cart:score", "D:cart:final"} <= set(ids)
    assert "D:ad:error" not in ids and "D:ad:propagation" not in ids
    prop = next(i for i in _items(entry) if i["id"] == "D:cart:propagation")
    assert prop["value"] == pytest.approx(0.1)
    assert {"G:cart:wait_from", "G:cart:leads", "G:cart:self_shift"} <= set(ids)
    assert {"L:log:L1", "L:log:L2", "L:log:claim1"} <= set(ids)
    claim = next(i for i in _items(entry) if i["id"] == "L:log:claim1")
    assert claim["cites"] == ["L:log:L2"] and claim["service"] == "cart"
    for item in _items(entry):
        assert {"id", "service", "text", "value"} <= set(item)
    lpipe = entry["steps"][4]
    assert lpipe["workers"]["metric"] == {"valid": False, "dropped": "no_digest"}
    assert lpipe["h_struct"] == {"outputs": 1, "failed": 0, "structural_zero": False}
    assert "RAW MODEL TEXT" not in canonical_json(entry)


def test_soft_cap_keeps_claims_and_cited_lines() -> None:
    entry = _build(
        evidence={
            "dpipe": _dpipe_evidence(),
            "gpipe": _gpipe_evidence(),
            "lpipe": _lpipe_evidence(n_lines=40, cite="L38"),
        }
    )
    items = entry["steps"][4]["items"]
    ids = [i["id"] for i in items]
    assert len(items) == ITEM_CAP
    assert "L:log:L38" in ids and "L:log:claim1" in ids
    assert "L:log:L39" not in ids and "L:log:L40" not in ids


def test_soft_cap_never_drops_claims_over_the_cap() -> None:
    ev = _lpipe_evidence(n_lines=40)
    ev["workers"]["log"]["claims"] = {
        "cart": [[f"claim {i}", [f"L{i}"]] for i in range(1, 36)]
    }
    entry = _build(evidence={"dpipe": _dpipe_evidence(), "gpipe": None, "lpipe": ev})
    ids = [i["id"] for i in entry["steps"][4]["items"]]
    assert len([i for i in ids if ":claim" in i]) == 35
    assert all(f"L:log:L{i}" in ids for i in range(1, 36))
    assert "L:log:L36" not in ids


def test_refs_match_rows() -> None:
    evidence = {
        "dpipe": _dpipe_evidence(),
        "gpipe": _gpipe_evidence(),
        "lpipe": _lpipe_evidence(),
    }
    verdicts = [
        _verdict(PipelineName.DPIPE, ["cart", "ad"]),
        _verdict(PipelineName.GPIPE, ["cart"]),
        _verdict(PipelineName.LPIPE, ["ad", "cart"]),
    ]
    fused = _fused()
    entry = _build(evidence=evidence, verdicts=verdicts, fused=fused)
    for step, verdict in zip(entry["steps"][2:5], verdicts, strict=True):
        name = verdict.pipeline.value
        assert step["refs"]["verdict"] == verdict.compute_decision_hash()
        stored = canonical_json(evidence[name])
        assert step["refs"]["evidence"] == hashlib.sha256(stored.encode()).hexdigest()
    assert entry["steps"][5]["refs"]["fusion"] == row_ref(
        fusion_record("run-1", "inc-1", "h" * 64, fused)
    )


def test_no_fused_list_still_builds() -> None:
    entry = _build(
        verdicts=[
            _verdict(PipelineName.DPIPE, []),
            _verdict(PipelineName.GPIPE, [], VerdictStatus.SKIPPED),
            _verdict(PipelineName.LPIPE, [], VerdictStatus.FAILED),
        ],
        evidence={"dpipe": {"services": []}},
        h_struct={"outputs": 0, "failed": 0, "structural_zero": False},
        fused=_fused(ranked=()),
        signal=None,
    )
    assert [s["id"] for s in entry["steps"]] == STEP_ORDER
    assert _items(entry) == []
    assert entry["steps"][1]["ran"] is True
    assert entry["steps"][4]["refs"]["evidence"] is None
    assert entry["steps"][5]["ranked"] == [] and entry["steps"][5]["disagree"] == []


def test_entry_has_no_ground_truth_keys() -> None:
    banned = {"root_cause", "fault", "inject", "injection", "label", "ground_truth"}

    def keys(obj: Any) -> set[str]:
        if isinstance(obj, dict):
            return set(obj) | set().union(*(keys(v) for v in obj.values()))
        if isinstance(obj, list):
            return set().union(set(), *(keys(v) for v in obj))
        return set()

    found = keys(_build())
    assert not {k for k in found if any(b in k.lower() for b in banned)}


def test_deterministic() -> None:
    a = _build()
    b = _build(
        verdicts=[
            v.model_copy(update={"latency_ms": 99.0})
            for v in [
                _verdict(PipelineName.DPIPE, ["cart", "ad"]),
                _verdict(PipelineName.GPIPE, ["cart"]),
                _verdict(PipelineName.LPIPE, ["ad", "cart"]),
            ]
        ]
    )
    assert a != b  # measured latency differs ...
    assert _strip_measured(a) == _strip_measured(b)  # ... nothing else does
    assert _build() == copy.deepcopy(a)


def test_d_items_carry_levels() -> None:
    items = {i["id"]: i for i in _items(_build())}
    latency = items["D:cart:latency"]
    assert (latency["before"], latency["after"], latency["unit"]) == (
        120.0,
        900.0,
        "ms",
    )
    assert "before" not in items["D:cart:error"]


def test_t_step_has_window_bounds() -> None:
    t = _build()["steps"][0]
    assert t["window_start"] == "2026-10-28T14:42:23+00:00"
    assert t["window_end"] == "2026-10-28T14:56:23+00:00"


# ── S2-BL-20 minors ──────────────────────────────────────────────────────────


def test_empty_evidence_has_no_ref_since_the_runner_stores_none() -> None:
    entry = _build(evidence={"dpipe": _dpipe_evidence(), "gpipe": {}, "lpipe": None})
    steps = {s["id"]: s for s in entry["steps"]}
    assert steps["P:gpipe"]["refs"]["evidence"] is None
    assert steps["P:lpipe"]["refs"]["evidence"] is None
    assert steps["P:dpipe"]["refs"]["evidence"] is not None


def test_verdict_row_ref_is_the_whole_row_hash() -> None:
    verdicts = [
        _verdict(PipelineName.DPIPE, ["cart", "ad"]),
        _verdict(PipelineName.GPIPE, ["cart"]),
        _verdict(PipelineName.LPIPE, ["ad", "cart"]),
    ]
    entry = _build(verdicts=verdicts)
    for step, verdict in zip(entry["steps"][2:5], verdicts, strict=True):
        assert step["measured"]["verdict_row"] == verdict.compute_verdict_hash()
        assert step["refs"]["verdict"] == verdict.compute_decision_hash()


def test_cites_outside_the_digest_are_counted() -> None:
    entry = _build(
        evidence={
            "dpipe": _dpipe_evidence(),
            "gpipe": _gpipe_evidence(),
            "lpipe": _lpipe_evidence(cite="L9"),
        }
    )
    (claim,) = [i for i in _items(entry) if i["id"].startswith("L:log:claim")]
    assert claim["cites"] == []
    assert claim["unknown_cites"] == 1
    ok = _build()
    (kept,) = [i for i in _items(ok) if i["id"].startswith("L:log:claim")]
    assert "unknown_cites" not in kept
