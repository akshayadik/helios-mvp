#!/usr/bin/env python3
"""Score stored runs after dispatch (S1.9 scoring path).

Usage (from repo root; build and pool ground truth need the ledger key):
    poetry run python bin/score_runs.py --db results.duckdb --corpus build
    poetry run python bin/score_runs.py --db results.duckdb --corpus captures
    poetry run python bin/score_runs.py --db results.duckdb --corpus build \
        --metrics --captures data/rcaeval/build   # also eval_run (S4.9)

Reads result_row and consensus_verdict from the results database, joins them
to the corpus' ground truth and writes eval_score (helios/evaluation/scoring.py).
With --metrics it then writes eval_run (S4.9: TTT, TTCD, CpR under the
price book's primary profile, H_struct, the ambiguous stratum from the
HELIOS-Full runs), reading each incident's recorded bytes from --captures.
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
from helios.evaluation.cost import load_price_book, window_bytes
from helios.evaluation.run_metrics import score_run_metrics
from helios.evaluation.scoring import (
    Corpus,
    GroundTruth,
    load_ground_truth,
    mean_scores,
    score_store,
)
from helios.evaluation.strata import (
    load_inject_times,
    load_tau,
    narrative_heavy_by_incident,
    novelty_share,
)
from helios.store.result_store import ResultStore
from helios.telemetry.log_templates import read_window_logs
from helios.telemetry.pool_lock import PoolLockedError
from helios.telemetry.reader import CaptureReader
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance
from helios.vcl.variants import CONFIRMATORY_VARIANTS

REPO_ROOT = Path(__file__).resolve().parent.parent


def narrative_strata(
    reader: CaptureReader, incidents: set[str], gt: GroundTruth, key: bytes | None
) -> dict[str, bool] | None:
    """A-H6 stratum per incident once tau_N is frozen; None before (or no key)."""
    tau = load_tau(REPO_ROOT)
    if tau is None or key is None or gt.corpus == Corpus.CAPTURES:
        return None
    inject = load_inject_times(gt.corpus, root=REPO_ROOT, key=key)
    shares: dict[str, float | None] = {}
    for incident_id in sorted(incidents & inject.keys()):
        logs = read_window_logs(reader.read(incident_id).window, REPO_ROOT)
        counts = None if logs is None else novelty_share(logs, inject[incident_id])
        shares[incident_id] = None if counts is None else counts.share
    return narrative_heavy_by_incident(shares, tau)


def run_metrics(
    store: ResultStore, gt: GroundTruth, captures: Path, key: bytes | None = None
) -> int:
    """Write eval_run; print counts and medians only (no case, no label)."""
    book = load_price_book()
    reader = CaptureReader(captures)
    incidents = {str(f["incident_id"]) for f in store.fetch_all_fusion_rows()}
    storage = {i: window_bytes(reader.read(i).window, REPO_ROOT) for i in incidents}
    full = CONFIRMATORY_VARIANTS["HELIOS-Full"].compute_variant_config_hash()
    heavy = narrative_strata(reader, incidents, gt, key)
    report = score_run_metrics(
        store,
        gt,
        book,
        storage_bytes=storage,
        full_config_hash=full,
        narrative_heavy=heavy,
    )
    if heavy is None:
        print("[metrics] narrative-heavy stratum: tau_N not frozen, left empty")
    else:
        print(
            f"[metrics] narrative-heavy: {sum(heavy.values())} of {len(heavy)} "
            "incidents with post-injection logs"
        )
    rows = report.rows

    def median(key: str) -> float:
        values = sorted(float(r[key]) for r in rows)
        return values[len(values) // 2] if values else float("nan")

    print(
        f"[metrics] {report.scored} runs, {report.unlabelled} without a label; "
        f"price book {book.provider} {book.digest[:12]}"
    )
    if rows:
        censored = sum(bool(r["ttcd_censored"]) for r in rows)
        print(
            f"[metrics] median graph_build_ms={median('graph_build_ms'):.0f} "
            f"ttt_ms={median('ttt_ms'):.0f} ttcd_s={median('ttcd_s'):.2f} "
            f"(censored {censored}) log_cpr={median('log_cpr'):.3f}"
        )
    return 0


def score(db: Path, corpus: str, captures: Path | None = None) -> int:
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
    if captures is not None:
        try:
            run_metrics(store, gt, captures, key)
        except PoolLockedError as exc:
            print(f"[metrics] refused: {exc}")
            store.close()
            return 3
    store.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--corpus", choices=[c.value for c in Corpus], required=True)
    parser.add_argument(
        "--metrics", action="store_true", help="also write eval_run (S4.9)"
    )
    parser.add_argument(
        "--captures", type=Path, help="capture directory of the corpus (--metrics)"
    )
    args = parser.parse_args(argv)
    if not args.db.is_file():
        print(f"[score] no results database at {args.db}")
        return 2
    if args.metrics and args.captures is None:
        print("[score] --metrics needs --captures (recorded bytes for CpR storage)")
        return 2
    return score(args.db, args.corpus, args.captures if args.metrics else None)


if __name__ == "__main__":
    sys.exit(main())
