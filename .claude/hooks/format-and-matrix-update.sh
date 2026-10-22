#!/bin/bash
# HELIOS PostToolUse: Format the edited Python file with the project toolchain

set -e

read -r JSON

FILE_PATH=$(echo "$JSON" | jq -r '.tool_input.file_path // .tool_input.path // ""')

[[ "$FILE_PATH" == *.py ]] || exit 0

echo "📝 Formatting $FILE_PATH"

# Use the project's pinned ruff (poetry venv), not whatever is on PATH.
POETRY=$(command -v poetry || echo "$HOME/.local/bin/poetry")
VENV=$("$POETRY" env info -p 2>/dev/null || true)
RUFF="$VENV/bin/ruff"
if [[ -x "$RUFF" ]]; then
    "$RUFF" check --fix "$FILE_PATH" 2>/dev/null || true
    "$RUFF" format "$FILE_PATH" 2>/dev/null || true
    echo "✅ Formatted with $("$RUFF" --version)"
else
    echo "⚠️ Not formatted: no Poetry virtualenv ruff found (run: poetry install)"
fi

# The former "ablation matrix update" step was removed (2026-10-22). It never
# ran (bare `python`), its row was built inside single quotes so `$(date)` was
# never expanded, and it targeted a root ablation_matrix.csv that does not
# exist. .claude/ablation_matrix.csv is the variant-definition table; per-edit
# events belong in experiments/experiment_log.csv (auto-test-and-log.sh).
