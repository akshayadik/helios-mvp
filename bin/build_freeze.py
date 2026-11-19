#!/usr/bin/env python3
"""Write or verify the build-freeze record (S5.6, design F-a).

Usage (from the repository root):
    poetry run python bin/build_freeze.py --write    # writes data/frozen/build_freeze.json
    poetry run python bin/build_freeze.py --verify   # recomputes and compares
    poetry run python bin/build_freeze.py --check    # the pool gate's own check

Every value is computed, none typed by hand, and the record has no
timestamp, so ``--verify`` recomputes it byte for byte. The commit that holds
the record cannot be named inside it: the commit SHA goes into the tag
message, the deviation entry and deposit 2.

The confirmatory pool's labels are never read: the pool part comes from
``data/rcaeval/pool_manifest.json`` (seal digests and stream paths) only.

Exit codes: 0 ok; 1 the record differs or the build is not frozen; 2 usage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helios.evaluation.run_metrics import METRICS_VERSION
from helios.evaluation.scoring import SCORING_VERSION
from helios.pipelines.l_pipe import lpipe_config
from helios.vcl import freeze
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance
from helios.vcl.variants import CONFIRMATORY_VARIANTS, EXPLORATORY_VARIANTS

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "build-freeze-v1"
POOL_MANIFEST = "data/rcaeval/pool_manifest.json"
PRICE_BOOK = "docs/tracking/price_book.md"
ANALYSIS_PLAN = "research/osf/analysis_plan.json"
_PIN = re.compile(r"([\w./:-]+@sha256:[0-9a-f]{64})")

# Design F-c: items outside the frozen build, each already recorded.
STAGE_B_MOVES: tuple[dict[str, Any], ...] = (
    {
        "item": "P4 cognitive layer (p4_cognitive): no consumer; noCogni refused; E-H1",
        "entries": [90],
    },
    {
        "item": "HIS tiers (his_tier): no consumer; HIS3 refused; E-H9",
        "entries": [90],
    },
    {"item": "sampling_regime_tag: no variant", "entries": [90]},
    {
        "item": "E-H8: the frozen router does not read the ACP",
        "entries": [82, 83],
    },
    {
        "item": "FGSV full twin, IOL sensitivity beyond the shared detector, "
        "NER redaction (lite versions frozen)",
        "entries": [89],
    },
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _images(root: Path, files: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for name in files:
        if not name.startswith(("deploy/", "baselines/")):
            continue
        pins = sorted(set(_PIN.findall((root / name).read_text(errors="replace"))))
        if pins:
            out[name] = pins
    return out


def _pool(root: Path) -> dict[str, Any]:
    path = root / POOL_MANIFEST
    manifest = json.loads(path.read_text())
    return {
        "file": POOL_MANIFEST,
        "sha256": _sha256(path),
        "manifest_digest": manifest["manifest_digest"],
        "cases": len(manifest["case_order"]),
        "dataset_revision": manifest["dataset_revision"],
    }


def build_record(root: Path = REPO_ROOT) -> dict[str, Any]:
    """The full record; ``frozen_paths`` is what the pool gate compares."""
    section = freeze.frozen_paths_section(root)
    files = sorted(section["files"])
    parameters = {
        name: section["files"][name]
        for name in files
        if name.startswith("data/frozen/") and name.endswith(".json")
    }
    router = json.loads((root / "data/frozen/router_params.json").read_text())
    variants = {**CONFIRMATORY_VARIANTS, **EXPLORATORY_VARIANTS}
    return {
        "schema_version": SCHEMA,
        "tag": freeze.BUILD_FREEZE_TAG,
        "design": "docs/sprints/s5-integration-freeze/s5_6_build_freeze_design.md",
        "parameters": parameters,
        "router": {
            "tau_acc": router["tau_acc"],
            "price_book_digest": router["price_book_digest"],
        },
        "price_book": {"file": PRICE_BOOK, "sha256": _sha256(root / PRICE_BOOK)},
        "model": {
            "name": lpipe_config.MODEL_NAME,
            "digest": lpipe_config.EXPECTED_MODEL_DIGEST,
            "protocol_a": {
                "temperature": lpipe_config.PROTOCOL_A_TEMPERATURE,
                "top_p": lpipe_config.PROTOCOL_A_TOP_P,
                "top_k": lpipe_config.PROTOCOL_A_TOP_K,
                "seed": lpipe_config.LLAMA_SEED,
            },
            "worker_prompt_shas": dict(sorted(lpipe_config.WORKER_PROMPT_SHAS.items())),
        },
        "images": _images(root, files),
        "variants": {
            name: m.compute_variant_config_hash()
            for name, m in sorted(variants.items())
        },
        "versions": {
            "scoring": SCORING_VERSION,
            "metrics": METRICS_VERSION,
            "analysis_plan_sha256": _sha256(root / ANALYSIS_PLAN),
        },
        "pool": _pool(root),
        "stage_b_moves": list(STAGE_B_MOVES),
        "frozen_paths": section,
    }


def render(record: dict[str, Any]) -> str:
    return json.dumps(record, indent=1, sort_keys=False, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    path = args.root / freeze.RECORD_PATH
    if args.check:
        problems = freeze.freeze_problems(args.root)
        for p in problems:
            print(f"[freeze] {p}")
        print(
            "[freeze] frozen build" if not problems else "[freeze] NOT the frozen build"
        )
        return 1 if problems else 0
    text = render(build_record(args.root))
    if args.write:
        path.write_text(text)
        record = json.loads(text)
        print(
            f"[freeze] wrote {freeze.RECORD_PATH}: {record['frozen_paths']['count']} "
            f"frozen files, digest {record['frozen_paths']['digest'][:12]}"
        )
        return 0
    if not path.is_file():
        print(f"[freeze] {freeze.RECORD_PATH} does not exist")
        return 1
    if path.read_text() != text:
        recorded = json.loads(path.read_text())
        for p in freeze.divergence(recorded, args.root)[:20]:
            print(f"[freeze] {p}")
        print("[freeze] the record differs from the build")
        return 1
    print(f"[freeze] record verified: {freeze.RECORD_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
