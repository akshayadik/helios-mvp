# HELIOS Claude Code Setup — Ablation-First Development Environment

**Optimized for DSR compliance, reproducibility, low token usage & cost efficiency.**

This document describes the complete `.claude/` configuration for the HELIOS research artefact.

## 1. Folder Structure (`.claude/`)

```bash
.claude/
├── settings.json                 # Hooks, default model (Sonnet), allowed tools
├── CLAUDE.md                     # Persistent project memory (core rules)
├── Local_CLAUDE.md               # Personal dev rules & token budget
├── commands/                     # Custom slash commands (highly recommended)
│   ├── review-and-commit.md
│   ├── log-deviation.md
│   ├── compact-research-session.md
│   ├── helios-summary.md
│   ├── token-audit.md
│   ├── ablation-runner.md
│   └── ... (more below)
├── agents/                       # Sub-agent definitions
│   ├── AblationCoordinatorAgent.md
│   ├── StatisticalPipelineAgent.md
│   ├── GraphPipelineAgent.md
│   ├── LLMReasoningAgent.md
│   └── EvaluationReporterAgent.md
├── hooks/                        # Pre/Post ToolUse automation
│   ├── research-compliance.py
│   ├── flag-guard.py
│   ├── auto-test-and-log.sh
│   └── format-and-matrix-update.sh
├── SKILL.md                      # All pipeline tester / metrics skills
└── shared_state/                 # experiment_registry.json, etc.
```

## 2. Core Commands (Copy these into `.claude/commands/`)

### `/review-and-commit` (Recommended before every check-in)
```
/review-and-commit variant=... scope=... message=...
```
- Runs reproducibility guard + scoped tests + metrics-evaluator
- Auto-generates deviation logs (handles single **or multiple** pipelines)
- Runs PostToolUse hooks
- Shows final commit message for approval

**Multi-pipeline example**:
```
/review-and-commit variant=HELIOS-Full message="L-pipe safety + Stats threshold"
```

### `/log-deviation` (Auto-called by review-and-commit)
```
/log-deviation variant=HELIOS-noLLM components="L-pipe,Statistical" changes="..." impacts="..." reasons="..."
```
Generates structured deviation table (one row per component) and appends to `experiments/deviation_log.md`.

### Essential Research Commands
- `/compact-research-session` — Condense session memory (use after every major task)
- `/metrics-evaluator variant=... focus=ablation-delta`
- `/ablation-runner component=LLM variant=HELIOS-noLLM`
- `/pipeline-tester pipeline=L-pipe`
- `/token-audit` — Analyze token usage + cost projection
- `/helios-summary` — Current state summary (<800 tokens)
- `/reproducibility-guard last-experiment`

## 3. Hooks (Automatic — configured in `settings.json`)

**PreToolUse** (blocking):
- `research-compliance.py` → Blocks hard-coded seeds, magic numbers, flag removal
- `flag-guard.py` → Enforces feature flags for every new component

**PostToolUse**:
- `auto-test-and-log.sh` → Runs pytest + logs to experiment_log.csv
- `format-and-matrix-update.sh` → Ruff/Black + appends to ablation_matrix.csv

## 4. Agents & Governance

- **AblationCoordinatorAgent** — Final authority for cross-pipeline changes
- Pipeline-specific agents (Statistical, Graph, LLM) — strictly scoped
- `agent_registry.py` + `validate_agent_action()` used before edits

## 5. Development Workflow (Token & Cost Optimized)

1. **Plan** → Use `/helios-summary` + planning mode (Opus only when needed)
2. **Implement** → Scoped edits (single pipeline preferred)
3. **Review** → `/review-and-commit`
4. **Compact** → `/compact-research-session`
5. **Commit** → Approve generated message

**Token-saving rules**:
- Always use `scope=` or `variant=` arguments
- Prefer Sonnet 4.6 (default)
- Compact every 10–15 turns
- Never load full proposal PDF unless necessary

## 6. Key Files to Reference

- `@CLAUDE.md`
- `@ablation_matrix.csv`
- `@dsr_preregistration.md`
- `@evaluation_protocol.md`
- `@settings.json`

---

**Setup Instructions (One-time)**

```bash
# 1. Create structure
mkdir -p .claude/{commands,agents,hooks,shared_state}

# 2. Copy settings
cp /home/workdir/attachments/settings.json .claude/settings.json

# 3. Copy all hooks, agents, skills (already in attachments)

# 4. Create commands (I can generate them now)
```

---
