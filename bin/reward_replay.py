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
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bin.labelling_runs import load_signer
from bin.log_deviation import load_key
from bin.router_build_run import REPORT_DIR, _write, collect_cases
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
)
from helios.evaluation.router_calibration import arm_outcomes
from helios.orchestrator.reward_ledger import (
    PROVISIONAL,
    TERMINAL,
    RewardLedger,
    check_pairs,
)
from helios.vcl import get_variant, set_current_manifest
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Sequence

    from helios.evaluation.reward_replay import Decision

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", type=int, required=True, help="reward_run<N>.json")
    parser.add_argument("--out", type=Path, default=None, help="ledger directory")
    parser.add_argument("--corpus", choices=("build", "pool"), default="build")
    args = parser.parse_args(argv)
    if args.corpus == "pool":
        print("[reward] the pool is locked until tag build-freeze", file=sys.stderr)
        return 2
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
