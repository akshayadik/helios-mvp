"""Run-level metrics (S4.9): TTT, TTCD, CpR, H_struct, H_fact, strata.

Design: docs/sprints/s4-product-eval-tooling/s4_9_metrics_design.md (M-a to
M-h, approved 2026-11-11). Computed after dispatch from stored rows joined to
the ground truth and written to ``eval_run``, beside ``eval_score`` (per list).
No pipeline reads either table.

- M-a: graph build counts in the clock (entry 46). It is the ``ueg_c`` timing
  row (handover to graph done); for runs stored before that row existed, the
  gap from the handover to the earliest pipeline start.
- M-b: a run publishes its first list at ``first_ms`` and its terminal list at
  ``terminal_ms``; a non-converged run's in-time list counts as published at
  ``CONVERGE_MS``. TTT = graph build + first publication. TTCD = graph build +
  the earliest publication whose top-1 is the ground truth, censored at the
  price book's censoring point. The narrator is outside both clocks.
- M-c: CpR asks for a human when the published state is PROVISIONAL or
  NON_CONVERGED.
- M-d: H_struct = failed / outputs (0 with none); H_fact = unsupported /
  labelled claims, 0 for a narrative with no claims, empty while any claim of
  the run is still pending.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from helios.consensus.calibration import State
from helios.consensus.timing import CONVERGE_MS
from helios.evaluation.cost import IncidentUsage, cpr
from helios.store.result_store import GRAPH_TIMING
from helios.telemetry.pool_lock import BUILD_FREEZE_TAG, PoolLockedError, build_frozen
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from helios.evaluation.cost import CostBreakdown, PriceBook
    from helios.evaluation.scoring import GroundTruth
    from helios.store.result_store import ResultStore

__all__ = [
    "METRICS_VERSION",
    "HFactCounts",
    "Publication",
    "RunMetricsReport",
    "Ttcd",
    "ambiguous",
    "ambiguous_by_incident",
    "baseline_publications",
    "graph_build_ms",
    "grounding_counts",
    "h_fact_by_run",
    "h_fact_value",
    "h_struct",
    "operational_ttcd",
    "publications",
    "requests_human",
    "run_metrics_row",
    "score_run_metrics",
    "ttcd",
    "usage_from_rows",
]

HELIOS_ENABLE_RUN_METRICS: bool = True

METRICS_VERSION = "run-metrics-v1"

_MS_PER_S = 1000
_HUMAN_STATES = frozenset({State.PROVISIONAL.value, State.NON_CONVERGED.value})
_UNSUPPORTED = "unsupported"


# ── timing (M-a, M-b) ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Publication:
    """One published list and when it was published, from the handover."""

    elapsed_ms: float
    ranked: tuple[str, ...]


@dataclass(frozen=True)
class Ttcd:
    """Time to correct diagnosis in seconds; ``censored`` when none was right."""

    seconds: float
    censored: bool


def graph_build_ms(timings: Iterable[Mapping[str, Any]], handover_unix: float) -> float:
    """Graph build of a run: the ``ueg_c`` row, else handover to first start.

    No pipeline row and no graph row (nothing ran) counts as zero. A negative
    gap (clock skew) is refused: it would shorten TTT and TTCD.
    """
    rows = list(timings)
    graph = [r for r in rows if r["pipeline"] == GRAPH_TIMING]
    if graph:
        ms = (float(graph[0]["published_unix"]) - float(graph[0]["started_unix"])) * (
            _MS_PER_S
        )
    elif rows:
        ms = (min(float(r["started_unix"]) for r in rows) - handover_unix) * _MS_PER_S
    else:
        ms = 0
    if ms < 0:
        raise ValueError("graph build time is negative (timing rows before handover)")
    return ms


def publications(fusion: Mapping[str, Any], graph_ms: float) -> list[Publication]:
    """The fused lists a run published, in order (design M-b).

    The first publication always exists. The terminal list follows at
    ``terminal_ms``; a non-converged run's in-time list at ``CONVERGE_MS``.
    """
    out = [
        Publication(graph_ms + float(fusion["first_ms"]), tuple(fusion["first_ranked"]))
    ]
    if fusion["non_converged"]:
        out.append(Publication(graph_ms + CONVERGE_MS, tuple(fusion["ranked"])))
    elif fusion["terminal_ms"] is not None:
        out.append(
            Publication(
                graph_ms + float(fusion["terminal_ms"]), tuple(fusion["ranked"])
            )
        )
    return out


def baseline_publications(
    runtime_ms: float, ranked: Sequence[str]
) -> list[Publication]:
    """A baseline publishes once, at its measured runtime from the handover."""
    return [Publication(float(runtime_ms), tuple(ranked))]


def ttcd(
    pubs: Sequence[Publication],
    is_correct_top1: Callable[[Sequence[str]], bool],
    *,
    censor_s: float,
) -> Ttcd:
    """Earliest publication whose top-1 is right, censored at ``censor_s``."""
    times = [p.elapsed_ms for p in pubs if p.ranked and is_correct_top1(p.ranked)]
    if not times:
        return Ttcd(censor_s, True)
    seconds = min(times) / _MS_PER_S
    if seconds >= censor_s:
        return Ttcd(censor_s, True)
    return Ttcd(seconds, False)


def operational_ttcd(
    detection_delay_s: float | None, value: Ttcd, *, censor_s: float
) -> Ttcd | None:
    """Detection delay + TTCD, censored (entries 71-72, exploratory); None
    without a live-detection time (external trigger, rows before S2-BL-12)."""
    if detection_delay_s is None:
        return None
    total = detection_delay_s + value.seconds
    if value.censored or total >= censor_s:
        return Ttcd(censor_s, True)
    return Ttcd(total, False)


# ── cost (M-c) ───────────────────────────────────────────────────────────────


def requests_human(state: str) -> bool:
    """A PROVISIONAL or NON_CONVERGED verdict goes to a human; CONFIRMED does not."""
    return state in _HUMAN_STATES


def usage_from_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    narrative: Mapping[str, Any] | None,
    storage_bytes: int,
) -> IncidentUsage:
    """Usage of one run from its stored pipeline rows (skipped ones add zero)
    and its narrative's tokens (S2.8)."""
    rows = list(rows)
    if len({str(r["run_id"]) for r in rows}) > 1:
        raise ValueError("rows of more than one run")
    n = narrative or {}
    return IncidentUsage(
        prompt_tokens=sum(int(r["prompt_tokens"]) for r in rows)
        + int(n.get("prompt_tokens", 0)),
        completion_tokens=sum(int(r["completion_tokens"]) for r in rows)
        + int(n.get("completion_tokens", 0)),
        cpu_ms=sum(float(r["cpu_ms"]) for r in rows),
        gpu_ms=sum(float(r["gpu_ms"]) for r in rows),
        storage_bytes=storage_bytes,
    )


