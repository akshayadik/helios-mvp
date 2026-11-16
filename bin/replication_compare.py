#!/usr/bin/env python3
"""S5.4 replication compare: a clean-clone campaign against its reference.

    poetry run python bin/replication_compare.py runs \
        --ref data/campaigns/s5_1/otel_build_v3 --clone <clone>/data/campaigns/s5_4/otel_build_v3 \
        --out docs/sprints/s5-integration-freeze/replication/compare_otel_build_v3.json
    poetry run python bin/replication_compare.py analysis --ref A.json --clone B.json --out ...

runs (design s5_4_replication_design.md R-e 3-4): schedule digest; per
first-run spec the outcome (passed or excluded, gate check); per HELIOS run
the snapshot hash, per-pipeline ranked list and decision hash, and the fused
list (first and terminal); per baseline run the snapshot hash and ranking.
A HELIOS run whose clone made a live L-pipe call (cache miss) is classed
apart: a difference there is model nondeterminism (S5.5), not the build.

analysis (R-e 5): leaf-by-leaf diff of two analysis JSONs. Leaves under a
node whose metric is timing-derived (CpR, TTCD, TTT) are reported apart;
every other leaf must be equal.

Reads the stores read-only; reads no ground truth; changes nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from helios.vcl import VCLFlag  # noqa: E402, F401 — flag-guard compliance

HELIOS_ENABLE_REPLICATION_COMPARE: bool = True
FIRST_RUN_PHASES = ("confirmatory", "exploratory", "baseline", "baseline_trigger")
TIMING_METRICS = frozenset(
    {
        "log_cpr",
        "log_ttcd",
        "ttt_ms",
        "log-CpR",
        "log-CpR at matched HR@3",
        "log time to correct diagnosis",
        "time to triage",
    }
)
LISTED = 50  # differing keys listed per class; counts are always complete


def final_outcomes(log: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """spec key -> last passed/excluded event, first-run phases only."""
    out: dict[str, dict[str, Any]] = {}
    for r in log:
        key = str(r.get("key", ""))
        if r.get("event") in {"passed", "excluded"} and (
            key.split("/", 1)[0] in FIRST_RUN_PHASES
        ):
            out[key] = r
    return out


def helios_signature(
    results: list[tuple[Any, ...]], fusion: tuple[Any, ...] | None
) -> dict[str, Any]:
    """results: (pipeline, snapshot_hash, ranked_candidates, decision_hash);
    fusion: (ranked_json, first_ranked_json, state)."""
    sig: dict[str, Any] = {
        "snapshot": sorted({str(r[1]) for r in results}),
        "pipelines": {
            str(p): {"ranked": ranked, "decision": dh}
            for p, _, ranked, dh in sorted(results, key=lambda r: str(r[0]))
        },
    }
    if fusion is not None:
        sig["fused"] = {"ranked": fusion[0], "first": fusion[1], "state": fusion[2]}
    return sig


def live_calls(evidence: dict[str, Any] | None) -> int:
    workers = (evidence or {}).get("workers") or {}
    return sum(1 for w in workers.values() if not w.get("cache_hit"))


def compare_runs(
    ref: dict[str, dict[str, Any]],
    clone: dict[str, dict[str, Any]],
    live: dict[str, int],
) -> dict[str, Any]:
    """ref/clone: spec key -> {"event", "gate_check", "sig"}; live: spec key
    -> live L-pipe calls in the clone run."""
    classes: dict[str, list[str]] = {
        "missing_in_clone": sorted(ref.keys() - clone.keys()),
        "extra_in_clone": sorted(clone.keys() - ref.keys()),
        "outcome_differs": [],
        "differs_cache_hit": [],
        "differs_live_call": [],
    }
    equal = Counter[str]()
    for key in sorted(ref.keys() & clone.keys()):
        a, b = ref[key], clone[key]
        if (a["event"], a.get("gate_check")) != (b["event"], b.get("gate_check")):
            classes["outcome_differs"].append(key)
        elif a.get("sig") != b.get("sig"):
            name = "differs_live_call" if live.get(key) else "differs_cache_hit"
            classes[name].append(key)
        else:
            equal[key.split("/", 1)[0]] += 1
    return {
        "compared": len(ref.keys() & clone.keys()),
        "equal_by_phase": dict(sorted(equal.items())),
        "clone_runs_with_live_calls": sum(1 for v in live.values() if v),
        "counts": {k: len(v) for k, v in classes.items()},
        "keys": {k: v[:LISTED] for k, v in classes.items() if v},
        "passes": not any(
            classes[k]
            for k in (
                "missing_in_clone",
                "extra_in_clone",
                "outcome_differs",
                "differs_cache_hit",
            )
        ),
    }


def load_campaign(
    directory: Path,
) -> tuple[str, dict[str, dict[str, Any]], dict[str, int]]:
    import duckdb

    digest = json.loads((directory / "schedule.json").read_text())["digest"]
    log = [
        json.loads(x)
        for x in (directory / "campaign_log.jsonl").read_text().splitlines()
        if x.strip()
    ]
    finals = final_outcomes(log)
    con = duckdb.connect(str(directory / "results.duckdb"), read_only=True)
    try:
        results: dict[str, list[tuple[Any, ...]]] = {}
        for row in con.execute(
            "select run_id, pipeline, snapshot_hash, ranked_candidates, decision_hash"
            " from result_row"
        ).fetchall():
            results.setdefault(str(row[0]), []).append(tuple(row[1:]))
        fusion = {
            str(r[0]): tuple(r[1:])
            for r in con.execute(
                "select run_id, ranked_json, first_ranked_json, state from fusion_row"
            ).fetchall()
        }
        baselines = {
            str(r[0]): {"snapshot": r[1], "ranked": r[2]}
            for r in con.execute(
                "select run_id, snapshot_hash, ranked_json from baseline_row"
            ).fetchall()
        }
        evidence = {
            str(r[0]): json.loads(r[1]) if r[1] else None
            for r in con.execute(
                "select run_id, evidence_json from evidence_row where pipeline = 'lpipe'"
            ).fetchall()
        }
    finally:
        con.close()
    runs: dict[str, dict[str, Any]] = {}
    live: dict[str, int] = {}
    for key, r in finals.items():
        run_id = str(r["run_id"])
        entry: dict[str, Any] = {"event": r["event"], "gate_check": r.get("gate_check")}
        if r["event"] == "passed":
            if run_id in baselines:
                entry["sig"] = baselines[run_id]
            else:
                entry["sig"] = helios_signature(
                    results.get(run_id, []), fusion.get(run_id)
                )
                live[key] = live_calls(evidence.get(run_id))
        runs[key] = entry
    return digest, runs, live


def leaf_diff(
    a: Any, b: Any, path: str = "", metric: str | None = None
) -> list[tuple[str, str | None]]:
    """(path, enclosing metric) of every leaf that differs."""
    if isinstance(a, dict) and isinstance(b, dict):
        here = a.get("metric") if isinstance(a.get("metric"), str) else metric
        out: list[tuple[str, str | None]] = []
        for k in sorted(a.keys() | b.keys(), key=str):
            if k not in a or k not in b:
                out.append((f"{path}/{k}", here))
            else:
                out += leaf_diff(a[k], b[k], f"{path}/{k}", here)
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [(f"{path}[len]", metric)]
        out = []
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            out += leaf_diff(x, y, f"{path}[{i}]", metric)
        return out
    return [] if a == b else [(path, metric)]


def compare_analysis(ref: Any, clone: Any) -> dict[str, Any]:
    diffs = leaf_diff(ref, clone)
    timing = [p for p, m in diffs if m in TIMING_METRICS]
    exact = [p for p, m in diffs if m not in TIMING_METRICS]
    return {
        "differing_leaves": len(diffs),
        "timing_derived": {"count": len(timing), "paths": timing[:LISTED]},
        "other": {"count": len(exact), "paths": exact[:LISTED]},
        "passes": not exact,
    }


def _write(report: dict[str, Any], out: Path | None) -> None:
    text = json.dumps(report, indent=1, sort_keys=True) + "\n"
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("runs", "analysis"):
        p = sub.add_parser(name)
        p.add_argument("--ref", type=Path, required=True)
        p.add_argument("--clone", type=Path, required=True)
        p.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    if not HELIOS_ENABLE_REPLICATION_COMPARE:
        print("replication compare disabled", file=sys.stderr)
        return 1
    if args.cmd == "analysis":
        report = compare_analysis(
            json.loads(args.ref.read_text()), json.loads(args.clone.read_text())
        )
        report["ref"], report["clone"] = args.ref.name, args.clone.name
        _write(report, args.out)
        print(
            f"analysis {args.ref.name}: {report['other']['count']} differing leaves, "
            f"{report['timing_derived']['count']} timing-derived; "
            f"{'PASS' if report['passes'] else 'FAIL'}"
        )
        return 0 if report["passes"] else 4
    d_ref, ref, _ = load_campaign(args.ref)
    d_clone, clone, live = load_campaign(args.clone)
    report = compare_runs(ref, clone, live)
    report["schedule_digest_equal"] = d_ref == d_clone
    report["passes"] = report["passes"] and report["schedule_digest_equal"]
    report["campaign"] = args.ref.name
    _write(report, args.out)
    print(
        f"runs {args.ref.name}: {report['compared']} compared; {report['counts']}; "
        f"schedule digest {'equal' if d_ref == d_clone else 'DIFFERS'}; "
        f"{'PASS' if report['passes'] else 'FAIL'}"
    )
    return 0 if report["passes"] else 4


if __name__ == "__main__":
    sys.exit(main())
