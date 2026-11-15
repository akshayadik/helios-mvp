#!/usr/bin/env python3
"""S5.5 per-call token equality over one campaign's determinism rerun.

    poetry run python bin/determinism_report.py --dir data/campaigns/s5_1/otel_build_v3 \
        --out docs/sprints/s5-integration-freeze/determinism/otel_build_v3.json

Design s5_5_determinism_design.md P-c, P-d. Reads ``determinism.json`` (written
by ``bin/helios_campaign.py compare``) and the two result stores. For every
L-pipe worker call that produced output on both sides, it asks whether the
prompt hashes match and, where they do, whether the raw model output is
byte-identical. Run-level rows (fused, L-pipe evidence, narrative) are
summarised as ``compare`` wrote them. Reads no ground truth; changes no run.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from helios.vcl import VCLFlag  # noqa: E402, F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

HELIOS_ENABLE_DETERMINISM_REPORT: bool = True
WORKERS: tuple[str, ...] = ("log", "metric", "trace")


def _prompt(evidence: Mapping[str, Any], worker: str) -> tuple[Any, ...]:
    """What the worker's rendered prompt is made of (personas.render_prompt):
    the persona template hash, the candidate list and the worker's digest.
    ``prompt_shas`` alone hashes only the template, the same for every case."""
    return (
        (evidence.get("prompt_shas") or {}).get(worker),
        evidence.get("candidates"),
        (evidence.get("digests") or {}).get(worker),
    )


def compare_calls(
    first: Mapping[str, Any] | None, again: Mapping[str, Any] | None
) -> dict[str, list[str]]:
    """Per worker: ``equal``, ``unequal``, ``prompt_differs`` or ``one_sided``
    (output on one side only); workers silent on both sides are omitted."""
    out: dict[str, list[str]] = defaultdict(list)
    a, b = first or {}, again or {}
    for w in WORKERS:
        raw_a = ((a.get("workers") or {}).get(w) or {}).get("raw")
        raw_b = ((b.get("workers") or {}).get(w) or {}).get("raw")
        if raw_a is None and raw_b is None:
            continue
        if raw_a is None or raw_b is None:
            out["one_sided"].append(w)
        elif _prompt(a, w) != _prompt(b, w):
            out["prompt_differs"].append(w)
        elif raw_a == raw_b:
            out["equal"].append(w)
        else:
            out["unequal"].append(w)
    return dict(out)


def _rate(c: Mapping[str, int]) -> dict[str, Any]:
    compared = c.get("equal", 0) + c.get("unequal", 0)
    return {
        "calls_compared": compared,
        "equal": c.get("equal", 0),
        "unequal": c.get("unequal", 0),
        "prompt_differs": c.get("prompt_differs", 0),
        "one_sided": c.get("one_sided", 0),
        "token_equality_rate": (
            round(c.get("equal", 0) / compared, 6) if compared else None
        ),
    }


def determinism_report(
    rows: Iterable[Mapping[str, Any]],
    fetch_first: Callable[[str], Mapping[str, Any] | None],
    fetch_again: Callable[[str], Mapping[str, Any] | None],
) -> dict[str, Any]:
    """Per-call counts and run-level counts, overall and per system."""
    calls: dict[str, Counter[str]] = defaultdict(Counter)
    runs: dict[str, Counter[str]] = defaultdict(Counter)
    detail: list[dict[str, Any]] = []
    for row in rows:
        system = str(row["system"])
        runs[system]["pairs"] += 1
        for part in row.get("differs", []):
            runs[system][f"differs_{part}"] += 1
        for part in row.get("not_comparable", []):
            runs[system][f"not_comparable_{part}"] += 1
        runs[system]["nondeterministic"] += bool(row.get("nondeterministic"))
        if system.startswith("BASELINE-"):
            continue
        result = compare_calls(
            fetch_first(str(row["run_id"])), fetch_again(str(row["rerun_id"]))
        )
        for kind, workers in result.items():
            calls[system][kind] += len(workers)
        if any(k != "equal" for k in result):
            detail.append({"run_id": row["run_id"], "system": system, **result})
    total_calls: Counter[str] = sum(calls.values(), Counter())
    total_runs: Counter[str] = sum(runs.values(), Counter())
    return {
        "calls": {"all": _rate(total_calls)}
        | {s: _rate(c) for s, c in sorted(calls.items())},
        "runs": {"all": dict(total_runs)}
        | {s: dict(c) for s, c in sorted(runs.items())},
        "calls_not_equal": detail,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--dir", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    if not HELIOS_ENABLE_DETERMINISM_REPORT:
        print("determinism report disabled", file=sys.stderr)
        return 1
    from helios.store.result_store import ResultStore

    rows = json.loads((args.dir / "determinism.json").read_text())
    first = ResultStore(args.dir / "results.duckdb")
    again = ResultStore(args.dir / "rerun.duckdb")
    try:
        report = determinism_report(
            rows,
            lambda r: first.fetch_evidence(r, "lpipe"),
            lambda r: again.fetch_evidence(r, "lpipe"),
        )
    finally:
        first.close()
        again.close()
    report["campaign"] = args.dir.name
    text = json.dumps(report, indent=1, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    c, r = report["calls"]["all"], report["runs"]["all"]
    print(
        f"{args.dir.name}: {r.get('pairs', 0)} pairs, "
        f"{r.get('nondeterministic', 0)} not equal; calls compared "
        f"{c['calls_compared']}, equal {c['equal']}, prompt differs "
        f"{c['prompt_differs']}, one-sided {c['one_sided']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
