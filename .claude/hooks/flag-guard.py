#!/usr/bin/env python3
import json
import re
import sys


def main():
    data = json.load(sys.stdin)
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool_name not in ["Write", "Edit", "MultiEdit", "Bash"]:
        sys.exit(0)

    content = tool_input.get("content", "") or tool_input.get("new_content", "") or ""
    command = tool_input.get("command", "")

    # New component introduced without flag?
    if re.search(
        r"def |class |pipeline_|component_", content, re.IGNORECASE
    ) and not re.search(
        r"HELIOS_ENABLE_|ABLA_TE_|feature_flag", content, re.IGNORECASE
    ):
        print(
            "❌ New component/pipeline added without corresponding feature flag.",
            file=sys.stderr,
        )
        print(
            "   All HELIOS components must be behind a flag for ablation studies.",
            file=sys.stderr,
        )
        sys.exit(2)

    # Bash guard: prevent direct python -c or non-reproducible runs
    if tool_name == "Bash" and re.search(r"python -c|random\.|time\.sleep", command):
        print("❌ Non-reproducible command detected in shell.", file=sys.stderr)
        sys.exit(2)

    print("✅ Flag guard passed", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
