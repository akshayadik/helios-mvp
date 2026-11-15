"""Tests for helios.vcl.disjointness — VCLFlag-compliant."""

from __future__ import annotations

import importlib
import textwrap
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

import pytest

from helios.vcl.catalog import flag_readers, flags_off_versus_full, unconsumed_variants
from helios.vcl.disjointness import (
    _REGISTRY,
    INTERACTIONS,
    NO_CONSUMER,
    REPO_ROOT,
    DisjointnessAuditor,
    DisjointnessRegistry,
    DisjointnessReport,
    Interaction,
    certify,
    main,
    register,
    scan,
)
from helios.vcl.registry import VCLFlag
from helios.vcl.variants import CONFIRMATORY_VARIANTS, EXPLORATORY_VARIANTS


def _unique_helios_path() -> str:
    """Return a unique helios.* qualname safe to use in _REGISTRY without pollution."""
    return f"helios.fake.fn_{uuid.uuid4().hex}"


def _unique_tests_path() -> str:
    return f"tests.fake.fn_{uuid.uuid4().hex}"


@pytest.fixture(autouse=True)
def _clean_registry() -> Generator[None, Any, None]:
    """Isolate each test: snapshot the full registry and restore it after."""
    snapshot = dict(_REGISTRY)
    yield
    _REGISTRY.clear()
    _REGISTRY.update(snapshot)


# ---------------------------------------------------------------------------
# Registry population
# ---------------------------------------------------------------------------


def test_no_helios_paths_registered_at_stage0() -> None:
    # The audit no longer imports modules (S5.2 scans source), so import them.
    importlib.import_module("helios.pipelines.g_pipe.pipeline")
    importlib.import_module("helios.pipelines.l_pipe.pipeline")
    registry = DisjointnessRegistry()
    # G-pipe and L-pipe are now real pipelines (stubs deleted at M3).
    assert "helios.pipelines.g_pipe.pipeline.run_gpipe" in registry._paths
    assert "helios.pipelines.l_pipe.pipeline.run_lpipe" in registry._paths


def test_register_increments_len() -> None:
    path = _unique_helios_path()
    before = len(DisjointnessRegistry())
    register(path, "dpipe")
    registry = DisjointnessRegistry()
    assert len(registry) == before + 1


def test_test_module_functions_filtered_out() -> None:
    tests_path = _unique_tests_path()
    before = len(DisjointnessRegistry())
    register(tests_path, "gpipe")
    registry = DisjointnessRegistry()
    assert len(registry) == before


def test_decorator_registers_helios_module_function() -> None:
    path = f"helios.pipelines.fake_{uuid.uuid4().hex}.run_gpipe"
    register(path, "gpipe")
    registry = DisjointnessRegistry()
    assert path in registry._paths


# ---------------------------------------------------------------------------
# Audit: no violations
# ---------------------------------------------------------------------------


def test_audit_returns_empty_when_all_paths_have_single_flag() -> None:
    paths = [_unique_helios_path() for _ in range(3)]
    flags = ["dpipe", "gpipe", "lpipe"]
    for p, f in zip(paths, flags, strict=False):
        register(p, f)
    assert DisjointnessRegistry().audit() == []


def test_single_flag_per_path_has_no_violations() -> None:
    path = _unique_helios_path()
    register(path, "mahc")
    assert DisjointnessRegistry().audit() == []


def test_audit_returns_empty_list_type() -> None:
    result = DisjointnessRegistry().audit()
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Audit: violations
# ---------------------------------------------------------------------------


def test_double_gating_produces_violation() -> None:
    path = _unique_helios_path()
    register(path, "dpipe")
    register(path, "gpipe")
    violations = DisjointnessRegistry().audit()
    assert len(violations) == 1


def test_violation_string_contains_path_and_flags() -> None:
    path = _unique_helios_path()
    register(path, "dpipe")
    register(path, "lpipe")
    violations = DisjointnessRegistry().audit()
    assert len(violations) == 1
    msg = violations[0]
    assert path in msg
    assert "dpipe" in msg
    assert "lpipe" in msg


