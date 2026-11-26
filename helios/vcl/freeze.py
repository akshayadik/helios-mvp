"""Build freeze: the frozen paths and the check that blocks a diverging build
(S5.6, design s5_6_build_freeze_design.md F-a, F-b).

The freeze record ``data/frozen/build_freeze.json`` holds the SHA-256 of every
tracked file under the frozen paths. A confirmatory run needs three things:
tag ``build-freeze-3`` exists, the record in the working tree is the record the
tag holds, and every frozen file matches its digest, with no file added or
left untracked. ``helios.telemetry.pool_lock`` asks this module, so every
pool gate (reader, scoring, strata, run metrics, analysis, campaign, API)
refuses a build that differs from the frozen one. Stage B keeps working on
``main``; phase E runs from a checkout of the tag.

The confirmatory pool's label files are never part of the frozen paths: only
``pool_manifest.json`` (seal digests and stream paths) is hashed.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

__all__ = [
    "BUILD_FREEZE_TAG",
    "FROZEN_DIRS",
    "FROZEN_FILES",
    "RECORD_PATH",
    "clear_cache",
    "divergence",
    "freeze_problems",
    "frozen_paths_section",
    "path_digests",
    "tree_digest",
]

# Deviation entry 106: the CR-03 narrative state reason is frozen as
# build-freeze-3; build-freeze (entry 101) and build-freeze-2 (entry 105) are
# superseded for phase E.
BUILD_FREEZE_TAG = "build-freeze-3"
RECORD_PATH = "data/frozen/build_freeze.json"

# Code, frozen parameters, the deposited artefacts and the container recipes.
FROZEN_DIRS: tuple[str, ...] = (
    "baselines",
    "bin",
    "data/frozen",
    "deploy",
    "helios",
    "research/osf",
)
# Single files outside those directories. The pool's ground truth and its
# checksum file are deliberately absent: they are never read before the tag.
FROZEN_FILES: tuple[str, ...] = (
    "data/rcaeval/pool_manifest.json",
    "docs/tracking/price_book.md",
    "poetry.lock",
    "pyproject.toml",
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, check=False
    )


def _tracked(repo_root: Path) -> list[str]:
    result = _git(repo_root, "ls-files", "-z", "--", *FROZEN_DIRS, *FROZEN_FILES)
    if result.returncode != 0:
        raise RuntimeError("git ls-files failed: " + result.stderr.decode().strip())
    names = [n for n in result.stdout.decode().split("\0") if n]
    return sorted(n for n in names if n != RECORD_PATH)


def _untracked(repo_root: Path) -> list[str]:
    result = _git(
        repo_root,
        "ls-files",
        "-z",
        "--others",
        "--exclude-standard",
        "--",
        *FROZEN_DIRS,
    )
    return sorted(
        n for n in result.stdout.decode().split("\0") if n and n != RECORD_PATH
    )


def path_digests(repo_root: Path = _REPO_ROOT) -> dict[str, str]:
    """SHA-256 of each tracked frozen file, read from the working tree."""
    out: dict[str, str] = {}
    for name in _tracked(repo_root):
        path = repo_root / name
        if path.is_file():
            out[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def tree_digest(digests: dict[str, str]) -> str:
    """One digest over the sorted ``path digest`` lines."""
    lines = "".join(f"{name} {digests[name]}\n" for name in sorted(digests))
    return hashlib.sha256(lines.encode()).hexdigest()


def frozen_paths_section(repo_root: Path = _REPO_ROOT) -> dict[str, Any]:
    """The record's ``frozen_paths`` part: what the check compares against."""
    digests = path_digests(repo_root)
    return {
        "dirs": list(FROZEN_DIRS),
        "files_outside_dirs": list(FROZEN_FILES),
        "count": len(digests),
        "digest": tree_digest(digests),
        "files": digests,
    }


def divergence(record: dict[str, Any], repo_root: Path = _REPO_ROOT) -> list[str]:
    """Every way the working tree differs from the record's frozen files."""
    frozen: dict[str, str] = record["frozen_paths"]["files"]
    current = path_digests(repo_root)
    problems = [
        f"changed: {n}"
        for n in sorted(frozen)
        if n in current and current[n] != frozen[n]
    ]
    problems += [f"missing: {n}" for n in sorted(frozen) if n not in current]
    problems += [f"added: {n}" for n in sorted(current) if n not in frozen]
    problems += [f"untracked: {n}" for n in _untracked(repo_root)]
    return problems


def _tag_exists(repo_root: Path) -> bool:
    try:
        result = _git(
            repo_root, "rev-parse", "-q", "--verify", f"refs/tags/{BUILD_FREEZE_TAG}"
        )
    except OSError:
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


@lru_cache(maxsize=4)
def _problems(repo_root: Path) -> tuple[str, ...]:
    try:
        if not _tag_exists(repo_root):
            return (f"git tag {BUILD_FREEZE_TAG!r} does not exist",)
        record_file = repo_root / RECORD_PATH
        if not record_file.is_file():
            return (f"{RECORD_PATH} is missing",)
        at_tag = _git(repo_root, "show", f"{BUILD_FREEZE_TAG}:{RECORD_PATH}")
        if at_tag.returncode != 0 or at_tag.stdout != record_file.read_bytes():
            return (
                f"{RECORD_PATH} differs from the record at tag {BUILD_FREEZE_TAG!r}",
            )
        record = json.loads(record_file.read_text())
        return tuple(divergence(record, repo_root))
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        # Fails closed: without git, a repository or a readable record the
        # build is not frozen (the S4.3 container image has no repository).
        return (f"freeze check failed: {exc}",)


def freeze_problems(repo_root: Path = _REPO_ROOT) -> list[str]:
    """Empty when the working tree is the frozen build; otherwise the reasons.

    Cached per process: a run does not change its own code."""
    return list(_problems(repo_root.resolve()))


def clear_cache() -> None:
    """Forget cached results (tests, and tools that change the tree)."""
    _problems.cache_clear()
