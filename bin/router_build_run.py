"""Fit, freeze and check the cheap-first router on build cases (S3.1 design §5.3-5.4).

Usage (from the repository root; the runner reads repo-relative stream paths):
    set -a; source .env; set +a
    poetry run python bin/router_build_run.py --run N          # fit, report
    poetry run python bin/router_build_run.py --freeze --run N # write data/frozen/
    poetry run python bin/router_build_run.py --check-frozen   # frozen file, build cases

Runs HELIOS-noRouter (every pipeline, G-pipe ungated, frozen detector, D-, G-
and L-pipe, frozen MAHC) over the sealed build corpora into a scratch store:
the full-information pass. L-pipe answers come only from the response cache;
a cache miss aborts the run. Each case is read back from the run's own CoE
ledger (the router features the runner recorded, the pipelines' lists and
latencies), so build data and runs share one feature path. Writes
``docs/sprints/s3-routing/calibration/router_run<N>.json`` (aggregates only,
never an incident ID). Exit 3 when no τ_acc can stop any case within the
tolerance (R-d): the owner decides. ``--freeze`` writes the reviewed report's
refit to ``data/frozen/router_params.json``; nothing else writes there.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bin.log_deviation import load_key
from bin.mahc_build_run import BUILD_CORPORA, CACHE_PATH, _CacheOnlyClient
from helios.adapters.rcaeval import verify_ground_truth
from helios.consensus.mahc import Vote
from helios.consensus.params import load_mahc_params
from helios.consensus.router_params import (
    ROUTER_PARAMS_PATH,
    load_router_params,
    router_params_from_dict,
    router_params_hash,
    write_router_params,
)
from helios.evaluation.cost import load_price_book
from helios.evaluation.router_calibration import (
    RouterCase,
    arm_outcomes,
    choose_tau,
    cross_fit,
    evaluate,
    fit_all,
    stage_medians,
)
from helios.evaluation.trigger_calibration import CORPORA
from helios.orchestrator.runner import RunOrchestrator
from helios.pipelines.l_pipe.cache import ResponseCache
from helios.pipelines.l_pipe.lpipe_config import MODEL_NAME, OLLAMA_BASE_URL
from helios.telemetry.scope import in_scope
from helios.telemetry.signal_type import SignalType
from helios.vcl import get_variant, set_current_manifest
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance
from helios.vcl.utils import canonical_json

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = REPO_ROOT / "docs/sprints/s3-routing/calibration"
VARIANT = "HELIOS-noRouter"
ROUTED = "HELIOS-Full"
LAMBDA = 1
ALPHA = 1


class _CountingLedger:
    def __init__(self) -> None:
        self.count = 0

    def append(self, fields: dict[str, str]) -> None:
        del fields
        self.count += 1


def _step(entry: dict[str, Any], step_id: str) -> dict[str, Any]:
    return next(s for s in entry["steps"] if s["id"] == step_id)


def case_from_entry(
    entry: dict[str, Any], corpus: str, label: dict[str, Any]
) -> RouterCase | None:
    """One RouterCase from a uniform run's CoE entry; None without features."""
    routing = _step(entry, "R")
    if "features_cheap" not in routing:
        return None
    votes: dict[str, Vote] = {}
    latency: dict[str, float] = {}
    for name in ("dpipe", "gpipe", "lpipe"):
        p = _step(entry, f"P:{name}")
        if p["status"] == "skipped":
            continue
        latency[name] = float(p["measured"]["latency_ms"])
        ranked = tuple(s for s in p["ranked"] if in_scope(s))
        if p["status"] == "ranked" and ranked:
            sigma = p.get("sigma")
            votes[name] = Vote(name, ranked, 1 if sigma is None else float(sigma))
    g_ranked = "gpipe" in votes
    return RouterCase(
        incident_id=str(entry["incident_id"]),
        corpus=corpus,
        group=str(label.get("system") or label["root_cause_service"]),
        signal=SignalType(_step(entry, "T").get("signal") or "unclassified"),
        x_cheap=tuple(float(v) for v in routing["features_cheap"]),
        x_dg=tuple(float(v) for v in routing["features"]) if g_ranked else None,
        graph=bool(routing.get("ran")),
        votes=votes,
        latency_ms=latency,
        root=str(label["root_cause_service"]),
    )


