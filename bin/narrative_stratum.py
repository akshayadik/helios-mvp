#!/usr/bin/env python3
"""Compute and freeze tau_N, the narrative-heavy threshold (A-H6; S4.9 M-e).

Usage (from repo root; the signed ground truth needs the ledger key):
    set -a; source .env; set +a
    poetry run python bin/narrative_stratum.py fit      # write the report once
    poetry run python bin/narrative_stratum.py freeze   # write data/frozen/narrative_tau.json

``fit`` computes each build case's novel-template share (helios.evaluation.strata)
over the RCAEval build corpus and sets tau_N to their median. The OTel v3 build
corpus is reported beside it, not pooled (its log volume differs). The report,
``docs/sprints/s4-product-eval-tooling/calibration/narrative_share.json``, has
aggregates only, never an incident ID or log text. ``fit`` refuses when the
report exists; ``freeze`` copies the reviewed report's tau_N and refuses to
replace an existing frozen file. The pool is never read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bin.log_deviation import load_key
from helios.evaluation.scoring import Corpus
from helios.evaluation.strata import (
    STRATUM_VERSION,
    TAU_PATH,
    is_narrative_heavy,
    load_inject_times,
    median_tau,
    novelty_share,
    tau_params_hash,
)
from helios.telemetry.log_templates import (
    BUCKET_SECONDS,
    DRAIN_DEPTH,
    DRAIN_SIM_TH,
    read_window_logs,
)
from helios.telemetry.reader import CaptureReader
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT = Path("docs/sprints/s4-product-eval-tooling/calibration/narrative_share.json")

# corpus -> (capture directory, manifest with case_order)
CORPORA: dict[str, tuple[Path, Path]] = {
    Corpus.BUILD.value: (
        Path("data/rcaeval/build"),
        Path("data/rcaeval/build_manifest.json"),
    ),
    Corpus.OTEL_BUILD_V3.value: (
        Path("data/otel/build_v3"),
        Path("data/otel/build_v3_manifest.json"),
    ),
}
QUANTILES = (10, 25, 50, 75, 90)  # percent, on a 5 % grid
GRID = 20


def corpus_shares(corpus: str, key: bytes) -> dict[str, Any]:
    """Shares of one build corpus (aggregates only) plus the raw share list."""
    directory, manifest_path = CORPORA[corpus]
    manifest = json.loads((REPO_ROOT / manifest_path).read_text(encoding="utf-8"))
    order: list[str] = manifest["case_order"]
    inject = load_inject_times(corpus, root=REPO_ROOT, key=key)
    reader = CaptureReader(REPO_ROOT / directory, seal_key=key)
    shares: list[float] = []
    no_logs = no_post = no_pre = seal_failed = 0
    post_lines = novel_lines = 0
    for incident_id in order:
        capture = reader.read(incident_id)
        if not capture.intact:
            seal_failed += 1
            continue
        logs = read_window_logs(capture.window, REPO_ROOT)
        counts = None if logs is None else novelty_share(logs, inject[incident_id])
        if counts is None:
            no_logs += 1
            continue
        share = counts.share
        if share is None:
            no_post += 1
            continue
        no_pre += counts.pre_lines == 0
        post_lines += counts.post_lines
        novel_lines += counts.novel_post_lines
        shares.append(share)
    return {
        "corpus": corpus,
        "windows": len(order),
        "seal_failed": seal_failed,
        "without_logs": no_logs,
        "without_post_injection_logs": no_post,
        "without_pre_injection_logs": no_pre,
        "with_share": len(shares),
        "post_injection_lines": post_lines,
        "novel_post_injection_lines": novel_lines,
        "shares": shares,
    }


def _summary(block: dict[str, Any], tau: float) -> dict[str, Any]:
    shares: list[float] = block.pop("shares")
    out = dict(block)
    if shares:
        cuts = statistics.quantiles(shares, n=GRID, method="inclusive")
        out["share_min"] = round(min(shares), 6)
        out["share_quantiles"] = {
            f"p{q}": round(cuts[q // 5 - 1], 6) for q in QUANTILES
        }
        out["share_max"] = round(max(shares), 6)
        out["narrative_heavy_at_tau"] = sum(
            bool(is_narrative_heavy(s, tau)) for s in shares
        )
    return out


def _commit() -> str:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return head.stdout.strip()


def fit() -> int:
    if (REPO_ROOT / REPORT).exists():
        print(f"[stratum] {REPORT} exists: fit runs once", file=sys.stderr)
        return 2
    key = load_key()
    build = corpus_shares(Corpus.BUILD.value, key)
    otel = corpus_shares(Corpus.OTEL_BUILD_V3.value, key)
    tau = median_tau(build["shares"])
    report: dict[str, Any] = {
        "version": STRATUM_VERSION,
        "commit": _commit(),
        "drain": {
            "sim_th": DRAIN_SIM_TH,
            "depth": DRAIN_DEPTH,
            "bucket_seconds": BUCKET_SECONDS,
        },
        "tau_n": round(tau, 6),
        "tau_source": "median over RCAEval build cases with post-injection logs",
        "build": _summary(build, tau),
        "otel_build_v3_descriptive": _summary(otel, tau),
    }
    path = REPO_ROOT / REPORT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"[stratum] tau_N={report['tau_n']} over {report['build']['with_share']} cases"
    )
    print(f"[stratum] report {REPORT}")
    return 0


def freeze() -> int:
    target = REPO_ROOT / TAU_PATH
    if target.exists():
        print(f"[stratum] {TAU_PATH} exists: not replaced", file=sys.stderr)
        return 2
    report_path = REPO_ROOT / REPORT
    if not report_path.exists():
        print("[stratum] no report: run fit first", file=sys.stderr)
        return 2
    report = json.loads(report_path.read_text(encoding="utf-8"))
    params = {
        "version": STRATUM_VERSION,
        "tau_n": report["tau_n"],
        "corpus": Corpus.BUILD.value,
        "cases": report["build"]["with_share"],
        "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "fit_commit": report["commit"],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(params, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"[stratum] frozen tau_N={params['tau_n']} hash {tau_params_hash(params)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("fit", help="compute shares and tau_N once; write the report")
    sub.add_parser("freeze", help="freeze the reviewed report's tau_N")
    args = parser.parse_args(argv)
    return fit() if args.command == "fit" else freeze()


if __name__ == "__main__":
    sys.exit(main())
