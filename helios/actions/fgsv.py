"""FGSV lite: fidelity-gated shadow validation on recorded data (S4.6).

Design s4_4_7_tier2_design.md T-e/T-f, Chapter 3 Algorithm 4. Gated by
``VCLFlag.FGSV_KS_GATE`` (HELIOS-noFGSV turns it off).

- **Proposal:** one per stored run, for the fused top-1 service. Stateful
  services are never restarted by HELIOS: they get ``escalate-to-human``.
- **Twin:** the capture's normal period before the trigger, split in two. The
  earlier half stands for the twin (built from older telemetry), the later
  half for production.
- **KS gate:** per pillar (metrics, logs), the series of the target and its
  direct callers are scaled by their production half (median, MAD) and pooled;
  one two-sample KS test per pillar, Holm across pillars at ``alpha_ks``.
  A rejection, or too little data, gives STALE.
- **Replay (ASRE structural mode):** over the incident graph's call edges,
  *coverage* is the share of anomalous services the target explains (itself
  and every service that calls it, directly or not); the *blast radius* is
  the number of direct callers a restart would disturb. PASS when coverage
  reaches ``coverage_min`` and the blast radius is at most ``blast_max``.

Nothing here reads a label or changes the ranking.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

from helios.graph.anomaly_intensity import bucket_count, log_series, metric_series
from helios.schemas.ueg_c import EdgeType, NodeType, UEGCSnapshot
from helios.telemetry.log_templates import features_for_window
from helios.telemetry.scope import in_scope
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.utils import canonical_json

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from helios.schemas.telemetry import TelemetryWindow

__all__ = [
    "FGSV_PARAMS_PATH",
    "PILLARS",
    "FGSVParams",
    "Proposal",
    "callers",
    "explained_by",
    "fgsv_params_hash",
    "ks_gate",
    "load_fgsv_params",
    "propose",
    "replay",
    "split_normal",
    "stateful",
    "unvalidated_step",
    "validate",
]

FGSV_PARAMS_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "frozen" / "fgsv_params.json"
)
PILLARS = ("metrics", "logs")
_KEYS = frozenset(
    {
        "alpha_ks",
        "sample_seconds",
        "min_samples",
        "coverage_min",
        "blast_max",
        "perturb_shift",
        "provisional",
    }
)
_MAD_TO_SIGMA = 1.4826
_DIGITS = 6
_CALL_EDGES = frozenset({EdgeType.STRUCTURAL, EdgeType.CALL})
# Name rule for services HELIOS never restarts (lite: no topology roles yet).
_STATEFUL = re.compile(
    r"(db|database|redis|valkey|kafka|rabbitmq|mongo|mysql|postgres|"
    r"cache|queue|memcache|zookeeper|etcd)",
    re.IGNORECASE,
)

PASS = "PASS"
FAIL = "FAIL"
STALE = "STALE"
UNVALIDATED = "UNVALIDATED"


@dataclass(frozen=True)
class FGSVParams:
    """Frozen FGSV parameters (``data/frozen/fgsv_params.json``)."""

    alpha_ks: float
    sample_seconds: int
    min_samples: int
    coverage_min: float
    blast_max: int
    perturb_shift: float  # E-H4 fidelity break, in production-half spreads (T-f)
    provisional: bool


def load_fgsv_params(path: Path = FGSV_PARAMS_PATH) -> FGSVParams:
    """The frozen parameters; a missing file or key is an error, never a default."""
    if not path.is_file():
        raise FileNotFoundError(f"FGSV parameters not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if set(raw) != _KEYS:
        raise ValueError(f"FGSV parameter keys must be {sorted(_KEYS)}")
    params = FGSVParams(
        alpha_ks=float(raw["alpha_ks"]),
        sample_seconds=int(raw["sample_seconds"]),
        min_samples=int(raw["min_samples"]),
        coverage_min=float(raw["coverage_min"]),
        blast_max=int(raw["blast_max"]),
        perturb_shift=float(raw["perturb_shift"]),
        provisional=bool(raw["provisional"]),
    )
    if not 0 < params.alpha_ks < 1 or not 0 <= params.coverage_min <= 1:
        raise ValueError("alpha_ks must be in (0, 1) and coverage_min in [0, 1]")
    if params.sample_seconds < 1 or params.min_samples < 2 or params.blast_max < 0:
        raise ValueError("sample_seconds >= 1, min_samples >= 2, blast_max >= 0")
    return params


def fgsv_params_hash(params: FGSVParams) -> str:
    """SHA-256 of the canonical parameters (CoE parameter hashes)."""
    return hashlib.sha256(canonical_json(asdict(params)).encode("utf-8")).hexdigest()


# ── proposal ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Proposal:
    """A remediation HELIOS would recommend; never executed in Stage A."""

    kind: str  # restart | scale-out | escalate-to-human | none
    target: str | None

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "target": self.target}


def stateful(service: str) -> bool:
    """True for services HELIOS never restarts or scales (name rule)."""
    return bool(_STATEFUL.search(service))


def propose(top: str | None, signal: str | None) -> Proposal:
    """The lite proposal for the fused top-1: a resource signal scales out,
    anything else restarts; stateful services go to a person."""
    if top is None:
        return Proposal("none", None)
    if stateful(top):
        return Proposal("escalate-to-human", top)
    return Proposal("scale-out" if signal == "resource" else "restart", top)


# ── structure (ASRE structural mode) ─────────────────────────────────────────


def _call_pairs(graph: UEGCSnapshot) -> set[tuple[str, str]]:
    """(caller, callee) pairs between production services."""
    services = set(graph.candidate_ids())
    return {
        (e.source, e.target)
        for e in graph.edges
        if e.edge_type in _CALL_EDGES
        and e.source in services
        and e.target in services
        and e.source != e.target
    }


def callers(graph: UEGCSnapshot, service: str) -> list[str]:
    """Direct callers of ``service`` (the services a restart disturbs)."""
    return sorted({a for a, b in _call_pairs(graph) if b == service})


def explained_by(graph: UEGCSnapshot, service: str) -> set[str]:
    """``service`` and every service that reaches it along call edges: a fault
    in ``service`` can show up in each of them."""
    up: dict[str, set[str]] = {}
    for a, b in _call_pairs(graph):
        up.setdefault(b, set()).add(a)
    seen = {service}
    stack = [service]
    while stack:
        for a in up.get(stack.pop(), ()):
            if a not in seen:
                seen.add(a)
                stack.append(a)
    return seen


def replay(
    graph: UEGCSnapshot, target: str, anomalous: Iterable[str]
) -> dict[str, Any]:
    """Coverage and blast radius of acting on ``target``.

    Only anomalous services in the graph count: the structure says nothing
    about the others. With no anomalous service besides the target, coverage
    is full.
    """
    in_graph = set(graph.candidate_ids())
    seen = sorted(s for s in set(anomalous) if s in in_graph)
    explained = explained_by(graph, target)
    covered = [s for s in seen if s in explained]
    coverage = len(covered) / len(seen) if seen else float(1)
    disturbed = callers(graph, target)
    return {
        "anomalous": seen,
        "covered": covered,
        "coverage": round(coverage, _DIGITS),
        "callers": disturbed,
        "blast_radius": len(disturbed),
    }


def has_structure(graph: UEGCSnapshot | None, target: str) -> bool:
    """A typed call graph that contains the target."""
    return (
        isinstance(graph, UEGCSnapshot)
        and target in graph.candidate_ids()
        and bool(_call_pairs(graph))
    )


# ── twin and KS gate ─────────────────────────────────────────────────────────


def split_normal(values: np.ndarray, normal: int) -> tuple[np.ndarray, np.ndarray]:
    """(twin, production): the earlier and later half of the first ``normal``
    samples, missing samples dropped."""
    head = np.asarray(values[: max(normal, 0)], dtype="float64")
    half = len(head) // 2
    twin, prod = head[:half], head[half : 2 * half]
    return twin[~np.isnan(twin)], prod[~np.isnan(prod)]


def _scaled(
    twin: np.ndarray, prod: np.ndarray, shift: float
) -> tuple[np.ndarray, np.ndarray] | None:
    """Both halves in units of the production half's spread (median, MAD;
    the standard deviation when the MAD is zero). A series constant in both
    halves carries no fidelity signal and is skipped. ``shift`` moves the twin
    by that many units: the E-H4 fidelity break (T-f)."""
    if len(twin) == 0 or len(prod) == 0:
        return None
    centre = float(np.median(prod))
    spread = float(np.median(np.abs(prod - centre))) * _MAD_TO_SIGMA
    if spread <= 0:
        spread = float(np.std(prod))
    if spread <= 0:
        if np.all(twin == centre) and shift == 0:
            return None
        spread = float(1)
    return (twin - centre) / spread + shift, (prod - centre) / spread


def ks_gate(
    pairs: Mapping[str, Sequence[tuple[np.ndarray, np.ndarray]]],
    params: FGSVParams,
    *,
    shift: float = 0,
) -> dict[str, Any]:
    """The pillar-matched KS gate over (twin, production) sample pairs.

    Returns ``passed`` (None: not enough data in any pillar), the p-value and
    sample sizes per tested pillar, and the Holm decision across pillars.
    """
    tested: dict[str, dict[str, Any]] = {}
    for pillar in PILLARS:
        scaled = [s for t, p in pairs.get(pillar, ()) if (s := _scaled(t, p, shift))]
        if not scaled:
            continue
        twin = np.concatenate([t for t, _ in scaled])
        prod = np.concatenate([p for _, p in scaled])
        if min(len(twin), len(prod)) < params.min_samples:
            continue
        p_value = float(ks_2samp(twin, prod).pvalue)
        tested[pillar] = {
            "p": round(p_value, _DIGITS),
            "series": len(scaled),
            "n_twin": len(twin),
            "n_prod": len(prod),
        }
    if not tested:
        return {"passed": None, "pillars": {}}
    # Holm across pillars: any rejection fails the gate.
    ordered = sorted(tested.items(), key=lambda kv: kv[1]["p"])
    m = len(ordered)
    rejected = []
    for i, (pillar, row) in enumerate(ordered):
        if row["p"] < params.alpha_ks / (m - i):
            rejected.append(pillar)
        else:
            break
    return {"passed": not rejected, "pillars": tested, "rejected": rejected}


def _resolve(path: str, root: Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else root / p


def twin_pairs(
    window: TelemetryWindow,
    services: Sequence[str],
    trigger_time_s: float,
    params: FGSVParams,
    *,
    root: Path,
) -> dict[str, list[tuple[np.ndarray, np.ndarray]]]:
    """(twin, production) sample pairs per pillar for ``services``."""
    start_s = pd.Timestamp(window.window_start_iso).timestamp()
    width = params.sample_seconds
    n = bucket_count(window.window_start_iso, window.window_end_iso, width)
    normal = int((trigger_time_s - start_s) // width)
    wanted = set(services)
    out: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {p: [] for p in PILLARS}
    if window.p1_metrics_path is not None:
        metrics = pd.read_parquet(_resolve(window.p1_metrics_path, root))
        series = metric_series(
            metrics, window.window_start_iso, n, width, fold_histograms=True
        )
        for svc in sorted(wanted & set(series)):
            out["metrics"] += [split_normal(s.values, normal) for s in series[svc]]
    features = features_for_window(window, root, width)
    if features is not None:
        logs = log_series(features, window.window_start_iso, n, width)
        for svc in sorted(wanted & set(logs)):
            out["logs"] += [split_normal(s.values, normal) for s in logs[svc]]
    return out


# ── the step ─────────────────────────────────────────────────────────────────


def unvalidated_step(proposal: Proposal, mode: str) -> dict[str, Any]:
    """CoE step ``A`` without FGSV (HELIOS-noFGSV): the proposal goes to a
    person unvalidated, as Chapter 3 has it."""
    return {
        "id": "A",
        "mode": mode,
        "proposal": proposal.as_dict(),
        "fgsv": False,
        "verdict": UNVALIDATED,
        "reason": "fgsv_off",
    }


def validate(
    proposal: Proposal,
    *,
    mode: str,
    graph: UEGCSnapshot | None,
    anomalous: Iterable[str],
    pairs: Mapping[str, Sequence[tuple[np.ndarray, np.ndarray]]] | None,
    params: FGSVParams,
    shift: float = 0,
) -> dict[str, Any]:
    """CoE step ``A`` with FGSV: gate, then replay. ``pairs`` is None when the
    twin was not read (no structure, or nothing to validate)."""
    step: dict[str, Any] = {
        "id": "A",
        "mode": mode,
        "proposal": proposal.as_dict(),
        "fgsv": True,
        "perturbation": {"shift": shift} if shift else None,
    }
    target = proposal.target
    if proposal.kind in ("none", "escalate-to-human") or target is None:
        return {**step, "verdict": FAIL, "reason": f"not_actionable:{proposal.kind}"}
    if graph is None or not has_structure(graph, target):
        return {**step, "verdict": STALE, "reason": "no_structure"}
    gate = ks_gate(pairs or {}, params, shift=shift)
    step["ks"] = gate
    if gate["passed"] is None:
        return {**step, "verdict": STALE, "reason": "no_twin_data"}
    if not gate["passed"]:
        return {**step, "verdict": STALE, "reason": "ks_gate"}
    result = replay(graph, target, anomalous)
    step["replay"] = result
    if result["coverage"] < params.coverage_min:
        return {**step, "verdict": FAIL, "reason": "coverage"}
    if result["blast_radius"] > params.blast_max:
        return {**step, "verdict": FAIL, "reason": "blast_radius"}
    return {**step, "verdict": PASS, "reason": "validated"}


def anomalous_services(
    services: Sequence[str], z: np.ndarray, from_bucket: int, threshold: float
) -> list[str]:
    """In-scope services whose detector score reaches ``threshold`` at or
    after the trigger bucket (the frozen detector's own scores)."""
    out = []
    for row, svc in enumerate(services):
        tail = z[row, max(from_bucket, 0) :]
        if (
            in_scope(svc)
            and tail.size
            and np.nanmax(np.abs(tail), initial=0) >= threshold
        ):
            out.append(svc)
    return out


def node_service(graph: UEGCSnapshot, node_id: str) -> str | None:
    """The service name of a production service node (ids are service names)."""
    for n in graph.nodes:
        if n.node_id == node_id and n.node_type == NodeType.SERVICE:
            return n.service_name
    return None
