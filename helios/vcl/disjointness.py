"""VCL disjointness audit — §3.9.1 Threat 2 (S5.2 certification).

Design: ``docs/sprints/s5-integration-freeze/s5_2_disjointness_design.md``
(D-a to D-g, owner-approved 2026-11-15).

A flag's *gated region* is every runtime location (``helios/`` outside
``helios/vcl/``) that reads it: ``VCLFlag.X`` (``@gated_by`` included) or an
attribute read on a manifest (``manifest.x``, ``self._manifest.x``). The
certificate requires:

1. every boolean flag has a non-empty region, or is on the declared
   no-consumer list (:data:`NO_CONSUMER`), and no listed flag has a reader;
2. no ``@gated_by`` entry point carries two flags (static check, plus the
   import-time :class:`DisjointnessRegistry`);
3. every place where two flags combine is declared in :data:`INTERACTIONS`,
   and every declared row still matches the code.

Two flags *combine* when they appear in one statement or condition, when one
is read inside a block guarded by the other (an ``if`` body, an early-return
guard, or a ``@gated_by`` function body), or when a local variable assigned
from one is used with the other. Calls across functions and flags copied
into object attributes are not followed; the S5.1 system test checks the
observable output of every OFF flag per variant (D-e).

Files are parsed, never imported.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path

from helios.vcl.registry import VCLFlag

__all__ = [
    "INTERACTIONS",
    "NO_CONSUMER",
    "REPO_ROOT",
    "Combination",
    "DisjointnessAuditor",
    "DisjointnessRegistry",
    "DisjointnessReport",
    "FlagRead",
    "Interaction",
    "certify",
    "main",
    "register",
    "runtime_readers",
    "scan",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
_RUNTIME_ROOT = "helios"
_BUILD_ROOT = "bin"
_SKIP = "helios/vcl/"
_MANIFEST_NAMES = frozenset({"manifest", "_manifest"})

# ── Import-time registry (filled by @gated_by) ──────────────────────────────

_REGISTRY: dict[str, list[str]] = {}


def register(qualname: str, flag_value: str) -> None:
    """Record that *qualname* is gated by *flag_value* (called by @gated_by)."""
    _REGISTRY.setdefault(qualname, []).append(flag_value)


class DisjointnessRegistry:
    """Snapshot of the import-time @gated_by registry (``helios.*`` only)."""

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


# ── Declarations (D-c, D-d) ─────────────────────────────────────────────────


@dataclass(frozen=True)
class Interaction:
    """A declared place where flags combine: file, scope and the flag set."""

    file: str
    scope: str
    flags: frozenset[str]
    reason: str


#: Ch3 flags that gate nothing in the Stage A build (S5.2 D-d). The variants
#: that differ from HELIOS-Full only in these are refused by the schedule.
NO_CONSUMER: frozenset[VCLFlag] = frozenset(
    {VCLFlag.P4_COGNITIVE, VCLFlag.HIS_TIER, VCLFlag.SAMPLING_REGIME_TAG}
)


def _i(file: str, scope: str, flags: set[str], reason: str) -> Interaction:
    return Interaction(file, scope, frozenset(flags), reason)


_RUNNER = "helios/orchestrator/runner.py"
_RUN = "RunOrchestrator._process_incident"
_GRAPH = "the G-pipe needs a graph: with l2b_graph OFF it cannot run"
_NARR = (
    "coe_narrative decides whether a narrative is written; l2c_llm picks the "
    "LLM or the template narrator"
)
_SIGNAL = "MAHC and the router both need the signal type"
_ARMS = (
    "the router chooses only among arms that are ON (reachable arm set, S3.1 "
    "R-c): it sees whether the G-pipe can run and whether the L-pipe is on"
)
_PROP = "propagation is a stage inside the D-pipe; with dpipe OFF it cannot run"

#: Every allowed combination (S5.2 D-c). Filled from the scan of the code as
#: built; an undeclared combination or a row with no match fails the audit.
INTERACTIONS: tuple[Interaction, ...] = (
    _i(_RUNNER, _RUN, {"gpipe", "l2b_graph"}, _GRAPH),
    _i(
        "helios/pipelines/g_pipe/pipeline.py",
        "should_run_gpipe",
        {"gpipe", "l2b_graph"},
        _GRAPH,
    ),
    _i(_RUNNER, _RUN, {"coe_narrative", "l2c_llm"}, _NARR),
    _i(_RUNNER, "RunOrchestrator._trigger_for", {"coe_narrative", "l2c_llm"}, _NARR),
    _i(
        _RUNNER,
        "RunOrchestrator._parameter_hashes",
        {"coe_narrative", "l2c_llm"},
        _NARR,
    ),
    _i(_RUNNER, _RUN, {"cbr_routing", "mahc_hierarchical"}, _SIGNAL),
    _i(_RUNNER, _RUN, {"cbr_routing", "gpipe", "l2b_graph"}, _ARMS),
    _i(_RUNNER, _RUN, {"cbr_routing", "l2c_llm"}, _ARMS),
    _i(
        "helios/pipelines/d_pipe/pipeline.py",
        "run_dpipe",
        {"dpipe", "dpipe_propagation"},
        _PROP,
    ),
)


# ── Scanner ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FlagRead:
    flag: str
    file: str
    scope: str
    line: int
    kind: str  # "decorator" | "vclflag" | "manifest"


@dataclass(frozen=True)
class Combination:
    file: str
    scope: str
    flags: frozenset[str]
    line: int
    how: str  # "statement" | "nested" | "guard" | "gated_body"

    def key(self) -> tuple[str, str, frozenset[str]]:
        return (self.file, self.scope, self.flags)


_BY_NAME = {f.name: f.value for f in VCLFlag.bool_flags()}
_VALUES = frozenset(_BY_NAME.values())
_EXITS = (ast.Return, ast.Raise, ast.Continue, ast.Break)
_Scope = ast.FunctionDef | ast.AsyncFunctionDef


def _is_manifest(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return node.id in _MANIFEST_NAMES
    return isinstance(node, ast.Attribute) and node.attr in _MANIFEST_NAMES


def _flag_of(node: ast.AST) -> tuple[str, str] | None:
    """(flag, kind) when *node* is a flag read, else None."""
    if not isinstance(node, ast.Attribute):
        return None
    if isinstance(node.value, ast.Name) and node.value.id == "VCLFlag":
        flag = _BY_NAME.get(node.attr)
        return (flag, "vclflag") if flag else None
    if node.attr in _VALUES and _is_manifest(node.value):
        return (node.attr, "manifest")
    return None


_OPAQUE = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_Def = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


def _walk(node: ast.AST, defs: list[_Def] | None = None) -> list[ast.AST]:
    """Like ast.walk, but treats function and class definitions as opaque:
    their bodies (and decorators) belong to their own scope. Definitions met
    on the way are appended to *defs* when given."""
    if isinstance(node, _OPAQUE):
        if defs is not None:
            defs.append(node)
        return []
    out: list[ast.AST] = []
    stack = [node]
    while stack:
        cur = stack.pop()
        out.append(cur)
        for child in ast.iter_child_nodes(cur):
            if isinstance(child, _OPAQUE):
                if defs is not None:
                    defs.append(child)
                continue
            stack.append(child)
    return out


def _gated_flags(fn: _Scope) -> list[str]:
    flags: list[str] = []
    for dec in fn.decorator_list:
        if (
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Name)
            and dec.func.id == "gated_by"
            and dec.args
        ):
            hit = _flag_of(dec.args[0])
            if hit:
                flags.append(hit[0])
    return flags


class _ScopeScan:
    """Reads and combinations inside one function (or module top level)."""

    def __init__(self, file: str, scope: str, body: list[ast.stmt]) -> None:
        self.file = file
        self.scope = scope
        self.aliases: dict[str, frozenset[str]] = {}
        self.combos: list[Combination] = []
        # Boolean aliases only (``routed_run = manifest.cbr_routing``): a
        # value computed from a flag (a narrative, a verdict) is data flow,
        # not gating, and is left to the S5.1 output checks.
        for node in [n for s in body for n in _walk(s)]:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name):
                    got = self._pure(node.value)
                    if got:
                        self.aliases[target.id] = got

    def _pure(self, node: ast.expr) -> frozenset[str] | None:
        """Flags of a purely boolean flag expression, else None."""
        hit = _flag_of(node)
        if hit:
            return frozenset({hit[0]})
        if isinstance(node, ast.Name) and node.id in self.aliases:
            return self.aliases[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return self._pure(node.operand)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "bool"
            and len(node.args) == 1
        ):
            return self._pure(node.args[0])
        if isinstance(node, ast.BoolOp):
            parts = [self._pure(v) for v in node.values]
            if all(p is not None for p in parts):
                return frozenset().union(*(p for p in parts if p is not None))
        return None

    def _guard(self, test: ast.expr) -> frozenset[str]:
        """Flags whose state alone decides an exiting ``if``: ``F``, ``not F``,
        or either as one operand of ``or``. ``F and X`` decides nothing."""
        operands = test.values if isinstance(test, ast.BoolOp) else [test]
        if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And):
            operands = [] if len(test.values) > 1 else operands
        out: set[str] = set()
        for op in operands:
            got = self._pure(op)
            if got and len(got) == 1:
                out |= got
        return frozenset(out)

    def flags(self, node: ast.AST) -> frozenset[str]:
        found: set[str] = set()
        for n in _walk(node):
            hit = _flag_of(n)
            if hit:
                found.add(hit[0])
            elif isinstance(n, ast.Name) and n.id in self.aliases:
                found |= self.aliases[n.id]
        return frozenset(found)

    def _add(self, got: frozenset[str], outer: frozenset[str], line: int) -> None:
        flags = got | outer
        if len(flags) > 1:
            how = "nested" if outer and got - outer else "statement"
            self.combos.append(Combination(self.file, self.scope, flags, line, how))

    def block(self, stmts: list[ast.stmt], outer: frozenset[str]) -> None:
        for i, stmt in enumerate(stmts):
            if isinstance(stmt, ast.If | ast.While):
                test = self.flags(stmt.test)
                if test:
                    self._add(test, outer, stmt.lineno)
                self.block(stmt.body, outer | test)
                self.block(stmt.orelse, outer | test)
                guard = self._guard(stmt.test)
                if guard and stmt.body and isinstance(stmt.body[-1], _EXITS):
                    # Everything after an exiting guard runs only in one
                    # state of the guarding flag.
                    self.block(stmts[i + 1 :], outer | guard)
                    return
            elif isinstance(
                stmt, ast.For | ast.AsyncFor | ast.With | ast.AsyncWith | ast.Try
            ):
                head = frozenset[str]()
                if isinstance(stmt, ast.For | ast.AsyncFor):
                    head = self.flags(stmt.iter)
                for sub in ("body", "orelse", "finalbody"):
                    self.block(getattr(stmt, sub, []), outer | head)
                for handler in getattr(stmt, "handlers", []):
                    self.block(handler.body, outer | head)
            elif not isinstance(stmt, _OPAQUE):
                got = self.flags(stmt)
                if got:
                    self._add(got, outer, stmt.lineno)


@dataclass
class DisjointnessReport:
    runtime: dict[str, list[FlagRead]] = field(default_factory=dict)
    build: dict[str, list[FlagRead]] = field(default_factory=dict)
    combinations: list[Combination] = field(default_factory=list)
    double_gated: list[str] = field(default_factory=list)
    undeclared: list[Combination] = field(default_factory=list)
    stale: list[Interaction] = field(default_factory=list)
    uncovered: list[str] = field(default_factory=list)
    no_consumer_read: list[str] = field(default_factory=list)

    @property
    def covered(self) -> list[str]:
        return sorted(f for f, reads in self.runtime.items() if reads)

    @property
    def violations(self) -> list[str]:
        return [
            *self.double_gated,
            *(
                f"undeclared combination {sorted(c.flags)} at {c.file}:{c.line} ({c.scope}, {c.how})"
                for c in self.undeclared
            ),
            *(
                f"stale interaction row {sorted(r.flags)} at {r.file} ({r.scope})"
                for r in self.stale
            ),
            *(
                f"no runtime reader and not declared no-consumer: {f}"
                for f in self.uncovered
            ),
            *(f"declared no-consumer but read: {f}" for f in self.no_consumer_read),
        ]

    @property
    def passed(self) -> bool:
        return not self.violations


def _scan_file(
    path: Path, rel: str
) -> tuple[list[FlagRead], list[Combination], list[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
    reads: list[FlagRead] = []
    combos: list[Combination] = []
    doubles: list[str] = []

    def visit(body: list[ast.stmt], scope: str, outer: frozenset[str]) -> None:
        scan = _ScopeScan(rel, scope, body)
        scan.block(body, outer)
        combos.extend(scan.combos)
        defs: list[_Def] = []
        for stmt in body:
            for node in _walk(stmt, defs):
                hit = _flag_of(node)
                if hit:
                    reads.append(
                        FlagRead(hit[0], rel, scope, getattr(node, "lineno", 0), hit[1])
                    )
        for node in defs:
            name = f"{scope}.{node.name}".lstrip(".")
            if isinstance(node, ast.ClassDef):
                visit(node.body, name, frozenset())
                continue
            gated = _gated_flags(node)
            if len(set(gated)) > 1:
                doubles.append(
                    f"{rel}:{name}: gated by multiple flags {sorted(set(gated))}"
                )
            for flag in gated:
                reads.append(FlagRead(flag, rel, name, node.lineno, "decorator"))
            # A @gated_by body runs only with its flag ON: reads inside it
            # combine with that flag (S5.2 D-c).
            visit(node.body, name, frozenset(gated))

    visit(tree.body, "", frozenset())
    return reads, combos, doubles


def scan(repo_root: Path = REPO_ROOT) -> DisjointnessReport:
    """Scan ``helios/`` (runtime) and ``bin/`` (build tools) for flag reads."""
    report = DisjointnessReport(
        runtime={f: [] for f in sorted(_VALUES)},
        build={f: [] for f in sorted(_VALUES)},
    )
    for root, sink in ((_RUNTIME_ROOT, report.runtime), (_BUILD_ROOT, report.build)):
        base = repo_root / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            rel = path.relative_to(repo_root).as_posix()
            if rel.startswith(_SKIP):
                continue
            reads, combos, doubles = _scan_file(path, rel)
            for r in reads:
                sink[r.flag].append(r)
            if root == _RUNTIME_ROOT:
                report.combinations.extend(combos)
                report.double_gated.extend(doubles)
    return report


def certify(
    report: DisjointnessReport,
    interactions: tuple[Interaction, ...] = INTERACTIONS,
    no_consumer: frozenset[VCLFlag] = NO_CONSUMER,
) -> DisjointnessReport:
    """Apply the declarations (D-c, D-d) to a scan; returns the same report."""
    declared = {(r.file, r.scope, r.flags) for r in interactions}
    seen = {c.key() for c in report.combinations}
    report.undeclared = sorted(
        {c.key(): c for c in report.combinations if c.key() not in declared}.values(),
        key=lambda c: (c.file, c.line),
    )
    report.stale = [r for r in interactions if (r.file, r.scope, r.flags) not in seen]
    listed = {f.value for f in no_consumer}
    report.uncovered = [
        f for f, reads in report.runtime.items() if not reads and f not in listed
    ]
    report.no_consumer_read = sorted(f for f in listed if report.runtime.get(f))
    return report


class DisjointnessAuditor:
    """Static audit of the code under *repo_root* against the declarations."""

    def __init__(self, repo_root: Path = REPO_ROOT) -> None:
        self.repo_root = repo_root

    def audit(self) -> DisjointnessReport:
        report = certify(scan(self.repo_root))
        report.double_gated.extend(DisjointnessRegistry().audit())
        return report


def runtime_readers(repo_root: Path = REPO_ROOT) -> dict[str, list[str]]:
    """Each boolean flag mapped to the runtime files that read it."""
    report = scan(repo_root)
    return {f: sorted({r.file for r in reads}) for f, reads in report.runtime.items()}


def main() -> int:
    """CLI: print readers per flag, declarations and violations; 1 on failure."""
    report = DisjointnessAuditor().audit()
    for flag, reads in report.runtime.items():
        files = sorted({r.file for r in reads})
        build = sorted({r.file for r in report.build[flag]})
        if files:
            print(f"  [COVERED]     {flag} → {', '.join(files)}")
        elif flag in {f.value for f in NO_CONSUMER}:
            print(f"  [NO-CONSUMER] {flag} (declared)")
        else:
            print(f"  [UNCOVERED]   {flag}")
        if build:
            print(f"                build tools: {', '.join(build)}")
    for row in INTERACTIONS:
        print(
            f"  [DECLARED]    {' + '.join(sorted(row.flags))} @ {row.file}:{row.scope}"
        )
    for v in report.violations:
        print(f"  [VIOLATION]   {v}", file=sys.stderr)
    covered = len(report.covered)
    summary = (
        f"{covered} covered, {len(NO_CONSUMER)} declared no-consumer, "
        f"{len(INTERACTIONS)} declared interactions, {len(report.violations)} violations"
    )
    if report.passed:
        print(f"Disjointness audit PASSED: {summary}.")
        return 0
    print(f"Disjointness audit FAILED: {summary}.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
