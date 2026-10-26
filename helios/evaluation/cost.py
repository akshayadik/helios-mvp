"""Cost per Resolution (CpR) — the five-component cost of one incident (S1.10).

Metric contract §3: CpR = token + infrastructure + storage + human time +
opportunity, in one currency, under the price book frozen before the build
freeze (docs/tracking/price_book.md), analysed as log(CpR). This is Ch3's
Plane 7 Critic Agent computation (p. 130). Usage comes from the stored
verdicts (``PipelineVerdict.cost``: tokens, CPU and GPU time, metered by the
orchestrator and the LLM gateway), the incident's telemetry bytes, the
published verdict's state and the time to correct diagnosis (TTCD).

Like accuracy scores, cost is computed after dispatch; a verdict records
usage, never money, so a price change never changes a stored verdict.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Iterable

    from helios.schemas.telemetry import TelemetryWindow
    from helios.schemas.verdict import PipelineVerdict

__all__ = [
    "PRICE_BOOK_PATH",
    "CostBreakdown",
    "IncidentUsage",
    "PriceBook",
    "cpr",
    "incident_usage",
    "load_price_book",
    "window_bytes",
]

HELIOS_ENABLE_COST: bool = True

PRICE_BOOK_PATH = Path(__file__).resolve().parents[2] / "docs/tracking/price_book.md"
_S_PER_H = 3_600
_S_PER_MIN = 60
_MS_PER_S = 1_000
_PER_MILLION = 1_000_000
_BYTES_PER_GIB = 2**30
_STREAMS = (
    "p1_metrics_path",
    "p2_traces_path",
    "p3_logs_path",
    "p4_events_path",
    "p5_profiles_path",
)


@dataclass(frozen=True)
class PriceBook:
    """Coefficients of docs/tracking/price_book.md; ``digest`` identifies the file."""

    version: str
    currency: str
    token_prompt_per_million: float
    token_completion_per_million: float
    cpu_per_vcpu_hour: float
    gpu_per_hour: float
    storage_per_gib_month: float
    storage_retention_months: float
    human_per_hour: float
    human_review_minutes: float
    opportunity_per_minute: float
    ttcd_censor_s: float
    digest: str


def load_price_book(path: Path = PRICE_BOOK_PATH) -> PriceBook:
    """Read the YAML front matter of the price book; every field is required."""
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) < 3 or parts[0].strip():
        raise ValueError(f"{path}: no YAML front matter")
    raw: dict[str, Any] = yaml.safe_load(parts[1])
    fields = [f for f in PriceBook.__dataclass_fields__ if f != "digest"]
    missing = sorted(set(fields) - set(raw))
    if missing:
        raise ValueError(f"{path}: price book lacks {missing}")
    values: dict[str, Any] = {f: raw[f] for f in fields}
    for f in fields:
        if f in ("version", "currency"):
            values[f] = str(values[f])
        else:
            values[f] = float(values[f])
            if values[f] < 0:
                raise ValueError(f"{path}: {f} must not be negative")
    return PriceBook(**values, digest=hashlib.sha256(text.encode()).hexdigest())


@dataclass(frozen=True)
class IncidentUsage:
    """Resources one incident run consumed, summed over its pipeline verdicts."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cpu_ms: float = 0
    gpu_ms: float = 0
    storage_bytes: int = 0


def incident_usage(
    verdicts: Iterable[PipelineVerdict], *, storage_bytes: int = 0
) -> IncidentUsage:
    """Sum the cost usage of one run's verdicts (skipped pipelines add nothing)."""
    verdicts = list(verdicts)
    if len({v.run_id for v in verdicts}) > 1:
        raise ValueError("verdicts of more than one run")
    return IncidentUsage(
        prompt_tokens=sum(v.cost.prompt_tokens for v in verdicts),
        completion_tokens=sum(v.cost.completion_tokens for v in verdicts),
        cpu_ms=sum(v.cost.cpu_ms for v in verdicts),
        gpu_ms=sum(v.cost.gpu_ms for v in verdicts),
        storage_bytes=storage_bytes,
    )


def window_bytes(window: TelemetryWindow, root: Path) -> int:
    """Bytes of the incident's recorded telemetry streams (P1-P5) on disk."""
    total = 0
    for name in _STREAMS:
        rel = getattr(window, name, None)
        if rel and (root / rel).is_file():
            total += (root / rel).stat().st_size
    return total


@dataclass(frozen=True)
class CostBreakdown:
    """The five CpR components and their sum, in the price book's currency."""

    token: float
    infrastructure: float
    storage: float
    human: float
    opportunity: float
    ttcd_s: float
    censored: bool
    price_book_version: str
    price_book_digest: str

    @property
    def total(self) -> float:
        return (
            self.token
            + self.infrastructure
            + self.storage
            + self.human
            + self.opportunity
        )

    @property
    def log_total(self) -> float:
        """log(CpR), the analysed form (A-H5, B-H7)."""
        return math.log(self.total)


def cpr(
    usage: IncidentUsage,
    *,
    requests_human: bool,
    ttcd_s: float | None,
    book: PriceBook,
) -> CostBreakdown:
    """Five-component CpR of one incident.

    ``ttcd_s`` is the time to correct diagnosis; None (no correct published
    verdict) or anything beyond the censoring point counts as censored.
    Infrastructure time is never zero for a real run, so a zero is refused
    (it would mean usage was not recorded).
    """
    if usage.cpu_ms <= 0 and usage.gpu_ms <= 0:
        raise ValueError(
            "no CPU or GPU time recorded: infrastructure cost is never zero"
        )
    if ttcd_s is not None and ttcd_s < 0:
        raise ValueError("ttcd_s must not be negative")
    censored = ttcd_s is None or ttcd_s >= book.ttcd_censor_s
    ttcd = book.ttcd_censor_s if censored or ttcd_s is None else ttcd_s
    token = (
        usage.prompt_tokens * book.token_prompt_per_million
        + usage.completion_tokens * book.token_completion_per_million
    ) / _PER_MILLION
    infrastructure = (
        usage.cpu_ms / _MS_PER_S * book.cpu_per_vcpu_hour / _S_PER_H
        + usage.gpu_ms / _MS_PER_S * book.gpu_per_hour / _S_PER_H
    )
    storage = (
        usage.storage_bytes
        / _BYTES_PER_GIB
        * book.storage_per_gib_month
        * book.storage_retention_months
    )
    human = (
        book.human_review_minutes * book.human_per_hour / _S_PER_MIN
        if requests_human
        else 0
    )
    opportunity = ttcd / _S_PER_MIN * book.opportunity_per_minute
    return CostBreakdown(
        token=token,
        infrastructure=infrastructure,
        storage=storage,
        human=human,
        opportunity=opportunity,
        ttcd_s=ttcd,
        censored=censored,
        price_book_version=book.version,
        price_book_digest=book.digest,
    )
