#!/usr/bin/env python3
"""Run the shared detection trigger over build windows and print counts (S2.1).

Usage (from repo root):
    poetry run python bin/trigger_check.py --corpus otel_build|rcaeval_build|captures
    poetry run python bin/trigger_check.py --window DIR [--json]

Counts mode prints how many triggers came from each source and the SHA-256 of
the canonical JSON of every record, so two runs can be compared byte for byte;
it never prints an incident ID or a suspect. ``--json`` prints the records
themselves (one per line) and is meant for a single window or a test fixture.
The confirmatory pool is refused: it is locked until tag build-freeze (D11).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helios.schemas.telemetry import TelemetryWindow
from helios.telemetry.trigger import (
    DETECTOR_PARAMS_PATH,
    TriggerRecord,
    detect,
    load_detector_params,
)
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance
from helios.vcl.utils import canonical_json

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPORA: dict[str, Path] = {
    "captures": Path("data/captures"),
    "otel_build": Path("data/otel/build"),
    "rcaeval_build": Path("data/rcaeval/build"),
}


def _window(case_dir: Path) -> TelemetryWindow:
    raw = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))
    raw.pop("window_hash", None)
    raw.pop("snapshot_hash", None)
    return TelemetryWindow(**raw)


def _case_dirs(args: argparse.Namespace) -> list[Path]:
    if args.window is not None:
        return [Path(args.window)]
    base = REPO_ROOT / CORPORA[args.corpus]
    return sorted(d for d in base.iterdir() if (d / "manifest.json").is_file())


def _line(record: TriggerRecord) -> str:
    return canonical_json(record.model_dump(mode="json"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--corpus", choices=(*CORPORA, "pool"))
    target.add_argument("--window", help="one capture directory (with manifest.json)")
    parser.add_argument("--params", default=str(DETECTOR_PARAMS_PATH))
    parser.add_argument("--json", action="store_true", help="print the records")
    args = parser.parse_args(argv)
    if args.corpus == "pool":
        print("[trigger] the pool is locked until tag build-freeze", file=sys.stderr)
        return 2

    params = load_detector_params(Path(args.params))
    lines = [
        _line(detect(_window(case), params, root=REPO_ROOT))
        for case in _case_dirs(args)
    ]
    if args.json:
        print("\n".join(lines))
        return 0
    sources = Counter(json.loads(line)["source"] for line in lines)
    digest = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
    name = args.corpus or "window"
    print(
        f"[trigger] {name}: {len(lines)} windows; sources {dict(sorted(sources.items()))}"
    )
    print(f"[trigger] params provisional={params.provisional}; records digest {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
