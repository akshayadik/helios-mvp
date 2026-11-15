#!/usr/bin/env python3
"""S5.1 system test over one campaign directory (design s5_1_system_test_design.md).

    poetry run python bin/system_test.py --dir data/campaigns/s5_1/otel_build_v3 \
        --out docs/sprints/s5-integration-freeze/system_test/otel_build_v3.json

Runs the S-c checks (bin/system_test_checks.py) and the campaign ledger
check (bin/verify_ledgers.py --campaign). Exit 1 if any check fails. Reads no
ground truth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from bin.system_test_checks import (  # noqa: E402
    HELIOS_ENABLE_SYSTEM_TEST,
    system_report,
)
from helios.vcl import VCLFlag  # noqa: E402, F401 — flag-guard compliance


def _digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ledger_check(directory: Path) -> dict[str, object]:
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "bin" / "verify_ledgers.py"),
            "--campaign",
            str(directory),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-3:]
    return {"returncode": proc.returncode, "tail": tail}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--dir", type=Path, required=True)
    ap.add_argument("--phases", default="confirmatory,exploratory")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--no-ledgers", action="store_true", help="tests only")
    args = ap.parse_args(argv)
    if not HELIOS_ENABLE_SYSTEM_TEST:
        print("system test disabled", file=sys.stderr)
        return 1
    report = system_report(args.dir, [p for p in args.phases.split(",") if p])
    if not args.no_ledgers:
        ledgers = ledger_check(args.dir)
        report["ledgers"] = ledgers
        if ledgers["returncode"] != 0:
            report["result"] = "fail"
    report["digests"] = {
        name: _digest(args.dir / name)
        for name in ("schedule.json", "campaign_log.jsonl", "exclusion_ledger.jsonl")
    }
    text = json.dumps(report, indent=1, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    c = report["completion"]
    print(
        f"{report['corpus']}: {c['scheduled']} scheduled, events {c['events']}, "
        f"gate exclusions {c['gate_exclusions']}; result {report['result'].upper()}"
    )
    for name, m in report["flag_marks"].items():
        if m["problems"]:
            print(f"  {name}: {m['problems']}")
    for name, u in report["unchanged_verdicts"].items():
        if u["differ"]:
            print(f"  {name}: {len(u['differ'])} cases differ from Full")
    for problem in report["parameter_problems"]:
        print(f"  parameters: {problem}")
    return 0 if report["result"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
