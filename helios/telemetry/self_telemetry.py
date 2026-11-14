"""IOL lite: HELIOS self-telemetry under ``tenant=self`` (S4.7).

Design s4_4_7_tier2_design.md T-g/T-h, Chapter 3 C5. Gated by
``VCLFlag.IOL_SELF_TELEMETRY`` (HELIOS-noIOL turns it off).

- One record per stored run: what each control-plane component did (wall
  time, model compute and failures, narrator fallbacks, non-convergence).
  Nearly all of it is measured already.
- The history of earlier runs becomes a ``tenant=self`` partition of the
  incident's UEG-C: one node per component, its series in the node metadata,
  structural edges between components. A run's own record is not known when
  its graph is built, so only earlier runs appear.
- The frozen trigger detector's firing rule (``decide``: threshold and
  persistence over causal z-scores) reads the partition with the run index as
  the bucket, so HELIOS's degradation is found by the same apparatus it
  applies to production, with no threshold of its own.
- The pipelines rank on the production graph only; the partition is composed
  onto it for the self-health step, so verdicts are identical with the flag
  ON and OFF.

Injection (E-H6, exploratory only): from a given run on, one component's
recorded metric is multiplied by a factor. Only the measurement changes,
never a verdict.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from helios.schemas.ueg_c import (
    TENANT_SELF,
    EdgeType,
    NodeType,
    UEGCEdge,
    UEGCNode,
    UEGCSnapshot,
)
from helios.telemetry.trigger import (
    DetectorParams,
    ServiceScores,
    TriggerSource,
    causal_z,
    decide,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "COMPONENTS",
    "HISTORY_RUNS",
    "INJECTION_PROTOCOL_PATH",
    "Injection",
    "SelfTelemetry",
    "check_protocol",
    "detect_degradation",
    "parse_injection",
    "self_partition",
    "with_self_partition",
]

COMPONENTS = (
    "helios.consensus",
    "helios.dpipe",
    "helios.gpipe",
    "helios.lpipe",
    "helios.model",
    "helios.narrator",
)
# Who calls whom inside HELIOS (structural, tenant=self).
_CALLS = (
    ("helios.consensus", "helios.dpipe"),
    ("helios.consensus", "helios.gpipe"),
    ("helios.consensus", "helios.lpipe"),
    ("helios.lpipe", "helios.model"),
    ("helios.narrator", "helios.model"),
)
# Event counts (Poisson scale in causal_z); everything else is a gauge.
_COUNTS = frozenset({"errors", "fallbacks", "non_converged"})
# Runs of history the detector reads (bounded cost per run).
HISTORY_RUNS = 200
# E-H6 severity ladder, frozen on build data (owner decision 2026-11-14):
# one exploratory campaign per factor.
INJECTION_PROTOCOL_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "frozen" / "iol_injection.json"
)


@dataclass(frozen=True)
class Injection:
    """Synthetic control-plane degradation (E-H6, T-h)."""

    component: str
    metric: str
    from_run: int
    factor: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "metric": self.metric,
            "from_run": self.from_run,
            "factor": self.factor,
        }


def parse_injection(spec: str) -> Injection:
    """``component=helios.model,metric=compute_ms,from=40,factor=3``."""
    parts = dict(p.split("=", 1) for p in spec.split(",") if "=" in p)
    try:
        inj = Injection(
            component=parts["component"],
            metric=parts["metric"],
            from_run=int(parts["from"]),
            factor=float(parts["factor"]),
        )
    except (KeyError, ValueError) as exc:
        raise ValueError(f"bad injection spec {spec!r}: {exc}") from None
    if inj.component not in COMPONENTS or inj.from_run < 0 or inj.factor <= 0:
        raise ValueError(f"bad injection spec {spec!r}")
    return inj


def check_protocol(inj: Injection, path: Path = INJECTION_PROTOCOL_PATH) -> None:
    """Refuse an injection outside the frozen E-H6 ladder."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if (
        inj.component != raw["component"]
        or inj.metric != raw["metric"]
        or inj.from_run != int(raw["from_run"])
        or inj.factor not in [float(f) for f in raw["factors"]]
    ):
        raise ValueError(
            f"injection {inj.as_dict()} is outside the frozen E-H6 protocol {raw}"
        )


