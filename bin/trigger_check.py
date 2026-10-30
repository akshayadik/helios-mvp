#!/usr/bin/env python3
"""Run the shared detection trigger over build windows and print counts (S2.1).

Usage (from repo root):
    poetry run python bin/trigger_check.py --corpus otel_build|rcaeval_build|captures
    poetry run python bin/trigger_check.py --window DIR [--json] [--with-dpipe]
        [--with-gpipe [--gpipe-params FILE]]

Counts mode prints how many triggers came from each source and the SHA-256 of
the canonical JSON of every record, so two runs can be compared byte for byte;
it never prints an incident ID or a suspect. ``--json`` prints the records
themselves (one per line) and is meant for a single window or a test fixture;
``--with-dpipe`` adds, after each record, the D-pipe verdict computed from it
(HELIOS-Full, frozen D-pipe parameters) for the rerun-equality check;
``--with-gpipe`` (S2.2) adds G-pipe's ranking, sigma and evidence on the graph
the runner builds, ignoring the routing gate as the selection run does (its
digest is printed in counts mode).
The confirmatory pool is refused: it is locked until tag build-freeze (D11).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helios.orchestrator.runner import incident_graph
from helios.pipelines.d_pipe.params import load_dpipe_params
from helios.pipelines.d_pipe.pipeline import run_dpipe
from helios.pipelines.g_pipe.params import GPIPE_PARAMS_PATH, load_gpipe_params
from helios.pipelines.g_pipe.pipeline import gpipe_rank
from helios.schemas.telemetry import TelemetryWindow
from helios.telemetry.trigger import (
    DETECTOR_PARAMS_PATH,
    DetectorParams,
    TriggerRecord,
    detect,
    load_detector_params,
)
from helios.vcl import get_variant, set_current_manifest
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance
from helios.vcl.utils import canonical_json

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPORA: dict[str, Path] = {
    "captures": Path("data/captures"),
    "otel_build": Path("data/otel/build"),
    "otel_build_v2": Path("data/otel/build_v2"),
    "otel_build_v3": Path("data/otel/build_v3"),
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


def _dpipe_out(
    window: TelemetryWindow, record: TriggerRecord, ref: float
) -> dict[str, Any]:
    manifest = get_variant("HELIOS-Full")
    set_current_manifest(manifest)
    dp = load_dpipe_params()
    out = run_dpipe(
        window=window,
        ueg_c=None,
        incident_id=window.incident_id,
        snapshot_hash=window.compute_window_hash(),
        variant_config_hash=manifest.compute_variant_config_hash(),
        evaluation_phase=window.evaluation_phase,
        run_id="trigger-check",
        trigger=record,
        evidence_ref=ref,
        w_error=dp.w_error,
        w_resource=dp.w_resource,
        rho_threshold=dp.rho_threshold,
        topology_boost_factor=dp.topology_boost_factor,
    )
    return {k: str(v) if hasattr(v, "value") else v for k, v in out.items()}


def _gpipe_line(
    window: TelemetryWindow,
    record: TriggerRecord,
    detector: DetectorParams,
    gparams_path: Path,
) -> str:
    dpipe = _dpipe_out(window, record, detector.threshold)
    manifest = get_variant("HELIOS-Full")
    set_current_manifest(manifest)
    graph, _seeds = incident_graph(
        window, manifest, manifest.compute_variant_config_hash(), record
    )
    if graph is None:
        return canonical_json({"graph": None})
    result = gpipe_rank(
        graph,
        dpipe.get("candidate_scores", {}),
        manifest=manifest,
        window=window,
        trigger=record,
        params=load_gpipe_params(gparams_path),
        detector=detector,
        root=REPO_ROOT,
    )
    return canonical_json(
        {
            "ranker": result.ranker,
            "ranked": result.ranked,
            "scores": result.scores,
            "sigma": result.sigma,
            "evidence": result.evidence,
        }
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--corpus", choices=(*CORPORA, "pool"))
    target.add_argument("--window", help="one capture directory (with manifest.json)")
    parser.add_argument("--params", default=str(DETECTOR_PARAMS_PATH))
    parser.add_argument("--json", action="store_true", help="print the records")
    parser.add_argument(
        "--with-dpipe", action="store_true", help="also print each D-pipe verdict"
    )
    parser.add_argument(
        "--with-gpipe",
        action="store_true",
        help="also print G-pipe's ranking and evidence (no routing gate)",
    )
    parser.add_argument("--gpipe-params", default=str(GPIPE_PARAMS_PATH))
    args = parser.parse_args(argv)
    if args.corpus == "pool":
        print("[trigger] the pool is locked until tag build-freeze", file=sys.stderr)
        return 2

    params = load_detector_params(Path(args.params))
    lines: list[str] = []
    dpipe_lines: list[str] = []
    gpipe_lines: list[str] = []
    for case in _case_dirs(args):
        window = _window(case)
        record = detect(window, params, root=REPO_ROOT)
        lines.append(_line(record))
        if args.with_dpipe:
            dpipe_lines.append(
                canonical_json(_dpipe_out(window, record, params.threshold))
            )
        if args.with_gpipe:
            gpipe_lines.append(
                _gpipe_line(window, record, params, Path(args.gpipe_params))
            )
    if args.json:
        columns = [lines, *(c for c in (dpipe_lines, gpipe_lines) if c)]
        print("\n".join(x for row in zip(*columns, strict=True) for x in row))
        return 0
    sources = Counter(json.loads(line)["source"] for line in lines)
    digest = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
    name = args.corpus or "window"
    print(
        f"[trigger] {name}: {len(lines)} windows; sources {dict(sorted(sources.items()))}"
    )
    print(f"[trigger] params provisional={params.provisional}; records digest {digest}")
    if gpipe_lines:
        g_digest = hashlib.sha256("\n".join(gpipe_lines).encode("utf-8")).hexdigest()
        print(f"[trigger] gpipe digest {g_digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
