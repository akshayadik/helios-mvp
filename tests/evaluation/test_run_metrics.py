"""S4.9 run metrics against hand computation (design M-h).

Every expected value below is worked out by hand in the comment beside it,
from the fixture price book:

    prompt 2 / M tokens, completion 4 / M tokens
    CPU 36 per vCPU-hour  -> 36 / 3600 = 0.01 per CPU-second
    GPU 72 per hour (unused: every fixture has gpu_ms 0)
    storage 3 per GiB-month, kept 2 months -> 6 per GiB
    human 60 per hour, 10 review minutes -> 10 per human-reviewed run
    opportunity 2 per minute; TTCD censored at 1,800 s
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import pytest

from helios.evaluation.cost import PriceBook
from helios.evaluation.run_metrics import (
    HFactCounts,
    Publication,
    Ttcd,
    ambiguous,
    baseline_publications,
    graph_build_ms,
    h_fact_by_run,
    h_fact_value,
    h_struct,
    operational_ttcd,
    publications,
    requests_human,
    run_metrics_row,
    score_run_metrics,
    ttcd,
)
from helios.evaluation.scoring import Corpus, GroundTruth
from helios.store.result_store import ResultStore
from helios.telemetry.pool_lock import PoolLockedError

if TYPE_CHECKING:
    from pathlib import Path

    from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

TOL = 1e-9
GIB = 2**30

BOOK = PriceBook(
    version="fixture",
    currency="X",
    provider="fixture",
    region="-",
    cpu_machine="-",
    gpu_machine="-",
    storage_tier="-",
    token_prompt_per_million=2,
    token_completion_per_million=4,
    cpu_per_vcpu_hour=36,
    gpu_per_hour=72,
    storage_per_gib_month=3,
    storage_retention_months=2,
    human_per_hour=60,
    human_review_minutes=10,
    opportunity_per_minute=2,
    ttcd_censor_s=1800,
    unverified=(),
    digest="book-digest",
)

GT = GroundTruth(
    corpus=Corpus.BUILD,
    labels={f"inc-{i}": "cart" for i in range(1, 6)},
    digest="gt-digest",
    stem=False,
)


def _row(
    run: str,
    pipeline: str,
    *,
    status: str = "ranked",
    ranked: list[str] | None = None,
    cpu_ms: float = 0,
    prompt: int = 0,
    completion: int = 0,
) -> dict[str, Any]:
    return {
        "run_id": run,
        "pipeline": pipeline,
        "status": status,
        "ranked_candidates": ranked or [],
        "cpu_ms": cpu_ms,
        "gpu_ms": 0,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
    }


def _fusion(
    run: str,
    incident: str,
    *,
    first_ms: float,
    first: list[str],
    terminal_ms: float | None,
    ranked: list[str],
    state: str,
    non_converged: bool = False,
) -> dict[str, Any]:
    return {
        "run_id": run,
        "incident_id": incident,
        "variant_config_hash": "h" * 64,
        "first_ms": first_ms,
        "first_ranked": first,
        "terminal_ms": terminal_ms,
        "ranked": ranked,
        "state": state,
        "non_converged": non_converged,
        "confidence": None,
    }


def _narrative(
    slots: dict[str, tuple[int, int, int]],
    *,
    wall_ms: float,
    prompt: int = 0,
    completion: int = 0,
) -> dict[str, Any]:
    """slots: name -> (displayed claims, drafted first, accepted first)."""
    return {
        "slots": {
            name: {
                "claims": [{"kind": "x"}] * claims,
                "drafted_first": drafted,
                "accepted_first": accepted,
            }
            for name, (claims, drafted, accepted) in slots.items()
        },
        "wall_ms": wall_ms,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
    }


# ── R1: uniform, converged, right only at the terminal list ──────────────────


def _r1() -> dict[str, Any] | None:
    return run_metrics_row(
        fusion=_fusion(
            "r1",
            "inc-1",
            first_ms=30_000,
            first=["ad", "cart"],
            terminal_ms=45_000,
            ranked=["cart", "ad"],
            state="confirmed",
        ),
        pipeline_rows=[
            _row("r1", "dpipe", cpu_ms=1_200, ranked=["cart"]),
            _row("r1", "gpipe", cpu_ms=600, ranked=["cart"]),
            _row(
                "r1", "lpipe", cpu_ms=1_200, prompt=3_000, completion=500, ranked=["ad"]
            ),
        ],
        timings=[
            {"pipeline": "ueg_c", "started_unix": 1_000, "published_unix": 1_002},
            {"pipeline": "dpipe", "started_unix": 1_002, "published_unix": 1_003},
        ],
        trigger={
            "handover_unix": 1_000,
            "trigger_time_s": 500,
            "known_at_s": 680,
            "source": "threshold",
        },
        routing={"mode": "uniform"},
        hstruct_rows=[{"outputs": 4, "failed": 1, "structural_zero": False}],
        narrative=_narrative(
            {"a": (3, 4, 3), "b": (2, 2, 2)},
            wall_ms=4_200,
            prompt=1_000,
            completion=250,
        ),
        gt=GT,
        book=BOOK,
        storage_bytes=GIB // 4,
        h_fact_counts=HFactCounts(labelled=5, unsupported=1, pending=0),
        is_ambiguous=True,
        narrative_heavy=False,
    )


def test_r1_timing() -> None:
    row = _r1()
    assert row is not None
    assert row["graph_build_ms"] == pytest.approx(2_000, abs=TOL)  # 1002 - 1000 s
    assert row["ttt_ms"] == pytest.approx(32_000, abs=TOL)  # 2,000 + 30,000
    # first list's top-1 is ad (wrong); terminal top-1 cart at 2,000 + 45,000 ms
    assert row["ttcd_s"] == pytest.approx(47, abs=TOL)
    assert row["ttcd_censored"] is False
    assert row["detection_delay_s"] == pytest.approx(180, abs=TOL)  # 680 - 500
    assert row["operational_ttcd_s"] == pytest.approx(227, abs=TOL)  # 180 + 47
    assert row["time_to_narrative_ms"] == 4_200


def test_r1_cpr() -> None:
    row = _r1()
    assert row is not None
    # tokens: prompt 3,000 + 1,000 = 4,000; completion 500 + 250 = 750
    #   (4,000 * 2 + 750 * 4) / 1e6 = 11,000 / 1e6
    token = 11_000 / 1_000_000
    infra = 3 * 36 / 3_600  # 1,200 + 600 + 1,200 ms = 3 CPU-s
    storage = 6 / 4  # a quarter GiB at 6 per GiB
    human = 0  # CONFIRMED: no review
    opportunity = 47 / 60 * 2
    total = token + infra + storage + human + opportunity
    assert row["cpr_token"] == pytest.approx(token, abs=TOL)
    assert row["cpr_infrastructure"] == pytest.approx(infra, abs=TOL)
    assert row["cpr_storage"] == pytest.approx(storage, abs=TOL)
    assert row["cpr_human"] == human
    assert row["cpr_opportunity"] == pytest.approx(opportunity, abs=TOL)
    assert row["cpr_total"] == pytest.approx(total, abs=TOL)
    assert row["log_cpr"] == pytest.approx(math.log(total), abs=TOL)
    assert row["requests_human"] is False


def test_r1_hallucination_and_flags() -> None:
    row = _r1()
    assert row is not None
    assert row["h_struct"] == pytest.approx(1 / 4, abs=TOL)  # 1 failed of 4
    assert row["h_struct_structural_zero"] is False
    assert row["narrative_claims"] == 5  # 3 + 2 displayed
    assert row["grounding_drafted"] == 6  # 4 + 2 drafted first
    assert row["grounding_rejected"] == 1  # 6 drafted - 5 accepted
    assert row["h_fact"] == pytest.approx(1 / 5, abs=TOL)  # 1 unsupported of 5
    assert row["h_fact_pending"] == 0
    assert row["routing_mode"] == "uniform"
    assert row["escalated"] is None  # uniform runs make no escalation decision
    assert row["llm_consulted"] is True
    assert row["ambiguous"] is True
    assert row["narrative_heavy"] is False
    assert row["trigger_source"] == "threshold"
    assert row["metrics_version"] == "run-metrics-v1"


# ── R2: routed, stopped on the cheap arm, right at once; template narrative ──


def test_r2_routed_stop_provisional_template() -> None:
    row = run_metrics_row(
        fusion=_fusion(
            "r2",
            "inc-2",
            first_ms=800,
            first=["cart", "ad"],
            terminal_ms=800,
            ranked=["cart", "ad"],
            state="provisional",
        ),
        pipeline_rows=[
            _row("r2", "dpipe", cpu_ms=900, ranked=["cart"]),
            _row("r2", "gpipe", cpu_ms=300, ranked=["cart"]),
            _row("r2", "lpipe", status="skipped"),
        ],
        timings=[
            {"pipeline": "ueg_c", "started_unix": 2_000, "published_unix": 2_001.5},
        ],
        trigger={
            "handover_unix": 2_000,
            "trigger_time_s": 10,
            "known_at_s": None,
            "source": "fallback",
        },
        routing={"mode": "routed", "escalate": False},
        hstruct_rows=[{"outputs": 0, "failed": 0, "structural_zero": True}],
        narrative=_narrative({"a": (0, 0, 0)}, wall_ms=3),
        gt=GT,
        book=BOOK,
        storage_bytes=0,
    )
    assert row is not None
    assert row["ttt_ms"] == pytest.approx(2_300, abs=TOL)  # 1,500 + 800
    assert row["ttcd_s"] == pytest.approx(2.3, abs=TOL)  # first list already right
    assert row["operational_ttcd_s"] is None  # no live-detection time
    infra = 1.2 * 36 / 3_600  # 900 + 300 ms
    human = 10  # PROVISIONAL goes to a human: 10 min at 60 per hour
    opportunity = 2.3 / 60 * 2
    assert row["cpr_human"] == human
    assert row["cpr_total"] == pytest.approx(infra + human + opportunity, abs=TOL)
    assert row["requests_human"] is True
    assert row["escalated"] is False
    assert row["llm_consulted"] is False
    assert (row["h_struct"], row["h_struct_structural_zero"]) == (0, True)
    # a narrative with no claims is H_fact 0 (contract §5), labels or not
    assert row["narrative_claims"] == 0
    assert row["h_fact"] == 0


# ── R3: routed, escalated, right only after the L-pipe ───────────────────────


def test_r3_escalated_right_after_escalation() -> None:
    row = run_metrics_row(
        fusion=_fusion(
            "r3",
            "inc-3",
            first_ms=900,
            first=["ad"],
            terminal_ms=25_000,
            ranked=["cart"],
            state="confirmed",
        ),
        pipeline_rows=[_row("r3", "dpipe", cpu_ms=1_000, ranked=["ad"])],
        timings=[{"pipeline": "ueg_c", "started_unix": 3_000, "published_unix": 3_001}],
        trigger={
            "handover_unix": 3_000,
            "trigger_time_s": 0,
            "known_at_s": 120,
            "source": "threshold",
        },
        routing={"mode": "routed", "escalate": True, "llm_unavailable": None},
        hstruct_rows=[],
        narrative=None,
        gt=GT,
        book=BOOK,
        storage_bytes=0,
    )
    assert row is not None
    assert row["ttt_ms"] == pytest.approx(1_900, abs=TOL)  # 1,000 + 900
    assert row["ttcd_s"] == pytest.approx(26, abs=TOL)  # 1,000 + 25,000 ms
    assert row["operational_ttcd_s"] == pytest.approx(146, abs=TOL)  # 120 + 26
    assert row["escalated"] is True
    assert row["h_fact"] is None  # no narrative stored
    assert row["narrative_claims"] is None


# ── R4: non-converged, in-time list published at 90 s; graph from fallback ───


def test_r4_non_converged_counts_at_converge_ms() -> None:
    row = run_metrics_row(
        fusion=_fusion(
            "r4",
            "inc-4",
            first_ms=30_000,
            first=["ad"],
            terminal_ms=None,
            ranked=["cart", "ad"],
            state="non_converged",
            non_converged=True,
        ),
        pipeline_rows=[_row("r4", "dpipe", cpu_ms=2_000, ranked=["ad"])],
        # no ueg_c row (stored before S4.9): handover 4,000 to first start 4,000.25
        timings=[
            {"pipeline": "dpipe", "started_unix": 4_000.25, "published_unix": 4_001}
        ],
        trigger={
            "handover_unix": 4_000,
            "trigger_time_s": 0,
            "known_at_s": None,
            "source": "threshold",
        },
        routing=None,
        hstruct_rows=[],
        narrative=None,
        gt=GT,
        book=BOOK,
        storage_bytes=0,
    )
    assert row is not None
    assert row["graph_build_ms"] == pytest.approx(250, abs=TOL)
    assert row["ttt_ms"] == pytest.approx(30_250, abs=TOL)
    assert row["ttcd_s"] == pytest.approx(90.25, abs=TOL)  # 250 + 90,000 ms
    assert row["requests_human"] is True  # NON_CONVERGED goes to a human
    assert row["cpr_human"] == 10
    assert row["routing_mode"] is None  # no routing record before S4.9


# ── R5: never right, censored; opportunity at the censoring point ───────────


def test_r5_never_right_is_censored() -> None:
    row = run_metrics_row(
        fusion=_fusion(
            "r5",
            "inc-5",
            first_ms=2_000,
            first=["ad"],
            terminal_ms=40_000,
            ranked=["db", "ad"],
            state="confirmed",
        ),
        pipeline_rows=[_row("r5", "dpipe", cpu_ms=3_600, ranked=["ad"])],
        timings=[{"pipeline": "ueg_c", "started_unix": 5_000, "published_unix": 5_000}],
        trigger={
            "handover_unix": 5_000,
            "trigger_time_s": 0,
            "known_at_s": 60,
            "source": "threshold",
        },
        routing={"mode": "uniform"},
        hstruct_rows=[],
        narrative=None,
        gt=GT,
        book=BOOK,
        storage_bytes=GIB,
    )
    assert row is not None
    assert (row["ttcd_s"], row["ttcd_censored"]) == (1_800, True)
    assert row["operational_ttcd_s"] == 1_800  # censored stays censored
    infra = 3.6 * 36 / 3_600
    storage = 6  # one GiB
    opportunity = 1_800 / 60 * 2  # 60
    assert row["cpr_total"] == pytest.approx(infra + storage + opportunity, abs=TOL)


def test_unlabelled_case_gives_no_row() -> None:
    fusion = _fusion(
        "r9",
        "inc-unlabelled",
        first_ms=1,
        first=["a"],
        terminal_ms=1,
        ranked=["a"],
        state="confirmed",
    )
    row = run_metrics_row(
        fusion=fusion,
        pipeline_rows=[_row("r9", "dpipe", cpu_ms=1)],
        timings=[],
        trigger={"handover_unix": 0, "trigger_time_s": 0, "known_at_s": None},
        routing=None,
        hstruct_rows=[],
        narrative=None,
        gt=GT,
        book=BOOK,
        storage_bytes=0,
    )
    assert row is None


# ── unit rules ──────────────────────────────────────────────────────────────


def test_baseline_publishes_once_at_its_runtime() -> None:
    pubs = baseline_publications(12_000, ["cart", "ad"])
    assert pubs == [Publication(12_000, ("cart", "ad"))]
    t = ttcd(pubs, lambda r: r[0] == "cart", censor_s=1_800)
    assert t == Ttcd(12, False)


def test_ttcd_right_only_after_the_censoring_point_is_censored() -> None:
    pubs = [Publication(1_900_000, ("cart",))]
    assert ttcd(pubs, lambda r: r[0] == "cart", censor_s=1_800) == Ttcd(1_800, True)


def test_operational_ttcd_past_the_censoring_point_is_censored() -> None:
    assert operational_ttcd(1_000, Ttcd(900, False), censor_s=1_800) == Ttcd(
        1_800, True
    )
    assert operational_ttcd(None, Ttcd(900, False), censor_s=1_800) is None


def test_publications_of_a_converged_run_are_first_then_terminal() -> None:
    fusion = _fusion(
        "r", "i", first_ms=10, first=["a"], terminal_ms=20, ranked=["b"], state="x"
    )
    assert publications(fusion, 5) == [Publication(15, ("a",)), Publication(25, ("b",))]


def test_graph_build_before_handover_is_refused() -> None:
    with pytest.raises(ValueError, match="negative"):
        graph_build_ms([{"pipeline": "dpipe", "started_unix": 9}], 10)
    assert graph_build_ms([], 10) == 0


def test_requests_human_by_state() -> None:
    assert requests_human("provisional") is True
    assert requests_human("non_converged") is True
    assert requests_human("confirmed") is False


def test_h_struct_no_outputs_is_zero_not_structural() -> None:
    # the L-pipe ran but produced nothing: 0, and not a structural zero
    assert h_struct([{"outputs": 0, "failed": 0, "structural_zero": False}]) == (
        0,
        False,
    )
    assert h_struct([]) == (0, False)


def test_h_fact_pending_or_unlabelled_stays_empty() -> None:
    assert h_fact_value(3, HFactCounts(labelled=2, unsupported=1, pending=1)) is None
    assert h_fact_value(3, None) is None
    assert h_fact_value(0, None) == 0
    assert h_fact_value(4, HFactCounts(labelled=4, unsupported=3, pending=0)) == 3 / 4


def test_h_fact_by_run_skips_planted_and_counts_pending() -> None:
    key: dict[str, dict[str, Any]] = {
        "c1": {"run_id": "r1"},
        "c2": {"run_id": "r1"},
        "c3": {"run_id": "r1"},
        "p1": {"run_id": "r1", "planted": True},
        "c4": {"run_id": "r2"},
    }
    cons = {
        "c1": {"verdict": "supported"},
        "c2": {"verdict": "unsupported"},
        "c3": {"verdict": "pending"},
        "p1": {"verdict": "unsupported"},
        "c4": {"verdict": "supported"},
    }
    assert h_fact_by_run(cons, key) == {
        "r1": HFactCounts(labelled=2, unsupported=1, pending=1),
        "r2": HFactCounts(labelled=1, unsupported=0, pending=0),
    }


def test_ambiguous_uses_only_lists_returned() -> None:
    rows = [
        {"status": "ranked", "ranked_candidates": ["cart", "ad"]},
        {"status": "ranked", "ranked_candidates": ["ad"]},
        {"status": "abstained", "ranked_candidates": []},
    ]
    assert ambiguous(rows) is True
    assert ambiguous(rows[:1] + rows[2:]) is False
    assert ambiguous([{"status": "skipped", "ranked_candidates": ["x"]}]) is False


# ── store integration ───────────────────────────────────────────────────────


def _seed_store(path: Path, *, phase: str = "exploratory") -> ResultStore:
    store = ResultStore(path)
    con = store._con
    full = "f" * 64
    for pipeline, top, cpu in (("dpipe", "cart", 1_000), ("gpipe", "ad", 500)):
        con.execute(
            "INSERT INTO result_row (run_id, incident_id, variant_config_hash, "
            "snapshot_hash, pipeline, evaluation_phase, status, ranked_candidates, "
            "candidate_scores, prompt_tokens, completion_tokens, cpu_ms, gpu_ms, "
            "latency_ms, narrative, decision_hash) VALUES "
            "(?, ?, ?, ?, ?, ?, 'ranked', ?, '{}', 0, 0, ?, 0, 1, '', 'd')",
            ["run-a", "inc-1", full, "s" * 64, pipeline, phase, f'["{top}"]', cpu],
        )
    con.execute(
        "INSERT INTO trigger_row (run_id, incident_id, variant_config_hash, "
        "trigger_time_s, suspects, context, source, detector_hash, "
        "seeds_from_trigger, handover_unix, known_at_s) VALUES "
        "('run-a', 'inc-1', ?, 0, '[]', '[]', 'threshold', 'x', true, 200, 30)",
        [full],
    )
    store.insert_graph_timing("run-a", 200, 201)
    con.execute(
        "INSERT INTO fusion_row VALUES ('run-a', 'inc-1', ?, 'mahc', '[\"cart\"]', "
        "'{}', 0.75, 0.25, 'confirmed', 2000, '[\"ad\"]', 6000, false, '{}')",
        [full],
    )
    store.insert_routing("run-a", "inc-1", {"mode": "uniform"})
    return store


def test_score_run_metrics_writes_eval_run(tmp_path: Path) -> None:
    store = _seed_store(tmp_path / "r.duckdb")
    report = score_run_metrics(
        store,
        GT,
        BOOK,
        storage_bytes={"inc-1": 0},
        full_config_hash="f" * 64,
        frozen=lambda: False,
    )
    assert (report.scored, report.unlabelled) == (1, 0)
    (row,) = store.fetch_run_metrics()
    assert row["ttt_ms"] == pytest.approx(3_000, abs=TOL)  # 1,000 + 2,000
    assert row["ttcd_s"] == pytest.approx(7, abs=TOL)  # 1,000 + 6,000 ms
    assert row["operational_ttcd_s"] == pytest.approx(37, abs=TOL)  # 30 + 7
    assert row["ambiguous"] is True  # Full's D says cart, G says ad
    assert row["routing_mode"] == "uniform"
    assert row["confidence"] == pytest.approx(3 / 4, abs=TOL)
    # re-scoring replaces, never duplicates
    score_run_metrics(store, GT, BOOK, storage_bytes={"inc-1": 0}, frozen=lambda: False)
    assert len(store.fetch_run_metrics()) == 1


def test_score_run_metrics_refuses_confirmatory_before_freeze(tmp_path: Path) -> None:
    store = _seed_store(tmp_path / "r.duckdb", phase="confirmatory")
    with pytest.raises(PoolLockedError):
        score_run_metrics(
            store, GT, BOOK, storage_bytes={"inc-1": 0}, frozen=lambda: False
        )
