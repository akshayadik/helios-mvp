"""Five-component CpR (S1.10): hand-computed cost matches on a fixture."""

from __future__ import annotations

import hashlib
import math
from typing import TYPE_CHECKING

import pytest

from helios.evaluation.cost import (
    PRICE_BOOK_PATH,
    IncidentUsage,
    PriceBook,
    cpr,
    incident_usage,
    load_price_book,
    window_bytes,
)
from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.schemas.verdict import (
    PipelineName,
    PipelineVerdict,
    VerdictCost,
    VerdictStatus,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path

# Round coefficients so every component can be worked by hand.
_BOOK = """---
version: test-book
currency: USD
as_of: "2026-10-26"
token_prompt_per_million: 2
token_completion_per_million: 4
cpu_per_vcpu_hour: 3.6
gpu_per_hour: 36
storage_per_gib_month: 2
storage_retention_months: 3
human_per_hour: 60
human_review_minutes: 10
opportunity_per_minute: 120
ttcd_censor_s: 1800
---

# Test price book
"""


@pytest.fixture()
def book(tmp_path: Path) -> PriceBook:
    path = tmp_path / "price_book.md"
    path.write_text(_BOOK, encoding="utf-8")
    return load_price_book(path)


USAGE = IncidentUsage(
    prompt_tokens=500_000,  # x 2 / 1e6 = 1
    completion_tokens=250_000,  # x 4 / 1e6 = 1
    cpu_ms=2_000,  # 2 s x 3.6 / 3600 = 0.002
    gpu_ms=3_000,  # 3 s x 36 / 3600 = 0.03
    storage_bytes=2**29,  # 1/2 GiB x 2 x 3 months = 3
)


def test_hand_computed_cost(book: PriceBook) -> None:
    c = cpr(USAGE, requests_human=True, ttcd_s=90, book=book)
    assert c.token == pytest.approx(2)
    assert c.infrastructure == pytest.approx(0.032)
    assert c.storage == pytest.approx(3)
    assert c.human == pytest.approx(10)  # 10 min x 60 / 60
    assert c.opportunity == pytest.approx(180)  # 1.5 min x 120
    assert c.total == pytest.approx(195.032)
    assert c.log_total == pytest.approx(math.log(195.032))
    assert not c.censored
    assert c.price_book_version == "test-book"


def test_automatic_verdict_carries_no_human_time(book: PriceBook) -> None:
    c = cpr(USAGE, requests_human=False, ttcd_s=90, book=book)
    assert c.human == 0
    assert c.total == pytest.approx(185.032)


@pytest.mark.parametrize("ttcd", [None, 1800, 5000])
def test_no_correct_verdict_is_censored_at_the_window(
    book: PriceBook, ttcd: float | None
) -> None:
    c = cpr(USAGE, requests_human=False, ttcd_s=ttcd, book=book)
    assert c.censored
    assert c.ttcd_s == 1800
    assert c.opportunity == pytest.approx(3_600)  # 30 min x 120


def test_zero_infrastructure_or_negative_ttcd_is_refused(book: PriceBook) -> None:
    with pytest.raises(ValueError, match="never zero"):
        cpr(IncidentUsage(prompt_tokens=5), requests_human=False, ttcd_s=1, book=book)
    with pytest.raises(ValueError, match="negative"):
        cpr(USAGE, requests_human=False, ttcd_s=-1, book=book)


def test_frozen_price_book_and_a_hand_computed_incident() -> None:
    real = load_price_book()
    assert real.version == "price-book-v1"
    assert real.currency == "USD"
    assert real.digest == hashlib.sha256(PRICE_BOOK_PATH.read_bytes()).hexdigest()
    usage = IncidentUsage(
        prompt_tokens=2_000,
        completion_tokens=300,
        cpu_ms=4_000,
        gpu_ms=12_000,
        storage_bytes=3 * 2**30,
    )
    c = cpr(usage, requests_human=True, ttcd_s=240, book=real)
    assert c.token == 0  # local inference
    # 4 s x 0.048 / 3600 + 12 s x 1.006 / 3600
    assert c.infrastructure == pytest.approx(4 * 0.048 / 3600 + 12 * 1.006 / 3600)
    assert c.storage == pytest.approx(3 * 0.023)
    assert c.human == pytest.approx(15 * 63.98 / 60)
    assert c.opportunity == pytest.approx(4 * 5600)
    assert c.total == pytest.approx(22416.0674067, rel=1e-9)


def test_price_book_must_be_complete_and_non_negative(tmp_path: Path) -> None:
    path = tmp_path / "b.md"
    path.write_text(_BOOK.replace("gpu_per_hour: 36\n", ""), encoding="utf-8")
    with pytest.raises(ValueError, match="gpu_per_hour"):
        load_price_book(path)
    path.write_text(_BOOK.replace("gpu_per_hour: 36", "gpu_per_hour: -1"))
    with pytest.raises(ValueError, match="negative"):
        load_price_book(path)
    path.write_text("# no front matter\n")
    with pytest.raises(ValueError, match="front matter"):
        load_price_book(path)


def _verdict(pipeline: PipelineName, run_id: str, cost: VerdictCost) -> PipelineVerdict:
    return PipelineVerdict(
        run_id=run_id,
        incident_id="inc-1",
        variant_config_hash="a" * 64,
        snapshot_hash="b" * 64,
        pipeline=pipeline,
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        status=VerdictStatus.SKIPPED,
        latency_ms=1,
        cost=cost,
    )


def test_incident_usage_sums_the_run(tmp_path: Path) -> None:
    verdicts = [
        _verdict(PipelineName.DPIPE, "r", VerdictCost(cpu_ms=40)),
        _verdict(PipelineName.GPIPE, "r", VerdictCost()),
        _verdict(
            PipelineName.LPIPE,
            "r",
            VerdictCost(prompt_tokens=210, completion_tokens=50, cpu_ms=5, gpu_ms=750),
        ),
    ]
    usage = incident_usage(verdicts, storage_bytes=7)
    assert usage == IncidentUsage(210, 50, 45, 750, 7)
    with pytest.raises(ValueError, match="more than one run"):
        incident_usage(
            [*verdicts, _verdict(PipelineName.DPIPE, "other", VerdictCost())]
        )


def test_window_bytes_counts_recorded_streams(tmp_path: Path) -> None:
    (tmp_path / "m.parquet").write_bytes(b"x" * 300)
    (tmp_path / "t.parquet").write_bytes(b"x" * 20)
    window = TelemetryWindow(
        incident_id="inc-1",
        variant_config_hash="a" * 64,
        window_start_iso="2026-01-01T00:00:00Z",
        window_end_iso="2026-01-01T00:05:00Z",
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        p1_metrics_path="m.parquet",
        p2_traces_path="t.parquet",
        p3_logs_path="missing.parquet",
    )
    assert window_bytes(window, tmp_path) == 320
