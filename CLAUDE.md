# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## What this codebase is

HELIOS is a doctoral research artefact: a Root Cause Analysis (RCA) framework built around **ablation-first design science**. The entire architecture is structured so every major component (C1–C6) can be toggled at runtime via feature flags, enabling controlled ablation studies. Research integrity is enforced by code — not convention.

Current stage: **Stage 0** (Spine + Harness). Pipeline modules (`helios/pipelines/`) are stubs; `bin/log_exclusion.py` is a Stage 1+ stub. Fully-implemented Stage 0 artefacts: **HMAC-chained deviation log** (`bin/log_deviation.py`), **tracking validator** (`scripts/validate_tracking.py`), and **VCL core** (`helios/vcl/`). Python must be exactly `>=3.11,<3.12` — the upper bound is a reproducibility commitment, not a preference.

---

## Core Invariants (Never Violate)

- Every major component must remain togglable via feature flags (ablation discipline).
- Never hard-code seeds or remove feature flags.
- Every protocol change with analytic consequence must be logged to `deviation_log.jsonl` **via the CLI before merging** — never edit the JSONL by hand.
- Every code edit must be followed by `poetry run pytest` + tracking matrix update.
- Immutable tracking columns (Task_ID, Day, Type, Description, Prop, DSR, Contrib, Owner, Deps, Gate) must never change after a row is committed.

---

## Commands

### Setup (once per clone)

```bash
# Generate HMAC secret (required for deviation log; must not be committed)
python3 -c "import secrets; print(f'DEVIATION_HMAC_SECRET={secrets.token_urlsafe(32)}')" > .env
chmod 600 .env

poetry env use python3.11
poetry install
poetry run pre-commit install
```

### Pre-push gate (run before every PR — exact CI sequence)

```bash
set -a; source .env; set +a && \
  poetry run ruff check helios/ scripts/ tests/ && \
  poetry run ruff format --check helios/ scripts/ tests/ && \
  poetry run mypy && \
  poetry run pytest && \
  poetry run python bin/log_deviation.py verify && \
  make validate-tracking
```

### Testing

```bash
poetry run pytest                                                      # all tests
poetry run pytest -v                                                   # verbose
poetry run pytest tests/test_deviation_log.py -v                      # HMAC canary (12 tests)
poetry run pytest tests/test_deviation_log.py::test_verify_chain_passes_on_clean_log -v  # single test
poetry run pytest tests/test_validate_tracking.py -v                  # tracking validator tests
poetry run pytest --cov=helios --cov-report=term-missing              # with coverage
```

Coverage gate: `--cov-fail-under=90` is enforced by default `addopts` in `pyproject.toml`. Lowering it requires a deviation log entry.

### Lint / format

```bash
poetry run ruff check helios/ scripts/ tests/           # lint check
poetry run ruff check --fix helios/ scripts/ tests/     # auto-fix
poetry run ruff format helios/ scripts/ tests/          # apply formatting
poetry run mypy                                         # type check (strict=true)
```

### Tracking document validation

```bash
make validate-tracking   # schema check (R1–R8); exit 0 = clean
make test-tracking       # pytest suite for the validator itself
```

### Deviation log

```bash
set -a; source .env; set +a

# Append a signed entry
poetry run python bin/log_deviation.py \
  --stage "Stage N" \
  --clause "§..." \
  --change "..." \
  --reason "..." \
  --analytic-consequence "..."

# Verify the full chain
poetry run python bin/log_deviation.py verify
```

Run `poetry run pytest tests/test_deviation_log.py -v` after every new entry.

### Stage gate tagging

```bash
git tag stage-N-exit
git push origin stage-N-exit
```

---

## Architecture

```
L0  Observability Ingestion (multimodal)
L1  Anomaly Detection         — D-pipe (statistical)
L2  Causal Inference / RCL    — G-pipe (graph)
L3  Explanation & Feedback    — L-pipe (LLM) + P4 cognitive layer
L4  Auto-Remediation
```

**Ablation variants:** HELIOS-Full, HELIOS-noLLM, HELIOS-noGraph, HELIOS-noStats (and per-component variants for C1–C6).

**Metrics:** HR@3, CpR, hallucination rate, CoE narrative quality, MTTR reduction.

### Key runtime artefacts

| Artefact | Path | Notes |
|---|---|---|
| Deviation log | `deviation_log.jsonl` | HMAC-SHA256 chained; append via CLI only |
| Exclusion ledger | `exclusion_ledger.jsonl` | Metric-integrity failures; Stage 1+ |
| Tracking docs | `docs/tracking/*.md` | 18 living documents; schema enforced by pre-commit + CI |
| VCL manifest | `helios/vcl/` | Feature-flag registry — **implemented** (registry, config, decorators, variants) |

### VCL implementation (Stage 0)

`helios/vcl/` contains the Variant Control Layer — C1 of the dissertation's methodological contribution. Key modules and non-obvious decisions:

**Flag registry (`registry.py`)**
- **14 flags** (not 13): 12 proposal flags + `router` (bool) + `ingest_mode` (str).
- `VCLFlag.bool_flags()` returns the 13 boolean flags, excluding `INGEST_MODE`. Always use this when iterating flags for gating — never iterate `VCLFlag` directly.

