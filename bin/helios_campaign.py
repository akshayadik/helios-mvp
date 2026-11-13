#!/usr/bin/env python3
"""Plan, run and bookkeep a run campaign (S4.10; design s4_10_orchestrator_design.md).

Usage (from repo root; the signed ground truth and ledgers need the key):
    set -a; source .env; set +a
    poetry run python bin/helios_campaign.py plan --dir CAMPAIGN \\
        --manifest data/otel/build_v3_manifest.json --gt-corpus otel_build_v3 \\
        --captures data/otel/build_v3
    poetry run python bin/helios_campaign.py run --dir CAMPAIGN \\
        [--phase confirmatory ...] [--limit N] [--cache-only]
    poetry run python bin/helios_campaign.py status --dir CAMPAIGN
    poetry run python bin/score_runs.py --db CAMPAIGN/results.duckdb \\
        --corpus otel_build_v3 --metrics --captures data/otel/build_v3
    poetry run python bin/helios_campaign.py cells --dir CAMPAIGN [--labels-due]
    poetry run python bin/helios_campaign.py compare --dir CAMPAIGN

``run`` resumes: finished specs are skipped, an unfinished one is discarded
and re-run. It regenerates the schedule and refuses a campaign planned under a
different one (for example after a flag gained its first reader).
A pool campaign is refused until tag build-freeze exists. The pool campaign
writes the repo-root exclusion ledger; every other campaign its own.
Prints counts only, never case IDs or labels.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bin.helios_run import _load_coe_signer
from bin.log_deviation import load_key
from bin.log_exclusion import ExclusionLedger
from helios.adapters.rcaeval import verify_ground_truth
from helios.analysis.run import build_case_table, variant_names
from helios.evaluation.cells import cell_table, missing_metrics
from helios.evaluation.cost import load_price_book
from helios.evaluation.scoring import GROUND_TRUTH_FILES, Corpus
from helios.orchestrator.campaign import Campaign, compare_rerun, read_log
from helios.orchestrator.runner import RunOrchestrator
from helios.orchestrator.schedule import (
    Phase,
    Schedule,
    build_schedule,
    scheduled_by_system,
    system_name,
)
from helios.pipelines.l_pipe.cache import ResponseCache
from helios.pipelines.l_pipe.lpipe_config import MODEL_NAME, OLLAMA_BASE_URL
from helios.store.result_store import ResultStore
from helios.telemetry.pool_lock import BUILD_FREEZE_TAG, PoolLockedError, build_frozen
from helios.vcl import get_variant
from helios.vcl.catalog import flag_readers, unconsumed_variants
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance
from helios.vcl.variants import EXPLORATORY_VARIANTS

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = REPO_ROOT / "data/cache/lpipe_cache.sqlite"
CONFIG = "campaign.json"


# ── planning ────────────────────────────────────────────────────────────────


def _check_pool(gt_corpus: str) -> None:
    if gt_corpus == Corpus.POOL and not build_frozen():
        raise PoolLockedError(
            f"a pool campaign is refused until tag {BUILD_FREEZE_TAG!r} exists (D11)"
        )


def case_apps(gt_corpus: str, order: list[str], key: bytes) -> dict[str, str]:
    """Benchmark system per case, from the signed ground truth (label-free use)."""
    _check_pool(gt_corpus)
    cases = verify_ground_truth(REPO_ROOT / GROUND_TRUTH_FILES[gt_corpus], key)
    return {
        c: str(cases[c].get("system") or cases[c].get("dataset") or gt_corpus)
        for c in order
    }


def schedule_for(config: dict[str, Any], key: bytes) -> Schedule:
    manifest = json.loads((REPO_ROOT / config["manifest"]).read_text())
    order = [str(c) for c in manifest["case_order"]]
    apps = case_apps(config["gt_corpus"], order, key)
    refused = unconsumed_variants(list(EXPLORATORY_VARIANTS), flag_readers(REPO_ROOT))
    return build_schedule(str(manifest["corpus"]), order, apps, refused=refused)


def exclusion_ledger(
    directory: Path, config: dict[str, Any], key: bytes
) -> ExclusionLedger:
    """The pool campaign uses the repo-root ledger; any other its own (O-d)."""
    path = (
        REPO_ROOT / "exclusion_ledger.jsonl"
        if config["gt_corpus"] == Corpus.POOL
        else directory / "exclusion_ledger.jsonl"
    )
    ledger = ExclusionLedger(key=key, log_path=path)
    if not ledger.anchor_path.exists() and not path.exists():
        path.touch()
        ledger.init_anchor()
    return ledger


def cmd_plan(args: argparse.Namespace, key: bytes) -> int:
    config = {
        "manifest": str(args.manifest),
        "gt_corpus": args.gt_corpus,
        "captures": str(args.captures),
    }
    path = args.dir / CONFIG
    if path.is_file() and json.loads(path.read_text()) != config:
        print(f"[campaign] refused: {args.dir} was planned with another config")
        return 2
    schedule = schedule_for(config, key)
    args.dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=1) + "\n")
    Campaign(
        args.dir, schedule, {}, exclusion_ledger=exclusion_ledger(args.dir, config, key)
    )
    print(f"[campaign] schedule {schedule.digest[:12]}: {schedule.counts()}")
    print(f"[campaign] refused variants: {sorted(schedule.refused)}")
    print(
        f"[campaign] determinism rerun cases {len(schedule.rerun_cases)}, "
        f"E-H5 subset {len(schedule.eh5_cases)}"
    )
    return 0


# ── running ─────────────────────────────────────────────────────────────────


def executors(
    directory: Path,
    config: dict[str, Any],
    systems: set[str],
    *,
    ledger: ExclusionLedger,
    key: bytes,
    rerun: bool,
    cache_only: bool,
) -> dict[str, RunOrchestrator]:
    """One orchestrator per HELIOS variant; the rerun ones bypass the cache
    and write to their own store, so the analysis never sees two runs."""
    client = None
    if cache_only:
        from bin.mahc_build_run import _CacheOnlyClient

        client = _CacheOnlyClient(OLLAMA_BASE_URL, MODEL_NAME)
    stem = "rerun" if rerun else "results"
    signer = _load_coe_signer()
    digest = load_price_book().digest
    out: dict[str, RunOrchestrator] = {}
    for name in sorted(systems):
        if name.startswith("BASELINE-"):
            continue
        out[name] = RunOrchestrator(
            manifest=get_variant(name),
            captures_dir=REPO_ROOT / config["captures"],
            db_path=directory / f"{stem}.duckdb",
            registry_path=directory / "registry" / f"{stem}.{name}.jsonl",
            reconciliation_path=directory / "reconciliation" / f"{stem}.{name}.jsonl",
            exclusion_ledger=ledger,
            hmac_key=key,
            coe_signer=signer,
            price_book_digest=digest,
            lpipe_client=client,
            lpipe_cache=None if rerun else ResponseCache(CACHE_PATH),
            coe_path=directory / "coe" / f"{stem}.{name}.coe.jsonl",
        )
    return out


def cmd_run(args: argparse.Namespace, key: bytes) -> int:
    config = json.loads((args.dir / CONFIG).read_text())
    schedule = schedule_for(config, key)
    ledger = exclusion_ledger(args.dir, config, key)
    phases = args.phase or [p.value for p in Phase]
    for phase in phases:
        specs = [s for s in schedule.specs if s.phase == phase]
        systems = {s.system for s in specs}
        if phase == Phase.BASELINE:
            print("[campaign] baseline phase: no executor until S4.8; skipped")
            continue
        execs = executors(
            args.dir,
            config,
            systems,
            ledger=ledger,
            key=key,
            rerun=phase == Phase.RERUN,
            cache_only=args.cache_only,
        )
        campaign = Campaign(args.dir, schedule, execs, exclusion_ledger=ledger)
        done = campaign.run([phase], limit=args.limit)
        print(f"[campaign] {phase}: {done}")
    return 0


# ── bookkeeping ─────────────────────────────────────────────────────────────


def _final(directory: Path) -> dict[str, dict[str, Any]]:
    final: dict[str, dict[str, Any]] = {}
    for r in read_log(directory / "campaign_log.jsonl"):
        if r["event"] in {"passed", "excluded"}:
            final[r["key"]] = r
    return final


def cmd_status(args: argparse.Namespace, key: bytes) -> int:
    del key
    body = json.loads((args.dir / "schedule.json").read_text())
    final = _final(args.dir)
    log = read_log(args.dir / "campaign_log.jsonl")
    per: dict[str, dict[str, int]] = {}
    for spec in body["specs"]:
        k = f"{spec['phase']}/{spec['case']}/{spec['system']}"
        state = final[k]["event"] if k in final else "pending"
        row = per.setdefault(spec["phase"], {})
        row[state] = row.get(state, 0) + 1
    retries = sum(r["event"] == "retry" for r in log)
    print(f"[campaign] schedule {body['digest'][:12]}; retries {retries}")
    for phase, row in per.items():
        print(f"[campaign]   {phase}: {row}")
    return 0


def cmd_cells(args: argparse.Namespace, key: bytes) -> int:
    """Score-time check (O-c) and the cell table (O-e)."""
    config = json.loads((args.dir / CONFIG).read_text())
    body = json.loads((args.dir / "schedule.json").read_text())
    ledger = exclusion_ledger(args.dir, config, key)
    store = ResultStore(args.dir / "results.duckdb")
    scores, runs = store.fetch_scores(), store.fetch_run_metrics()
    store.close()
    if not scores or not runs:
        print("[campaign] refused: score the campaign first (score_runs --metrics)")
        return 2
    table = build_case_table(scores, runs, variant_names())
    final = _final(args.dir)
    passed = {
        (system_name(str(s["system"])), str(s["case"])): final[k]["run_id"]
        for s in body["specs"]
        if s["phase"] != Phase.RERUN
        and (k := f"{s['phase']}/{s['case']}/{s['system']}") in final
        and final[k]["event"] == "passed"
    }
    already = {
        (r["run_id"], r["metric"])
        for r in read_log(args.dir / "campaign_log.jsonl")
        if r["event"] == "metric_excluded"
    }
    new = 0
    with (args.dir / "campaign_log.jsonl").open("a", encoding="utf-8") as fh:
        for system, case, metric in missing_metrics(
            table, list(passed), labels_due=args.labels_due
        ):
            run_id = passed[system, case]
            if (run_id, metric) in already:
                continue
            ledger.append(
                {
                    "phase": "score",
                    "system": system,
                    "metric": metric,
                    "schedule_digest": body["digest"],
                    "variant_config_hash": _config_hash(system),
                    "snapshot_hash": "UNKNOWN",
                    "run_id": run_id,
                    "incident_id": case,
                    "gate_check": "metric_missing",
                    "reason": f"passed run has no {metric} after scoring",
                    "analytic_consequence": "run excluded for this metric only",
                    "covariates": "{}",
                }
            )
            fh.write(
                json.dumps(
                    {
                        "event": "metric_excluded",
                        "key": "score",
                        "run_id": run_id,
                        "metric": metric,
                    }
                )
                + "\n"
            )
            new += 1
    apps = {str(c): str(a) for c, a in body["apps"].items()}
    cells = cell_table(table, apps, scheduled_by_system(body))
    (args.dir / "cells.json").write_text(
        json.dumps([c.as_dict() for c in cells.values()], indent=1) + "\n"
    )
    failing = [c for c in cells.values() if not c.passes]
    print(
        f"[campaign] {new} metric exclusions written; {len(cells)} cells, "
        f"{len(failing)} below the cell rule"
    )
    return 0


def _config_hash(system: str) -> str:
    if system in variant_names().values():
        return get_variant(system).compute_variant_config_hash()
    return "BASELINE"


def cmd_compare(args: argparse.Namespace, key: bytes) -> int:
    """Determinism rerun (O-g): fused list, narrative and L-pipe evidence."""
    del key
    body = json.loads((args.dir / "schedule.json").read_text())
    final = _final(args.dir)
    main = ResultStore(args.dir / "results.duckdb")
    rerun = ResultStore(args.dir / "rerun.duckdb")
    rows: list[dict[str, Any]] = []
    for s in body["specs"]:
        if s["phase"] != Phase.RERUN:
            continue
        first = final.get(
            f"{Phase.CONFIRMATORY}/{s['case']}/{s['system']}"
        ) or final.get(f"{Phase.EXPLORATORY}/{s['case']}/{s['system']}")
        again = final.get(f"{Phase.RERUN}/{s['case']}/{s['system']}")
        if not (first and again) or {first["event"], again["event"]} != {"passed"}:
            continue  # compare only when both runs passed
        a, b = first["run_id"], again["run_id"]
        result = compare_rerun(
            {
                "fused": _ranked(main.fetch_fusion(a)),
                "lpipe": main.fetch_evidence(a, "lpipe"),
                "narrative": main.fetch_narrative(a),
            },
            {
                "fused": _ranked(rerun.fetch_fusion(b)),
                "lpipe": rerun.fetch_evidence(b, "lpipe"),
                "narrative": rerun.fetch_narrative(b),
            },
        )
        rows.append(
            {
                "run_id": a,
                "rerun_id": b,
                "system": s["system"],
                "nondeterministic": bool(result["differs"]),
                **result,
            }
        )
    main.close()
    rerun.close()
    (args.dir / "determinism.json").write_text(json.dumps(rows, indent=1) + "\n")
    n_bad = sum(r["nondeterministic"] for r in rows)
    n_nc = sum(bool(r["not_comparable"]) for r in rows)
    print(
        f"[campaign] determinism: {len(rows)} pairs compared, {n_bad} not equal, "
        f"{n_nc} with a narrative not comparable (no model answer on one side)"
    )
    return 0


def _ranked(fusion: dict[str, Any] | None) -> Any:
    return None if fusion is None else fusion.get("ranked")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--manifest", type=Path, required=True)
    plan.add_argument("--gt-corpus", choices=sorted(GROUND_TRUTH_FILES), required=True)
    plan.add_argument("--captures", type=Path, required=True)
    run = sub.add_parser("run")
    run.add_argument("--phase", action="append", choices=[p.value for p in Phase])
    run.add_argument("--limit", type=int)
    run.add_argument("--cache-only", action="store_true")
    cells = sub.add_parser("cells")
    cells.add_argument("--labels-due", action="store_true")
    sub.add_parser("status")
    sub.add_parser("compare")
    for p in sub.choices.values():
        p.add_argument("--dir", type=Path, required=True)
    args = parser.parse_args(argv)
    commands = {
        "plan": cmd_plan,
        "run": cmd_run,
        "status": cmd_status,
        "cells": cmd_cells,
        "compare": cmd_compare,
    }
    try:
        return commands[args.command](args, load_key())
    except PoolLockedError as exc:
        print(f"[campaign] refused: {exc}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
