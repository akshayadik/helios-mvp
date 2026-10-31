"""Chain-of-Evidence ledger (S2.7 design; owner decisions C-a, C-b).

One entry per stored incident run: every decision in order (trigger, routing,
each pipeline, fusion, integrity gate) and the evidence behind it under one ID
namespace, so the S2.8 narrator cites one record and its grounding verifier
checks against it. Entries are HMAC-chained; after each entry the anchor (entry
count, head, digest of the whole file) is Ed25519-signed when the key is loaded
(``verify_public`` with the public key alone), else marked unsigned.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from helios.schemas.verdict import VerdictStatus
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.hmac_chain import HMACChainedLog
from helios.vcl.utils import canonical_json

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from helios.consensus.mahc import FusedVerdict
    from helios.schemas.verdict import PipelineVerdict
    from helios.telemetry.trigger import TriggerRecord

__all__ = ["ITEM_CAP", "CoELedger", "build_coe_entry", "fusion_record", "row_ref"]

# Items per pipeline in one entry (design §5.2). Soft: L-pipe claims and the
# lines they cite are always kept; the cap trims only uncited lines.
ITEM_CAP = 30
_DPIPE_TOP = 5
_PIPELINES = ("dpipe", "gpipe", "lpipe")

HELIOS_ENABLE_COE_LEDGER: bool = True


class CoELedger(HMACChainedLog):
    """Append-only CoE log for one orchestrator run."""

    REQUIRED_FIELDS: tuple[str, ...] = (
        "run_id",
        "incident_id",
        "variant_config_hash",
        "snapshot_hash",
        "evaluation_phase",
        "steps",
    )
    LOG_KIND = "coe"
    ANCHOR_ED25519 = True


def row_ref(row: Mapping[str, Any]) -> str:
    """SHA-256 of a stored row's canonical JSON (an evidence row's stored text)."""
    return hashlib.sha256(canonical_json(dict(row)).encode("utf-8")).hexdigest()


def fusion_record(
    run_id: str, incident_id: str, variant_config_hash: str, fused: FusedVerdict
) -> dict[str, Any]:
    """The fusion row as ``ResultStore.fetch_fusion`` returns it."""
    sched = fused.schedule
    return {
        "run_id": run_id,
        "incident_id": incident_id,
        "variant_config_hash": variant_config_hash,
        "method": fused.method,
        "ranked": list(fused.ranked),
        "scores": dict(fused.scores),
        "confidence": fused.confidence,
        "fused_sigma": fused.fused_sigma,
        "state": fused.state.value,
        "first_ms": float(sched.first_ms),
        "first_ranked": list(fused.first_ranked),
        "terminal_ms": None if sched.terminal_ms is None else float(sched.terminal_ms),
        "non_converged": bool(sched.non_converged),
        "evidence": dict(fused.evidence),
    }


def _item(item_id: str, service: str | None, text: str, value: Any) -> dict[str, Any]:
    return {"id": item_id, "service": service, "text": text, "value": value}


def _dpipe_items(evidence: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    items = []
    for s in (evidence or {}).get("services", [])[:_DPIPE_TOP]:
        svc = s["service"]
        for channel in ("error", "latency", "resource"):
            if s.get(channel) is not None:
                text = f"post-trigger {channel} shift (robust units)"
                items.append(_item(f"D:{svc}:{channel}", svc, text, s[channel]))
        items.append(_item(f"D:{svc}:score", svc, "pre-propagation score", s["score"]))
        if s["score"] is not None and s["final"] != s["score"]:
            adjustment = s["final"] - s["score"]
            text = "propagation adjustment to the score"
            items.append(_item(f"D:{svc}:propagation", svc, text, adjustment))
        items.append(_item(f"D:{svc}:final", svc, "final D-pipe score", s["final"]))
    return items[:ITEM_CAP]


_GPIPE_TEXT = {
    "wait_from": "wait share from callers after the trigger",
    "leads": "callers whose shift it leads",
    "ghost_edges": "call edges seen only after the trigger",
    "self_shift": "self-time shift",
}


def _gpipe_items(evidence: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    items = []
    for suspect in (evidence or {}).get("suspects", []):
        svc = suspect["service"]
        for feature, text in _GPIPE_TEXT.items():
            value = suspect.get(feature)
            if feature != "self_shift" and not value:
                continue
            items.append(_item(f"G:{svc}:{feature}", svc, text, value))
    return items[:ITEM_CAP]


def _lpipe_items(evidence: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Digest lines and worker claims; claims and cited lines survive the cap."""
    if not evidence:
        return []
    digests = evidence.get("digests") or {}
    workers = evidence.get("workers") or {}
    lines: dict[str, list[dict[str, Any]]] = {}
    claims: dict[str, list[dict[str, Any]]] = {}
    cited: set[str] = set()
    for worker in sorted(set(digests) | set(workers)):
        record = digests.get(worker) or {}
        lines[worker] = [
            _item(f"L:{worker}:{line_id}", svc, text, None)
            for line_id, svc, text in record.get("lines", [])
        ]
        known = {i["id"] for i in lines[worker]}
        claims[worker] = []
        by_service = (workers.get(worker) or {}).get("claims", {})
        for svc in sorted(by_service):
            for text, cites in by_service[svc]:
                ids = [f"L:{worker}:{c}" for c in cites if f"L:{worker}:{c}" in known]
                cited.update(ids)
                n = len(claims[worker]) + 1
                claim = _item(f"L:{worker}:claim{n}", svc, text, None)
                claims[worker].append({**claim, "cites": ids})
    required = sum(len(c) for c in claims.values()) + len(cited)
    budget = max(ITEM_CAP - required, 0)
    items = []
    for worker in lines:
        for line in lines[worker]:
            if line["id"] in cited:
                items.append(line)
            elif budget > 0:
                items.append(line)
                budget -= 1
        items.extend(claims[worker])
    return items


