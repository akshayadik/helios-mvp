"""Confirmatory-pool lock (D11 §1, §3): no confirmatory window is read for a
run before the build is frozen.

The pool is converted and sealed in S1, but its telemetry must not reach any
pipeline until git tag ``build-freeze`` exists (S5.6). CaptureReader calls
``require_unlocked`` for every window whose evaluation_phase is
confirmatory. Sealing and seal verification do not read windows through the
reader, so they work while the pool is locked.

There is deliberately no override: the only way to unlock is the tag.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance

__all__ = ["BUILD_FREEZE_TAG", "PoolLockedError", "build_frozen", "require_unlocked"]

HELIOS_ENABLE_POOL_LOCK: bool = True

BUILD_FREEZE_TAG = "build-freeze"
_REPO_ROOT = Path(__file__).resolve().parents[2]


class PoolLockedError(PermissionError):
    """A confirmatory window was requested before tag build-freeze exists."""


def build_frozen(repo_root: Path = _REPO_ROOT) -> bool:
    """True when the annotated or lightweight tag build-freeze exists."""
    result = subprocess.run(
        ["git", "rev-parse", "-q", "--verify", f"refs/tags/{BUILD_FREEZE_TAG}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def require_unlocked(incident_id: str, repo_root: Path = _REPO_ROOT) -> None:
    """Raise PoolLockedError unless the build is frozen."""
    if not build_frozen(repo_root):
        raise PoolLockedError(
            f"{incident_id} is a confirmatory-pool case; the pool stays locked "
            f"until git tag {BUILD_FREEZE_TAG!r} exists (D11)."
        )
