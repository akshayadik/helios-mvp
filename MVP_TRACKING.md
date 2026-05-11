# HELIOS MVP — Operational Reference

Frequently used commands for development, CI, validation, testing, and ablation-driven delivery. All commands assume you are at the repo root with the Poetry virtualenv active.

---

## Quickstart after clone

```bash
poetry env use python3.11
poetry install
cp .env.example .env          # fill in DEVIATION_HMAC_SECRET (≥32 chars)
make install-hooks            # install pre-commit hooks (once per clone)
set -a; source .env; set +a
poetry run python bin/log_deviation.py verify   # confirm chain is intact
```

---

## Pre-push gate

Run this before every PR. Mirrors the CI job sequence exactly.

```bash
set -a; source .env; set +a && \
  poetry run ruff check helios/ scripts/ tests/ && \
  poetry run ruff format --check helios/ scripts/ tests/ && \
  poetry run mypy && \
  poetry run pytest && \
  poetry run python bin/log_deviation.py verify && \
  make validate-tracking
```

Each step individually:

| Step | Command |
|---|---|
| Lint | `poetry run ruff check helios/ scripts/ tests/` |
| Format check | `poetry run ruff format --check helios/ scripts/ tests/` |
| Type check | `poetry run mypy` |
| Tests | `poetry run pytest` |
| HMAC chain | `poetry run python bin/log_deviation.py verify` |
| Tracking schema | `make validate-tracking` |

---

## Testing

```bash
# All tests
poetry run pytest

# Verbose output
poetry run pytest -v

# Single test file
poetry run pytest tests/test_deviation_log.py -v
poetry run pytest tests/test_validate_tracking.py -v

# Single test by name
poetry run pytest tests/test_deviation_log.py::test_verify_chain_fails_on_tampered_log -v

# HMAC canary suite (run after every deviation log entry)
poetry run pytest tests/test_deviation_log.py -v

# Tracking validator suite
make test-tracking
```

---

## Coverage

```bash
# Terminal report with uncovered lines
poetry run pytest --cov=helios --cov-report=term-missing

# HTML report (open htmlcov/index.html)
poetry run pytest --cov=helios --cov-report=html

# Enforce CI threshold (90%)
poetry run pytest --cov=helios --cov-fail-under=90
```

`.coverage` and `htmlcov/` are gitignored.

---

## Lint and format

```bash
# Lint check (no changes written)
poetry run ruff check helios/ scripts/ tests/

# Auto-fix safe violations
poetry run ruff check --fix helios/ scripts/ tests/

# Format check (no changes written)
poetry run ruff format --check helios/ scripts/ tests/

# Apply formatting
poetry run ruff format helios/ scripts/ tests/
```

---

## Type checking

```bash
poetry run mypy
```

Targets are declared in `[tool.mypy] files` in `pyproject.toml` (`helios`, `bin`, `tests`).

---

## Tracking document validation

`docs/tracking/helios_mvp_tracking.md` is governed by an 8-rule schema contract. The pre-commit hook runs automatically on commit; CI re-runs it to catch `--no-verify` bypasses.

```bash
make validate-tracking   # validate now (exit 0 = clean, 1 = violations)
make test-tracking       # run the full pytest suite against the validator
make install-hooks       # (re-)install pre-commit hooks
```

Violations print with rule codes (R1–R8). Fix flagged rows and re-stage before committing.

---

## Deviation log

Log any protocol change with analytic consequence **before merging**:

```bash
set -a; source .env; set +a

poetry run python bin/log_deviation.py \
  --stage "Stage N" \
  --clause "§..." \
  --change "..." \
  --reason "..." \
  --analytic-consequence "..."

# Then immediately verify and run the canary
poetry run python bin/log_deviation.py verify
poetry run pytest tests/test_deviation_log.py -v
```

Do not edit `deviation_log.jsonl` by hand — the HMAC chain will break.

---

## CI workflows (GitHub Actions)

| Workflow | Trigger | What it checks |
|---|---|---|
| `ci.yml` | push to main/develop, PR | lint, format, type check, tests |
| `ledger_verification.yml` | push to main, PR | HMAC canary tests + on-disk `verify` |
| `disjointness_audit.yml` | PR | VCL disjointness (stub until Stage 5) |

The `ledger_verification.yml` chain check requires `DEVIATION_HMAC_SECRET` in repo Secrets → Actions. If unset, that step skips with a warning (does not block the workflow).

---

## Ablation-driven development checklist

Before closing a stage or merging a research-impacting change:

- [ ] All CI checks green (see pre-push gate above)
- [ ] `deviation_log.jsonl` chain verified (`...verify`)
- [ ] Tracking document updated and schema clean (`make validate-tracking`)
- [ ] `docs/tracking/ablation_architecture.md` updated if variant matrix changed
- [ ] `docs/tracking/hypothesis_variant_metric_mapping.md` consistent with implementation
- [ ] `docs/tracking/vcl_manifest_tracking.md` updated if VCL config changed
- [ ] `docs/tracking/snapshot_hash_registry.md` updated if new incidents processed
- [ ] Weekly status entry filed in `docs/tracking/helios_mvp_tracking.md`
- [ ] Stage gate tag pushed: `git tag stage-N-exit && git push origin stage-N-exit`

---

## Dependency management

```bash
# Add a runtime dependency
poetry add <package>

# Add a dev-only dependency
poetry add --group dev <package>

# Verify Tier 1 lock targets (pydantic 2.x)
poetry show pydantic

# Regenerate lock after pyproject.toml changes
poetry lock --no-update   # preserve existing versions
poetry install
```

If any Tier 1 lock diverges from the expected version, write a deviation log entry before proceeding.

---

## Day 1 Drop in

```
# Replace your current files with these, then from the repo root:

# 1. Regenerate poetry.lock with the new dependency set.
poetry install --with dev

# 2. Verify the three Tier 1 locks match targets:
poetry show pydantic pyarrow duckdb
# Expected: pydantic 2.9.2 | pyarrow 18.1.0 | duckdb 1.1.3
# If any differ → write a deviation-log entry before proceeding.

# 3. Re-install the pre-commit hook (needed once after pyproject.toml changes).
poetry run pre-commit install

# 4. Run the full local CI stack.
poetry run ruff check helios/ scripts/ tests/
poetry run ruff format --check helios/ scripts/ tests/
poetry run black --check helios/ scripts/ tests/
poetry run mypy helios/ scripts/
poetry run pytest

# 5. Commit both files together with poetry.lock.
git add pyproject.toml poetry.lock .github/workflows/ci.yml
git commit -m "chore: merge pyproject.toml and ci.yml to HELIOS spec (S0-D1-ENG07)"
```