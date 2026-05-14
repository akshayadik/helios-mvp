#!/bin/bash
# HELIOS Gemini AfterTool: Run tests + append experiment log

# Read Gemini hook JSON from stdin
JSON=$(cat)

# Extract tool name and input
TOOL_NAME=$(echo "$JSON" | jq -r '.tool_name // ""')
# For file-related tools, extract the path
FILE_PATH=$(echo "$JSON" | jq -r '.tool_input.file_path // .tool_input.path // .tool_input.dir_path // ""')

# Only run for modifying tools to avoid excessive overhead
case "$TOOL_NAME" in
  "replace" | "write_file" | "run_shell_command")
    # Log to stderr so it shows up in the CLI
    echo "🔧 AfterTool triggered: $TOOL_NAME on $FILE_PATH" >&2

    # Run relevant tests
    if [[ -f "pyproject.toml" ]]; then
        echo "🧪 Running HELIOS verification..." >&2
        # Run subset of fast tests to avoid blocking the user
        poetry run pytest -q --tb=no tests/test_vcl.py tests/test_hmac_chain.py tests/test_validate_tracking.py >&2 || echo "⚠️ Some core tests failed (logged)" >&2
    fi

    # Log experiment metadata
    LOG_FILE="experiments/experiment_log.csv"
    mkdir -p experiments

    COMMIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    SEED=${SEED:-42}

    # CSV Format: Timestamp, SHA, Path, Tool, Seed
    echo "$TIMESTAMP,$COMMIT_SHA,$FILE_PATH,$TOOL_NAME,$SEED" >> "$LOG_FILE"
    echo "✅ Entry added to $LOG_FILE" >&2
    ;;
  *)
    # Do nothing for read-only tools
    ;;
esac

# Return allow decision
echo '{"decision": "allow"}'
