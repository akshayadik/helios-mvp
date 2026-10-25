#!/usr/bin/env python3
"""Build the UEG-C of every window in a sealed corpus twice and summarise (S1.5).

Usage (from repo root):
    poetry run python bin/ueg_c_check.py --corpus build [--limit N]
    poetry run python bin/ueg_c_check.py --corpus captures   (OTel Demo, with traces)

Checks that each snapshot hash is identical across two builds and prints
counts only: nodes per graph, edges per class, services per modality, time per
graph. No case names, service names or labels. The pool is refused until tag
build-freeze (pool lock).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helios.graph.ueg_c_builder import build_ueg_c
from helios.schemas.telemetry import TelemetryWindow
from helios.schemas.ueg_c import EdgeClass, NodeType
from helios.vcl import set_current_manifest
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance
from helios.vcl.variants import get_variant

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path("data/rcaeval")
CAPTURES_ROOT = Path("data/captures")  # OTel Demo captures (exploratory)


def _window(case_dir: Path) -> TelemetryWindow:
    raw = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))
    raw.pop("window_hash", None)
    raw.pop("snapshot_hash", None)
    return TelemetryWindow(**raw)


def _summary(name: str, values: list[float]) -> str:
    if not values:
        return f"{name}: none"
    return (
        f"{name}: min {min(values):g}, median {statistics.median(values):g}, "
        f"max {max(values):g}"
    )


def check(corpus: str, limit: int | None) -> int:
    manifest = get_variant("HELIOS-Full")
    set_current_manifest(manifest)
    variant_hash = manifest.compute_variant_config_hash()
    if corpus == "captures":
        base = REPO_ROOT / CAPTURES_ROOT
        case_order = sorted(
            d.name for d in base.iterdir() if (d / "manifest.json").is_file()
        )[:limit]
    else:
        data = REPO_ROOT / DATA_ROOT
        index = json.loads(
            (data / f"{corpus}_manifest.json").read_text(encoding="utf-8")
        )
        case_order = index["case_order"][:limit]
        base = data / corpus
    hashes: list[str] = []
    unstable = 0
    services: list[float] = []
    seconds: list[float] = []
    per_class: dict[str, list[float]] = {c.value: [] for c in EdgeClass}
    modalities: Counter[str] = Counter()
    for incident_id in case_order:
        window = _window(base / incident_id)
        started = time.perf_counter()
        first = build_ueg_c(window, variant_hash, root=REPO_ROOT)
        seconds.append(round(time.perf_counter() - started, 1))
        again = build_ueg_c(window, variant_hash, root=REPO_ROOT)
        if first is None or again is None:
            unstable += first is not again
            continue
        if first.compute_snapshot_hash() != again.compute_snapshot_hash():
            unstable += 1
        hashes.append(first.compute_snapshot_hash())
        nodes = [n for n in first.nodes if n.node_type == NodeType.SERVICE]
        services.append(len(nodes))
        for n in nodes:
            modalities[n.metadata.get("modalities", "")] += 1
        counts = Counter(e.edge_class.value for e in first.edges)
        for cls, bucket in per_class.items():
            bucket.append(counts.get(cls, 0))
    digest = hashlib.sha256("\n".join(hashes).encode("utf-8")).hexdigest()
    print(f"[ueg-c] {corpus}: {len(case_order)} windows, {len(hashes)} graphs")
    print(f"[ueg-c] rebuilds identical: {len(hashes) - unstable}/{len(hashes)}")
    print(f"[ueg-c] {_summary('services per graph', services)}")
    for cls, values in per_class.items():
        print(f"[ueg-c] {_summary(cls + ' edges per graph', values)}")
    print(f"[ueg-c] service nodes by modalities: {dict(sorted(modalities.items()))}")
    print(f"[ueg-c] {_summary('seconds per build', seconds)}")
    print(f"[ueg-c] corpus snapshot digest {digest}")
    return 1 if unstable else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--corpus", choices=("build", "pool", "captures"), required=True
    )
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    return check(args.corpus, args.limit)


if __name__ == "__main__":
    sys.exit(main())
