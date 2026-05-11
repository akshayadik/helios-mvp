#!/bin/bash
# HELIOS PostToolUse: Format code + update ablation matrix

set -e

read -r JSON

FILE_PATH=$(echo "$JSON" | jq -r '.tool_input.file_path // .tool_input.path // ""')

echo "📝 Formatting + updating ablation matrix for $FILE_PATH"

# Format (choose your tool — ruff is fastest)
if command -v ruff >/dev/null; then
    ruff check --fix "$FILE_PATH" 2>/dev/null || true
    ruff format "$FILE_PATH" 2>/dev/null || true
elif command -v black >/dev/null; then
    black --quiet "$FILE_PATH" 2>/dev/null || true
fi

# Update ablation matrix (assumes you have a simple CSV updater)
python -c '
import csv, sys, datetime
row = ["$(date -u +"%Y-%m-%d %H:%M:%S")", "$(git rev-parse --short HEAD 2>/dev/null || echo unknown)", "'"$FILE_PATH"'", "edited", "42"]
with open("ablation_matrix.csv", "a", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(row)
print("✅ Ablation matrix updated")
' 2>/dev/null || echo "⚠️ Matrix update skipped (file may not exist yet)"

echo "✅ Format + matrix update complete"