"""Ground truth never reaches a pipeline (S1.9; metric contract §1, D11 §3).

Three independent checks:

1. no entry point of the run path accepts a ground-truth-like parameter;
2. no module of the run path mentions ground truth or imports the scoring
   path (static scan of the source);
3. an orchestrator run never opens a ground-truth file (runtime trap).
"""

from __future__ import annotations

import ast
import builtins
import datetime as dt
import inspect
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from helios.graph.khop_pruner import khop_prune
from helios.graph.structural_bundle import apply_structural_bundle
from helios.graph.ueg_c_builder import build_ueg_c
from helios.integrity_gate import AppendOnlyLedger
from helios.orchestrator.runner import RunOrchestrator
from helios.pipelines.d_pipe.pipeline import run_dpipe
from helios.pipelines.d_pipe.stages.d_verdict import DVerdict
from helios.pipelines.g_pipe.pipeline import run_gpipe, should_run_gpipe
from helios.pipelines.l_pipe.pipeline import run_lpipe
from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.telemetry.seal import write_seal
from helios.telemetry.trigger import detect
from helios.vcl import VCLFlag, get_variant, set_current_manifest  # noqa: F401

if TYPE_CHECKING:
    from collections.abc import Callable

REPO = Path(__file__).resolve().parents[2]
RUN_PATH = ("pipelines", "graph", "orchestrator", "consensus", "telemetry", "schemas")
LEAK_WORDS = ("ground", "truth", "label", "root_cause", "inject")
LEAK_TOKENS = (
    "ground_truth",
    "root_cause_service",
    "inject_time",
    "helios.evaluation",
)
_KEY = b"test-secret-at-least-32-chars-long!!"

ENTRY_POINTS: tuple[Callable[..., Any], ...] = (
    run_dpipe,
    run_gpipe,
    run_lpipe,
    should_run_gpipe,
    DVerdict.compute,
    build_ueg_c,
    apply_structural_bundle,
    khop_prune,
    detect,
    RunOrchestrator.__init__,
    RunOrchestrator.run,
)


@pytest.mark.parametrize("fn", ENTRY_POINTS, ids=lambda f: f.__qualname__)
def test_no_entry_point_accepts_ground_truth(fn: Callable[..., Any]) -> None:
    params = inspect.signature(fn).parameters
    leaks = [p for p in params if any(w in p.lower() for w in LEAK_WORDS)]
    assert leaks == []


def _run_path_modules() -> list[Path]:
    return sorted(
        p
        for part in RUN_PATH
        for p in (REPO / "helios" / part).rglob("*.py")
        if "__pycache__" not in p.parts
    )


def _docstrings(tree: ast.AST) -> set[int]:
    """ids of the docstring nodes (prose may say "ground truth"; code may not)."""
    found = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (
            isinstance(body, list)
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            found.add(id(body[0].value))
    return found


def _code_tokens(tree: ast.AST) -> set[str]:
    """Identifiers, parameter names, keyword names, imported modules and
    non-docstring string literals of one module."""
    docs = _docstrings(tree)
    tokens: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            tokens.add(n.id)
        elif isinstance(n, ast.Attribute):
            tokens.add(n.attr)
        elif isinstance(n, ast.arg | ast.keyword) and n.arg:
            tokens.add(n.arg)
        elif isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            tokens.add(n.name)
        elif isinstance(n, ast.ImportFrom):
            tokens.add(n.module or "")
            tokens.update(a.name for a in n.names)
        elif isinstance(n, ast.Import):
            tokens.update(a.name for a in n.names)
        elif (
            isinstance(n, ast.Constant)
            and isinstance(n.value, str)
            and id(n) not in docs
        ):
            tokens.add(n.value)
    return tokens


def test_run_path_never_mentions_ground_truth() -> None:
    modules = _run_path_modules()
    offenders = [
        f"{path.relative_to(REPO)}: {token}"
        for path in modules
        for token in LEAK_TOKENS
        if any(
            token in s
            for s in _code_tokens(ast.parse(path.read_text(encoding="utf-8")))
        )
    ]
    assert offenders == []
    assert len(modules) > 20  # the scan really covers the run path


def test_the_scan_would_catch_a_leak() -> None:
    leaky = ast.parse(
        "def run(x, ground_truth_service=None):\n"
        '    """Docstrings may say ground_truth."""\n'
        "    return x\n"
    )
    assert any("ground_truth" in s for s in _code_tokens(leaky))
    clean = ast.parse('def run(x):\n    """Never sees ground_truth."""\n    return x\n')
    assert not any("ground_truth" in s for s in _code_tokens(clean))


def test_orchestrator_run_never_opens_ground_truth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captures = tmp_path / "captures"
    inc_dir = captures / "inc-001"
    inc_dir.mkdir(parents=True)
    window = TelemetryWindow(
        incident_id="inc-001",
        variant_config_hash="a" * 64,
        window_start_iso=dt.datetime(2026, 1, 1, tzinfo=dt.UTC).isoformat(),
        window_end_iso=dt.datetime(2026, 1, 1, 0, 5, tzinfo=dt.UTC).isoformat(),
        evaluation_phase=EvaluationPhase.EXPLORATORY,
    )
    manifest = window.model_dump()
    manifest["window_hash"] = window.compute_window_hash()
    (inc_dir / "manifest.json").write_text(json.dumps(manifest, default=str))
    write_seal(inc_dir, window, _KEY)
    # A ground-truth file sits right next to the captures.
    (tmp_path / "ground_truth.json").write_text("{}")

    opened: list[str] = []
    real_open = builtins.open
    real_read_text = Path.read_text
    real_read_bytes = Path.read_bytes

    def _trap(path: object) -> None:
        if "ground_truth" in str(path):
            opened.append(str(path))

    def _open(file: Any, *args: Any, **kwargs: Any) -> Any:
        _trap(file)
        return real_open(file, *args, **kwargs)

    def _read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        _trap(self)
        return real_read_text(self, *args, **kwargs)

    def _read_bytes(self: Path) -> bytes:
        _trap(self)
        return real_read_bytes(self)

    variant = get_variant("HELIOS-Full")
    manifest_hash = variant.compute_variant_config_hash()
    monkeypatch.setattr(builtins, "open", _open)
    monkeypatch.setattr(Path, "read_text", _read_text)
    monkeypatch.setattr(Path, "read_bytes", _read_bytes)
    monkeypatch.setattr(
        "helios.orchestrator.runner.run_lpipe",
        lambda **kw: {
            **kw,
            "pipeline": "lpipe",
            "variant_config_hash": manifest_hash,
            "status": "abstained",
            "snapshot": None,
        },
    )
    set_current_manifest(variant)
    RunOrchestrator(
        manifest=variant,
        captures_dir=captures,
        db_path=tmp_path / "results.duckdb",
        registry_path=tmp_path / "registry.jsonl",
        reconciliation_path=tmp_path / "reconciliation.jsonl",
        exclusion_ledger=MagicMock(spec=AppendOnlyLedger),
        hmac_key=_KEY,
    ).run(captures)

    assert opened == []
    rows = (tmp_path / "reconciliation.jsonl").read_text().splitlines()
    assert json.loads(rows[0])["outcome"] == "passed"
