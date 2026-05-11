#!/usr/bin/env python3
"""
HELIOS MVP — Tracking-File Pre-Commit Validator

Enforces the schema contract documented in docs/tracking/helios_mvp_tracking.md.
Runs as a Git pre-commit hook; rejects commits that violate any of the rules
below, mirroring the C1 runtime-enforcement discipline (Execution Plan §6.1).

Rules enforced
--------------
R1  DONE rows must have non-empty Started, Done, SHA, Ev_Type, Ev_Ref.
R2  DEFERRED or CARRIED_OVER rows must have a non-empty Deviation_Ref.
R3  Status must be one of the six legal values.
R4  State transitions must be legal per the documented state machine.
R5  Immutable columns (1-9, 16) must not change between commits.
R6  Task_ID must match the format S0-D{day}-{TYPE}{nn}.
R7  Day field must be 1-5 for Stage 0 Week 1 rows.
R8  Type field must be one of ENG / RES / EVAL / GATE.

Exit codes
----------
0  All rules satisfied (or tracker absent — first commit case).
1  One or more violations; details printed to stderr.
2  Internal error (tracker malformed beyond parsing, git unavailable).

Stdlib only. No third-party dependencies.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

TRACKER_PATH = Path("docs/tracking/helios_mvp_tracking.md")

# Column indices (0-based) within a parsed row.
# Order must match the markdown table header exactly.
COL_TASK_ID = 0
COL_DAY = 1
COL_TYPE = 2
COL_DESCRIPTION = 3
COL_PROP = 4
COL_DSR = 5
COL_CONTRIB = 6
COL_OWNER = 7
COL_DEPS = 8
COL_STATUS = 9
COL_STARTED = 10
COL_DONE = 11
COL_SHA = 12
COL_EV_TYPE = 13
COL_EV_REF = 14
COL_GATE = 15
COL_DEV_REF = 16
COL_NOTES = 17

EXPECTED_COL_COUNT = 18

# Immutable columns: changing any of these between commits is a violation.
IMMUTABLE_COLS = frozenset(
    {
        COL_TASK_ID,
        COL_DAY,
        COL_TYPE,
        COL_DESCRIPTION,
        COL_PROP,
        COL_DSR,
        COL_CONTRIB,
        COL_OWNER,
        COL_DEPS,
        COL_GATE,
    }
)

LEGAL_STATUSES = frozenset(
    {
        "PLANNED",
        "IN_PROGRESS",
        "BLOCKED",
        "DONE",
        "DEFERRED",
        "CARRIED_OVER",
    }
)

LEGAL_TYPES = frozenset({"ENG", "RES", "EVAL", "GATE"})

# State machine (see helios_mvp_tracking.md). Empty set = terminal state.
LEGAL_TRANSITIONS: dict[str, frozenset[str]] = {
    "PLANNED": frozenset({"IN_PROGRESS", "BLOCKED", "DEFERRED"}),
    "IN_PROGRESS": frozenset({"BLOCKED", "DONE", "CARRIED_OVER", "DEFERRED"}),
    "BLOCKED": frozenset({"IN_PROGRESS", "DEFERRED", "CARRIED_OVER"}),
    "DONE": frozenset(),  # terminal
    "DEFERRED": frozenset(),  # terminal
    "CARRIED_OVER": frozenset(),  # terminal
}

# Task_ID format: S0-D{1-5}-{ENG|RES|EVAL|GATE}{2-digit number}
TASK_ID_REGEX = re.compile(r"^S0-D[1-5]-(ENG|RES|EVAL|GATE)\d{2}$")


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Violation:
    task_id: str
    rule: str
    detail: str

    def format(self) -> str:
        tid = self.task_id or "<unknown>"
        return f"[{self.rule}] {tid}: {self.detail}"


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


def parse_rows(text: str) -> list[list[str]]:
    """
    Extract task rows from the tracker markdown.

    A task row is any pipe-delimited line that:
      - has exactly EXPECTED_COL_COUNT cells, and
      - whose first cell looks like a task identifier (starts with 'S' followed
        by a digit, e.g. S0, S1, S2 — i.e. any stage).

    This accepts malformed Task_IDs (so R6 can flag them) while still rejecting
    table headers, separator rows, prose, and the summary statistics table.

    Returns a list of cell-value lists.
    """
    rows: list[list[str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            continue
        # Split by pipe and discard the leading/trailing empty cells.
        parts = [c.strip() for c in line.split("|")[1:-1]]
        if len(parts) != EXPECTED_COL_COUNT:
            continue
        first = parts[0]
        # Task-ID cells start with 'S' + a digit (stage prefix). Header cells
        # ("Task_ID"), separator cells ("---"), and summary rows (numbers like
        # "1", "Total") all fail this check.
        if len(first) >= 2 and first[0] == "S" and first[1].isdigit():
            rows.append(parts)
    return rows


def get_previous_tracker(repo_path: Path = Path(".")) -> str | None:
    """
    Read the tracker as it existed at HEAD via `git show`. Returns None on the
    initial commit (no HEAD yet) or if the tracker was not in the previous
    commit. Any other git failure raises.
    """
    rel = TRACKER_PATH.as_posix()
    try:
        result = subprocess.run(
            ["git", "show", f"HEAD:{rel}"],
            cwd=str(repo_path),
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git executable not found on PATH") from exc

    if result.returncode == 0:
        return result.stdout
    stderr = result.stderr.lower()
    benign = (
        "unknown revision" in stderr
        or "does not exist" in stderr
        or "exists on disk, but not in" in stderr
        or "bad revision" in stderr
        or "not a git repository" in stderr
        or "invalid object name" in stderr  # fresh repo, no HEAD yet
        or "ambiguous argument" in stderr  # alternate phrasing on some git versions
    )
    if benign:
        return None
    raise RuntimeError(f"git show failed: {result.stderr.strip()}")


# --------------------------------------------------------------------------- #
# Per-rule validators
# --------------------------------------------------------------------------- #


def _empty(cell: str) -> bool:
    """A cell is 'empty' if it is blank or the placeholder dash."""
    return cell == "" or cell == "-"


def validate_row_shape(row: list[str], row_num: int) -> Violation | None:
    """R0: row must have exactly EXPECTED_COL_COUNT cells."""
    if len(row) != EXPECTED_COL_COUNT:
        tid = row[COL_TASK_ID] if row else f"row#{row_num}"
        return Violation(
            task_id=tid,
            rule="R0",
            detail=f"expected {EXPECTED_COL_COUNT} cells, found {len(row)}",
        )
    return None


def validate_task_id(row: list[str]) -> Violation | None:
    """R6: Task_ID must match S0-D{1-5}-{TYPE}{nn}."""
    tid = row[COL_TASK_ID]
    if not TASK_ID_REGEX.match(tid):
        return Violation(
            task_id=tid,
            rule="R6",
            detail=f"malformed Task_ID '{tid}'",
        )
    return None


def validate_day_and_type(row: list[str]) -> list[Violation]:
    """R7 + R8: Day in 1-5; Type in legal set."""
    out: list[Violation] = []
    tid = row[COL_TASK_ID]
    day = row[COL_DAY]
    if day not in {"1", "2", "3", "4", "5"}:
        out.append(Violation(tid, "R7", f"Day must be 1-5, got '{day}'"))
    typ = row[COL_TYPE]
    if typ not in LEGAL_TYPES:
        out.append(
            Violation(
                tid, "R8", f"Type must be one of {sorted(LEGAL_TYPES)}, got '{typ}'"
            )
        )
    return out


def validate_status_value(row: list[str]) -> Violation | None:
    """R3: Status must be a legal enum value."""
    tid = row[COL_TASK_ID]
    status = row[COL_STATUS]
    if status not in LEGAL_STATUSES:
        return Violation(
            task_id=tid,
            rule="R3",
            detail=f"illegal Status '{status}' (legal: {sorted(LEGAL_STATUSES)})",
        )
    return None


def validate_done_row(row: list[str]) -> list[Violation]:
    """R1: DONE rows require Started, Done, SHA, Ev_Type, Ev_Ref."""
    out: list[Violation] = []
    if row[COL_STATUS] != "DONE":
        return out
    tid = row[COL_TASK_ID]
    required = [
        (COL_STARTED, "Started"),
        (COL_DONE, "Done"),
        (COL_SHA, "SHA"),
        (COL_EV_TYPE, "Ev_Type"),
        (COL_EV_REF, "Ev_Ref"),
    ]
    for col, name in required:
        if _empty(row[col]):
            out.append(Violation(tid, "R1", f"Status=DONE requires {name} to be set"))
    return out


def validate_deferred_row(row: list[str]) -> Violation | None:
    """R2: DEFERRED or CARRIED_OVER rows require Deviation_Ref."""
    if row[COL_STATUS] not in ("DEFERRED", "CARRIED_OVER"):
        return None
    tid = row[COL_TASK_ID]
    if _empty(row[COL_DEV_REF]):
        return Violation(
            task_id=tid,
            rule="R2",
            detail=f"Status={row[COL_STATUS]} requires Deviation_Ref to be set",
        )
    return None


def validate_transition(
    prev_row: list[str] | None, curr_row: list[str]
) -> Violation | None:
    """R4: Status transition must be legal per LEGAL_TRANSITIONS."""
    if prev_row is None:
        return None
    prev_status = prev_row[COL_STATUS]
    curr_status = curr_row[COL_STATUS]
    if prev_status == curr_status:
        return None
    if curr_status not in LEGAL_TRANSITIONS.get(prev_status, frozenset()):
        return Violation(
            task_id=curr_row[COL_TASK_ID],
            rule="R4",
            detail=f"illegal transition {prev_status} -> {curr_status}",
        )
    return None


def validate_immutable(
    prev_row: list[str] | None, curr_row: list[str]
) -> list[Violation]:
    """R5: immutable columns must not change between commits."""
    out: list[Violation] = []
    if prev_row is None or len(prev_row) != EXPECTED_COL_COUNT:
        return out
    column_names = {
        COL_TASK_ID: "Task_ID",
        COL_DAY: "Day",
        COL_TYPE: "Type",
        COL_DESCRIPTION: "Description",
        COL_PROP: "Prop_section",
        COL_DSR: "DSR",
        COL_CONTRIB: "Contrib",
        COL_OWNER: "Owner",
        COL_DEPS: "Deps",
        COL_GATE: "Gate",
    }
    tid = curr_row[COL_TASK_ID]
    for col in IMMUTABLE_COLS:
        if prev_row[col] != curr_row[col]:
            name = column_names[col]
            out.append(
                Violation(
                    task_id=tid,
                    rule="R5",
                    detail=f"immutable column '{name}' changed: '{prev_row[col]}' -> '{curr_row[col]}'",
                )
            )
    return out


# --------------------------------------------------------------------------- #
# Top-level validation
# --------------------------------------------------------------------------- #


def validate(current_text: str, previous_text: str | None) -> list[Violation]:
    """Run every rule and return the aggregated violation list."""
    violations: list[Violation] = []
    current_rows = parse_rows(current_text)

    prev_lookup: dict[str, list[str]] = {}
    if previous_text is not None:
        for prow in parse_rows(previous_text):
            if prow and len(prow) == EXPECTED_COL_COUNT:
                prev_lookup[prow[COL_TASK_ID]] = prow

    for i, row in enumerate(current_rows, start=1):
        shape_v = validate_row_shape(row, i)
        if shape_v is not None:
            violations.append(shape_v)
            continue

        if v := validate_task_id(row):
            violations.append(v)
        violations.extend(validate_day_and_type(row))
        if v := validate_status_value(row):
            violations.append(v)
            continue
        violations.extend(validate_done_row(row))
        if v := validate_deferred_row(row):
            violations.append(v)

        prev_row = prev_lookup.get(row[COL_TASK_ID])
        if v := validate_transition(prev_row, row):
            violations.append(v)
        violations.extend(validate_immutable(prev_row, row))

    return violations


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    if not TRACKER_PATH.exists():
        return 0

    try:
        current_text = TRACKER_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"validator: cannot read {TRACKER_PATH}: {exc}", file=sys.stderr)
        return 2

    try:
        previous_text = get_previous_tracker()
    except RuntimeError as exc:
        print(f"validator: {exc}", file=sys.stderr)
        return 2

    violations = validate(current_text, previous_text)

    if not violations:
        return 0

    n = len(violations)
    print(
        f"\nTRACKING VALIDATION FAILED ({n} violation{'s' if n != 1 else ''}):\n",
        file=sys.stderr,
    )
    for v in violations:
        print(f"  {v.format()}", file=sys.stderr)
    print(
        "\nFix the rows above and re-stage. See docs/tracking/helios_mvp_tracking.md "
        "for the schema contract.\n",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
