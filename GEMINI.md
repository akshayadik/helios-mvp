# GEMINI.md

This file provides the governance protocol for Gemini when interacting with the HELIOS research artefact.

---

## Research Context: HELIOS (Stage 0)
HELIOS is an ablation-first Root Cause Analysis (RCA) framework. Research integrity depends on the **Variant Control Layer (VCL)**. Gemini must treat the architecture as a controlled experiment where components C1–C6 are independent variables.

### Mandatory Session Context
**ALWAYS reference these documents before any research-related suggestions or creative work:**
1. `.claude/docs/pdf/research_proposal_akshayadik.pdf` — Ground all RQ framing, hypothesis justification, and artefact design here.
2. `.claude/docs/pdf/project_plan.md` — Use to assess task fit and milestone alignment.

---

## Core Invariants (Never Violate)

- **Ablation-First Logic:** Every new function or class must be wrapped in a `@gated_by(VCLFlag.X)` decorator. If Gemini suggests a feature, it *must* suggest the corresponding flag.
- **Reproducibility Bound:** Strictly use Python `3.11.x`. Do not suggest features from 3.12+.
- **HMAC Chain Integrity:** Gemini is forbidden from manual edits to `deviation_log.jsonl`. All changes requiring a deviation must be performed via `bin/log_deviation.py`.
- **No Hallucinated Seeds:** Never suggest hard-coded random seeds. Use the project's central entropy management.
- **Strict Typing:** All Python code must be PEP 484 compliant and pass `mypy` with `strict=true`.
- **Tracking Discipline:** Never change immutable tracking columns (Task_ID, Day, Type, etc.) after a row is committed.
- **Literal Check:** Avoid literals like `0.0`, `1.0`, `0.5`, or `100` as word-bounded tokens in code or documentation to pass `research-compliance.py`.

---

## Gemini Workflow Commands

### Verification Suite
Run this sequence before every commit of research logic:
```bash
set -a; source .env; set +a && \
poetry run ruff check helios/ scripts/ tests/ && \
poetry run ruff format --check helios/ scripts/ tests/ && \
poetry run mypy && \
poetry run pytest && \
poetry run python bin/log_deviation.py verify && \
make validate-tracking
```

### Deviation Logging
When a protocol change has analytic consequences:
```bash
set -a; source .env; set +a
poetry run python bin/log_deviation.py \
  --stage "Stage N" \
  --clause "§..." \
  --change "..." \
  --reason "..." \
  --analytic-consequence "..."
```

---

## VCL & Pipeline Patterns

- **Consumer Pattern:** Annotate entry points with `@gated_by(VCLFlag.X)`.
- **Manifest Setup:** Call `set_current_manifest(manifest)` before invoking gated components.
- **Flag Iteration:** Use `VCLFlag.bool_flags()` for audits/tests, not `VCLFlag` directly.
- **Pydantic V2:** `VCLManifest` is `frozen=True`. Use `@field_validator` for cross-field logic.

---

## Tracking Schema Rules (R1–R8)
- **R1:** DONE rows must have Started, Done, SHA, Ev_Type, Ev_Ref.
- **R2:** DEFERRED/CARRIED_OVER rows must have Deviation_Ref.
- **R3-R4:** Status and Transitions must follow the defined state machine.
- **R6:** Task_ID format: `S0-D{1-5}-{ENG|RES|EVAL|GATE}{nn}`.

---

## OSF Protocol Bindings
- **Asymmetric Inferential Rule:** For A-H4 and A-H8, non-rejection ≠ falsification.
- **Two-Environment Firewall:** OTEL Demo = exploratory; AIOpsLab = confirmatory.
- **Effect Size:** Cohen's h ≥ 0.276 is binding.