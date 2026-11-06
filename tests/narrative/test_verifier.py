"""Grounding verifier: one test per rejection reason (S2.8 design §5.2, §5.5)."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from helios.narrative.claims import Claim, ClaimKind
from helios.narrative.params import load_narrator_params
from helios.narrative.verifier import Reason, entry_services, mentions, verify
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

P = load_narrator_params()


def _item(item_id: str, service: str, value: Any, **extra: Any) -> dict[str, Any]:
    return {"id": item_id, "service": service, "text": "t", "value": value, **extra}


ENTRY: dict[str, Any] = {
    "steps": [
        {
            "id": "T",
            "trigger_time_s": 540.0,
            "window_start": "2026-10-28T14:42:23+00:00",
            "window_end": "2026-10-28T14:56:23+00:00",
        },
        {"id": "R", "ran": True},
        {
            "id": "P:dpipe",
            "ranked": ["cart", "ad", "payment"],
            "items": [
                _item(
                    "D:cart:latency", "cart", 6.2, before=120.0, after=900.0, unit="ms"
                ),
                _item("D:cart:error", "cart", 3.0),
                _item("D:ad:resource", "ad", 2.5, before=0.42, after=0.94, unit="cpu"),
                _item(
                    "D:payment:resource",
                    "payment",
                    1.9,
                    before=10.0,
                    after=4.0,
                    unit="socket",
                ),
                _item("D:cart:score", "cart", 0.8),
                _item("D:cart:final", "cart", 0.8),
            ],
        },
        {
            "id": "P:gpipe",
            "ranked": ["ad", "cart"],
            "items": [
                _item("G:cart:wait_from", "cart", {"frontend": 0.94}),
                _item("G:cart:leads", "cart", ["checkout"]),
                _item("G:cart:ghost_edges", "cart", [["cart", "redis"]]),
                _item("G:ad:self_shift", "ad", 1.5),
            ],
        },
        {
            "id": "P:lpipe",
            "ranked": ["cart", "cartservice"],
            "items": [
                {
                    "id": "L:log:L12",
                    "service": "cart",
                    "text": 'cart log template "connection pool exhausted after <DUR>": '
                    "2 lines before trigger, 40 after",
                    "value": None,
                },
                {
                    "id": "L:log:claim1",
                    "service": "cart",
                    "text": "pool exhausted",
                    "value": None,
                    "cites": ["L:log:L12"],
                },
            ],
        },
        {
            "id": "F",
            "ranked": ["cart", "ad", "payment", "email"],
            "confidence": 0.91,
            "state": "confirmed",
            "disagree": ["gpipe"],
        },
        {"id": "G", "outcome": "PASS"},
    ]
}


def c(kind: str, sentence: str, cites: list[str], **fields: Any) -> Claim:
    return Claim(kind=ClaimKind(kind), sentence=sentence, cites=tuple(cites), **fields)


SUPPORTED = {
    "shift": c(
        "shift",
        "cart latency rose from 120 ms to 900 ms.",
        ["D:cart:latency"],
        service="cart",
        channel="latency",
        direction="up",
    ),
    "call_structure": c(
        "call_structure",
        "frontend spent 94% of its time waiting on cart.",
        ["G:cart:wait_from"],
        caller="frontend",
        callee="cart",
        feature="wait",
    ),
    "log_message": c(
        "log_message",
        'cart logged "connection pool exhausted".',
        ["L:log:L12"],
        service="cart",
        snippet="connection pool exhausted",
    ),
    "ranking": c("ranking", "cart is the top suspect.", ["F"], service="cart", rank=1),
    "contradiction": c(
        "contradiction",
        "G-pipe ranks ad first, unlike the fused verdict that ranks cart first.",
        ["G:ad:self_shift"],
        pipeline="gpipe",
        service="ad",
    ),
    "verification_step": c(
        "verification_step",
        "Query cart p99 latency between 14:50 and 14:55.",
        ["D:cart:latency"],
        target_service="cart",
        action_verb="query",
        modality="metric",
    ),
}


@pytest.mark.parametrize("kind", sorted(SUPPORTED))
def test_accepts_supported_claim_of_each_kind(kind: str) -> None:
    assert verify(SUPPORTED[kind], ENTRY, P) is None


def test_missing_cite() -> None:
    claim = SUPPORTED["ranking"].model_copy(update={"cites": ()})
    assert verify(claim, ENTRY, P) == Reason.MISSING_CITE


def test_unknown_id_and_worker_claim_not_citable() -> None:
    for bad in ("D:cart:nothing", "L:log:claim1"):
        claim = SUPPORTED["ranking"].model_copy(update={"cites": ("F", bad)})
        assert verify(claim, ENTRY, P) == Reason.UNKNOWN_ID, bad


def test_wrong_direction_word() -> None:
    claim = SUPPORTED["shift"].model_copy(
        update={"sentence": "cart latency fell to 900 ms."}
    )
    assert verify(claim, ENTRY, P) == Reason.WRONG_DIRECTION


def test_wrong_direction_field_against_levels() -> None:
    down = c(
        "shift",
        "payment socket use dropped from 10 to 4.",
        ["D:payment:resource"],
        service="payment",
        channel="resource",
        direction="down",
    )
    assert verify(down, ENTRY, P) is None
    up = down.model_copy(
        update={"direction": "up", "sentence": "payment socket use rose to 4."}
    )
    assert verify(up, ENTRY, P) == Reason.WRONG_DIRECTION


def test_wrong_edge_inverted_caller_callee() -> None:
    claim = SUPPORTED["call_structure"].model_copy(
        update={
            "caller": "cart",
            "callee": "frontend",
            "sentence": "cart spent 94% of its time waiting on frontend.",
        }
    )
    assert verify(claim, ENTRY, P) == Reason.WRONG_EDGE


def test_lead_and_ghost_edges() -> None:
    lead = c(
        "call_structure",
        "cart moved before its caller checkout.",
        ["G:cart:leads"],
        caller="checkout",
        callee="cart",
        feature="lead",
    )
    ghost = c(
        "call_structure",
        "cart started calling redis after the trigger.",
        ["G:cart:ghost_edges"],
        caller="cart",
        callee="redis",
        feature="ghost",
    )
    assert verify(lead, ENTRY, P) is None
    assert verify(ghost, ENTRY, P) is None


def test_snippet_must_be_verbatim() -> None:
    claim = SUPPORTED["log_message"].model_copy(
        update={"snippet": "out of memory", "sentence": "cart ran out of memory."}
    )
    assert verify(claim, ENTRY, P) == Reason.SNIPPET_NOT_FOUND


def test_foreign_service_token_match() -> None:
    assert mentions("cartservice and cart and ad's pool", entry_services(ENTRY)) == {
        "cart",
        "cartservice",
        "ad",
    }
    assert "ad" not in mentions("the address and adapter", entry_services(ENTRY))
    claim = SUPPORTED["shift"].model_copy(
        update={"sentence": "cart latency rose to 900 ms because of payment."}
    )
    assert verify(claim, ENTRY, P) == Reason.FOREIGN_SERVICE
    ok = SUPPORTED["shift"].model_copy(
        update={"sentence": "cart latency rose to 900 ms; cartservice is unrelated."}
    )
    assert verify(ok, ENTRY, P) == Reason.FOREIGN_SERVICE  # cartservice is not cart


def test_numbers_normalised() -> None:
    base = SUPPORTED["shift"]
    for sentence in (
        "cart latency rose to 0.9 s.",
        "cart latency rose to ~900 ms.",
        "cart latency rose to about 0.9 seconds.",
        "cart latency rose from 120ms to 900ms.",
        "cart latency climbed from 120 ms to 900 ms after the trigger.",
    ):
        claim = base.model_copy(update={"sentence": sentence})
        assert verify(claim, ENTRY, P) is None, sentence
    ad = c(
        "shift",
        "ad cpu use rose from 42% to 94%.",
        ["D:ad:resource"],
        service="ad",
        channel="resource",
        direction="up",
    )
    assert verify(ad, ENTRY, P) is None


def test_ids_ranks_and_times_are_not_evidence_numbers() -> None:
    # Rank words, p99 and HH:MM are not checked as evidence numbers; under the
    # closed vocabulary (N-j) IDs and "#1" may not appear in a sentence at all.
    step = SUPPORTED["verification_step"].model_copy(
        update={"sentence": "Query cart p99 latency between 14:50 and 14:55."}
    )
    assert verify(step, ENTRY, P) is None
    ranked = SUPPORTED["ranking"].model_copy(
        update={"sentence": "cart is the first and most likely suspect."}
    )
    assert verify(ranked, ENTRY, P) is None
    ids = SUPPORTED["ranking"].model_copy(
        update={"sentence": "cart is the #1 suspect (see L12)."}
    )
    assert verify(ids, ENTRY, P) is not None


def test_number_not_in_evidence() -> None:
    claim = SUPPORTED["shift"].model_copy(
        update={"sentence": "cart latency rose to 1500 ms."}
    )
    assert verify(claim, ENTRY, P) == Reason.NUMBER_NOT_IN_EVIDENCE


def test_time_out_of_window() -> None:
    claim = SUPPORTED["verification_step"].model_copy(
        update={"sentence": "Query cart p99 latency between 13:00 and 13:10."}
    )
    assert verify(claim, ENTRY, P) == Reason.TIME_OUT_OF_WINDOW


def test_verb_and_modality() -> None:
    step = SUPPORTED["verification_step"]
    reboot = step.model_copy(
        update={"action_verb": "restart", "sentence": "Restart cart at 14:52."}
    )
    assert verify(reboot, ENTRY, P) == Reason.VERB_NOT_ALLOWED
    wrong = step.model_copy(update={"modality": "log"})
    assert verify(wrong, ENTRY, P) == Reason.MODALITY_MISMATCH


def test_verification_target_top3_or_cited_neighbour() -> None:
    step = SUPPORTED["verification_step"]
    email = step.model_copy(
        update={"target_service": "email", "sentence": "Query email latency at 14:52."}
    )
    assert verify(email, ENTRY, P) == Reason.FOREIGN_SERVICE
    frontend = c(
        "verification_step",
        "Inspect frontend connections to cart at 14:52.",
        ["G:cart:wait_from"],
        target_service="frontend",
        action_verb="inspect",
        modality="edge",
    )
    assert verify(frontend, ENTRY, P) is None


def test_rank_mismatch() -> None:
    claim = SUPPORTED["ranking"].model_copy(update={"rank": 2})
    assert verify(claim, ENTRY, P) == Reason.RANK_MISMATCH


def test_not_in_disagree() -> None:
    claim = SUPPORTED["contradiction"].model_copy(update={"pipeline": "dpipe"})
    assert verify(claim, ENTRY, P) == Reason.NOT_IN_DISAGREE


def test_ranking_claim_may_cite_score_items_shift_may_not() -> None:
    ranking = SUPPORTED["ranking"].model_copy(update={"cites": ("D:cart:score",)})
    assert verify(ranking, ENTRY, P) is None
    shift = SUPPORTED["shift"].model_copy(update={"cites": ("D:cart:score",)})
    assert verify(shift, ENTRY, P) == Reason.KIND_MISMATCH


def test_shift_may_not_be_grounded_by_a_log_line() -> None:
    # N-j: a shift claim needs its own D-pipe item.
    claim = c(
        "shift",
        "cart errors rose.",
        ["L:log:L12"],
        service="cart",
        channel="error",
        direction="up",
    )
    assert verify(claim, ENTRY, P) == Reason.KIND_MISMATCH


def test_log_snippet_text_is_not_rechecked() -> None:
    # The quoted snippet is verified verbatim; its own numbers, times and names
    # are evidence, not new claims.
    entry = {
        "steps": [
            *[s for s in ENTRY["steps"] if s["id"] != "P:lpipe"],
            {
                "id": "P:lpipe",
                "ranked": ["cart"],
                "items": [
                    {
                        "id": "L:log:L3",
                        "service": "cart",
                        "text": 'cart log template "cart -> payment timeout after '
                        '30s at 13:02": 0 lines before trigger, 5 after',
                        "value": None,
                    }
                ],
            },
        ]
    }
    claim = c(
        "log_message",
        'cart logged: "cart -> payment timeout after 30s at 13:02"',
        ["L:log:L3"],
        service="cart",
        snippet="cart -> payment timeout after 30s at 13:02",
    )
    assert verify(claim, entry, P) is None
    outside = claim.model_copy(
        update={"sentence": 'cart logged: "timeout after 30s" 45 times.'}
    )
    assert verify(outside, entry, P) == Reason.SNIPPET_NOT_FOUND


def test_time_window_crossing_midnight() -> None:
    entry = {
        "steps": [
            {
                "id": "T",
                "window_start": "2026-10-28T23:52:47+00:00",
                "window_end": "2026-10-29T00:11:02+00:00",
            },
            *[s for s in ENTRY["steps"] if s["id"] != "T"],
        ]
    }
    step = SUPPORTED["verification_step"]
    ok = step.model_copy(
        update={"sentence": "Query cart latency between 23:52 and 00:11."}
    )
    assert verify(ok, entry, P) is None
    late = step.model_copy(update={"sentence": "Query cart latency at 00:30."})
    assert verify(late, entry, P) == Reason.TIME_OUT_OF_WINDOW


def _with_metric_line() -> dict[str, Any]:
    entry = copy.deepcopy(ENTRY)
    lpipe = next(s for s in entry["steps"] if s["id"] == "P:lpipe")
    lpipe["items"].insert(
        0,
        {
            "id": "L:metric:M1",
            "service": "cart",
            "text": "cart span_mean_latency_milliseconds up 6.2 robust units",
            "value": None,
        },
    )
    return entry


def test_logged_claim_needs_a_log_line_not_a_metric_digest_line() -> None:
    # Round 3 smoke: "cart logged <metric digest line>" was accepted.
    entry = _with_metric_line()
    claim = c(
        "log_message",
        'cart logged "cart span_mean_latency_milliseconds up".',
        ["L:metric:M1"],
        service="cart",
        snippet="cart span_mean_latency_milliseconds up",
    )
    assert verify(claim, entry, P) == Reason.KIND_MISMATCH
    step = c(
        "verification_step",
        "Filter cart logs between 14:42 and 14:56.",
        ["L:metric:M1"],
        target_service="cart",
        action_verb="filter",
        modality="log",
    )
    assert verify(step, entry, P) == Reason.MODALITY_MISMATCH


SEVERITY_LINE = "cart 38 error-level lines after trigger, 9 before"


def _with_severity_line() -> dict[str, Any]:
    entry = copy.deepcopy(ENTRY)
    lpipe = next(s for s in entry["steps"] if s["id"] == "P:lpipe")
    lpipe["items"].insert(
        0, {"id": "L:log:L1", "service": "cart", "text": SEVERITY_LINE, "value": None}
    )
    return entry


def test_log_snippet_must_come_from_the_quoted_template() -> None:
    # Review C1: L-pipe log lines are digests; only the template text inside
    # the quotes is something the service logged.
    entry = _with_severity_line()

    def logged(snippet: str, cite: str) -> Reason | None:
        claim = c(
            "log_message",
            f'cart logged "{snippet}".',
            [cite],
            service="cart",
            snippet=snippet,
        )
        return verify(claim, entry, P)

    assert logged("connection pool exhausted", "L:log:L12") is None
    assert logged("38 error-level lines after", "L:log:L1") == Reason.SNIPPET_NOT_FOUND
    assert logged("2 lines before trigger", "L:log:L12") == Reason.SNIPPET_NOT_FOUND
    assert logged("cart log template", "L:log:L12") == Reason.SNIPPET_NOT_FOUND
