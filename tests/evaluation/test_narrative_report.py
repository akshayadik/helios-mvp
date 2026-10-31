"""Machine verification report (S2.8 owner decision N-h, design §5.8)."""

from __future__ import annotations

import inspect
from typing import Any

from helios.evaluation import narrative_report as module
from helios.evaluation.narrative_report import narrative_report
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def _slot(
    source: str,
    attempts: int,
    claims: list[str],
    *,
    fallback: bool = False,
    rejections: list[list[Any]] | None = None,
    drafted: int = 0,
    accepted: int = 0,
) -> dict[str, Any]:
    return {
        "source": source,
        "attempts": attempts,
        "fallback": fallback,
        "rejections": rejections or [],
        "drafted_first": drafted,
        "accepted_first": accepted,
        "claims": [{"kind": "ranking", "sentence": s, "cites": ["F"]} for s in claims],
    }


ROWS = [
    {
        "narrator": "llm",
        "slots": {
            "story": _slot("llm", 1, ["a b c", "d e"], drafted=2, accepted=2),
            "contradictions": _slot(
                "llm", 2, ["x"], rejections=[[0, "rank_mismatch"]], drafted=1
            ),
            "verification": _slot(
                "template",
                2,
                ["q r s t"],
                fallback=True,
                rejections=[[0, "verb_not_allowed"], [-1, "schema"]],
                drafted=1,
            ),
        },
    },
    {
        "narrator": "template",
        "slots": {
            "story": _slot("template", 0, ["a b c d"]),
            "contradictions": _slot("template", 0, []),
            "verification": _slot("template", 0, ["e f"]),
        },
    },
]


def test_report_counts_and_rates() -> None:
    report = narrative_report(ROWS)
    llm = report["llm"]
    assert llm["narratives"] == 1
    assert llm["claims_displayed"] == 4
    assert llm["first_pass_claim_acceptance"] == 2 / 4
    assert llm["slots_called"] == 3
    assert llm["first_pass_slot_acceptance"] == 1 / 3
    assert llm["retry_success"] == 1 / 2
    assert llm["slot_fallback_rate"] == 1 / 3
    assert llm["rejections"] == {"rank_mismatch": 1, "verb_not_allowed": 1, "schema": 1}
    # Style shapes by who wrote the slot (review I6): the llm narrator's
    # template-fallback slot is counted with the template's sentences.
    assert llm["style"]["llm"]["sentence_words"]["mean"] == (3 + 2 + 1) / 3
    assert llm["style"]["template"]["sentence_words"]["mean"] == 4
    assert llm["style"]["llm"]["claims_per_slot"]["mean"] == 3 / 2
    tmpl = report["template"]
    assert tmpl["narratives"] == 1 and tmpl["claims_displayed"] == 2
    assert tmpl["slots_called"] == 0 and tmpl["slot_fallback_rate"] is None
    assert tmpl["style"]["template"]["claims_per_slot"]["mean"] == 1


def test_digest_level_fallback_is_counted() -> None:
    # Model unreachable before any call: attempts 0, fallback True.
    rows = [
        {
            "narrator": "llm",
            "slots": {
                "story": _slot("template", 0, ["a"], fallback=True),
                "contradictions": _slot("template", 0, []),
                "verification": _slot("template", 0, ["b"], fallback=True),
            },
        }
    ]
    llm = narrative_report(rows)["llm"]
    assert llm["slots_called"] == 2
    assert llm["slot_fallback_rate"] == 1


def test_report_reads_no_ground_truth() -> None:
    source = inspect.getsource(module)
    for word in ("ground_truth", "root_cause", "inject", "fault"):
        assert word not in source
    assert list(inspect.signature(narrative_report).parameters) == ["rows"]