# ── hallucination (M-d) ──────────────────────────────────────────────────────


def h_struct(rows: Iterable[Mapping[str, Any]]) -> tuple[float, bool]:
    """(failed / outputs over the run's hstruct rows, structural zero).

    0 when there are no outputs (entry 59). Structural zero: every row is one.
    """
    rows = list(rows)
    outputs = sum(int(r["outputs"]) for r in rows)
    failed = sum(int(r["failed"]) for r in rows)
    structural = bool(rows) and all(bool(r["structural_zero"]) for r in rows)
    return (failed / outputs if outputs else 0, structural)


@dataclass(frozen=True)
class HFactCounts:
    """Adjudicated labels of one run's displayed claims."""

    labelled: int
    unsupported: int
    pending: int


def h_fact_by_run(
    cons: Mapping[str, Mapping[str, Any]], key: Mapping[str, Mapping[str, Any]]
) -> dict[str, HFactCounts]:
    """Per run, from the S2.9 consensus labels and the set's sealed key.

    Planted claims are calibration items, never part of a run's narrative.
    """
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for item, c in cons.items():
        k = key[item]
        if k.get("planted"):
            continue
        row = counts[str(k["run_id"])]
        verdict = str(c["verdict"])
        if verdict == "pending":
            row[2] += 1
        else:
            row[0] += 1
            row[1] += verdict == _UNSUPPORTED
    return {run: HFactCounts(*c) for run, c in counts.items()}


