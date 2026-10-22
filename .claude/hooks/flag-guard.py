#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path


def edited_text(tool_name, tool_input):
    """Return the file content the tool call would produce.

    Write sends the whole file as `content`. Edit/MultiEdit send fragments
    (`old_string`/`new_string`), so the flag check must run on the file as it
    will look after the edit — a fragment adding a `def` to a module that
    already imports VCLFlag is compliant.
    """
    if tool_name == "Write":
        return tool_input.get("content", "") or ""
    path = Path(tool_input.get("file_path", ""))
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    edits = tool_input.get("edits") or [tool_input]
    for e in edits:
        old, new = e.get("old_string", ""), e.get("new_string", "")
        if e.get("replace_all"):
            text = text.replace(old, new)
        elif old:
            text = text.replace(old, new, 1)
        else:
            text = new + text
    return text


def main():
    data = json.load(sys.stdin)
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool_name not in ["Write", "Edit", "MultiEdit", "Bash"]:
        sys.exit(0)

    command = tool_input.get("command", "")
    file_path = tool_input.get("file_path", "")
    content = "" if tool_name == "Bash" else edited_text(tool_name, tool_input)

    # VCL implements the flag discipline itself — it is always flag-compliant
    # by definition. Exempting helios/vcl/ prevents the guard from blocking
    # the very system it enforces. (Approved in planning session 2026-05-11)
    # .claude/ holds dev tooling (these hooks), not HELIOS components.
    is_exempt = "helios/vcl/" in file_path or "/.claude/" in f"/{file_path}"

    # New component introduced without flag?
    if (
        not is_exempt
        and re.search(r"def |class |pipeline_|component_", content, re.IGNORECASE)
        and not re.search(
            r"HELIOS_ENABLE_|ABLA_TE_|feature_flag|VCLFlag|gated_by|VCLManifest",
            content,
            re.IGNORECASE,
        )
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
