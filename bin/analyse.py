#!/usr/bin/env python3
"""Run the registered analysis over a scored result store (S4.11).

Usage (from repo root; the signed ground truth needs the ledger key):
    set -a; source .env; set +a
    poetry run python bin/analyse.py --db results.duckdb --corpus build \
        --output analysis.json [--holm data_order|fixed_sequence] \
        [--a-h7 intersection_union|h_fact_only|sum]

Reads the harness-written eval tables only (eval_score, eval_run). Case groups
(system x root-cause service x fault) and service counts for the random floor
come from the signed ground truth, under the pool lock. The output is
labelled exploratory unless the confirmatory guard passes. Prints counts and
statistics only, never case IDs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bin.log_deviation import load_key
from helios.adapters.rcaeval import verify_ground_truth
from helios.analysis.run import A_H7_MODES, HOLM_READINGS, analyse
from helios.evaluation.scoring import GROUND_TRUTH_FILES, Corpus
from helios.store.result_store import ResultStore
from helios.telemetry.pool_lock import BUILD_FREEZE_TAG, PoolLockedError, build_frozen
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance

REPO_ROOT = Path(__file__).resolve().parent.parent


def case_info(corpus: str, key: bytes) -> tuple[dict[str, str], dict[str, int]]:
    """Groups and candidate-service counts per case from the signed ground truth."""
    c = Corpus(corpus)
    if c == Corpus.POOL and not build_frozen():
        raise PoolLockedError(
            f"the confirmatory ground truth stays locked until tag {BUILD_FREEZE_TAG!r}"
        )
    if c == Corpus.CAPTURES:
        return {}, {}
    cases = verify_ground_truth(REPO_ROOT / GROUND_TRUTH_FILES[c.value], key)
    groups: dict[str, str] = {}
    services: dict[str, int] = {}
    for case_id, v in cases.items():
        system = str(v.get("system") or v.get("dataset") or corpus)
        groups[case_id] = f"{system}|{v['root_cause_service']}|{v['fault']}"
        if v.get("candidate_services"):
            services[case_id] = len(v["candidate_services"])
    return groups, services


def _summary(out: dict[str, Any]) -> None:
    print(f"[analyse] {out['label']} ({out['version']}); systems {out['systems']}")
    for reason in out["guard_reasons"]:
        print(f"[analyse]   not confirmatory: {reason}")
    for family in ("family_a", "family_b"):
        fam = out[family]
        decision = {r["id"]: r for r in fam["holm_binding"]}
        for h in fam["hypotheses"]:
            p = h["p_value"]
            text = "untestable" if p is None else f"p={p:.4g}"
            row = decision[h["id"]]
            flag = row.get("rejected", row.get("below_threshold_descriptive"))
            print(
                f"[analyse] {h['id']:<5} {text:<12} n={h.get('n_pairs', 0):<4} "
                f"below Holm threshold: {flag}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--corpus", choices=[c.value for c in Corpus], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--holm", choices=HOLM_READINGS, default="data_order")
    parser.add_argument("--a-h7", choices=A_H7_MODES, default="intersection_union")
    args = parser.parse_args(argv)
    try:
        key = load_key()
        groups, services = case_info(args.corpus, key)
        store = ResultStore(args.db)
        scores = store.fetch_scores()
        runs = store.fetch_run_metrics()
        store.close()
    except PoolLockedError as exc:
        print(f"[analyse] refused: {exc}")
        return 3
    expected = len(groups) if groups else len({str(s["incident_id"]) for s in scores})
    out = analyse(
        scores,
        runs,
        expected_cases=expected,
        groups=groups,
        n_services=services,
        holm=args.holm,
        a_h7_mode=args.a_h7,
    )
    args.output.write_text(
        json.dumps(out, indent=2, default=str) + "\n", encoding="utf-8"
    )
    _summary(out)
    print(f"[analyse] wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
