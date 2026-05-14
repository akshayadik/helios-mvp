"""VCL disjointness registry — §3.9.1 Threat 2 audit.

Populated at import time via @gated_by in decorators.py.
DisjointnessRegistry() snapshots the registry and exposes audit().
DisjointnessAuditor() imports pipeline modules and checks flag coverage.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field

from helios.vcl.registry import VCLFlag

__all__ = [
    "CoveredEntry",
    "DisjointnessAuditor",
    "DisjointnessRegistry",
    "DisjointnessReport",
    "DisjointnessViolation",
    "register",
]

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


_PIPELINE_MODULES = [
    "helios.pipelines.d_pipe.stub",
    "helios.pipelines.g_pipe.stub",
    "helios.pipelines.l_pipe.stub",
]


@dataclass(frozen=True)
class CoveredEntry:
    flag: VCLFlag
    function_name: str
    module: str


@dataclass(frozen=True)
class DisjointnessViolation:
    flag: VCLFlag
    functions: list[str]
    message: str


@dataclass
class DisjointnessReport:
    covered: list[CoveredEntry] = field(default_factory=list)
    uncovered: list[VCLFlag] = field(default_factory=list)
    violations: list[DisjointnessViolation] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.violations) == 0


class DisjointnessAuditor:
    """Audit pipeline modules for VCL flag disjointness."""

    def audit(self) -> DisjointnessReport:
        """Import pipeline modules; build flag→function map; check disjointness."""
        flag_to_fns: dict[VCLFlag, list[str]] = {f: [] for f in VCLFlag.bool_flags()}

        for module_path in _PIPELINE_MODULES:
            mod = importlib.import_module(module_path)
            for name in getattr(mod, "__all__", []):
                obj = getattr(mod, name, None)
                if obj is None or not callable(obj):
                    continue
                gated_by: VCLFlag | None = getattr(obj, "__gated_by__", None)
                if gated_by is not None and gated_by in flag_to_fns:
                    flag_to_fns[gated_by].append(f"{module_path}.{name}")

        report = DisjointnessReport()
        for flag, fns in flag_to_fns.items():
            if len(fns) == 0:
                report.uncovered.append(flag)
            elif len(fns) == 1:
                mod_name, fn_name = fns[0].rsplit(".", 1)
                report.covered.append(
                    CoveredEntry(flag=flag, function_name=fn_name, module=mod_name)
                )
            else:
                report.violations.append(
                    DisjointnessViolation(
                        flag=flag,
                        functions=fns,
                        message=f"Flag {flag!r} gates multiple functions: {fns}",
                    )
                )
        return report


def main() -> int:
    """CLI entry point — exits 1 if disjointness violations found."""
    import sys

    auditor = DisjointnessAuditor()
    report = auditor.audit()

    for entry in report.covered:
        print(f"  [COVERED]   {entry.flag} → {entry.module}.{entry.function_name}")
    for flag in report.uncovered:
        print(f"  [UNCOVERED] {flag} — no pipeline function gates this flag yet")
    for v in report.violations:
        print(f"  [VIOLATION] {v.message}", file=sys.stderr)

    if report.passed:
        print("Disjointness audit PASSED.")
        return 0
    print(
        f"Disjointness audit FAILED — {len(report.violations)} violation(s).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
