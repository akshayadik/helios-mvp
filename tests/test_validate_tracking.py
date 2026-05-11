"""
Tests for scripts/validate_tracking.py

One test per rule, plus integration tests that exercise the full pipeline
(parse → validate → exit code) end-to-end via subprocess against a real
temporary git repository.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# Make the script importable as a module.
SCRIPT_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import validate_tracking as vt  # noqa: E402,I001


# --------------------------------------------------------------------------- #
# Test fixtures
# --------------------------------------------------------------------------- #

_TABLE_COLS = "| Task_ID | Day | Type | Description | Prop_§ | DSR | Contrib | Own | Deps | Status | Started | Done | SHA | Ev_Type | Ev_Ref | Gate | Dev_Ref | Notes |"
HEADER = textwrap.dedent(f"""
    # HELIOS MVP — Stage 0 Week 1 Tracking

    Some prose here. The validator should ignore it.

    {_TABLE_COLS}
    |---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
""").strip()


def make_row(
    task_id: str = "S0-D1-ENG01",
    day: str = "1",
    typ: str = "ENG",
    description: str = "Init project",
    prop: str = "§3.6.2",
    dsr: str = "Design",
    contrib: str = "infra",
    owner: str = "AA",
    deps: str = "-",
    status: str = "PLANNED",
    started: str = "-",
    done: str = "-",
    sha: str = "-",
    ev_type: str = "-",
    ev_ref: str = "-",
    gate: str = "-",
    dev_ref: str = "-",
    notes: str = "-",
) -> str:
    """Build one row of the markdown table with keyword overrides."""
    cells = [
        task_id,
        day,
        typ,
        description,
        prop,
        dsr,
        contrib,
        owner,
        deps,
        status,
        started,
        done,
        sha,
        ev_type,
        ev_ref,
        gate,
        dev_ref,
        notes,
    ]
    return "| " + " | ".join(cells) + " |"


def make_tracker(*rows: str) -> str:
    """Concatenate header and rows into a full tracker file body."""
    return HEADER + "\n" + "\n".join(rows) + "\n"


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


class TestParsing:
    def test_skips_header_and_separator(self):
        text = make_tracker(make_row())
        rows = vt.parse_rows(text)
        assert len(rows) == 1
        assert rows[0][vt.COL_TASK_ID] == "S0-D1-ENG01"

    def test_extracts_all_18_cells(self):
        text = make_tracker(make_row(notes="hello"))
        rows = vt.parse_rows(text)
        assert len(rows[0]) == 18
        assert rows[0][vt.COL_NOTES] == "hello"

    def test_strips_whitespace(self):
        text = make_tracker(make_row(description="   spaced   "))
        rows = vt.parse_rows(text)
        assert rows[0][vt.COL_DESCRIPTION] == "spaced"

    def test_empty_tracker_returns_no_rows(self):
        rows = vt.parse_rows("# Empty file\n\nNo rows here.\n")
        assert rows == []

    def test_summary_table_not_picked_up(self):
        # Summary rows start with "| 1" or "| Total", not "| S0-".
        text = make_tracker(make_row()) + "\n| 1 | 9 | 0 | 0 | 0 | 0 | 0 | 0 |\n"
        rows = vt.parse_rows(text)
        assert len(rows) == 1


# --------------------------------------------------------------------------- #
# Rule R1 — DONE row completeness
# --------------------------------------------------------------------------- #


class TestRuleR1:
    def test_done_with_all_required_fields_passes(self):
        row = make_row(
            status="DONE",
            started="2026-05-08",
            done="2026-05-08",
            sha="a3f4e21",
            ev_type="TEST",
            ev_ref="tests/test_x.py::test_y",
        )
        assert vt.validate_done_row(vt.parse_rows(make_tracker(row))[0]) == []

    def test_done_missing_sha_fails(self):
        row = make_row(
            status="DONE",
            started="2026-05-08",
            done="2026-05-08",
            sha="-",
            ev_type="TEST",
            ev_ref="tests/test_x.py",
        )
        viols = vt.validate_done_row(vt.parse_rows(make_tracker(row))[0])
        assert len(viols) == 1
        assert "SHA" in viols[0].detail

    def test_done_missing_multiple_fields_yields_multiple_violations(self):
        row = make_row(status="DONE")  # everything still "-"
        viols = vt.validate_done_row(vt.parse_rows(make_tracker(row))[0])
        # 5 required fields missing
        assert len(viols) == 5

    def test_planned_row_skipped(self):
        row = make_row(status="PLANNED")
        assert vt.validate_done_row(vt.parse_rows(make_tracker(row))[0]) == []

    def test_empty_string_treated_as_empty(self):
        row = make_row(
            status="DONE",
            started="2026-05-08",
            done="2026-05-08",
            sha="",
            ev_type="TEST",
            ev_ref="x",
        )
        viols = vt.validate_done_row(vt.parse_rows(make_tracker(row))[0])
        assert any("SHA" in v.detail for v in viols)


# --------------------------------------------------------------------------- #
# Rule R2 — DEFERRED / CARRIED_OVER need Deviation_Ref
# --------------------------------------------------------------------------- #


class TestRuleR2:
    def test_deferred_with_deviation_ref_passes(self):
        row = make_row(status="DEFERRED", dev_ref="dev-007")
        assert vt.validate_deferred_row(vt.parse_rows(make_tracker(row))[0]) is None

    def test_deferred_without_deviation_ref_fails(self):
        row = make_row(status="DEFERRED", dev_ref="-")
        v = vt.validate_deferred_row(vt.parse_rows(make_tracker(row))[0])
        assert v is not None
        assert v.rule == "R2"

    def test_carried_over_without_deviation_ref_fails(self):
        row = make_row(status="CARRIED_OVER", dev_ref="-")
        v = vt.validate_deferred_row(vt.parse_rows(make_tracker(row))[0])
        assert v is not None and v.rule == "R2"

    def test_done_row_skipped(self):
        row = make_row(status="DONE")
        assert vt.validate_deferred_row(vt.parse_rows(make_tracker(row))[0]) is None


# --------------------------------------------------------------------------- #
# Rule R3 — Status enum
# --------------------------------------------------------------------------- #


class TestRuleR3:
    @pytest.mark.parametrize("status", sorted(vt.LEGAL_STATUSES))
    def test_each_legal_status_passes(self, status):
        row = make_row(status=status)
        assert vt.validate_status_value(vt.parse_rows(make_tracker(row))[0]) is None

    def test_lowercase_status_rejected(self):
        row = make_row(status="done")
        v = vt.validate_status_value(vt.parse_rows(make_tracker(row))[0])
        assert v is not None and v.rule == "R3"

    def test_unknown_status_rejected(self):
        row = make_row(status="WIP")
        v = vt.validate_status_value(vt.parse_rows(make_tracker(row))[0])
        assert v is not None


# --------------------------------------------------------------------------- #
# Rule R4 — State transitions
# --------------------------------------------------------------------------- #


class TestRuleR4:
    def test_planned_to_in_progress_legal(self):
        prev = vt.parse_rows(make_tracker(make_row(status="PLANNED")))[0]
        curr = vt.parse_rows(make_tracker(make_row(status="IN_PROGRESS")))[0]
        assert vt.validate_transition(prev, curr) is None

    def test_planned_to_done_illegal(self):
        prev = vt.parse_rows(make_tracker(make_row(status="PLANNED")))[0]
        curr = vt.parse_rows(make_tracker(make_row(status="DONE")))[0]
        v = vt.validate_transition(prev, curr)
        assert v is not None and v.rule == "R4"

    def test_done_to_anything_illegal(self):
        prev = vt.parse_rows(make_tracker(make_row(status="DONE")))[0]
        curr = vt.parse_rows(make_tracker(make_row(status="IN_PROGRESS")))[0]
        v = vt.validate_transition(prev, curr)
        assert v is not None and v.rule == "R4"

    def test_blocked_to_done_illegal(self):
        prev = vt.parse_rows(make_tracker(make_row(status="BLOCKED")))[0]
        curr = vt.parse_rows(make_tracker(make_row(status="DONE")))[0]
        v = vt.validate_transition(prev, curr)
        assert v is not None

    def test_in_progress_to_done_legal(self):
        prev = vt.parse_rows(make_tracker(make_row(status="IN_PROGRESS")))[0]
        curr = vt.parse_rows(make_tracker(make_row(status="DONE")))[0]
        assert vt.validate_transition(prev, curr) is None

    def test_no_change_legal(self):
        prev = vt.parse_rows(make_tracker(make_row(status="IN_PROGRESS")))[0]
        curr = vt.parse_rows(make_tracker(make_row(status="IN_PROGRESS")))[0]
        assert vt.validate_transition(prev, curr) is None

    def test_new_row_no_prev_legal(self):
        curr = vt.parse_rows(make_tracker(make_row(status="PLANNED")))[0]
        assert vt.validate_transition(None, curr) is None


# --------------------------------------------------------------------------- #
# Rule R5 — Immutable columns
# --------------------------------------------------------------------------- #


class TestRuleR5:
    def test_description_change_blocked(self):
        prev = vt.parse_rows(make_tracker(make_row(description="Old desc")))[0]
        curr = vt.parse_rows(make_tracker(make_row(description="New desc")))[0]
        viols = vt.validate_immutable(prev, curr)
        assert len(viols) == 1
        assert "Description" in viols[0].detail

    def test_proposal_section_change_blocked(self):
        prev = vt.parse_rows(make_tracker(make_row(prop="§3.6.2")))[0]
        curr = vt.parse_rows(make_tracker(make_row(prop="§3.6.7")))[0]
        viols = vt.validate_immutable(prev, curr)
        assert len(viols) == 1

    def test_gate_ref_change_blocked(self):
        prev = vt.parse_rows(make_tracker(make_row(gate="EG1")))[0]
        curr = vt.parse_rows(make_tracker(make_row(gate="EG2")))[0]
        viols = vt.validate_immutable(prev, curr)
        assert len(viols) == 1

    def test_status_change_allowed(self):
        prev = vt.parse_rows(make_tracker(make_row(status="PLANNED")))[0]
        curr = vt.parse_rows(make_tracker(make_row(status="IN_PROGRESS")))[0]
        assert vt.validate_immutable(prev, curr) == []

    def test_notes_change_allowed(self):
        prev = vt.parse_rows(make_tracker(make_row(notes="-")))[0]
        curr = vt.parse_rows(make_tracker(make_row(notes="blocker resolved")))[0]
        assert vt.validate_immutable(prev, curr) == []

    def test_multiple_immutable_changes_all_reported(self):
        prev = vt.parse_rows(
            make_tracker(make_row(description="A", prop="§1", contrib="C1"))
        )[0]
        curr = vt.parse_rows(
            make_tracker(make_row(description="B", prop="§2", contrib="C2"))
        )[0]
        viols = vt.validate_immutable(prev, curr)
        assert len(viols) == 3


# --------------------------------------------------------------------------- #
# Rule R6 — Task_ID format
# --------------------------------------------------------------------------- #


class TestRuleR6:
    @pytest.mark.parametrize(
        "tid",
        [
            "S0-D1-ENG01",
            "S0-D5-GATE06",
            "S0-D3-RES02",
            "S0-D4-EVAL01",
        ],
    )
    def test_legal_formats(self, tid):
        row = make_row(task_id=tid, day=tid[4], typ=tid.split("-")[2][:-2])
        assert vt.validate_task_id(vt.parse_rows(make_tracker(row))[0]) is None

    @pytest.mark.parametrize(
        "tid",
        [
            "S0-D6-ENG01",  # day out of range
            "S0-D0-ENG01",  # day 0
            "S0-D1-XXX01",  # bad type
            "S0-D1-ENG1",  # 1-digit number
            "S0-D1-ENG001",  # 3-digit number
            "S1-D1-ENG01",  # wrong stage (Stage 1, not Stage 0)
        ],
    )
    def test_illegal_formats(self, tid):
        """Task IDs that look like task IDs but fail validation."""
        row = make_row(task_id=tid)
        v = vt.validate_task_id(vt.parse_rows(make_tracker(row))[0])
        assert v is not None and v.rule == "R6"

    def test_completely_unprefixed_id_skipped_by_parser(self):
        """
        Rows whose first cell doesn't even look like a task ID (e.g. 'ENG01',
        'foo', summary numerics) should not be picked up as task rows at all.
        This is the parser's responsibility, not R6's.
        """
        row = make_row(task_id="ENG01")  # no S<digit> prefix
        rows = vt.parse_rows(make_tracker(row))
        assert rows == []


# --------------------------------------------------------------------------- #
# Rule R7 + R8 — Day and Type
# --------------------------------------------------------------------------- #


class TestRulesR7R8:
    def test_day_6_rejected(self):
        row = make_row(task_id="S0-D1-ENG01", day="6")
        viols = vt.validate_day_and_type(vt.parse_rows(make_tracker(row))[0])
        assert any(v.rule == "R7" for v in viols)

    def test_unknown_type_rejected(self):
        row = make_row(typ="DOC")
        viols = vt.validate_day_and_type(vt.parse_rows(make_tracker(row))[0])
        assert any(v.rule == "R8" for v in viols)

    def test_legal_types_accepted(self):
        for typ in ("ENG", "RES", "EVAL", "GATE"):
            row = make_row(typ=typ)
            assert vt.validate_day_and_type(vt.parse_rows(make_tracker(row))[0]) == []


# --------------------------------------------------------------------------- #
# Top-level validate() integration
# --------------------------------------------------------------------------- #


class TestValidateIntegration:
    def test_clean_tracker_returns_empty(self):
        text = make_tracker(make_row())
        assert vt.validate(text, None) == []

    def test_aggregates_multiple_violations(self):
        # Two rows: one with bad status, one DONE-without-evidence.
        rows = [
            make_row(task_id="S0-D1-ENG01", status="WIP"),
            make_row(task_id="S0-D1-ENG02", status="DONE"),  # missing evidence
        ]
        text = make_tracker(*rows)
        viols = vt.validate(text, None)
        rules = {v.rule for v in viols}
        assert "R3" in rules
        assert "R1" in rules

    def test_immutable_check_uses_prev_text(self):
        prev_text = make_tracker(make_row(description="Original"))
        curr_text = make_tracker(make_row(description="Edited"))
        viols = vt.validate(curr_text, prev_text)
        assert any(v.rule == "R5" for v in viols)

    def test_no_prev_skips_immutable_check(self):
        text = make_tracker(make_row())
        assert vt.validate(text, None) == []


# --------------------------------------------------------------------------- #
# End-to-end: real git repo, run the script as a subprocess
# --------------------------------------------------------------------------- #


@pytest.fixture
def git_repo(tmp_path: Path):
    """Spin up a fresh git repo with the validator script copied in."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@h.local"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=tmp_path, check=True)

    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    src = SCRIPT_DIR / "validate_tracking.py"
    shutil.copy(src, scripts_dir / "validate_tracking.py")

    tracking_dir = tmp_path / "docs" / "tracking"
    tracking_dir.mkdir(parents=True)
    return tmp_path


