"""Select the G-pipe candidate on the build cases (S2.2 design §5.3).

Usage:
    set -a; source .env; set +a
    poetry run python bin/gpipe_select.py [--workers 8]

Per case: the frozen trigger, the graph the runner builds (HELIOS-Full), the
frozen D-pipe verdict, then the three candidates — plain PPR, feature-weighted
PPR, and the learned ranker scored by leaving one fault type out (trained on
the other faults). The routing gate is ignored; the gated view is reported
beside the selection. Writes ``docs/sprints/s2-reasoning/s2_2_gpipe_selection.json``
(aggregates only, never an incident ID) and prints counts. It never writes the
frozen parameter file; the owner reviews the result first.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bin.log_deviation import load_key
from helios.evaluation.gpipe_calibration import (
    CANDIDATES,
    MARGIN_HITS,
    GPipeCase,
    load_gpipe_cases,
    root_folds,
    select_gpipe,
)
from helios.evaluation.scoring import score_ranking
from helios.orchestrator.runner import incident_graph
from helios.pipelines.d_pipe.params import dpipe_params_hash, load_dpipe_params
from helios.pipelines.d_pipe.pipeline import run_dpipe
from helios.pipelines.g_pipe.features import GraphFeatures, compute_features
from helios.pipelines.g_pipe.gpipe_config import DISAGREEMENT_THRESHOLD
from helios.pipelines.g_pipe.params import GPipeParams, gpipe_params_hash
from helios.pipelines.g_pipe.pipeline import compute_ppr_disagreement
from helios.pipelines.g_pipe.rankers import LinearRanker, plain_ppr, weighted_ppr
from helios.telemetry.trigger import detect, detector_hash, load_detector_params
from helios.vcl import get_variant, set_current_manifest
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance
from helios.vcl.utils import canonical_json

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT = Path("docs/sprints/s2-reasoning/s2_2_gpipe_selection.json")
VARIANT = "HELIOS-Full"
_DIGITS = 6


@dataclass(frozen=True)
class _Scored:
    fault: str
    root: str
    stem: bool
    corpus: str
    trigger_source: str
    has_graph: bool
    gated: bool
    features: GraphFeatures | None
    dpipe: list[str]
    ppr: list[str]
    weighted: list[str]


def _ranked(scores: dict[str, float]) -> list[str]:
    return sorted(scores, key=scores.__getitem__, reverse=True)


def _absolute(case: GPipeCase) -> Any:
    window = case.window
    for attr in ("p1_metrics_path", "p2_traces_path", "p3_logs_path"):
        value = getattr(window, attr)
        if value is not None and not Path(value).is_absolute():
            window = window.model_copy(update={attr: str(REPO_ROOT / value)})
    return window


def _score_case(case: GPipeCase) -> _Scored:
    manifest = get_variant(VARIANT)
    set_current_manifest(manifest)
    config_hash = manifest.compute_variant_config_hash()
    detector = load_detector_params()
    dp = load_dpipe_params()
    window = _absolute(case)
    trigger = detect(window, detector, root=REPO_ROOT)
    graph, _seeds = incident_graph(window, manifest, config_hash, trigger)
    out = run_dpipe(
        window=window,
        ueg_c=graph,
        incident_id=window.incident_id,
        snapshot_hash=window.compute_window_hash(),
        variant_config_hash=config_hash,
        evaluation_phase=window.evaluation_phase,
        run_id="gpipe-select",
        trigger=trigger,
        evidence_ref=detector.threshold,
        w_error=dp.w_error,
        w_resource=dp.w_resource,
        rho_threshold=dp.rho_threshold,
        topology_boost_factor=dp.topology_boost_factor,
    )
    seeds: dict[str, float] = dict(out.get("candidate_scores") or {})
    corpus = "earlier_captures" if case.stem else "otel_build_v3"
    base = _Scored(
        fault=case.fault,
        root=case.root_cause,
        stem=case.stem,
        corpus=corpus,
        trigger_source=trigger.source.value,
        has_graph=False,
        gated=False,
        features=None,
        dpipe=list(out.get("ranked_candidates") or []),
        ppr=[],
        weighted=[],
    )
    if graph is None:
        return base
    ppr = plain_ppr(graph, seeds)
    features = compute_features(
        window, trigger, seeds, ppr, graph.candidate_ids(), detector, root=REPO_ROOT
    )
    weighted = weighted_ppr(features, seeds) if features is not None else ppr
    return replace(
        base,
        has_graph=True,
        gated=compute_ppr_disagreement(seeds) >= DISAGREEMENT_THRESHOLD,
        features=features,
        ppr=_ranked(ppr),
        weighted=_ranked(weighted),
    )


def _hit(ranked: list[str], s: _Scored) -> int:
    return score_ranking(ranked, s.root, stem=s.stem).hr_at_3 if ranked else 0


def _learned_lofo(scored: list[_Scored]) -> list[list[str]]:
    """Each case ranked by a model trained on the other root services."""
    rankings: list[list[str]] = [s.ppr for s in scored]  # fallback: plain PPR
    for train_idx, test_idx in root_folds([s.root for s in scored]):
        train = [
            (f, scored[i].root, scored[i].stem)
            for i in train_idx
            if (f := scored[i].features) is not None
        ]
        model = LinearRanker.fit(train)
        for i in test_idx:
            f = scored[i].features
            if f is not None:
                rankings[i] = _ranked(model.score(f))
    return rankings


def _by_fault(values: list[int], scored: list[_Scored]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for v, s in zip(values, scored, strict=True):
        out.setdefault(s.fault, []).append(v)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--corpus", choices=("build", "pool"), default="build")
    args = parser.parse_args(argv)
    if args.corpus == "pool":
        print("[gpipe] the pool is locked until tag build-freeze", file=sys.stderr)
        return 2
    detector = load_detector_params()
    dp = load_dpipe_params()
    if detector.provisional or dp.provisional:
        print(
            "[gpipe] detector or D-pipe parameters are provisional; freeze them first",
            file=sys.stderr,
        )
        return 2

    cases = load_gpipe_cases(root=REPO_ROOT, key=load_key())
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        scored = list(pool.map(_score_case, cases, chunksize=2))
    learned = _learned_lofo(scored)
    rankings = {
        "learned": learned,
        "weighted_ppr": [s.weighted for s in scored],
        "ppr": [s.ppr for s in scored],
    }
    hits = {
        name: _by_fault(
            [_hit(r, s) for r, s in zip(ranks, scored, strict=True)], scored
        )
        for name, ranks in rankings.items()
    }
    dpipe_hits = _by_fault([_hit(s.dpipe, s) for s in scored], scored)
    selected = select_gpipe(hits)
    refit = LinearRanker.fit(
        [(s.features, s.root, s.stem) for s in scored if s.features is not None]
    )
    learned_params = GPipeParams(ranker="learned", model=refit, provisional=False)
    gated = [i for i, s in enumerate(scored) if s.gated]
    report: dict[str, Any] = {
        "variant": VARIANT,
        "detector_hash": detector_hash(detector),
        "dpipe_params_hash": dpipe_params_hash(dp),
        "cases": len(scored),
        "cases_by_corpus": dict(sorted(Counter(s.corpus for s in scored).items())),
        "trigger_sources": {
            corpus: dict(
                sorted(
                    Counter(
                        s.trigger_source for s in scored if s.corpus == corpus
                    ).items()
                )
            )
            for corpus in sorted({s.corpus for s in scored})
        },
        "cases_without_graph": sum(not s.has_graph for s in scored),
        "feature_fallbacks": sum(s.has_graph and s.features is None for s in scored),
        "margin_hits": MARGIN_HITS,
        "hr_at_3": {
            name: {
                "total": sum(sum(v) for v in hits[name].values()),
                "by_fault": {f: sum(v) for f, v in sorted(hits[name].items())},
            }
            for name in CANDIDATES
        },
        "dpipe_hr_at_3": {
            "total": sum(sum(v) for v in dpipe_hits.values()),
            "by_fault": {f: sum(v) for f, v in sorted(dpipe_hits.items())},
        },
        "gated_view": {
            "cases": len(gated),
            **{
                name: sum(_hit(rankings[name][i], scored[i]) for i in gated)
                for name in CANDIDATES
            },
        },
        "selected": selected,
        "learned_refit": {
            **learned_params.as_dict(),
            "gpipe_params_hash": gpipe_params_hash(learned_params),
        },
    }
    text = json.dumps(json.loads(canonical_json(report)), indent=2, sort_keys=True)
    (REPO_ROOT / REPORT).write_text(text + "\n", encoding="utf-8")
    print(
        f"[gpipe] {len(scored)} cases; feature fallbacks {report['feature_fallbacks']}; gated {len(gated)}"
    )
    for name in CANDIDATES:
        print(
            f"[gpipe]   {name}: HR@3 hits {report['hr_at_3'][name]['total']}/{len(scored)}"
        )
    print(
        f"[gpipe]   dpipe: HR@3 hits {report['dpipe_hr_at_3']['total']}/{len(scored)}"
    )
    print(f"[gpipe] selected by the rule: {selected}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
