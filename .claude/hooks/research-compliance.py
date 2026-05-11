#!/usr/bin/env python3
import json
import re
import sys

# HELIOS Research Compliance Guard
# Blocks edits that violate ablation-first principles


def main():
    data = json.load(sys.stdin)
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool_name not in ["Write", "Edit", "MultiEdit"]:
        print("OK", file=sys.stderr)
        sys.exit(0)

    # Get the content being written/edited
    content = tool_input.get("content", "") or tool_input.get("new_content", "") or ""
    file_path = tool_input.get("file_path", tool_input.get("path", ""))

    violations = []

    # 1. No hard-coded seeds (must use config/flag)
    if re.search(
        r"seed\s*=\s*(42|123|random|np\.random|torch\.manual_seed)",
        content,
        re.IGNORECASE,
    ):
        violations.append(
            "❌ Hard-coded seed detected. Use HELIOSConfig or feature flag instead."
        )

    # 2. Never remove feature flags
    if re.search(
        r"feature_flag|HELIOS_.*ENABLE|ABLA_TE|noLLM|noGraph|noStats",
        content,
        re.IGNORECASE,
    ) and re.search(
        r"(if False|if 0|# TODO: remove flag|delete flag)", content, re.IGNORECASE
    ):
        violations.append(
            "❌ Attempt to disable/remove feature flag without ablation matrix update."
        )

    # 3. No magic numbers in critical paths
    if (
        re.search(r"\b(0\.0|1\.0|0\.5|100)\b", content)
        and "config" not in file_path.lower()
    ):
        violations.append(
            "❌ Magic number in core logic. Use configurable constant via feature flag."
        )

    if violations:
        print("\n".join(violations), file=sys.stderr)
        print("🚫 Research compliance violation — edit blocked.", file=sys.stderr)
        sys.exit(2)  # Block the tool

    print("✅ Research compliance passed", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