def run_validator(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/validate_tracking.py"],
        cwd=repo,
        capture_output=True,
        text=True,
    )


class TestE2E:
    def test_no_tracker_returns_zero(self, git_repo):
        result = run_validator(git_repo)
        assert result.returncode == 0

    def test_clean_tracker_first_commit_passes(self, git_repo):
        tracker = git_repo / "docs" / "tracking" / "helios_mvp_tracking.md"
        tracker.write_text(make_tracker(make_row()))
        result = run_validator(git_repo)
        assert result.returncode == 0, result.stderr

    def test_done_without_evidence_fails(self, git_repo):
        tracker = git_repo / "docs" / "tracking" / "helios_mvp_tracking.md"
        tracker.write_text(make_tracker(make_row(status="DONE")))
        result = run_validator(git_repo)
        assert result.returncode == 1
        assert "R1" in result.stderr

    def test_immutable_change_caught_across_commits(self, git_repo):
        tracker = git_repo / "docs" / "tracking" / "helios_mvp_tracking.md"
        # First commit: clean tracker.
        tracker.write_text(make_tracker(make_row(description="Original")))
        subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=git_repo, check=True)
        # Second state: edit immutable column.
        tracker.write_text(make_tracker(make_row(description="Tampered")))
        result = run_validator(git_repo)
        assert result.returncode == 1
        assert "R5" in result.stderr
        assert "Description" in result.stderr

    def test_legal_transition_across_commits_passes(self, git_repo):
        tracker = git_repo / "docs" / "tracking" / "helios_mvp_tracking.md"
        tracker.write_text(make_tracker(make_row(status="PLANNED")))
        subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=git_repo, check=True)
        tracker.write_text(
            make_tracker(
                make_row(
                    status="DONE",
                    started="2026-05-08",
                    done="2026-05-08",
                    sha="abc1234",
                    ev_type="TEST",
                    ev_ref="tests/x.py::y",
                )
            )
        )
        # PLANNED -> DONE is illegal (must go through IN_PROGRESS).
        result = run_validator(git_repo)
        assert result.returncode == 1
        assert "R4" in result.stderr

    def test_proper_two_step_transition_passes(self, git_repo):
        tracker = git_repo / "docs" / "tracking" / "helios_mvp_tracking.md"
        # Commit 1: PLANNED
        tracker.write_text(make_tracker(make_row(status="PLANNED")))
        subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "c1"], cwd=git_repo, check=True)
        # Commit 2: IN_PROGRESS
        tracker.write_text(
            make_tracker(make_row(status="IN_PROGRESS", started="2026-05-08"))
        )
        result = run_validator(git_repo)
        assert result.returncode == 0, result.stderr
        subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "c2"], cwd=git_repo, check=True)
        # Commit 3: DONE with all evidence
        tracker.write_text(
            make_tracker(
                make_row(
                    status="DONE",
                    started="2026-05-08",
                    done="2026-05-08",
                    sha="abc1234",
                    ev_type="TEST",
                    ev_ref="tests/x.py::y",
                )
            )
        )
        result = run_validator(git_repo)
        assert result.returncode == 0, result.stderr
