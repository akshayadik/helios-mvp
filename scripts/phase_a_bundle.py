#!/usr/bin/env python3
"""Phase A (A6): replication-bundle manifest for one results package.

Usage (from the checkout that produced the results, normally the phase E
worktree at the freeze tag):
    poetry run python scripts/phase_a_bundle.py \
        --campaign CAMPAIGN [--campaign ...] \
        --artefact analysis.json --artefact tables.md [--artefact ...] \
        --out bundle_manifest.json [--readme BUNDLE_README.md]

Records what produced the results, with SHA-256 digests:

- the build: git commit, the freeze tag pointing at it (if any), the freeze
  record's own digest and its ``frozen_paths`` digest and count, read by name;
- the deviation log head: entry count, head signature, log digest (anchor);
- the deposited OSF artefacts (``research/osf/*.json``), the analysis plan among
  them, and ``poetry.lock``;
- each campaign's inputs: ``schedule.json`` and ``campaign.json`` digests, the
  schedule digest and build-freeze digest each records, and the result stores;
- each output artefact (analysis JSON, tables, evidence) and the BCa seeds
  the analysis JSON names.

It writes digests and names only: no case ID, no label, no ground truth. It
lives outside the frozen paths and changes nothing it reads. S4.11 T-j asks
the analysis JSON to carry the input digests and plan hash; the frozen
``bin/analyse.py`` does not, so this manifest records them beside it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

__all__ = ["bca_seeds", "build_manifest", "main", "sha256_file"]

REPO_ROOT = Path(__file__).resolve().parents[1]
RECORD = Path("data/frozen/build_freeze.json")
ANCHOR = Path("deviation_log.anchor.json")
OSF_DIR = Path("research/osf")
_CHUNK = 1 << 20
_STORES = ("results.duckdb", "rerun.duckdb")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(_CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def _git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip() or None


def build_info(root: Path) -> dict[str, Any]:
    record_path = root / RECORD
    record = json.loads(record_path.read_text(encoding="utf-8"))
    frozen = record.get("frozen_paths") or {}
    commit = _git(root, "rev-parse", "HEAD")
    tags = (_git(root, "tag", "--points-at", "HEAD") or "").split()
    return {
        "commit": commit,
        "tags_at_commit": tags,
        "record_tag": record.get("tag"),
        "record_sha256": sha256_file(record_path),
        "frozen_paths_digest": frozen.get("digest"),
        "frozen_paths_count": frozen.get("count"),
        "working_tree_clean": not _git(
            root, "status", "--porcelain", "--", *_frozen_dirs(record)
        ),
    }


def _frozen_dirs(record: Mapping[str, Any]) -> list[str]:
    frozen = record.get("frozen_paths") or {}
    dirs = list(frozen.get("dirs") or [])
    files = list(frozen.get("files_outside_dirs") or [])
    return dirs + files or ["."]


def ledger_info(root: Path) -> dict[str, Any]:
    anchor = json.loads((root / ANCHOR).read_text(encoding="utf-8"))
    return {
        "entries": anchor.get("entries"),
        "head_signature": anchor.get("head_signature"),
        "log_sha256": anchor.get("log_sha256"),
        "anchor_sha256": sha256_file(root / ANCHOR),
    }


def deposit_info(root: Path) -> dict[str, str]:
    out = {
        str(p.relative_to(root)): sha256_file(p)
        for p in sorted((root / OSF_DIR).glob("*"))
        if p.is_file()
    }
    lock = root / "poetry.lock"
    if lock.exists():
        out["poetry.lock"] = sha256_file(lock)
    return out


def campaign_info(campaign: Path) -> dict[str, Any]:
    info: dict[str, Any] = {"path": str(campaign)}
    for name in ("schedule.json", "campaign.json"):
        p = campaign / name
        if p.exists():
            info[name] = sha256_file(p)
    schedule = campaign / "schedule.json"
    if schedule.exists():
        body = json.loads(schedule.read_text(encoding="utf-8"))
        info["schedule_digest"] = body.get("digest")
    camp = campaign / "campaign.json"
    if camp.exists():
        body = json.loads(camp.read_text(encoding="utf-8"))
        info["build_freeze_digest"] = body.get("build_freeze_digest")
        info["gt_corpus"] = body.get("gt_corpus")
    info["stores"] = {
        s: sha256_file(campaign / s) for s in _STORES if (campaign / s).exists()
    }
    return info


def bca_seeds(analysis: Any) -> dict[str, int]:
    """Every ``bca_seed`` in an analysis JSON, keyed by the nearest ``id``."""
    seeds: dict[str, int] = {}

    def walk(node: Any, owner: str | None) -> None:
        if isinstance(node, dict):
            here = str(node.get("id", owner)) if node.get("id") else owner
            if "bca_seed" in node and node["bca_seed"] is not None and here:
                seeds.setdefault(here, int(node["bca_seed"]))
            for v in node.values():
                walk(v, here)
        elif isinstance(node, list):
            for v in node:
                walk(v, owner)

    walk(analysis, None)
    return dict(sorted(seeds.items()))


def artefact_info(paths: Iterable[Path]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for p in paths:
        entry: dict[str, Any] = {"sha256": sha256_file(p)}
        if p.suffix == ".json":
            body = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(body, dict):
                entry["version"] = body.get("version")
                entry["label"] = body.get("label")
                seeds = bca_seeds(body)
                if seeds:
                    entry["bca_seeds"] = seeds
        out[str(p)] = entry
    return out


def build_manifest(
    root: Path, campaigns: Sequence[Path], artefacts: Sequence[Path]
) -> dict[str, Any]:
    build = build_info(root)
    camps = [campaign_info(c) for c in campaigns]
    mismatched = [
        c["path"]
        for c in camps
        if c.get("build_freeze_digest")
        and build["frozen_paths_digest"]
        and not str(build["frozen_paths_digest"]).startswith(
            str(c["build_freeze_digest"])
        )
    ]
    return {
        "version": "bundle-v1",
        "build": build,
        "deviation_log": ledger_info(root),
        "deposit": deposit_info(root),
        "campaigns": camps,
        "campaigns_from_another_build": mismatched,
        "artefacts": artefact_info(artefacts),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(terse=True),
        },
    }


def readme(manifest: Mapping[str, Any]) -> str:
    b = manifest["build"]
    lines = [
        "# Replication bundle",
        "",
        f"- Build: commit `{b['commit']}`, tags {b['tags_at_commit'] or 'none'}, "
        f"freeze record tag `{b['record_tag']}`.",
        f"- Freeze record SHA-256 `{b['record_sha256']}`; frozen-paths digest "
        f"`{b['frozen_paths_digest']}` over {b['frozen_paths_count']} files; "
        f"frozen paths clean: {b['working_tree_clean']}.",
        f"- Deviation log: {manifest['deviation_log']['entries']} entries, log "
        f"SHA-256 `{manifest['deviation_log']['log_sha256']}`.",
        "",
        "## Campaigns",
        "",
    ]
    for c in manifest["campaigns"]:
        lines.append(
            f"- `{c['path']}`: schedule `{c.get('schedule_digest')}`, build-freeze "
            f"digest `{c.get('build_freeze_digest')}`, stores "
            + ", ".join(f"{k} `{v[:12]}`" for k, v in c["stores"].items())
        )
    if manifest["campaigns_from_another_build"]:
        lines += [
            "",
            "**Warning:** these campaigns were planned under another build: "
            + ", ".join(manifest["campaigns_from_another_build"]),
        ]
    lines += ["", "## Artefacts", ""]
    for path, a in manifest["artefacts"].items():
        tail = f" ({a['label']})" if a.get("label") else ""
        lines.append(f"- `{path}`: `{a['sha256'][:12]}`{tail}")
    lines += [
        "",
        "## Reproduce",
        "",
        "1. `git checkout <commit above>`; `poetry install`; restore `.env` "
        "(ledger key) and the response cache.",
        "2. `bin/build_freeze.py --check` must report the frozen build.",
        "3. Per campaign: `bin/score_runs.py --db CAMPAIGN/results.duckdb "
        "--metrics` (and on `rerun.duckdb`), then `bin/helios_campaign.py cells`.",
        "4. `bin/analyse.py --db CAMPAIGN/results.duckdb --corpus pool --campaign "
        "CAMPAIGN --captures data/rcaeval/pool --reruns CAMPAIGN/rerun.duckdb "
        "--output analysis.json`.",
        "5. `scripts/phase_a_tables.py` and `scripts/phase_a_evidence.py` on the "
        "outputs; compare every digest above.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--campaign", type=Path, action="append", default=[])
    parser.add_argument("--artefact", type=Path, action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--readme", type=Path)
    args = parser.parse_args(argv)
    manifest = build_manifest(args.root, args.campaign, args.artefact)
    args.out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if args.readme is not None:
        args.readme.write_text(readme(manifest), encoding="utf-8")
    if manifest["campaigns_from_another_build"]:
        print(
            "[bundle] warning: campaigns planned under another build: "
            + ", ".join(manifest["campaigns_from_another_build"])
        )
    print(f"[bundle] {len(manifest['artefacts'])} artefacts → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
