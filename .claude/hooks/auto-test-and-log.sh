#!/bin/bash
# HELIOS PostToolUse: Run tests + append experiment log

set -e

# Read Claude hook JSON from stdin
read -r JSON

TOOL_NAME=$(echo "$JSON" | jq -r '.tool_name // ""')
FILE_PATH=$(echo "$JSON" | jq -r '.tool_input.file_path // .tool_input.path // ""')

echo "🔧 PostToolUse triggered: $TOOL_NAME on $FILE_PATH"

# Run relevant tests (adjust to your test command)
if [[ -f "pyproject.toml" || -f "requirements.txt" ]]; then
    echo "🧪 Running tests..."
    python -m pytest --tb=no -q || echo "⚠️ Some tests failed (logged)"
fi

# Log experiment metadata
LOG_FILE="experiments/experiment_log.csv"
mkdir -p experiments

COMMIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
SEED=${SEED:-42}  # Can be overridden by environment

echo "$TIMESTAMP,$COMMIT_SHA,$FILE_PATH,$TOOL_NAME,$SEED" >> "$LOG_FILE"

echo "✅ Test + log completed. Entry added to $LOG_FILE"