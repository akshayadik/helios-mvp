"""VCL disjointness registry — §3.9.1 Threat 2 audit.

Populated at import time via @gated_by in decorators.py.
DisjointnessRegistry() snapshots the registry and exposes audit().
"""

from __future__ import annotations

__all__ = ["DisjointnessRegistry", "register"]

_REGISTRY: dict[str, list[str]] = {}


def register(qualname: str, flag_value: str) -> None:
    """Record that *qualname* is gated by *flag_value*.

    Called by @gated_by at decoration time. Safe to call multiple times for
    the same qualname — each call appends to the list, enabling violation
    detection when a path is gated by more than one flag.
    """
    _REGISTRY.setdefault(qualname, []).append(flag_value)


class DisjointnessRegistry:
    """Snapshot of the import-time @gated_by registry for audit purposes.

    Filters to ``helios.*`` paths only so test-only decorated helpers do not
    pollute the audit.  The CI disjointness job constructs an instance and
    calls ``audit()``; violations cause the job to exit non-zero.
    """

    def __init__(self) -> None:
        self._paths: dict[str, list[str]] = {
            k: v for k, v in _REGISTRY.items() if k.startswith("helios.")
        }

    def audit(self) -> list[str]:
        """Return one violation string per code path gated by multiple flags."""
        return [
            f"{path}: gated by multiple flags {sorted(flags)!r}"
            for path, flags in self._paths.items()
            if len(flags) > 1
        ]

    def __len__(self) -> int:
        return len(self._paths)
