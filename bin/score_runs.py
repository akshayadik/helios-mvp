#!/usr/bin/env python3
"""Score stored runs after dispatch (S1.9 scoring path).

Usage (from repo root; build and pool ground truth need the ledger key):
    poetry run python bin/score_runs.py --db results.duckdb --corpus build
    poetry run python bin/score_runs.py --db results.duckdb --corpus captures

Reads result_row and consensus_verdict from the results database, joins them
to the corpus' ground truth and writes eval_score (helios/evaluation/scoring.py).
Prints counts and per-list means only — never a case name, incident ID or
label. The pool's ground truth, and any confirmatory run, are refused until
tag build-freeze exists.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bin.log_deviation import load_key
from helios.evaluation.scoring import (
    Corpus,
    load_ground_truth,
    mean_scores,
    score_store,
)
from helios.store.result_store import ResultStore
from helios.telemetry.pool_lock import PoolLockedError
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance

REPO_ROOT = Path(__file__).resolve().parent.parent


def score(db: Path, corpus: str) -> int:
    key = None if corpus == Corpus.CAPTURES else load_key()
    try:
        gt = load_ground_truth(corpus, root=REPO_ROOT, key=key)
        store = ResultStore(db)
        report = score_store(store, gt)
    except PoolLockedError as exc:
        print(f"[score] refused: {exc}")
        return 3
    groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in report.rows:
        groups[str(row["list_kind"]), str(row["source"])].append(row)
    print(
        f"[score] {corpus}: {report.scored} lists scored, "
        f"{report.skipped_pipelines} skipped pipelines not scored, "
        f"{report.unlabelled} without a label (not imputed); "
        f"ground truth {gt.digest[:12]}"
    )
    for (kind, source), rows in sorted(groups.items()):
        means = mean_scores(rows)
        print(
            f"[score] {kind} {source}: n={len(rows)} "
            + " ".join(f"{k}={v:.3f}" for k, v in means.items())
        )
    store.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--corpus", choices=[c.value for c in Corpus], required=True)
    args = parser.parse_args(argv)
    if not args.db.is_file():
        print(f"[score] no results database at {args.db}")
        return 2
    return score(args.db, args.corpus)


if __name__ == "__main__":
    sys.exit(main())