_ITEMS = {"dpipe": _dpipe_items, "gpipe": _gpipe_items, "lpipe": _lpipe_items}


def _pipeline_step(
    verdict: PipelineVerdict,
    evidence: Mapping[str, Any] | None,
    h_struct: Mapping[str, Any],
) -> dict[str, Any]:
    name = verdict.pipeline.value
    cost = verdict.cost
    decision = verdict.compute_decision_hash()
    step: dict[str, Any] = {
        "id": f"P:{name}",
        "status": verdict.status.value,
        "ranked": list(verdict.ranked_candidates),
        "mu": verdict.mu,
        "sigma": verdict.sigma,
        "decision_hash": decision,
        "cost": {
            "prompt_tokens": cost.prompt_tokens,
            "completion_tokens": cost.completion_tokens,
        },
        "measured": {"latency_ms": verdict.latency_ms, "cpu_ms": cost.cpu_ms},
        "items": _ITEMS[name](evidence),
        "refs": {
            "verdict": decision,
            "evidence": None if evidence is None else row_ref(evidence),
        },
    }
    if name == "lpipe":
        workers = (evidence or {}).get("workers") or {}
        step["workers"] = {
            w: {"valid": r.get("dropped") is None, "dropped": r.get("dropped")}
            for w, r in sorted(workers.items())
        }
        step["h_struct"] = dict(h_struct)
    return step


def build_coe_entry(
    *,
    run_id: str,
    incident_id: str,
    variant_config_hash: str,
    snapshot_hash: str,
    evaluation_phase: str,
    parameter_hashes: Mapping[str, str],
    trigger: TriggerRecord,
    signal: str | None,
    routing: Mapping[str, Any],
    verdicts: Sequence[PipelineVerdict],
    evidence: Mapping[str, Mapping[str, Any] | None],
    h_struct: Mapping[str, Any],
    fused: FusedVerdict,
    gate_outcome: str,
) -> dict[str, Any]:
    """One CoE entry (design §5.1): decisions T, R, P:*, F, G in order.

    Timing is under ``measured`` keys, outside rerun equality; no ground-truth
    field is read or written.
    """
    by_name = {v.pipeline.value: v for v in verdicts}
    top = fused.ranked[0] if fused.ranked else None
    disagree = sorted(
        v.pipeline.value
        for v in verdicts
        if top is not None
        and v.status == VerdictStatus.RANKED
        and v.ranked_candidates
        and v.ranked_candidates[0] != top
    )
    sched = fused.schedule
    steps: list[dict[str, Any]] = [
        {
            "id": "T",
            "source": trigger.source.value,
            "trigger_time_s": trigger.trigger_time_s,
            "suspects": list(trigger.suspects),
            "context": list(trigger.context),
            "signal": signal,
            "detector_hash": trigger.detector_hash,
        },
        {"id": "R", **dict(routing)},
    ]
    steps += [
        _pipeline_step(by_name[name], evidence.get(name), h_struct)
        for name in _PIPELINES
    ]
    steps.append(
        {
            "id": "F",
            "method": fused.method,
            "ranked": list(fused.ranked),
            "scores": dict(fused.scores),
            "confidence": fused.confidence,
            "fused_sigma": fused.fused_sigma,
            "state": fused.state.value,
            "first_ranked": list(fused.first_ranked),
            "non_converged": sched.non_converged,
            "disagree": disagree,
            "detail": dict(fused.evidence),
            "measured": {"first_ms": sched.first_ms, "terminal_ms": sched.terminal_ms},
            "refs": {
                "fusion": row_ref(
                    fusion_record(run_id, incident_id, variant_config_hash, fused)
                )
            },
        }
    )
    steps.append({"id": "G", "outcome": gate_outcome})
    return {
        "run_id": run_id,
        "incident_id": incident_id,
        "variant_config_hash": variant_config_hash,
        "snapshot_hash": snapshot_hash,
        "evaluation_phase": evaluation_phase,
        "parameter_hashes": dict(sorted(parameter_hashes.items())),
        "steps": steps,
    }
