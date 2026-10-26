#!/usr/bin/env python3
"""Calibrate the K-hop pruner (Algorithm 5) on build data (S1.7).

Usage (from repo root):
    poetry run python bin/khop_calibrate.py --corpus build [--limit N]
    poetry run python bin/khop_calibrate.py --corpus captures   (OTel Demo, exploratory)

Builds each window's UEG-C once (HELIOS-Full), prunes it for every (K, top-n)
in the grid and prints counts only: services kept, graphs in the 50-200 range,
edges cut, and how often the labelled root cause stays in the pruned graph
(build and capture labels only — the pool is refused, it is locked until tag
build-freeze). The grid runs Algorithm 5 without the 50-node floor, so it
measures how far from the seeds the root cause lies. Selection rule, fixed
before the build run (design note): highest root-cause retention; ties go to
the smaller K, then the smaller top-n. The selected setting is then reported
with the floor on, as the orchestrator runs it.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helios.graph.khop_pruner import MIN_NODES, khop_prune
from helios.graph.ueg_c_builder import build_ueg_c
from helios.schemas.telemetry import TelemetryWindow
from helios.vcl import set_current_manifest
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance
from helios.vcl.variants import get_variant

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path("data/rcaeval")
CAPTURES_ROOT = Path("data/captures")
CAPTURES_TRUTH = Path("data/ground_truth.json")
K_GRID = (0, 1, 2, 3)
TOP_N_GRID = (50, 120, 200)


def _key(name: str) -> str:
    """Comparable service name: OTel labels say `adService`, nodes say `ad`."""
    key = "".join(ch for ch in name.lower() if ch.isalnum())
    return key.removesuffix("service") or key


def _window(case_dir: Path) -> TelemetryWindow:
    raw = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))
    raw.pop("window_hash", None)
    raw.pop("snapshot_hash", None)
    return TelemetryWindow(**raw)


def _cases(corpus: str, limit: int | None) -> tuple[Path, list[str], dict[str, str]]:
    if corpus == "captures":
        base = REPO_ROOT / CAPTURES_ROOT
        order = sorted(
            d.name for d in base.iterdir() if (d / "manifest.json").is_file()
        )
        truth = json.loads((REPO_ROOT / CAPTURES_TRUTH).read_text(encoding="utf-8"))
        labels = {k: v["root_cause_service"] for k, v in truth.items()}
    else:
        data = REPO_ROOT / DATA_ROOT
        index = json.loads((data / "build_manifest.json").read_text(encoding="utf-8"))
        order = index["case_order"]
        truth = json.loads(
            (data / "ground_truth_build.json").read_text(encoding="utf-8")
        )
        labels = {k: v["root_cause_service"] for k, v in truth["cases"].items()}
        base = data / "build"
    return base, order[:limit], labels


def _summary(values: list[int]) -> str:
    if not values:
        return "none"
    return f"min {min(values)}, median {statistics.median(values):g}, max {max(values)}"


def calibrate(corpus: str, limit: int | None) -> int:
    manifest = get_variant("HELIOS-Full")
    set_current_manifest(manifest)
    variant_hash = manifest.compute_variant_config_hash()
    base, order, labels = _cases(corpus, limit)
    graphs = []
    for incident_id in order:
        snapshot = build_ueg_c(
            _window(base / incident_id), variant_hash, root=REPO_ROOT
        )
        if snapshot is not None and incident_id in labels:
            graphs.append((snapshot, _key(labels[incident_id])))
    sizes = [len(s.candidate_ids()) for s, _ in graphs]
    labelled = [g for g in graphs if g[1] in {_key(c) for c in g[0].candidate_ids()}]
    large = sum(n > MIN_NODES for n in sizes)
    print(f"[khop] {corpus}: {len(order)} windows, {len(graphs)} graphs")
    print(f"[khop] services per graph: {_summary(sizes)}")
    print(f"[khop] graphs with more than {MIN_NODES} services: {large}")
    print(f"[khop] root cause is a service node: {len(labelled)}/{len(graphs)}")
    seed_hits = 0
    sources: dict[str, int] = {}
    results = []
    for k in K_GRID:
        for top_n in TOP_N_GRID:
            kept, reach, cut_r, after = [], [], [], []
            retained = 0
            for snapshot, root in labelled:
                pruned, res = khop_prune(snapshot, k=k, top_n=top_n, min_nodes=0)
                kept.append(res.services_after)
                reach.append(res.services_in_reach)
                cut_r.append(res.edges_below_r)
                after.append(res.edges_after)
                retained += root in {_key(c) for c in pruned.candidate_ids()}
                if k == K_GRID[0] and top_n == TOP_N_GRID[0]:
                    seed_hits += root in {_key(s) for s in res.seeds}
                    sources[res.seed_source.value] = (
                        sources.get(res.seed_source.value, 0) + 1
                    )
            in_range = sum(MIN_NODES <= n <= top_n for n in kept)
            results.append((-retained, k, top_n))
            print(
                f"[khop] K={k} top-n={top_n}: root cause kept {retained}/{len(labelled)}; "
                f"services in reach {_summary(reach)}; kept {_summary(kept)}; "
                f"graphs in {MIN_NODES}-{top_n}: {in_range}; "
                f"edges cut by r {_summary(cut_r)}; edges kept {_summary(after)}"
            )
    print(f"[khop] seed sources: {dict(sorted(sources.items()))}")
    print(f"[khop] root cause among the seeds: {seed_hits}/{len(labelled)}")
    if results:
        _, k, top_n = min(results)
        print(f"[khop] selected by the rule: K={k}, top-n={top_n}")
        runs = [khop_prune(s, k=k, top_n=top_n) for s, _ in labelled]
        kept_root = sum(
            root in {_key(c) for c in pruned.candidate_ids()}
            for (pruned, _), (_, root) in zip(runs, labelled, strict=True)
        )
        print(
            f"[khop] with the {MIN_NODES}-node floor: root cause kept "
            f"{kept_root}/{len(labelled)}; services kept "
            f"{_summary([r.services_after for _, r in runs])}; nodes kept "
            f"{_summary([r.nodes_after for _, r in runs])}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", choices=("build", "captures"), required=True)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    return calibrate(args.corpus, args.limit)


if __name__ == "__main__":
    sys.exit(main())
