#!/usr/bin/env python3
"""Parse ground_truth_labelling.md and emit data/ground_truth.json.

Usage:
    python scripts/compile_ground_truth.py [--input PATH] [--output PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

_DEFAULT_INPUT = Path("docs/tracking/ground_truth_labelling.md")
_DEFAULT_OUTPUT = Path("data/ground_truth.json")


def _parse_md_table(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    header: list[str] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if header is None:
            if "incident_id" in cells:
                header = cells
            continue
        if re.fullmatch(r"[-| :]+", line):
            continue
        if header and len(cells) == len(header):
            rows.append(dict(zip(header, cells, strict=False)))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile ground truth labels to JSON.")
    parser.add_argument("--input", type=Path, default=_DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    text = args.input.read_text(encoding="utf-8")
    rows = _parse_md_table(text)
    if not rows:
        print(f"ERROR: no rows parsed from {args.input}", file=sys.stderr)
        return 1

    result = {r["incident_id"]: r for r in rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Compiled {len(result)} entries → {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
