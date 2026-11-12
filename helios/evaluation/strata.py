"""Narrative-heavy stratum (A-H6; metric contract §7; S4.9 design M-e).

A case is narrative-heavy when the share of its post-injection log lines whose
template is not seen in the pre-injection part of the window is at or above
tau_N, the median of that share over the RCAEval build cases.

- Templates are the S1.4 Drain3 templates (``helios.telemetry.log_templates``,
  same parameters and masks), mined once over the whole window in canonical
  order, so a pre- and a post-injection line of one message shape get the same
  template.
- "Seen" is window-wide: a template counts as seen when any service emits it
  before the injection time.
- The split point is the injection time from the signed ground truth. Only the
  evaluation harness reads it, under the same lock as the labels; it is never
  passed to a pipeline.
- A case without post-injection log lines has no share and no stratum (None):
  it is reported and counted, never imputed.

tau_N is computed once on build data (``bin/narrative_stratum.py fit``) and
frozen in ``data/frozen/narrative_tau.json`` with a deviation entry.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

from helios.adapters.rcaeval import verify_ground_truth
from helios.evaluation.scoring import GROUND_TRUTH_FILES, Corpus
from helios.telemetry.log_templates import line_templates
from helios.telemetry.pool_lock import BUILD_FREEZE_TAG, PoolLockedError, build_frozen
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

__all__ = [
    "STRATUM_VERSION",
    "TAU_PATH",
    "NoveltyShare",
    "inject_unix",
    "is_narrative_heavy",
    "load_inject_times",
    "load_tau",
    "median_tau",
    "narrative_heavy_by_incident",
    "novelty_share",
    "tau_params_hash",
]

HELIOS_ENABLE_NARRATIVE_STRATUM: bool = True

STRATUM_VERSION = "narrative-stratum-v1"
TAU_PATH = Path("data/frozen/narrative_tau.json")


@dataclass(frozen=True)
class NoveltyShare:
    """Line counts of one window split at the injection time."""

    pre_lines: int
    post_lines: int
    novel_post_lines: int
    novel_post_templates: int

    @property
    def share(self) -> float | None:
        """Novel post-injection lines / post-injection lines; None without any."""
        if self.post_lines == 0:
            return None
        return self.novel_post_lines / self.post_lines


def novelty_share(logs: pd.DataFrame, inject_at: float) -> NoveltyShare | None:
    """Novelty counts of P3 log rows (timestamp, service_name, body); None if empty.

    ``inject_at`` is the injection time in Unix seconds. Lines at or after it
    are post-injection.
    """
    frame, _ = line_templates(logs)
    if frame.empty:
        return None
    cut = pd.Timestamp(inject_at, unit="s", tz="UTC")
    pre = frame[frame["ts"] < cut]
    post = frame[frame["ts"] >= cut]
    seen = set(pre["template_id"])
    novel = post[~post["template_id"].isin(seen)]
    return NoveltyShare(
        pre_lines=len(pre),
        post_lines=len(post),
        novel_post_lines=len(novel),
        novel_post_templates=int(novel["template_id"].nunique()),
    )


def inject_unix(value: Any) -> float:
    """Injection time in Unix seconds from a ground-truth value (number or ISO)."""
    if isinstance(value, bool):
        raise TypeError("injection time must be a number or an ISO timestamp")
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        stamp = pd.Timestamp(value)
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        return float(stamp.timestamp())
    raise TypeError("injection time must be a number or an ISO timestamp")


def load_inject_times(
    corpus: Corpus | str,
    *,
    root: Path,
    key: bytes,
    frozen: Callable[[], bool] = build_frozen,
) -> dict[str, float]:
    """Injection times (Unix seconds) of a signed corpus, under the label lock."""
    corpus = Corpus(corpus)
    if corpus == Corpus.POOL and not frozen():
        raise PoolLockedError(
            f"the confirmatory ground truth stays locked until tag {BUILD_FREEZE_TAG!r}"
        )
    if corpus == Corpus.CAPTURES:
        raise ValueError("the S0 captures carry no injection time")
    cases = verify_ground_truth(root / GROUND_TRUTH_FILES[corpus.value], key)
    return {k: inject_unix(v["inject_time"]) for k, v in cases.items()}


def median_tau(shares: Iterable[float | None]) -> float:
    """tau_N: the median of the defined shares (mean of the middle two if even)."""
    values = [s for s in shares if s is not None]
    if not values:
        raise ValueError("tau_N needs at least one case with post-injection logs")
    return float(statistics.median(values))


def is_narrative_heavy(share: float | None, tau: float) -> bool | None:
    """At or above tau_N; None when the case has no share."""
    if share is None:
        return None
    return share >= tau


def narrative_heavy_by_incident(
    shares: Mapping[str, float | None], tau: float
) -> dict[str, bool]:
    """Stratum flag per incident; incidents without a share are left out."""
    flags = {i: is_narrative_heavy(s, tau) for i, s in shares.items()}
    return {i: f for i, f in flags.items() if f is not None}


def tau_params_hash(params: Mapping[str, Any]) -> str:
    """First 12 hex digits of the SHA-256 of the canonical frozen-tau JSON."""
    text = json.dumps(dict(params), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def load_tau(root: Path, path: Path = TAU_PATH) -> float | None:
    """The frozen tau_N, or None before it is frozen."""
    full = path if path.is_absolute() else root / path
    if not full.exists():
        return None
    params = json.loads(full.read_text(encoding="utf-8"))
    if params.get("version") != STRATUM_VERSION:
        raise ValueError(f"{full}: unexpected stratum version")
    return float(params["tau_n"])