def collect_cases(*, key: bytes) -> tuple[list[RouterCase], dict[str, int]]:
    """Run HELIOS-noRouter over both build corpora; the cases and counts."""
    manifest = get_variant(VARIANT)
    cases: list[RouterCase] = []
    excluded = 0
    unfeatured = 0
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
                lpipe_client=_CacheOnlyClient(OLLAMA_BASE_URL, MODEL_NAME),
                lpipe_cache=ResponseCache(CACHE_PATH),
                mahc_params=load_mahc_params(),
                coe_path=work / f"{corpus}.coe.jsonl",
            )
            orch.run(captures)
            for line in orch.coe_path.read_text(encoding="utf-8").splitlines():
                entry = json.loads(line)
                case = case_from_entry(entry, corpus, labels[entry["incident_id"]])
                if case is None:
                    unfeatured += 1
                else:
                    cases.append(case)
            excluded += ledger.count
            print(f"[router] {corpus}: {len(cases)} cases so far", flush=True)
    return cases, {"excluded": excluded, "unfeatured": unfeatured}


def _write(name: str, report: dict[str, Any]) -> Path:
    text = json.dumps(json.loads(canonical_json(report)), indent=2, sort_keys=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / name
    path.write_text(text + "\n", encoding="utf-8")
    return path


def _print(report: dict[str, Any]) -> None:
    for name, g in report["by_corpus"].items():
        line = f"[router] {name}: {g['cases']} cases, uniform HR@3 {g['uniform_hr3']}"
        if "routed_hr3" in g:
            line += (
                f", routed {g['routed_hr3']}, escalated {g['escalated_share']}, "
                f"L-pipe calls saved {g['lpipe_calls_saved']}"
            )
        print(line)


def _fit(run: int) -> int:
    cases, counts = collect_cases(key=load_key())
    set_current_manifest(get_variant(ROUTED))  # the policy is gated by cbr_routing
    mahc = load_mahc_params()
    outcomes = [arm_outcomes(c, mahc) for c in cases]
    medians = stage_medians(cases)
    held = cross_fit(cases, outcomes, lam=LAMBDA, alpha=ALPHA, medians=medians)
    tau = choose_tau(cases, held, outcomes, mahc)
    report = evaluate(cases, held, outcomes, mahc, tau)
    report.update(
        {
            "variant": VARIANT,
            "cases": len(cases),
            **counts,
            "lam": LAMBDA,
            "alpha": ALPHA,
            "stage_median_ms": medians,
        }
    )
    if tau is not None:
        refit = fit_all(
            cases,
            outcomes,
            lam=LAMBDA,
            alpha=ALPHA,
            tau=tau,
            medians=medians,
            digest=load_price_book().digest,
        )
        report["refit"] = refit.as_dict()
        report["refit_hash"] = router_params_hash(refit)
    path = _write(f"router_run{run}.json", report)
    _print(report)
    print(f"[router] report {path.name}")
    if tau is None:
        print(
            "[router] no tau_acc stops any case within one point of uniform: stop (R-d)",
            file=sys.stderr,
        )
        return 3
    print(f"[router] tau_acc {tau}")
    return 0


def _freeze(run: int) -> int:
    path = REPORT_DIR / f"router_run{run}.json"
    if not path.is_file():
        print(f"[router] no report {path.name}: run and review first", file=sys.stderr)
        return 2
    report = json.loads(path.read_text(encoding="utf-8"))
    if "refit" not in report:
        print("[router] the report has no refit (exit 3 run)", file=sys.stderr)
        return 3
    params = router_params_from_dict(report["refit"])
    if router_params_hash(params) != report["refit_hash"]:
        print("[router] refit does not match its hash", file=sys.stderr)
        return 3
    write_router_params(params, ROUTER_PARAMS_PATH)
    print(f"[router] frozen {router_params_hash(params)}")
    return 0


def _check_frozen() -> int:
    params = load_router_params(ROUTER_PARAMS_PATH)
    if params.provisional:
        print("[router] router parameters are provisional", file=sys.stderr)
        return 2
    cases, counts = collect_cases(key=load_key())
    set_current_manifest(get_variant(ROUTED))
    mahc = load_mahc_params()
    outcomes = [arm_outcomes(c, mahc) for c in cases]
    frozen = dict.fromkeys(range(len(cases)), params)
    report = evaluate(cases, frozen, outcomes, mahc, params.tau_acc)
    report.update(
        {"frozen_hash": router_params_hash(params), "cases": len(cases), **counts}
    )
    _write("router_frozen_check.json", report)
    _print(report)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", choices=("build", "pool"), default="build")
    parser.add_argument("--run", type=int, default=1, help="router_run<N>.json")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--freeze", action="store_true", help="freeze a reviewed run")
    mode.add_argument("--check-frozen", action="store_true")
    args = parser.parse_args(argv)
    if args.corpus == "pool":
        print("[router] the pool is locked until tag build-freeze", file=sys.stderr)
        return 2
    if args.freeze:
        return _freeze(args.run)
    if Path.cwd().resolve() != REPO_ROOT:
        print(
            "[router] run from the repository root (stream paths are relative)",
            file=sys.stderr,
        )
        return 2
    if args.check_frozen:
        return _check_frozen()
    return _fit(args.run)


if __name__ == "__main__":
    sys.exit(main())
