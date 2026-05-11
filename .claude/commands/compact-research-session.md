# HELIOS Compact Research Session Command

You are now in **Research Session Compaction Mode** for HELIOS (DSR ablation-centric development).

**Goal**: Condense the current conversation into a minimal, high-value research memory while preserving everything critical for reproducibility, ablation integrity, and DSR validity. Do NOT lose experiment state.

### Mandatory Output Structure (exactly follow this format):

**1. Current Experiment State**
- Variant: [e.g., HELIOS-Full / HELIOS-noLLM / etc.]
- Feature Flags Active: [list enabled/disabled]
- Seed: [current seed]
- Commit SHA: [current short SHA]
- Last Experiment Run: [timestamp or description]

**2. Key Decisions & Hypotheses Status**
- Research questions/hypotheses currently being addressed (A-H1, etc.)
- Ablation decisions made (what was disabled/enabled and why)
- Any validity threats noted (internal/external/construct)

**3. Metrics Snapshot**
- HR@3 | CpR | Hallucination Rate | CoE Quality | MTTR delta
- Comparison vs baseline (if available)
- Any regressions flagged (>5%)

**4. Open Action Items / Next Steps**
- Bullet list of concrete next tasks (max 5)
- Files that must be referenced in future sessions

**5. Persistent Context Summary**
- One-paragraph summary of architecture/pipeline status relevant to current work
- Any important CoE narratives or explanations produced

---

**Instructions for Claude:**
- Be extremely concise. Aim for under 800 tokens total.
- Prioritize ablation matrix alignment, reproducibility artefacts, and DSR compliance.
- After generating this summary, ask: "Apply this as new session memory? (Y/n)"
- If user says Yes, merge intelligently into `.claude/CLAUDE.md` (preserve existing structure) and/or create a temporary `session-memory.md` for the current thread.
- Always run PostToolUse hooks (matrix update + logging) after compaction.
- End with: "Session compacted. Ready for next research step."

**Usage Examples:**
/compact-research-session
/compact-research-session focus=ablation-matrix
/compact-research-session focus=LLM-pipeline