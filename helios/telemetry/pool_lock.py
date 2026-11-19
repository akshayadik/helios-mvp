"""Confirmatory-pool lock (D11 §1, §3): no confirmatory window is read for a
run before the build is frozen.

The pool is converted and sealed in S1, but its telemetry must not reach any
pipeline until the build is frozen (S5.6). CaptureReader calls
``require_unlocked`` for every window whose evaluation_phase is
confirmatory. Sealing and seal verification do not read windows through the
reader, so they work while the pool is locked.

"Frozen" means more than the tag (S5.6 design F-b): git tag ``build-freeze``
exists, the working tree holds the record the tag holds, and every frozen
file matches the record (``helios.vcl.freeze``). A checkout that has moved
on, such as Stage B work on ``main``, is locked again for the pool.

There is deliberately no override: the only way to unlock is the frozen build.
"""

from __future__ import annotations

from pathlib import Path

from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance
from helios.vcl.freeze import BUILD_FREEZE_TAG, freeze_problems

__all__ = [
    "BUILD_FREEZE_TAG",
    "PoolLockedError",
    "build_frozen",
    "lock_reasons",
    "require_unlocked",
]

HELIOS_ENABLE_POOL_LOCK: bool = True

_REPO_ROOT = Path(__file__).resolve().parents[2]


class PoolLockedError(PermissionError):
    """A confirmatory window was requested before the build is frozen."""


def lock_reasons(repo_root: Path = _REPO_ROOT) -> list[str]:
    """Why the pool is locked; empty when this checkout is the frozen build."""
    return freeze_problems(repo_root)


def build_frozen(repo_root: Path = _REPO_ROOT) -> bool:
    """True when this checkout is the frozen build (tag, record, files).

    Fails closed: without git or a repository (the S4.3 container image has
    neither) the pool stays locked."""
    return not lock_reasons(repo_root)


def require_unlocked(incident_id: str, repo_root: Path = _REPO_ROOT) -> None:
    """Raise PoolLockedError unless the build is frozen."""
    reasons = lock_reasons(repo_root)
    if reasons:
        shown = "; ".join(reasons[:5]) + ("; ..." if len(reasons) > 5 else "")
        raise PoolLockedError(
            f"{incident_id} is a confirmatory-pool case; the pool stays locked "
            f"until this checkout is the frozen build of git tag "
            f"{BUILD_FREEZE_TAG!r} (D11, S5.6): {shown}"
        )
