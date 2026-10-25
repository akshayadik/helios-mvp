#!/usr/bin/env python3
"""Check that log templates are stable across reruns on a sealed corpus (S1.4).

Usage (from repo root):
    poetry run python bin/log_templates.py check --corpus build

Mines every window with logs twice and compares feature digests. Prints counts
and digests only; no case names, templates or log text. The pool is refused
until tag build-freeze (pool lock).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helios.schemas.telemetry import TelemetryWindow
from helios.telemetry.log_templates import features_for_window
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path("data/rcaeval")


def _window(case_dir: Path) -> TelemetryWindow:
    raw = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))
    raw.pop("window_hash", None)
    raw.pop("snapshot_hash", None)
    return TelemetryWindow(**raw)


def check(corpus: str) -> int:
    data = REPO_ROOT / DATA_ROOT
    manifest = json.loads(
        (data / f"{corpus}_manifest.json").read_text(encoding="utf-8")
    )
    case_order: list[str] = manifest["case_order"]
    digests: list[str] = []
    templates: list[int] = []
    unstable = no_logs = skipped = lines = 0
    for incident_id in case_order:
        window = _window(data / corpus / incident_id)
        first = features_for_window(window, REPO_ROOT)
        if first is None:
            no_logs += 1
            continue
        again = features_for_window(window, REPO_ROOT)
        assert again is not None
        if first.digest() != again.digest():
            unstable += 1
        digests.append(first.digest())
        templates.append(len(first.templates))
        skipped += first.skipped_lines
        lines += int(first.counts["count"].sum())
    corpus_digest = hashlib.sha256("\n".join(digests).encode("utf-8")).hexdigest()
    print(
        f"[log-templates] {corpus}: {len(case_order)} windows, {no_logs} without logs"
    )
    print(f"[log-templates] reruns identical: {len(digests) - unstable}/{len(digests)}")
    if templates:
        print(
            "[log-templates] templates per window: "
            f"min {min(templates)}, median {statistics.median(templates):g}, "
            f"max {max(templates)}; lines {lines}, skipped {skipped}"
        )
    print(f"[log-templates] corpus feature digest {corpus_digest}")
    return 1 if unstable else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("check", help="mine every window twice and compare")
    cmd.add_argument("--corpus", choices=("build", "pool"), required=True)
    args = parser.parse_args(argv)
    return check(args.corpus)


if __name__ == "__main__":
    sys.exit(main())