def h_fact_value(claims: int, counts: HFactCounts | None) -> float | None:
    """H_fact of one run (contract §5 with entry 65; design M-d).

    A narrative with no claims is 0. Otherwise the run needs labels for its
    claims: with none, or any still pending, the value is empty (never imputed).
    """
    if claims == 0:
        return 0
    if counts is None or counts.pending or counts.labelled == 0:
        return None
    return counts.unsupported / counts.labelled


def grounding_counts(narrative: Mapping[str, Any] | None) -> tuple[int, int, int]:
    """(displayed claims, claims the verifier rejected, claims first drafted)."""
    if narrative is None:
        return (0, 0, 0)
    slots = narrative["slots"].values()
    claims = sum(len(s["claims"]) for s in slots)
    drafted = sum(int(s.get("drafted_first") or 0) for s in slots)
    accepted = sum(int(s.get("accepted_first") or 0) for s in slots)
    return (claims, drafted - accepted, drafted)


# ── strata (M-e) ─────────────────────────────────────────────────────────────


def ambiguous(pipeline_rows: Iterable[Mapping[str, Any]]) -> bool:
    """A-H4: the pipelines that returned a list disagree on top-1 (no label)."""
    tops = set()
    for r in pipeline_rows:
        ranked = r["ranked_candidates"]
        if r["status"] == "ranked" and ranked:
            tops.add(str(ranked[0]))
    return len(tops) >= 2


def ambiguous_by_incident(store: ResultStore, full_config_hash: str) -> dict[str, bool]:
    """The ambiguous flag of each incident, from its HELIOS-Full run."""
    by_run: dict[str, list[dict[str, Any]]] = defaultdict(list)
    incident: dict[str, str] = {}
    for r in store.fetch_all_pipeline_rows():
        if r["variant_config_hash"] != full_config_hash:
            continue
        row = dict(r)
        row["ranked_candidates"] = _ranked(row["ranked_candidates"])
        by_run[str(row["run_id"])].append(row)
        incident[str(row["run_id"])] = str(row["incident_id"])
    return {incident[run]: ambiguous(rows) for run, rows in sorted(by_run.items())}


# ── one run, and the store ───────────────────────────────────────────────────


def _ranked(value: object) -> list[str]:
    if isinstance(value, str):
        value = json.loads(value)
    return [str(c) for c in value] if isinstance(value, list) else []


def run_metrics_row(
    *,
    fusion: Mapping[str, Any],
    pipeline_rows: Sequence[Mapping[str, Any]],
    timings: Sequence[Mapping[str, Any]],
    trigger: Mapping[str, Any],
    routing: Mapping[str, Any] | None,
    hstruct_rows: Sequence[Mapping[str, Any]],
    narrative: Mapping[str, Any] | None,
    gt: GroundTruth,
    book: PriceBook,
    storage_bytes: int,
    h_fact_counts: HFactCounts | None = None,
    is_ambiguous: bool | None = None,
    narrative_heavy: bool | None = None,
) -> dict[str, Any] | None:
    """The eval_run row of one run, or None when the case has no label."""
    incident_id = str(fusion["incident_id"])
    if incident_id not in gt.labels:
        return None

    def correct_top1(ranked: Sequence[str]) -> bool:
        case = gt.score(incident_id, ranked)
        return case is not None and case.rank == 1

    graph_ms = graph_build_ms(timings, float(trigger["handover_unix"]))
    pubs = publications(fusion, graph_ms)
    t = ttcd(pubs, correct_top1, censor_s=book.ttcd_censor_s)
    known = trigger.get("known_at_s")
    delay = None if known is None else float(known) - float(trigger["trigger_time_s"])
    op = operational_ttcd(delay, t, censor_s=book.ttcd_censor_s)
    state = str(fusion["state"])
    human = requests_human(state)
    usage = usage_from_rows(
        pipeline_rows, narrative=narrative, storage_bytes=storage_bytes
    )
    cost: CostBreakdown = cpr(usage, requests_human=human, ttcd_s=t.seconds, book=book)
    hs, structural = h_struct(hstruct_rows)
    claims, rejected, drafted = grounding_counts(narrative)
    lpipe_ran = any(
        r["pipeline"] == "lpipe" and r["status"] != "skipped" for r in pipeline_rows
    )
    routing = routing or {}
    mode = routing.get("mode")
    return {
        "run_id": str(fusion["run_id"]),
        "incident_id": incident_id,
        "variant_config_hash": str(fusion["variant_config_hash"]),
        "corpus": gt.corpus.value,
        "state": state,
        "non_converged": bool(fusion["non_converged"]),
        "requests_human": human,
        "routing_mode": mode,
        "escalated": bool(routing["escalate"]) if "escalate" in routing else None,
        "llm_consulted": lpipe_ran,
        "llm_unavailable": routing.get("llm_unavailable"),
        "trigger_source": trigger.get("source"),
        "graph_build_ms": graph_ms,
        "ttt_ms": pubs[0].elapsed_ms,
        "ttcd_s": t.seconds,
        "ttcd_censored": t.censored,
        "detection_delay_s": delay,
        "operational_ttcd_s": None if op is None else op.seconds,
        "time_to_narrative_ms": None if narrative is None else narrative["wall_ms"],
        "cpr_token": cost.token,
        "cpr_infrastructure": cost.infrastructure,
        "cpr_storage": cost.storage,
        "cpr_human": cost.human,
        "cpr_opportunity": cost.opportunity,
        "cpr_total": cost.total,
        "log_cpr": cost.log_total,
        "h_struct": hs,
        "h_struct_structural_zero": structural,
        "narrative_claims": None if narrative is None else claims,
        "grounding_rejected": None if narrative is None else rejected,
        "grounding_drafted": None if narrative is None else drafted,
        "h_fact": (None if narrative is None else h_fact_value(claims, h_fact_counts)),
        "h_fact_pending": None if h_fact_counts is None else h_fact_counts.pending,
        "ambiguous": is_ambiguous,
        "narrative_heavy": narrative_heavy,
        "confidence": fusion.get("confidence"),
        "price_book_digest": book.digest,
        "ground_truth_sha256": gt.digest,
        "metrics_version": METRICS_VERSION,
    }


