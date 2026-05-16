"""Stage C: directional propagation — Spearman P1→P1, topology-boost P1→non-P1."""

from __future__ import annotations

import math
from dataclasses import dataclass

import scipy.stats

from helios.schemas.ueg_c import EdgeType, UEGCEdge
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


@dataclass
class PropagationEngine:
    rho_threshold: float
    topology_boost_factor: float

    def propagate(
        self,
        scores: dict[str, float],
        error_deltas: dict[str, list[float]],
        call_edges: list[UEGCEdge],
        *,
        p1_services: list[str],
    ) -> dict[str, float]:
        p1_set = set(p1_services)
        boost: dict[str, float] = {}

        for edge in call_edges:
            if edge.edge_type != EdgeType.CALL:
                continue
            caller, callee = edge.source, edge.target
            if caller not in p1_set:
                continue

            if callee in p1_set:
                a = [x for x in error_deltas.get(caller, []) if not math.isnan(x)]
                b = [x for x in error_deltas.get(callee, []) if not math.isnan(x)]
                n = min(len(a), len(b))
                if n >= 2:
                    rho_val, _ = scipy.stats.spearmanr(a[:n], b[:n])
                    rho = float(rho_val) if not math.isnan(float(rho_val)) else 0.00
                    if rho >= self.rho_threshold:
                        boost[callee] = boost.get(callee, 0.00) + rho * scores.get(
                            caller, 0.00
                        )
            else:
                new_boost = self.topology_boost_factor * scores.get(caller, 0.00)
                boost[callee] = max(boost.get(callee, 0.00), new_boost)

        all_services = set(scores.keys()) | set(boost.keys())
        return {s: scores.get(s, 0.00) + boost.get(s, 0.00) for s in all_services}
