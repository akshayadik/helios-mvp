"""The three G-pipe candidates (S2.2 design §5.2), simplest last.

- ``plain_ppr``: today's traversal — personalised PageRank over every UEG-C
  edge, seeded by D-pipe's scores.
- ``weighted_ppr``: the walk over call edges only, caller → callee, weighted
  by the caller's wait share after the trigger, plus a self-loop weighted by
  the service's self share; restart vector = D-pipe's scores, multiplied by
  ``LEADER_RESTART_FACTOR`` for a service that leads one of its callers.
  Mass flows from victims to the callees they wait on and pools where a
  service does its own work. Constants fixed before the selection run.
- ``LinearRanker``: a linear score over ``FEATURE_COLUMNS``, fitted with a
  pairwise logistic loss (the root against every other service of its
  window) and L2 strength ``RIDGE_LAMBDA``, by a deterministic solver.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import networkx as nx
import numpy as np
from scipy.optimize import minimize

from helios.evaluation.scoring import service_key
from helios.pipelines.g_pipe.features import FEATURE_COLUMNS, assert_no_identity
from helios.pipelines.g_pipe.gpipe_config import GPIPE_PPR_ALPHA
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from helios.pipelines.g_pipe.features import GraphFeatures
    from helios.schemas.ueg_c import UEGCSnapshot

__all__ = [
    "LEADER_RESTART_FACTOR",
    "RIDGE_LAMBDA",
    "LinearRanker",
    "plain_ppr",
    "weighted_ppr",
]

LEADER_RESTART_FACTOR: int = 2
RIDGE_LAMBDA: float = 1


def plain_ppr(snapshot: UEGCSnapshot, seeds: Mapping[str, float]) -> dict[str, float]:
    """PageRank over every edge of the graph, candidates only (unchanged)."""
    graph: nx.DiGraph = nx.DiGraph()
    for node in snapshot.nodes:
        graph.add_node(node.node_id)
    for edge in snapshot.edges:
        graph.add_edge(edge.source, edge.target, weight=edge.weight)
    personalization: dict[str, float] | None = {
        k: v for k, v in seeds.items() if k in graph.nodes
    }
    if not personalization or sum(personalization.values()) <= 0:
        personalization = None
    raw: dict[str, float] = nx.pagerank(
        graph, alpha=GPIPE_PPR_ALPHA, personalization=personalization
    )
    candidates = set(snapshot.candidate_ids())
    return {k: v for k, v in raw.items() if k in candidates}


def weighted_ppr(
    features: GraphFeatures, seeds: Mapping[str, float]
) -> dict[str, float]:
    """The feature-weighted walk over ``features.services``."""
    graph: nx.DiGraph = nx.DiGraph()
    graph.add_nodes_from(features.services)
    for service in features.services:
        graph.add_edge(service, service, weight=features.self_share.get(service, 1))
    for (caller, callee), share in sorted(features.edge_wait_after.items()):
        if share > 0:
            graph.add_edge(caller, callee, weight=share)
    restart = {
        s: float(seeds.get(s, 0))
        * (LEADER_RESTART_FACTOR if s in features.leaders else 1)
        for s in features.services
    }
    personalization = restart if sum(restart.values()) > 0 else None
    scores: dict[str, float] = nx.pagerank(
        graph, alpha=GPIPE_PPR_ALPHA, personalization=personalization
    )
    return {s: scores[s] for s in features.services}


def _root_row(features: GraphFeatures, root: str, stem: bool) -> int | None:
    names = [service_key(s) for s in features.services] if stem else features.services
    target = service_key(root) if stem else root
    return names.index(target) if target in names else None


@dataclass(frozen=True)
class LinearRanker:
    """Standardised linear score over FEATURE_COLUMNS."""

    weights: tuple[float, ...]
    mean: tuple[float, ...]
    scale: tuple[float, ...]

    @classmethod
    def fit(cls, examples: Sequence[tuple[GraphFeatures, str, bool]]) -> LinearRanker:
        """Fit on (features, root label, stem matching) windows; windows whose
        root is not a ranked service carry no pair and are skipped."""
        for features, _, _ in examples:
            assert_no_identity(FEATURE_COLUMNS, features.services)
        rows = np.vstack([f.table for f, _, _ in examples])
        mean = rows.mean(axis=0)
        scale = rows.std(axis=0)
        scale[scale == 0] = 1
        diffs = []
        for features, root, stem in examples:
            r = _root_row(features, root, stem)
            if r is None:
                continue
            x = (features.table - mean) / scale
            diffs.append(x[r] - np.delete(x, r, axis=0))
        d = np.vstack(diffs)

        def loss(w: np.ndarray) -> tuple[float, np.ndarray]:
            margin = d @ w
            value = np.logaddexp(0, -margin).mean() + RIDGE_LAMBDA * (w @ w) / 2
            grad = -(d.T @ (1 / (1 + np.exp(margin)))) / len(d) + RIDGE_LAMBDA * w
            return float(value), grad

        result = minimize(loss, np.zeros(d.shape[1]), jac=True, method="L-BFGS-B")
        return cls(
            weights=tuple(float(v) for v in result.x),
            mean=tuple(float(v) for v in mean),
            scale=tuple(float(v) for v in scale),
        )

    def score(self, features: GraphFeatures) -> dict[str, float]:
        """Linear score of every service of the window."""
        x = (features.table - np.array(self.mean)) / np.array(self.scale)
        values = x @ np.array(self.weights)
        return {s: float(v) for s, v in zip(features.services, values, strict=True)}
