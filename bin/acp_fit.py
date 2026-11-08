"""Fit and freeze the Action-Class Predictor on build cases (S3.2 design P-d).

Usage (from the repository root; the runner reads repo-relative stream paths):
    set -a; source .env; set +a
    poetry run python bin/acp_fit.py            # one cross-fitted fit, report
    poetry run python bin/acp_fit.py --freeze   # write data/frozen/acp_params.json

Runs HELIOS-noLLM (ACP on, no L-pipe calls: the ACP features are known
before any L-pipe step) over both sealed build corpora into a scratch store,
reads each case's ACP features back from the run's own CoE ledger, maps its
fault type to a remediation family (``FAULT_CLASS``, entry 82), and reports
five-fold cross-fitted accuracy, macro-F1, log loss and confusion, overall and
per corpus, plus the fit on all cases. Writes
``docs/sprints/s3-routing/calibration/acp_fit.json`` (aggregates only, never
an incident ID). The fit runs once: the tool refuses when the report exists.
``--freeze`` writes the reviewed report's fit to ``data/frozen/acp_params.json``
and refuses to replace an existing frozen file.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bin.log_deviation import load_key
from bin.mahc_build_run import BUILD_CORPORA
from helios.acp.params import (
    ACP_PARAMS_PATH,
    acp_params_from_dict,
    acp_params_hash,
    write_acp_params,
)
from helios.adapters.rcaeval import verify_ground_truth
from helios.evaluation.acp_fit import (
    FAULT_CLASS,
    ACPCase,
    cross_fit,
    fit_params,
    scores,
)
from helios.evaluation.trigger_calibration import CORPORA
from helios.orchestrator.runner import RunOrchestrator
from helios.vcl import get_variant, set_current_manifest
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance
from helios.vcl.utils import canonical_json

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT = REPO_ROOT / "docs/sprints/s3-routing/calibration/acp_fit.json"
VARIANT = "HELIOS-noLLM"
LAMBDA = 1
FOLDS = 5


class _CountingLedger:
    def __init__(self) -> None:
        self.count = 0

    def append(self, fields: dict[str, str]) -> None:
        del fields
        self.count += 1


def _routing(entry: dict[str, Any]) -> dict[str, Any]:
    return next(s for s in entry["steps"] if s["id"] == "R")


def case_from_entry(
    entry: dict[str, Any], corpus: str, label: dict[str, Any]
) -> ACPCase:
    """One ACPCase from a run's CoE entry and its label."""
    acp = _routing(entry).get("acp") or {}
    if acp.get("status") not in {"unfit", "predicted"}:
        raise ValueError("the run did not record ACP features (acp_stateful OFF?)")
    fault = str(label.get("fault") or "")
    if fault not in FAULT_CLASS:
        raise ValueError(f"fault type {fault!r} has no remediation family")
    return ACPCase(
        incident_id=str(entry["incident_id"]),
        corpus=corpus,
        x=tuple(float(v) for v in acp["features"]),
        label=FAULT_CLASS[fault],
    )


def collect_cases(*, key: bytes) -> tuple[list[ACPCase], dict[str, Any]]:
    """Run HELIOS-noLLM over both build corpora; the cases and counts."""
    manifest = get_variant(VARIANT)
    if not manifest.acp_stateful:
        raise RuntimeError(f"{VARIANT} has acp_stateful OFF")
    cases: list[ACPCase] = []
    excluded = 0
    tiers: dict[str, Counter[str]] = {}
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for corpus in BUILD_CORPORA:
            captures, _manifest, truth = (REPO_ROOT / p for p in CORPORA[corpus])
            labels = verify_ground_truth(truth, key)
            ledger = _CountingLedger()
            set_current_manifest(manifest)
            orch = RunOrchestrator(
                manifest=manifest,
                captures_dir=captures,
                db_path=work / f"{corpus}.duckdb",
                registry_path=work / f"{corpus}.registry.jsonl",
                reconciliation_path=work / f"{corpus}.reconciliation.jsonl",
                exclusion_ledger=ledger,
                hmac_key=key,
                coe_path=work / f"{corpus}.coe.jsonl",
            )
            orch.run(captures)
            tier = tiers.setdefault(corpus, Counter())
            for line in orch.coe_path.read_text(encoding="utf-8").splitlines():
                entry = json.loads(line)
                cases.append(
                    case_from_entry(entry, corpus, labels[entry["incident_id"]])
                )
                tier[str(_routing(entry)["acp"]["blast_tier"])] += 1
            excluded += ledger.count
            print(f"[acp] {corpus}: {len(cases)} cases so far", flush=True)
    return cases, {
        "excluded": excluded,
        "blast_tier_by_corpus": {c: dict(sorted(t.items())) for c, t in tiers.items()},
    }


def _write(report: dict[str, Any]) -> None:
    text = json.dumps(json.loads(canonical_json(report)), indent=2, sort_keys=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(text + "\n", encoding="utf-8")


def _fit() -> int:
    if REPORT.exists():
        print(f"[acp] {REPORT.name} exists: the fit runs once", file=sys.stderr)
        return 2
    if ACP_PARAMS_PATH.exists():
        print("[acp] frozen ACP parameters exist: nothing to fit", file=sys.stderr)
        return 2
    cases, counts = collect_cases(key=load_key())
    held = cross_fit(cases, LAMBDA, FOLDS)
    params = fit_params(cases, LAMBDA)
    in_sample = [params.probabilities(c.x) for c in cases]
    by_corpus = {
        corpus: scores(
            [c for c in cases if c.corpus == corpus],
            [p for c, p in zip(cases, held, strict=True) if c.corpus == corpus],
        )
        for corpus in BUILD_CORPORA
    }
    report: dict[str, Any] = {
        "deviation_entry": 82,
        "variant": VARIANT,
        "lam": LAMBDA,
        "folds": FOLDS,
        "class_counts": dict(sorted(Counter(c.label for c in cases).items())),
        **counts,
        "cross_fitted": scores(cases, held),
        "cross_fitted_by_corpus": by_corpus,
        "in_sample": scores(cases, in_sample),
        "fit": params.as_dict(),
        "fit_hash": acp_params_hash(params),
    }
    _write(report)
    cf = report["cross_fitted"]
    print(
        f"[acp] {cf['cases']} cases: cross-fitted accuracy {cf['accuracy']}, "
        f"macro-F1 {cf['macro_f1']}, log loss {cf['log_loss']}"
    )
    print(f"[acp] report {REPORT.name}; fit hash {report['fit_hash']}")
    return 0


def _freeze() -> int:
    if not REPORT.is_file():
        print("[acp] no report: fit and review first", file=sys.stderr)
        return 2
    if ACP_PARAMS_PATH.exists():
        print("[acp] frozen ACP parameters exist: not replaced", file=sys.stderr)
        return 2
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    params = acp_params_from_dict(report["fit"])
    if acp_params_hash(params) != report["fit_hash"]:
        print("[acp] fit does not match its hash", file=sys.stderr)
        return 3
    write_acp_params(params, ACP_PARAMS_PATH)
    print(f"[acp] frozen {acp_params_hash(params)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args(argv)
    if Path.cwd().resolve() != REPO_ROOT:
        print("[acp] run from the repository root", file=sys.stderr)
        return 2
    return _freeze() if args.freeze else _fit()


if __name__ == "__main__":
    sys.exit(main())
