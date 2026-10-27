#!/usr/bin/env python3
"""Calibrate the shared detection trigger on both build corpora (S2.1, S2-M7-EVAL01).

Usage (from repo root, with the ledger key that signs the build labels):
    set -a; source .env; set +a
    poetry run python bin/trigger_calibrate.py [--workers N]

Scores every build window once per bucket size (helios.telemetry.trigger
.service_scores, in parallel, results in a fixed order), sweeps threshold and
persistence on those scores (``decide``), applies the selection rule fixed in
helios.evaluation.trigger_calibration, and audits the selected setting on
cropped windows. Writes docs/sprints/s2-reasoning/s2_1_trigger_calibration.json
(aggregates only) and prints counts. Exit 1 when no setting meets the owner's
5% limit on every corpus or the audit fails: the result then goes to the owner.
The confirmatory pool is never read.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from itertools import product
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bin.log_deviation import load_key
from helios.evaluation.trigger_calibration import (
    CORPORA,
    CROP_FRACTIONS,
    FALSE_RATE_LIMIT,
    GRID,
    CalibrationCase,
    CorpusResult,
    audit_passes,
    crop_starts,
    evaluate,
    load_cases,
    select,
)
from helios.telemetry.trigger import (
    WARMUP_BUCKETS,
    DetectorParams,
    ServiceScores,
    TriggerRecord,
    TriggerSource,
    decide,
    detector_hash,
    service_scores,
)
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance
from helios.vcl.utils import canonical_json

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT = Path("docs/sprints/s2-reasoning/s2_1_trigger_calibration.json")


def _score(job: tuple[CalibrationCase, int, float]) -> ServiceScores:
    case, bucket, crop = job
    return service_scores(case.window, bucket, root=REPO_ROOT, crop_start_s=crop)


def _scores(
    pool: ProcessPoolExecutor, jobs: list[tuple[CalibrationCase, int, float]]
) -> list[ServiceScores]:
    return list(pool.map(_score, jobs, chunksize=4))


def _records(
    scores: list[ServiceScores], cases: list[CalibrationCase], params: DetectorParams
) -> list[TriggerRecord]:
    return [
        decide(s, params, incident_id=c.incident_id)
        for s, c in zip(scores, cases, strict=True)
    ]


def _params(bucket: float, threshold: float, persistence: float) -> DetectorParams:
    return DetectorParams(
        bucket_seconds=int(bucket),
        threshold=float(threshold),
        persistence=int(persistence),
        provisional=False,
    )


def _audit(
    pool: ProcessPoolExecutor,
    params: DetectorParams,
    cases: list[CalibrationCase],
    full: list[TriggerRecord],
) -> dict[str, Any]:
    out: dict[str, Any] = {"crops": {}, "passes": True}
    for index, fraction in enumerate(CROP_FRACTIONS):
        usable = [
            (i, c, starts[index])
            for i, c in enumerate(cases)
            if (starts := crop_starts(c, params.bucket_seconds))
        ]
        subset = [c for _, c, _ in usable]
        uncropped = evaluate(
            [full[i] for i, _, _ in usable],
            subset,
            bucket_seconds=params.bucket_seconds,
        )
        scores = _scores(pool, [(c, params.bucket_seconds, s) for _, c, s in usable])
        cropped = evaluate(
            _records(scores, subset, params),
            subset,
            bucket_seconds=params.bucket_seconds,
        )
        passes = audit_passes(
            uncropped, {fraction: cropped}, bucket_seconds=params.bucket_seconds
        )
        out["crops"][str(fraction)] = {
            "cases": len(usable),
            "skipped_no_slack": len(cases) - len(usable),
            "uncropped": uncropped.as_dict(),
            "cropped": cropped.as_dict(),
            "passes": passes,
        }
        out["passes"] = out["passes"] and passes
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--corpus", choices=(*CORPORA, "pool"), action="append")
    args = parser.parse_args(argv)
    if args.corpus and "pool" in args.corpus:
        print("[calibrate] the pool is locked until tag build-freeze", file=sys.stderr)
        return 2

    key = load_key()
    cases = {c: load_cases(c, root=REPO_ROOT, key=key) for c in CORPORA}
    for corpus, items in cases.items():
        print(f"[calibrate] {corpus}: {len(items)} cases")

    results: dict[DetectorParams, dict[str, CorpusResult]] = {}
    records: dict[DetectorParams, dict[str, list[TriggerRecord]]] = {}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for bucket in GRID["bucket_seconds"]:
            scores = {
                corpus: _scores(pool, [(c, int(bucket), 0) for c in items])
                for corpus, items in cases.items()
            }
            print(f"[calibrate] scored bucket {int(bucket)} s")
            for threshold, persistence in product(
                GRID["threshold"], GRID["persistence"]
            ):
                params = _params(bucket, threshold, persistence)
                records[params] = {
                    corpus: _records(scores[corpus], items, params)
                    for corpus, items in cases.items()
                }
                results[params] = {
                    corpus: evaluate(
                        records[params][corpus],
                        items,
                        bucket_seconds=params.bucket_seconds,
                    )
                    for corpus, items in cases.items()
                }
        selected = select(results)
        audit: dict[str, Any] = {}
        if selected is not None:
            audit = {
                corpus: _audit(pool, selected, items, records[selected][corpus])
                for corpus, items in cases.items()
            }

    report: dict[str, Any] = {
        "detector_version": "trigger-v1",
        "warmup_buckets": WARMUP_BUCKETS,
        "false_rate_limit": FALSE_RATE_LIMIT,
        "grid": {k: list(v) for k, v in GRID.items()},
        "crop_fractions": list(CROP_FRACTIONS),
        "results": [
            {
                "bucket_seconds": p.bucket_seconds,
                "threshold": p.threshold,
                "persistence": p.persistence,
                **{corpus: r.as_dict() for corpus, r in by_corpus.items()},
            }
            for p, by_corpus in results.items()
        ],
        "selected": None,
        "audit": audit,
    }
    if selected is not None:
        chosen = results[selected]
        report["selected"] = {
            "bucket_seconds": selected.bucket_seconds,
            "threshold": selected.threshold,
            "persistence": selected.persistence,
            "detector_hash": detector_hash(selected),
            **{corpus: r.as_dict() for corpus, r in chosen.items()},
            "context_nonempty": {
                corpus: sum(bool(r.context) for r in recs)
                for corpus, recs in records[selected].items()
            },
            "fallbacks": {
                corpus: sum(r.source == TriggerSource.FALLBACK for r in recs)
                for corpus, recs in records[selected].items()
            },
        }
    text = json.dumps(json.loads(canonical_json(report)), indent=2, sort_keys=True)
    (REPO_ROOT / REPORT).write_text(text + "\n", encoding="utf-8")

    qualifying = sum(
        all(r.false_rate <= FALSE_RATE_LIMIT for r in by_corpus.values())
        for by_corpus in results.values()
    )
    print(
        f"[calibrate] {len(results)} settings; {qualifying} meet the 5% limit on every corpus"
    )
    if selected is None:
        print("[calibrate] NO SETTING QUALIFIES — stop and report to the owner")
        return 1
    print(
        f"[calibrate] selected bucket {selected.bucket_seconds} s, threshold "
        f"{selected.threshold:g}, persistence {selected.persistence}"
    )
    for corpus, r in results[selected].items():
        print(
            f"[calibrate]   {corpus}: n {r.n}, true {r.true}, false {r.false} "
            f"({r.false_rate:.1%}), no trigger {r.no_trigger}, excluded {r.excluded}, "
            f"median delay {r.median_delay_s} s, root among suspects {r.root_among_suspects}"
        )
    passes = all(a["passes"] for a in audit.values())
    print(f"[calibrate] crop audit {'PASSES' if passes else 'FAILS'}")
    return 0 if passes else 1


if __name__ == "__main__":
    sys.exit(main())
