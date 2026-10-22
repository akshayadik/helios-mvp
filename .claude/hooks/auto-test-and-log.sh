#!/bin/bash
# HELIOS PostToolUse: Run tests + append experiment log

set -e

# Read Claude hook JSON from stdin
read -r JSON

TOOL_NAME=$(echo "$JSON" | jq -r '.tool_name // ""')
FILE_PATH=$(echo "$JSON" | jq -r '.tool_input.file_path // .tool_input.path // ""')

echo "🔧 PostToolUse triggered: $TOOL_NAME on $FILE_PATH"

# Resolve the project's Poetry interpreter. A bare `python` is absent on some
# hosts (macOS + Homebrew ships only python3), and a failed lookup used to be
# reported as "Some tests failed" while no test had run.
POETRY=$(command -v poetry || echo "$HOME/.local/bin/poetry")
PY=""
if [[ -x "$POETRY" ]]; then
    VENV=$("$POETRY" env info -p 2>/dev/null || true)
    [[ -n "$VENV" && -x "$VENV/bin/python" ]] && PY="$VENV/bin/python"
    # Some tests shell out to `poetry run ...`; expose poetry + venv tools.
    export PATH="$(dirname "$POETRY"):$VENV/bin:$PATH"
fi

# Run relevant tests (adjust to your test command)
if [[ -f "pyproject.toml" || -f "requirements.txt" ]]; then
    if [[ -z "$PY" ]]; then
        echo "⚠️ Tests NOT run: no Poetry virtualenv found (run: poetry install)"
    else
        echo "🧪 Running tests with $("$PY" -V 2>&1)..."
        if "$PY" -m pytest --tb=no -q --no-cov >/dev/null 2>&1; then
            echo "✅ Tests passed"
        else
            echo "⚠️ Tests FAILED (run: poetry run pytest)"
        fi
    fi
fi

# Log experiment metadata
LOG_FILE="experiments/experiment_log.csv"
mkdir -p experiments

COMMIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
SEED=${SEED:-42}  # Can be overridden by environment

echo "$TIMESTAMP,$COMMIT_SHA,$FILE_PATH,$TOOL_NAME,$SEED" >> "$LOG_FILE"

echo "✅ Edit logged to $LOG_FILE"