# ---------------------------------------------------------------------------
# S5.2 certification (design s5_2_disjointness_design.md D-a to D-d)
# ---------------------------------------------------------------------------


_FORMS = """
                def statement():
                    if manifest.gpipe and manifest.l2b_graph:
                        pass
                def nested():
                    if manifest.coe_narrative:
                        run(llm=manifest.l2c_llm)
                def guard():
                    if not manifest.gpipe or ready is None:
                        return None
                    return manifest.ueg_structural
                def alias():
                    routed = manifest.cbr_routing
                    if manifest.mahc_hierarchical or routed:
                        pass
                @gated_by(VCLFlag.DPIPE)
                def gated_body():
                    if manifest.dpipe_propagation:
                        pass
            """

_NOT_FORMS = """
                def refusal():
                    # Exits only when the flag is ON *and* something else
                    # holds: the rest runs with the flag in either state.
                    if manifest.mahc_hierarchical and provisional:
                        raise ValueError
                    return manifest.cbr_routing
                def data_flow():
                    narrative = narrate(llm=manifest.l2c_llm)
                    if manifest.iol_self_telemetry:
                        record(narrative)
                def separate():
                    if manifest.gpipe:
                        pass
                    if manifest.acp_stateful:
                        pass
                def outer():
                    if manifest.gpipe:
                        def inner():
                            return manifest.l2c_llm
                        return inner
            """

_DOUBLE = """
                @gated_by(VCLFlag.DPIPE)
                @gated_by(VCLFlag.GPIPE)
                def both(): ...
            """


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text))
    return tmp_path


def _bare(tmp_path: Path, files: dict[str, str]) -> DisjointnessReport:
    """Scan a synthetic tree with no declarations."""
    return certify(
        scan(_tree(tmp_path, files)), interactions=(), no_consumer=frozenset()
    )


def _combos(report: DisjointnessReport) -> set[tuple[str, frozenset[str]]]:
    return {(c.scope, c.flags) for c in report.combinations}


def test_the_code_as_built_is_certified() -> None:
    report = DisjointnessAuditor().audit()
    assert report.violations == []
    assert report.passed
    no_consumer = {f.value for f in NO_CONSUMER}
    assert no_consumer == {"p4_cognitive", "his_tier", "sampling_regime_tag"}
    assert set(report.covered) == {f.value for f in VCLFlag.bool_flags()} - no_consumer
    assert len(INTERACTIONS) == len({(r.file, r.scope, r.flags) for r in INTERACTIONS})
    assert all(r.reason for r in INTERACTIONS)


def test_the_cli_prints_the_certificate(capsys: pytest.CaptureFixture[str]) -> None:
    assert main() == 0
    out = capsys.readouterr().out
    assert "[NO-CONSUMER] p4_cognitive (declared)" in out
    assert "[DECLARED]    gpipe + l2b_graph" in out
    assert "13 covered, 3 declared no-consumer" in out


def test_reads_of_each_kind_and_what_is_not_a_read(tmp_path: Path) -> None:
    report = _bare(
        tmp_path,
        {
            "helios/a.py": """
                @gated_by(VCLFlag.DPIPE)
                def run(): ...
                x = manifest.gpipe
                y = VCLFlag.L2C_LLM
                z = chain.dpipe  # a parameter set, not the flag
                class Runner:
                    def go(self):
                        return self._manifest.acp_stateful
            """,
            "helios/vcl/b.py": "w = manifest.fgsv_ks_gate\n",  # the flag system
            "bin/tool.py": "v = manifest.reconcile_terminal\n",
        },
    )
    kinds = {f: sorted(r.kind for r in rs) for f, rs in report.runtime.items() if rs}
    assert kinds == {
        "dpipe": ["decorator"],
        "gpipe": ["manifest"],
        "l2c_llm": ["vclflag"],
        "acp_stateful": ["manifest"],
    }
    assert report.runtime["acp_stateful"][0].scope == "Runner.go"
    assert report.runtime["fgsv_ks_gate"] == []
    assert report.runtime["reconcile_terminal"] == []  # build tools do not count
    assert [r.file for r in report.build["reconcile_terminal"]] == ["bin/tool.py"]
    assert "fgsv_ks_gate" in report.uncovered


