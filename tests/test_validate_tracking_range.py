"""Tests for validate_tracking.py --range: per-commit validation as run in CI.

Before --range, the CI job compared the checked-out tracker with HEAD, i.e. the
file with itself, so R4/R5 could never fail in CI. These tests build real git
histories and check every commit is judged against its own parent(s).
"""

from __future__ import annotations

import contextlib
import io
import subprocess
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from tests.test_validate_tracking import SCRIPT_DIR, make_row, make_tracker

sys.path.insert(0, str(SCRIPT_DIR))
import validate_tracking as vt

if TYPE_CHECKING:
    from pathlib import Path

_DONE = {
    "status": "DONE",
    "started": "2026-05-08",
    "done": "2026-05-08",
    "sha": "abc1234",
    "ev_type": "TEST",
    "ev_ref": "tests/x.py::y",
}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _commit(repo: Path, *rows: str, msg: str = "c") -> str:
    (repo / "docs/tracking/helios_mvp_tracking.md").write_text(make_tracker(*rows))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--no-verify", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


def _merge(repo: Path, branch: str, *rows: str) -> None:
    """Merge `branch` (always a real merge commit), resolving the tracker to `rows`."""
    subprocess.run(
        ["git", "merge", "-q", "--no-ff", "--no-commit", branch],
        cwd=repo,
        capture_output=True,
        check=False,  # both sides edit the table, so a conflict is expected
    )
    (repo / "docs/tracking/helios_mvp_tracking.md").write_text(make_tracker(*rows))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--no-verify", "-m", "merge")


@dataclass
class _Result:
    returncode: int
    stderr: str


def _run(repo: Path, rev_range: str) -> _Result:
    """Run main(--range) in-process so coverage measures it (CLI path: see below)."""
    err = io.StringIO()
    with (
        contextlib.chdir(repo),
        contextlib.redirect_stderr(err),
        contextlib.redirect_stdout(io.StringIO()),
    ):
        rc = vt.main(["--range", rev_range])
    return _Result(rc, err.getvalue())


def _run_cli(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the script exactly as the CI step does."""
    return subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "validate_tracking.py"), *args],
        cwd=repo,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@h.local")
    _git(tmp_path, "config", "user.name", "Tester")
    (tmp_path / "docs/tracking").mkdir(parents=True)
    (tmp_path / "README").write_text("base\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def test_two_step_transition_across_commits_passes(repo: Path) -> None:
    base = _commit(repo, make_row())
    _commit(repo, make_row(status="IN_PROGRESS", started="2026-05-08"))
    _commit(repo, make_row(**_DONE))
    result = _run(repo, f"{base}..HEAD")
    assert result.returncode == 0, result.stderr


def test_multi_commit_pr_is_not_collapsed_into_one_jump(repo: Path) -> None:
    """PLANNED -> IN_PROGRESS -> DONE in one PR is legal step by step;
    a whole-range diff would wrongly see PLANNED -> DONE."""
    base = _commit(repo, make_row())
    _commit(repo, make_row(status="IN_PROGRESS", started="2026-05-08"))
    _commit(repo, make_row(**_DONE))
    assert _run(repo, f"{base}..HEAD").returncode == 0


def test_illegal_jump_in_one_commit_is_reported_with_sha(repo: Path) -> None:
    base = _commit(repo, make_row())
    bad = _commit(repo, make_row(**_DONE))
    result = _run(repo, f"{base}..HEAD")
    assert result.returncode == 1
    assert bad[:7] in result.stderr
    assert "R4" in result.stderr


def test_immutable_change_in_committed_history_is_reported(repo: Path) -> None:
    """The CI blind spot: an R5 edit that is already committed."""
    base = _commit(repo, make_row())
    _commit(repo, make_row(description="Rewritten after the fact"))
    result = _run(repo, f"{base}..HEAD")
    assert result.returncode == 1
    assert "R5" in result.stderr


def test_violation_hidden_mid_range_is_found(repo: Path) -> None:
    base = _commit(repo, make_row())
    bad = _commit(repo, make_row(owner="Someone else"))
    _commit(repo, make_row(owner="Someone else", notes="later commit"))
    result = _run(repo, f"{base}..HEAD")
    assert result.returncode == 1
    assert bad[:7] in result.stderr


def test_merge_of_two_legal_branches_passes(repo: Path) -> None:
    row_a = make_row(task_id="S0-D1-ENG01")
    row_b = make_row(task_id="S0-D1-ENG02")
    base = _commit(repo, row_a, row_b)
    # Side branch takes ENG02 through two legal steps; seen from main's parent
    # that is PLANNED -> DONE, so judging a merge by one parent would fail.
    _git(repo, "checkout", "-q", "-b", "side")
    _commit(repo, row_a, make_row(task_id="S0-D1-ENG02", status="IN_PROGRESS"))
    _commit(repo, row_a, make_row(task_id="S0-D1-ENG02", **_DONE))
    _git(repo, "checkout", "-q", "main")
    _commit(repo, make_row(task_id="S0-D1-ENG01", status="IN_PROGRESS"), row_b)
    _merge(
        repo,
        "side",
        make_row(task_id="S0-D1-ENG01", status="IN_PROGRESS"),
        make_row(task_id="S0-D1-ENG02", **_DONE),
    )
    assert len(_git(repo, "rev-list", "--parents", "-n", "1", "HEAD").split()) == 3
    result = _run(repo, f"{base}..HEAD")
    assert result.returncode == 0, result.stderr


def test_violation_introduced_in_merge_commit_is_reported(repo: Path) -> None:
    """A merge must not be a hiding place: invalid against every parent."""
    row = make_row()
    base = _commit(repo, row)
    _git(repo, "checkout", "-q", "-b", "side")
    _commit(repo, row, make_row(task_id="S0-D1-ENG02"))
    _git(repo, "checkout", "-q", "main")
    _merge(
        repo,
        "side",
        make_row(description="Changed in merge"),
        make_row(task_id="S0-D1-ENG02"),
    )
    assert len(_git(repo, "rev-list", "--parents", "-n", "1", "HEAD").split()) == 3
    result = _run(repo, f"{base}..HEAD")
    assert result.returncode == 1
    assert "R5" in result.stderr


def test_bad_range_is_internal_error(repo: Path) -> None:
    assert _run(repo, "nope..alsonope").returncode == 2


def test_unknown_argument_is_rejected(repo: Path) -> None:
    with contextlib.chdir(repo), contextlib.redirect_stderr(io.StringIO()):
        assert vt.main(["--bogus"]) == 2


def test_cli_range_end_to_end_as_ci_runs_it(repo: Path) -> None:
    base = _commit(repo, make_row())
    bad = _commit(repo, make_row(description="Rewritten after the fact"))
    result = _run_cli(repo, "--range", f"{base}..HEAD")
    assert result.returncode == 1
    assert bad[:7] in result.stderr
    assert _run_cli(repo, "--range", f"{bad}..HEAD").returncode == 0
    assert _run_cli(repo, "--bogus").returncode == 2
