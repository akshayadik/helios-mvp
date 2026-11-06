"""Router features (S3.1 design §5.2): label-free, from the cheap stage only.

The router reads the D-pipe verdict and its in-scope candidate scores, the
PPR disagreement value (the May gate's quantity), the frozen signal type and
whether traces are present; after G-pipe ran, also the G-pipe verdict. It
never reads a fusion output: noConsensus routes with vote-only fusion, so a
router that read MAHC could route Full and noConsensus differently and break
A-H4's pairing.

Signal type is three indicators against the bias term (unclassified sets
none), so the indicators are not collinear with the bias. Values are rounded
to six digits, the ``canonical_json`` convention, so reruns are bitwise equal.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from helios.schemas.verdict import VerdictStatus
from helios.telemetry.scope import in_scope
from helios.telemetry.signal_type import SignalType
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping

    from helios.schemas.verdict import PipelineVerdict

__all__ = ["FEATURE_NAMES", "cheap_features", "with_gpipe"]

HELIOS_ENABLE_ROUTER_FEATURES: bool = True

FEATURE_NAMES: tuple[str, ...] = (
    "bias",
    "d_mu",
    "d_sigma",
    "d_top1_share",
    "d_margin",
    "gate_value",
    "signal_resource",
    "signal_latency",
    "signal_error",
    "traces",
    "g_ran",
    "g_mu",
    "g_sigma",
    "dg_top1_agree",
    "dg_top3_overlap",
)
_DIGITS = 6
_TOP = 3
_G_START = FEATURE_NAMES.index("g_ran")


def _ranked(v: PipelineVerdict) -> list[str]:
    if v.status != VerdictStatus.RANKED:
        return []
    return [s for s in v.ranked_candidates if in_scope(s)]


def _share_and_margin(
    ranked: list[str], scores: Mapping[str, float]
) -> tuple[float, float]:
    """Top-1 share of the in-scope scores and (s1 - s2) / s1; one candidate is
    the whole share and the full margin. Non-positive totals give zeros."""
    values = [max(float(scores.get(s, 0)), 0) for s in ranked]
    total = sum(values)
    if not values or total <= 0:
        return 0, 0
    top = values[0]
    second = values[1] if len(values) > 1 else 0
    return top / total, ((top - second) / top) if top > 0 else 0


def _round(x: list[float]) -> tuple[float, ...]:
    return tuple(round(float(v), _DIGITS) for v in x)


def cheap_features(
    d: PipelineVerdict,
    d_scores: Mapping[str, float],
    *,
    gate_value: float | None,
    signal: SignalType,
    traces: bool,
) -> tuple[float, ...]:
    """Features known after the D-pipe; the G block is zero (``g_ran`` = 0)."""
    ranked = _ranked(d)
    share, margin = _share_and_margin(ranked, d_scores)
    ok = bool(ranked)
    x: list[float] = [
        1,
        (d.mu or 0) if ok else 0,
        d.sigma if ok and d.sigma is not None else 1,
        share,
        margin,
        gate_value or 0,
        1 if signal == SignalType.RESOURCE else 0,
        1 if signal == SignalType.LATENCY else 0,
        1 if signal == SignalType.ERROR else 0,
        1 if traces else 0,
        0,  # g_ran
        0,  # g_mu
        1,  # g_sigma: unknown
        0,  # dg_top1_agree
        0,  # dg_top3_overlap
    ]
    return _round(x)


def with_gpipe(
    x: tuple[float, ...], g: PipelineVerdict, d: PipelineVerdict
) -> tuple[float, ...]:
    """``x`` with the G block filled from a G-pipe verdict that has a list;
    unchanged when G-pipe was skipped, failed or abstained."""
    g_ranked = _ranked(g)
    if not g_ranked:
        return x
    d_ranked = _ranked(d)
    agree = bool(d_ranked) and d_ranked[0] == g_ranked[0]
    overlap = len(set(d_ranked[:_TOP]) & set(g_ranked[:_TOP])) / _TOP
    block = [
        1,
        g.mu or 0,
        g.sigma if g.sigma is not None else 1,
        1 if agree else 0,
        overlap,
    ]
    return _round([*x[:_G_START], *block])
