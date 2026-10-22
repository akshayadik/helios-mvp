"""Hit-rate-at-k metric for RCA evaluation."""

from __future__ import annotations

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

HELIOS_ENABLE_EVALUATION_METRICS: bool = True


def hr_at_k(verdicts: list[str], ground_truth: str, *, k: int) -> int:
    """Return 1 if ground_truth appears in verdicts[:k], else 0."""
    return int(ground_truth in verdicts[:k])
