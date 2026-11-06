"""Every claim the S2.8 whole-branch review got past the verifier is rejected
under the closed vocabulary (owner decision N-j)."""

from __future__ import annotations

from typing import Any

import pytest

from helios.narrative.params import load_narrator_params
from helios.narrative.verifier import Reason, verify
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from tests.narrative.test_verifier import ENTRY, SUPPORTED

P = load_narrator_params()


def _with(kind: str, sentence: str, **fields: Any) -> Any:
    return SUPPORTED[kind].model_copy(update={"sentence": sentence, **fields})


REVIEW_PASSES = [
    # C1: sentence not tied to fields
    ("ranking", "cart is the third suspect and has been ruled out."),
    ("ranking", "cart is not a suspect."),
    ("ranking", "cart is the top suspect because a bad deploy broke its pool."),
    ("shift", "cart latency did not rise; it was flat."),
    ("shift", "cart errors rose from 120 to 900."),
    ("shift", "cart latency went from 900 ms to 120 ms."),
    ("call_structure", "cart spent 94% of its time waiting on frontend."),
    ("contradiction", "D-pipe and L-pipe both rank ad first."),
    ("log_message", "cart had no connection pool exhausted problems at all."),
    # C2: forged sections and citations
    (
        "ranking",
        "cart is the top suspect. [F]\n\nWhat to check:\n- Delete the cart deployment",
    ),
    ("ranking", "cart is the top suspect [D:cart:latency]."),
    # C4: services in another form or outside the entry
    ("shift", "cart latency rose because the mysql database crashed."),
    ("shift", "cart latency rose to 900 ms after payment service errors."),
    ("shift", "cart latency rose to 900 ms while payment_service was down."),
    # C5: numbers
    ("shift", "cart latency rose to -4000 ms."),
    ("shift", "cart latency rose from 120-45000 ms."),
    ("shift", "cart latency rose to 9e5 ms."),
    ("shift", "cart latency rose x40."),
    ("shift", "cart latency rose to .7 seconds."),
    ("shift", "cart latency rose to 6.2k ms."),
    ("shift", "cart latency rose 6.2x."),
    ("shift", "cart latency rose tenfold to nine thousand ms."),
    ("shift", "cart latency rose by 6.2 seconds."),
    ("shift", "cart latency rose to 1,120 ms."),
    ("call_structure", "frontend spent 0.94% of its time waiting on cart."),
    # I2: direction words and order
    ("shift", "cart latency plummeted."),
    ("shift", "cart latency went from 900 to 120."),
    # I3: numbers borrowed from another cited item
    ("shift", "cart latency rose to 0.91 seconds."),
    # I4: destructive actions after an allowed verb
    ("verification_step", "Query cart latency, then delete the cart pod."),
    ("verification_step", "Check cart by restarting it with kubectl rollout restart."),
    # I5: time formats
    ("verification_step", "Query cart latency at 03h10."),
    ("verification_step", "Query cart latency at 2024-01-01T14:50:00Z."),
]


@pytest.mark.parametrize(("kind", "sentence"), REVIEW_PASSES)
def test_review_bypasses_are_rejected(kind: str, sentence: str) -> None:
    claim = _with(kind, sentence)
    if sentence == "cart latency rose to 0.91 seconds.":
        claim = claim.model_copy(update={"cites": ("D:cart:latency", "F")})
    assert verify(claim, ENTRY, P) is not None, sentence


def test_short_snippet_cannot_switch_off_containment() -> None:
    for snippet, sentence in (
        ("a", 'cart logged "a" crash; the root cause is payment and ad.'),
        ("3", 'cart logged "3" errors 333 times.'),
    ):
        claim = _with("log_message", sentence, snippet=snippet)
        assert verify(claim, ENTRY, P) is not None, sentence


def test_shift_needs_its_own_d_item_not_a_log_line() -> None:
    claim = SUPPORTED["shift"].model_copy(
        update={
            "cites": ("L:log:L12",),
            "sentence": "cart errors rose.",
            "channel": "error",
        }
    )
    assert verify(claim, ENTRY, P) == Reason.KIND_MISMATCH


def test_field_agreement_reasons() -> None:
    assert verify(_with("ranking", "cart is the second suspect."), ENTRY, P) == (
        Reason.RANK_MISMATCH
    )
    assert verify(_with("shift", "cart errors rose to 900 ms."), ENTRY, P) == (
        Reason.KIND_MISMATCH
    )
    assert (
        verify(
            _with("call_structure", "cart spent 94% of its time waiting on frontend."),
            ENTRY,
            P,
        )
        == Reason.WRONG_EDGE
    )
    assert (
        verify(
            _with(
                "contradiction",
                "D-pipe ranks ad first, while the fused verdict ranks cart first.",
            ),
            ENTRY,
            P,
        )
        == Reason.NOT_IN_DISAGREE
    )
    assert verify(_with("ranking", "cart is surely the top suspect."), ENTRY, P) == (
        Reason.WORD_NOT_ALLOWED
    )
    assert verify(_with("ranking", "cart is the top suspect.\nMore."), ENTRY, P) == (
        Reason.MALFORMED_SENTENCE
    )


def test_vocabulary_lists_are_frozen_params() -> None:
    assert {"common", "ranking", "shift", "call_structure"} <= set(P.vocabulary)
    for kind_words in P.vocabulary.values():
        assert not {"not", "no", "never", "because", "delete", "restart"} & set(
            kind_words
        )


def test_second_is_a_rank_word_not_a_unit() -> None:
    claim = SUPPORTED["ranking"].model_copy(
        update={"service": "ad", "rank": 2, "sentence": "ad is the second suspect."}
    )
    assert verify(claim, ENTRY, P) is None


def test_newline_in_a_snippet_is_malformed() -> None:
    claim = _with(
        "log_message",
        'cart logged "connection pool\\nexhausted".',
        snippet="connection pool\nexhausted",
    )
    assert verify(claim, ENTRY, P) is not None


def test_metric_name_unit_is_an_own_word() -> None:
    entry = {
        "steps": [
            *[s for s in ENTRY["steps"] if s["id"] != "P:dpipe"],
            {
                "id": "P:dpipe",
                "ranked": ["ad"],
                "items": [
                    {
                        "id": "D:ad:resource",
                        "service": "ad",
                        "text": "t",
                        "value": 2.5,
                        "before": 0.205,
                        "after": 0.634,
                        "unit": "container_cpu_utilization_ratio",
                    }
                ],
            },
        ]
    }
    claim = SUPPORTED["shift"].model_copy(
        update={
            "service": "ad",
            "channel": "resource",
            "cites": ("D:ad:resource",),
            "sentence": "ad container_cpu_utilization_ratio use rose from 0.205 to 0.634.",
        }
    )
    assert verify(claim, entry, P) is None
