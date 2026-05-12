# Save Bug Fixes to Memory

Scan this conversation for bugs diagnosed and fixed, then write persistent memory entries so future HELIOS sessions don't repeat the same mistakes.

**Arguments (optional):** $ARGUMENTS — topic filter (e.g. "ruff", "pydantic", "poetry")

## Memory directory (project-specific)

`/home/akshay/.claude/projects/-home-akshay-workspace-helios-mvp/memory/`

Create with `mkdir -p` if missing.

## What to extract

For each fixed bug, capture:
- **Symptom** — visible error or failure
- **Root cause** — the specific mechanism (not "code was wrong")
- **Rule** — generalised, actionable, transferable to future sessions

Skip trivial typos, one-off codebase-specific mistakes, and anything already in an existing memory file.

## File format

Write one `feedback_<slug>.md` per bug. Use Bash heredoc (not Write tool) to avoid flag-guard blocks on content containing `def ` or `class `.

```
---
name: <short name>
description: <one sentence — specific enough to trigger recall>
type: feedback
---

<rule — lead with the rule, not the story>

**Why:** <root cause mechanism>

**How to apply:** <when this kicks in and what to do>
```

## Update MEMORY.md

Append one line per new file to `memory/MEMORY.md`:
```
- [<name>](<filename>.md) — <one-line hook, under 150 chars>
```
Read existing MEMORY.md first — do not overwrite or duplicate entries.

## Output

Report: count of new entries written, one-line summary each, memory directory path.