@dataclass
class SelfTelemetry:
    """The run-by-run self-telemetry of one orchestrator (one variant).

    ``path`` (optional) keeps the history across resumed runs: one JSON line
    per run.
    """

    path: Path | None = None
    injection: Injection | None = None
    records: list[dict[str, dict[str, float]]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.path is not None and self.path.is_file():
            with self.path.open(encoding="utf-8") as fh:
                self.records = [
                    json.loads(line)["metrics"] for line in fh if line.strip()
                ]

    def record(self, run_id: str, metrics: Mapping[str, Mapping[str, float]]) -> None:
        """Add one run (after injection, if any)."""
        index = len(self.records)
        row = {c: {k: float(v) for k, v in m.items()} for c, m in metrics.items()}
        inj = self.injection
        if inj is not None and index >= inj.from_run:
            part = row.setdefault(inj.component, {})
            if inj.metric in part:
                part[inj.metric] *= inj.factor
        self.records.append(row)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps({"run_id": run_id, "index": index, "metrics": row})
                    + "\n"
                )

    def series(self) -> dict[str, dict[str, list[float]]]:
        """Per component and metric, the last ``HISTORY_RUNS`` values (NaN where
        a run had no value, e.g. a skipped pipeline)."""
        recent = self.records[-HISTORY_RUNS:]
        names: dict[str, set[str]] = {}
        for rec in recent:
            for comp, metrics in rec.items():
                names.setdefault(comp, set()).update(metrics)
        return {
            comp: {
                m: [float(rec.get(comp, {}).get(m, np.nan)) for rec in recent]
                for m in sorted(names[comp])
            }
            for comp in sorted(names)
        }


def self_partition(
    series: Mapping[str, Mapping[str, Sequence[float]]],
) -> tuple[list[UEGCNode], list[UEGCEdge]]:
    """The ``tenant=self`` nodes and edges for a series history."""
    nodes = [
        UEGCNode(
            node_id=comp,
            node_type=NodeType.SERVICE,
            service_name=comp,
            tenant=TENANT_SELF,
            metadata={
                "series": json.dumps(
                    {
                        m: [None if np.isnan(v) else v for v in vals]
                        for m, vals in series.get(comp, {}).items()
                    },
                    sort_keys=True,
                )
            },
        )
        for comp in COMPONENTS
    ]
    edges = [
        UEGCEdge(source=a, target=b, edge_type=EdgeType.STRUCTURAL, weight=1)
        for a, b in _CALLS
    ]
    return nodes, edges


def with_self_partition(
    graph: UEGCSnapshot | None,
    series: Mapping[str, Mapping[str, Sequence[float]]],
    *,
    incident_id: str,
    config_hash: str,
    captured_at_iso: str,
) -> UEGCSnapshot:
    """The incident graph with the self partition composed onto it (a
    self-only graph when the incident has none)."""
    nodes, edges = self_partition(series)
    if not isinstance(graph, UEGCSnapshot):
        return UEGCSnapshot(
            incident_id=incident_id,
            variant_config_hash=config_hash,
            nodes=nodes,
            edges=edges,
            captured_at_iso=captured_at_iso,
        )
    return graph.model_copy(
        update={"nodes": [*graph.nodes, *nodes], "edges": [*graph.edges, *edges]}
    )


def _component_z(metrics: Mapping[str, Sequence[float]], n: int) -> np.ndarray:
    """A component's score per run: the largest causal z over its metrics
    (rises only: degradation is slower, more errors, more fallbacks)."""
    rows = [
        causal_z(
            np.asarray(vals, dtype="float64"),
            count_series=name in _COUNTS,
            upward_only=True,
        )
        for name, vals in metrics.items()
    ]
    if not rows:
        return np.full(n, np.nan)
    with np.errstate(all="ignore"):
        stacked = np.vstack(rows)
        out = np.full(n, np.nan)
        finite = np.isfinite(stacked).any(axis=0)
        out[finite] = np.nanmax(stacked[:, finite], axis=0)
    return out


def detect_degradation(
    graph: UEGCSnapshot, detector: DetectorParams, *, first_run: int
) -> dict[str, Any]:
    """Read the self partition of ``graph`` with the frozen firing rule.

    The run index is the bucket (``first_run`` is the index of the oldest
    run in the history). Returns the degraded component and the run it was
    first seen in, or none.
    """
    selves = [
        n for n in graph.nodes if n.tenant == TENANT_SELF and n.node_id in COMPONENTS
    ]
    per = {
        n.node_id: {
            m: [np.nan if v is None else v for v in vals]
            for m, vals in json.loads(n.metadata.get("series", "{}")).items()
        }
        for n in selves
    }
    n_runs = max((len(v) for m in per.values() for v in m.values()), default=0)
    if n_runs == 0:
        return {"degraded": None, "runs_read": 0}
    services = sorted(per)
    z = np.vstack([_component_z(per[s], n_runs) for s in services])
    run_params = DetectorParams(
        bucket_seconds=1,
        threshold=detector.threshold,
        persistence=detector.persistence,
        provisional=detector.provisional,
    )
    record = decide(
        ServiceScores(services=services, z=z, start_s=float(first_run)),
        run_params,
        incident_id="helios-self",
    )
    if record.source != TriggerSource.THRESHOLD or not record.suspects:
        return {"degraded": None, "runs_read": n_runs}
    return {
        "degraded": record.suspects[0],
        "from_run": int(record.trigger_time_s),
        "known_at_run": None if record.known_at_s is None else int(record.known_at_s),
        "runs_read": n_runs,
    }