def test_each_form_of_combination_is_found(tmp_path: Path) -> None:
    report = _bare(
        tmp_path,
        {"helios/c.py": _FORMS},
    )
    assert _combos(report) == {
        ("statement", frozenset({"gpipe", "l2b_graph"})),
        ("nested", frozenset({"coe_narrative", "l2c_llm"})),
        ("guard", frozenset({"gpipe", "ueg_structural"})),
        ("alias", frozenset({"cbr_routing", "mahc_hierarchical"})),
        ("gated_body", frozenset({"dpipe", "dpipe_propagation"})),
    }
    assert len(report.undeclared) == 5
    assert not report.passed


def test_what_is_not_a_combination(tmp_path: Path) -> None:
    report = _bare(
        tmp_path,
        {"helios/d.py": _NOT_FORMS},
    )
    assert report.combinations == []


def test_double_gating_is_a_violation(tmp_path: Path) -> None:
    report = _bare(
        tmp_path,
        {"helios/e.py": _DOUBLE},
    )
    assert report.double_gated == [
        "helios/e.py:both: gated by multiple flags ['dpipe', 'gpipe']"
    ]
    assert not report.passed


def test_declared_rows_must_match_and_stale_rows_fail(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {"helios/f.py": "def g():\n    return manifest.gpipe and manifest.l2b_graph\n"},
    )
    row = Interaction("helios/f.py", "g", frozenset({"gpipe", "l2b_graph"}), "graph")
    stale = Interaction("helios/f.py", "h", frozenset({"gpipe", "dpipe"}), "gone")
    ok = certify(scan(root), interactions=(row,), no_consumer=frozenset())
    assert ok.undeclared == []
    assert ok.stale == []
    bad = certify(scan(root), interactions=(row, stale), no_consumer=frozenset())
    assert bad.stale == [stale]
    assert any("stale interaction row" in v for v in bad.violations)


def test_the_no_consumer_list_fails_in_both_directions(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"helios/g.py": "x = manifest.p4_cognitive\n"})
    read = certify(
        scan(root), interactions=(), no_consumer=frozenset({VCLFlag.P4_COGNITIVE})
    )
    assert read.no_consumer_read == ["p4_cognitive"]
    assert "declared no-consumer but read: p4_cognitive" in read.violations
    unlisted = certify(scan(root), interactions=(), no_consumer=frozenset())
    assert "his_tier" in unlisted.uncovered
    assert "p4_cognitive" not in unlisted.uncovered


def test_schedule_refuses_exactly_the_no_consumer_variants() -> None:
    """D-d: the refused variants are those that differ from HELIOS-Full only in
    no-consumer flags (noCogni and HIS3); sampling_regime_tag is in no variant."""
    no_consumer = {f.value for f in NO_CONSUMER}
    expected = {
        name
        for name in EXPLORATORY_VARIANTS
        if set(flags_off_versus_full(name)) <= no_consumer
    }
    refused = unconsumed_variants(list(EXPLORATORY_VARIANTS), flag_readers(REPO_ROOT))
    assert set(refused) == expected == {"HELIOS-noCogni", "HELIOS-HIS3"}
    assert (
        unconsumed_variants(list(CONFIRMATORY_VARIANTS), flag_readers(REPO_ROOT)) == {}
    )
    in_any = {f for name in EXPLORATORY_VARIANTS for f in flags_off_versus_full(name)}
    assert "sampling_regime_tag" not in in_any


def test_the_ci_job_no_longer_runs_the_label_only_step() -> None:
    workflow = (REPO_ROOT / ".github/workflows/disjointness_audit.yml").read_text()
    assert "HELIOS-noGraph" not in workflow
    assert "python -m helios.vcl.disjointness" in workflow