@dataclass(frozen=True)
class RunMetricsReport:
    """What one pass wrote (counts only, no labels)."""

    scored: int
    unlabelled: int
    rows: tuple[dict[str, Any], ...]


def score_run_metrics(
    store: ResultStore,
    gt: GroundTruth,
    book: PriceBook,
    *,
    storage_bytes: Mapping[str, int],
    h_fact_counts: Mapping[str, HFactCounts] | None = None,
    full_config_hash: str | None = None,
    narrative_heavy: Mapping[str, bool] | None = None,
    frozen: Callable[[], bool] = build_frozen,
) -> RunMetricsReport:
    """Write eval_run for every stored fused verdict. Confirmatory runs are
    refused until build-freeze, as in the accuracy scoring path."""
    if not frozen() and any(
        r.get("evaluation_phase") == "confirmatory"
        for r in store.fetch_all_pipeline_rows()
    ):
        raise PoolLockedError(
            f"confirmatory runs are scored only after tag {BUILD_FREEZE_TAG!r}"
        )
    amb = (
        ambiguous_by_incident(store, full_config_hash)
        if full_config_hash is not None
        else {}
    )
    rows: list[dict[str, Any]] = []
    unlabelled = 0
    for f in store.fetch_all_fusion_rows():
        run_id = str(f["run_id"])
        incident_id = str(f["incident_id"])
        trigger = store.fetch_trigger_row(run_id)
        if trigger is None:
            raise ValueError(f"run {run_id} has a fused verdict but no trigger row")
        pipeline_rows = store.fetch_run_pipeline_rows(run_id)
        row = run_metrics_row(
            fusion=f,
            pipeline_rows=pipeline_rows,
            timings=store.fetch_timings(run_id),
            trigger=trigger,
            routing=store.fetch_routing(run_id),
            hstruct_rows=store.fetch_hstruct(run_id),
            narrative=store.fetch_narrative(run_id),
            gt=gt,
            book=book,
            storage_bytes=storage_bytes[incident_id],
            h_fact_counts=(h_fact_counts or {}).get(run_id),
            is_ambiguous=amb.get(incident_id),
            narrative_heavy=(narrative_heavy or {}).get(incident_id),
        )
        if row is None:
            unlabelled += 1
            continue
        rows.append(row)
    store.replace_run_metrics(rows)
    return RunMetricsReport(scored=len(rows), unlabelled=unlabelled, rows=tuple(rows))