**Manifest and hashing (`config.py`, `utils.py`)**
- `VCLManifest` is `frozen=True` + `extra="forbid"`. Hash is exhaustive — adding a field without updating the model breaks hash stability.
- `canonical_json()` pre-normalises floats with `round(o, 6)` **before** passing to `json.dumps`. This is required because `json.dumps` handles `float` natively and never calls the `default` hook for them; a `default`-only approach silently produces un-rounded output.
- `ingest_mode` is validated by `@field_validator` to `"recorded" | "live"` at every construction path (direct, `from_flags`, deserialization).

**Decorator (`decorators.py`)**
- `@gated_by(VCLFlag.X)` raises `TypeError` at **decoration time** (import time) if `X` is not a boolean flag. Do not attempt to gate on `INGEST_MODE`.
- `VCLManifest` is imported under `TYPE_CHECKING` only — with `from __future__ import annotations` all annotations are lazy strings, so this is correct and satisfies `TCH001`.
- Uses `ContextVar` for thread/async safety. Call `set_current_manifest()` before invoking any `@gated_by` component; missing manifest raises `RuntimeError`.

**Variants (`variants.py`)**
- `router` defaults to `True` in `VCLManifest`; only `HELIOS-noRouter` sets it `False`. All other 7 confirmatory variants inherit `router=True` implicitly — do not set it explicitly in every variant.
- All 8 variant hashes are unique (enforced by `test_all_variant_hashes_are_unique`). If you add a variant that duplicates an existing hash, a test will fail.

**Hook and lint**
- `flag-guard.py` exempts `helios/vcl/` from the "component without flag" check — VCL is the flag system itself. Consumers of VCL (files outside `helios/vcl/`) are recognised as flag-compliant if they import `VCLFlag`, `gated_by`, or `VCLManifest`.
- `[tool.ruff.lint]` has `preview = true` so `RUF022` (`__all__` sort) fires locally as it does in CI. ruff is pinned to `>=0.6.9,<0.7` in both `pyproject.toml` and `ci.yml` — widen only after reformatting the codebase with the new version.

### Key documents to read before multi-pipeline changes

- `docs/tracking/ablation_architecture.md` — architectural decision record
- `docs/tracking/hypothesis_variant_metric_mapping.md` — RQ → hypothesis → variant → metric
- `docs/tracking/vcl_manifest_tracking.md` — variant config hash registry
- `docs/tracking/helios_mvp_tracking.md` — daily task tracker (schema enforced)

### Pre-commit hooks (run on every `git commit`)

| Hook | What it checks |
|---|---|
| `gitleaks` | Secret scanning — blocks commits containing credentials |
| `ruff` + `ruff-format` | Lint (auto-fix) + format |
| `validate-tracking` | Tracking schema R1–R8; only fires when `helios_mvp_tracking.md` or `validate_tracking.py` changes |

### Claude Code hooks (`.claude/hooks/`)

| Hook | When it fires | What it blocks |
|---|---|---|
| `flag-guard.py` | Before Write/Edit/Bash | New `def`/`class`/pipeline without a `HELIOS_ENABLE_*` feature flag; non-reproducible shell commands (`python -c`, `random.`, `time.sleep`) |
| `research-compliance.py` | Before tool calls | Research-integrity violations |

### CI workflows

| Workflow | What it checks |
|---|---|
| `ci.yml` | ruff, mypy, pytest |
| `disjointness_audit.yml` | Feature-flag disjointness — Stage 5 stub; exits 0 on `ImportError` until `helios/vcl/disjointness.py` is implemented |
| `ledger_verification.yml` | HMAC chain integrity; requires `DEVIATION_HMAC_SECRET` in repo Secrets |

### Tracking schema rules (R1–R8)

Enforced by `scripts/validate_tracking.py` as a pre-commit hook and in CI:

- **R1** DONE rows must have Started, Done, SHA, Ev_Type, Ev_Ref populated.
- **R2** DEFERRED/CARRIED_OVER rows must have Deviation_Ref.
- **R3** Status must be one of: PLANNED, IN_PROGRESS, BLOCKED, DONE, DEFERRED, CARRIED_OVER.
- **R4** Transitions must follow the state machine (DONE and DEFERRED are terminal).
- **R5** Immutable columns must not change after a row is committed.
- **R6** Task_ID format: `S0-D{1-5}-{ENG|RES|EVAL|GATE}{nn}`.
- **R7** Day must be 1–5.
- **R8** Type must be ENG, RES, EVAL, or GATE.

---

## Development rules

- Default model: **Sonnet 4.6**. Use Opus only for cross-pipeline reasoning.
- Plan mode (`Shift+Tab`) required for cross-pipeline changes.
- `bin/log_deviation.py` requires `DEVIATION_HMAC_SECRET` loaded from `.env` (`set -a; source .env; set +a`).
- The `.env` file is gitignored — back it up in a password manager; losing it breaks chain verification.
- `DEVIATION_HMAC_SECRET` must also be set in GitHub Secrets for `ledger_verification.yml` to run the on-disk chain check.
