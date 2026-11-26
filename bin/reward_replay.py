"""Replay delayed two-stage rewards through a thawed router (S3.3; entry 74).

Usage (from the repository root; the runner reads repo-relative stream paths):
    set -a; source .env; set +a
    poetry run python bin/reward_replay.py --run N [--out data/replay/reward_runN]

Collects the S3.1 full-information build cases (HELIOS-noRouter, L-pipe from
the response cache only), then, for each of the 8 seeded streams and each
mean inter-arrival gap, pre-warms the router on one half of the build folds,
streams the other half (and the swap) as HELIOS-Full and HELIOS-noReconcile,
and records every provisional and terminal reward in a signed reward ledger
(one file per variant, gap, stream and half, under ``--out``; never committed).
Writes ``docs/sprints/s3-routing/calibration/reward_run<N>.json``: aggregates
only, never an incident ID. The frozen router file is read, never written.

Pool replay (E-H5, design docs/sprints/e-evidence/eh5_pool_replay_design.md,
entry 110), after the E1 campaign is scored, from the frozen build:
    poetry run python bin/reward_replay.py --corpus pool --campaign CAMPAIGN

P-a: the cases are HELIOS-noRouter's chain-of-evidence entries of CAMPAIGN
(no pipeline runs again) for the registered E-H5 subset (``eh5_cases`` of
schedule.json, entry 87). P-b: the pool ground truth is read through the pool
gate, and only once CAMPAIGN's store is scored. P-c: the router starts from
the full-information rows of every build case under the frozen router's fit
reward (HR@1 since CR-01), and the tool refuses unless that state equals the
frozen router. P-d: same variants, gaps, delays and update rule as the build
replay; each stream is one sub-stream over the subset from the registered
seed. P-e: per gap, entry 92's two E-H5 forms from RRE per (case, stream).
Ledgers and ``report.json`` go to CAMPAIGN/eh5_replay; aggregates only.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bin.labelling_runs import load_signer
from bin.log_deviation import load_key
from bin.router_build_run import REPORT_DIR, _write, case_from_entry, collect_cases
from helios.adapters.rcaeval import verify_ground_truth
from helios.analysis.run import e_h5_forms
from helios.consensus.params import load_mahc_params
from helios.consensus.router_params import load_router_params, router_params_hash
from helios.evaluation.reward_replay import (
    MEAN_GAPS_S,
    STREAMS,
    ThawedRouter,
    draws,
    full_information_rows,
    halves,
    replay,
    rre,
    rre_by_case_stream,
    single_draws,
    state_gap,
)
from helios.evaluation.router_calibration import REWARD, arm_outcomes
from helios.evaluation.scoring import GROUND_TRUTH_FILES
from helios.orchestrator.reward_ledger import (
    PROVISIONAL,
    TERMINAL,
    RewardLedger,
    check_pairs,
)
from helios.telemetry.pool_lock import BUILD_FREEZE_TAG, PoolLockedError, build_frozen
from helios.vcl import get_variant, set_current_manifest
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from helios.consensus.params import MAHCParams
    from helios.consensus.router_params import RouterParams
    from helios.evaluation.reward_replay import Decision
    from helios.evaluation.router_calibration import RouterCase

REPO_ROOT = Path(__file__).resolve().parent.parent
VARIANTS = ("HELIOS-Full", "HELIOS-noReconcile")
DEVIATION_ENTRY = 74
DECILES = 10
_DIGITS = 4


def _rate(values: Sequence[int]) -> float | None:
    return round(sum(values) / len(values), _DIGITS) if values else None


def _stream_stats(decisions: Sequence[Decision], tau: float) -> dict[str, Any]:
    rres = [r for d in decisions if (r := rre(d, tau)) is not None]
    return {
        "cases": len(decisions),
        "hr3": _rate([d.hit for d in decisions]),
        "escalated_share": _rate([int(d.escalated) for d in decisions]),
        "rre_rate": _rate(rres),
        "no_r1_share": _rate([int(d.r1 is None) for d in decisions]),
    }


def _spread(values: Sequence[float | None]) -> dict[str, float | None]:
    kept = [v for v in values if v is not None]
    if not kept:
        return {"mean": None, "min": None, "max": None}
    return {
        "mean": round(statistics.fmean(kept), _DIGITS),
        "min": min(kept),
        "max": max(kept),
    }


def _curve(
    runs: Sequence[tuple[Sequence[Decision], int]],
) -> dict[str, list[float | None]]:
    """HR@3 and escalation share by stream-position decile, pooled over streams."""
    hits: list[list[int]] = [[] for _ in range(DECILES)]
    esc: list[list[int]] = [[] for _ in range(DECILES)]
    for decisions, length in runs:
        for d in decisions:
            k = min(d.position * DECILES // max(length, 1), DECILES - 1)
            hits[k].append(d.hit)
            esc[k].append(int(d.escalated))
    return {"hr3": [_rate(h) for h in hits], "escalated_share": [_rate(e) for e in esc]}


def _summary(
    per_stream: dict[int, list[tuple[list[Decision], int]]], corpus: str, tau: float
) -> dict[str, Any]:
    stats = []
    runs: list[tuple[Sequence[Decision], int]] = []
    for subs in per_stream.values():
        mine = [d for decisions, _ in subs for d in decisions if d.corpus == corpus]
        stats.append(_stream_stats(mine, tau))
        runs += [([d for d in ds if d.corpus == corpus], n) for ds, n in subs]
    out: dict[str, Any] = {"cases_per_stream": stats[0]["cases"]}
    for key in ("hr3", "escalated_share", "rre_rate", "no_r1_share"):
        out[key] = _spread([s[key] for s in stats])
    out["by_decile"] = _curve(runs)
    return out


def run_replays(
    cases: Sequence[Any], out: Path, *, streams: int = STREAMS
) -> dict[str, Any]:
    """Every (gap, variant, stream, half) replay; the report body."""
    mahc = load_mahc_params()
    frozen = load_router_params()
    assert frozen.tau_acc is not None
    tau = frozen.tau_acc
    outcomes = [arm_outcomes(c, mahc) for c in cases]
    parts = halves(cases)
    rows = [full_information_rows(cases, parts[h], mahc) for h in (0, 1)]
    key, signer = load_key(), load_signer()
    corpora = sorted({c.corpus for c in cases})
    report: dict[str, Any] = {
        "deviation_entry": DEVIATION_ENTRY,
        "router_hash": router_params_hash(frozen),
        "tau_acc": tau,
        "streams": streams,
        "halves": [len(parts[0]), len(parts[1])],
        "gaps": {},
    }
    records = {"provisional": 0, "terminal": 0, "superseded": 0}
    for gap in MEAN_GAPS_S:
        by_variant: dict[str, Any] = {}
        for variant in VARIANTS:
            set_current_manifest(get_variant(variant))
            per_stream: dict[int, list[tuple[list[Decision], int]]] = {}
            for s in range(streams):
                for h, stream in enumerate(draws(s, parts)):
                    label = f"r{s}h{h}"
                    path = out / f"{variant}-gap{gap}-{label}.reward.jsonl"
                    ledger = RewardLedger(key, path, ed25519_private=signer)
                    decisions = replay(
                        cases,
                        outcomes,
                        stream,
                        ThawedRouter(frozen, rows[h]),
                        mahc,
                        ledger,
                        variant=variant,
                        label=label,
                        mean_gap_s=gap,
                        counts=records,
                    )
                    if err := check_pairs(path):
                        raise RuntimeError(f"{path.name}: {err}")
                    for stage in (PROVISIONAL, TERMINAL):
                        records[stage] += path.read_text(encoding="utf-8").count(
                            f'"stage": "{stage}"'
                        )
                    per_stream.setdefault(s, []).append((decisions, len(stream.order)))
            by_variant[variant] = {c: _summary(per_stream, c, tau) for c in corpora}
        full, plain = (by_variant[v] for v in VARIANTS)
        by_variant["difference"] = {
            c: {
                k: _diff(full[c][k]["mean"], plain[c][k]["mean"])
                for k in ("hr3", "escalated_share", "rre_rate")
            }
            for c in corpora
        }
        report["gaps"][str(gap)] = by_variant
    report["records"] = records
    return report


def _diff(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else round(a - b, _DIGITS)


def _print(report: dict[str, Any]) -> None:
    for gap, by_variant in report["gaps"].items():
        for variant in VARIANTS:
            for corpus, g in by_variant[variant].items():
                print(
                    f"[reward] gap {gap}s {variant} {corpus}: HR@3 "
                    f"{g['hr3']['mean']}, escalated {g['escalated_share']['mean']}, "
                    f"RRE {g['rre_rate']['mean']}, no r1 {g['no_r1_share']['mean']}"
                )


# ── pool replay (E-H5, entry 110) ───────────────────────────────────────────

POOL_SOURCE_VARIANT = "HELIOS-noRouter"
POOL_COE = Path("coe") / f"results.{POOL_SOURCE_VARIANT}.coe.jsonl"
POOL_OUT = "eh5_replay"
POOL_CORPUS = "pool"
PREWARM_TOLERANCE = 1e-6


def pool_subset(campaign: Path) -> list[str]:
    """The registered E-H5 subset (entry 87) from the campaign's schedule."""
    body = json.loads((campaign / "schedule.json").read_text(encoding="utf-8"))
    subset = [str(c) for c in body.get("eh5_cases") or []]
    if not subset:
        raise ValueError("schedule.json has no E-H5 subset (eh5_cases)")
    return subset


def scored_pool_rows(campaign: Path) -> int:
    """Scored pool rows in the campaign's main store (P-b: labels only after)."""
    db = campaign / "results.duckdb"
    if not db.exists():
        return 0
    con = duckdb.connect(str(db), read_only=True)
    try:
        tables = {r[0] for r in con.execute("show tables").fetchall()}
        if "eval_score" not in tables:
            return 0
        row = con.execute(
            "select count(*) from eval_score where corpus = ?", [POOL_CORPUS]
        ).fetchone()
        return int(row[0]) if row else 0
    finally:
        con.close()


def pool_cases(
    campaign: Path,
    key: bytes,
    *,
    frozen: Callable[[], bool] = build_frozen,
    labels: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[list[RouterCase], dict[str, int]]:
    """P-a and P-b: the subset's cases from HELIOS-noRouter's E1 CoE entries."""
    if not frozen():
        raise PoolLockedError(
            f"the pool replay runs only from the frozen build (tag {BUILD_FREEZE_TAG!r})"
        )
    subset = set(pool_subset(campaign))
    if scored_pool_rows(campaign) == 0:
        raise ValueError("the campaign store is not scored: run score_runs first")
    coe = campaign / POOL_COE
    if not coe.exists():
        raise ValueError(f"{POOL_COE} is missing: E1 has not run")
    if labels is None:
        labels = verify_ground_truth(REPO_ROOT / GROUND_TRUTH_FILES[POOL_CORPUS], key)
    want = get_variant(POOL_SOURCE_VARIANT).compute_variant_config_hash()
    entries: dict[str, dict[str, Any]] = {}
    for line in coe.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        incident = str(entry.get("incident_id"))
        if incident in subset and entry.get("variant_config_hash") == want:
            entries[incident] = entry
    cases: list[RouterCase] = []
    unfeatured = 0
    for incident in sorted(entries):
        case = case_from_entry(entries[incident], POOL_CORPUS, dict(labels[incident]))
        if case is None:
            unfeatured += 1
        else:
            cases.append(case)
    counts = {
        "subset": len(subset),
        "found": len(entries),
        "missing": len(subset) - len(entries),
        "unfeatured": unfeatured,
    }
    return cases, counts


def prewarm(
    build_cases: Sequence[RouterCase], frozen: RouterParams, mahc: MAHCParams
) -> tuple[dict[Any, list[tuple[tuple[float, ...], float]]], float]:
    """P-c: full-information rows of every build case under the frozen fit
    reward, and the gap between that state and the frozen router."""
    rows = full_information_rows(build_cases, range(len(build_cases)), mahc, REWARD)
    return rows, state_gap(ThawedRouter(frozen, rows).params(), frozen)


def _pool_stats(decisions: Sequence[Decision], tau: float) -> dict[str, Any]:
    rres = [r for d in decisions if (r := rre(d, tau)) is not None]
    return {
        "hit": _rate([d.hit for d in decisions]),
        "escalated_share": _rate([int(d.escalated) for d in decisions]),
        "rre_rate": _rate(rres),
        "with_r1": len(rres),
    }


def run_pool_replay(
    cases: Sequence[RouterCase],
    build_cases: Sequence[RouterCase],
    out: Path,
    *,
    streams: int = STREAMS,
) -> dict[str, Any]:
    """P-c to P-e over the pool subset; the report body (aggregates only)."""
    mahc = load_mahc_params()
    frozen = load_router_params()
    assert frozen.tau_acc is not None
    tau = frozen.tau_acc
    rows, gap_to_frozen = prewarm(build_cases, frozen, mahc)
    if gap_to_frozen > PREWARM_TOLERANCE:
        raise ValueError(
            f"the build pre-warm differs from the frozen router by {gap_to_frozen:.3g} "
            "(design P-c); not replaying"
        )
    outcomes = [arm_outcomes(c, mahc) for c in cases]
    key, signer = load_key(), load_signer()
    out.mkdir(parents=True)
    report: dict[str, Any] = {
        "deviation_entry": 110,
        "router_hash": router_params_hash(frozen),
        "tau_acc": tau,
        "reward": REWARD,
        "streams": streams,
        "cases": len(cases),
        "build_cases": len(build_cases),
        "prewarm_gap_to_frozen": gap_to_frozen,
        "gaps": {},
    }
    records = {"provisional": 0, "terminal": 0, "superseded": 0}
    for mean_gap in MEAN_GAPS_S:
        per_variant: dict[str, Any] = {}
        rre_maps: dict[str, dict[str, int]] = {}
        for variant in VARIANTS:
            set_current_manifest(get_variant(variant))
            stats, merged = [], {}
            for s in range(streams):
                label = f"s{s}"
                path = out / f"{variant}-gap{mean_gap}-{label}.reward.jsonl"
                ledger = RewardLedger(key, path, ed25519_private=signer)
                decisions = replay(
                    cases,
                    outcomes,
                    single_draws(s, len(cases)),
                    ThawedRouter(frozen, rows),
                    mahc,
                    ledger,
                    variant=variant,
                    label=label,
                    mean_gap_s=mean_gap,
                    counts=records,
                    measure=REWARD,
                )
                if err := check_pairs(path):
                    raise RuntimeError(f"{path.name}: {err}")
                for stage in (PROVISIONAL, TERMINAL):
                    records[stage] += path.read_text(encoding="utf-8").count(
                        f'"stage": "{stage}"'
                    )
                stats.append(_pool_stats(decisions, tau))
                merged.update(rre_by_case_stream(decisions, cases, tau, label))
            per_variant[variant] = {
                k: _spread([st[k] for st in stats])
                for k in ("hit", "escalated_share", "rre_rate", "with_r1")
            }
            rre_maps[variant] = merged
        per_variant["e_h5"] = e_h5_forms(
            rre_maps["HELIOS-Full"], rre_maps["HELIOS-noReconcile"]
        )
        report["gaps"][str(mean_gap)] = per_variant
    report["records"] = records
    return report


def pool_main(campaign: Path, out: Path | None) -> int:
    out = out or campaign / POOL_OUT
    if out.exists():
        print(f"[reward] refused: {out} exists", file=sys.stderr)
        return 2
    if Path.cwd().resolve() != REPO_ROOT:
        print("[reward] run from the repository root", file=sys.stderr)
        return 2
    key = load_key()
    try:
        cases, counts = pool_cases(campaign, key)
    except (PoolLockedError, ValueError) as exc:
        print(f"[reward] refused: {exc}", file=sys.stderr)
        return 2
    if not cases:
        print("[reward] refused: no featured case in the E-H5 subset", file=sys.stderr)
        return 2
    build_cases, build_counts = collect_cases(key=key)
    try:
        report = run_pool_replay(cases, build_cases, out)
    except ValueError as exc:
        print(f"[reward] refused: {exc}", file=sys.stderr)
        return 2
    report.update(subset_counts=counts, build_counts=build_counts)
    path = out / "report.json"
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for gap, body in report["gaps"].items():
        same = (body["e_h5"] or {}).get("same_case_form") or {}
        print(
            f"[reward] gap {gap}s: E-H5 same-case n {same.get('n')}, "
            f"mean difference {same.get('mean_difference')}"
        )
    print(
        f"[reward] wrote {path} ({counts['found']} of {counts['subset']} subset cases)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", type=int, help="reward_run<N>.json (build replay)")
    parser.add_argument("--out", type=Path, default=None, help="ledger directory")
    parser.add_argument("--corpus", choices=("build", "pool"), default="build")
    parser.add_argument("--campaign", type=Path, help="scored E1 campaign (pool)")
    args = parser.parse_args(argv)
    if args.corpus == "pool":
        if args.campaign is None:
            parser.error("--corpus pool needs --campaign")
        return pool_main(args.campaign, args.out)
    if args.run is None:
        parser.error("the build replay needs --run")
    out = args.out or REPO_ROOT / f"data/replay/reward_run{args.run}"
    if out.exists():
        print(f"[reward] refused: {out} exists", file=sys.stderr)
        return 2
    if (REPORT_DIR / f"reward_run{args.run}.json").exists():
        print(f"[reward] refused: reward_run{args.run}.json exists", file=sys.stderr)
        return 2
    if Path.cwd().resolve() != REPO_ROOT:
        print("[reward] run from the repository root", file=sys.stderr)
        return 2
    cases, counts = collect_cases(key=load_key())
    report = run_replays(cases, out)
    report.update(counts, cases=len(cases))
    path = _write(f"reward_run{args.run}.json", report)
    _print(report)
    print(f"[reward] wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
