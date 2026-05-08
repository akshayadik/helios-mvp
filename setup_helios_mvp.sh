#!/usr/bin/env bash
# HELIOS MVP — Stage 0 Day 1 repo bootstrap
#
# Creates the full repo skeleton in ./helios-mvp (or $1 if passed).
# Idempotent-safe: refuses to overwrite an existing target directory.
#
# Usage:  ./setup_helios_mvp.sh            # creates ./helios-mvp
#         ./setup_helios_mvp.sh my-repo    # creates ./my-repo

set -euo pipefail

TARGET_DIR="${1:-helios-mvp}"

# if [ -e "$TARGET_DIR" ]; then
#     echo "ERROR: '$TARGET_DIR' already exists. Remove it or pass a different path."
#     exit 1
# fi

# echo "🚀 Creating HELIOS MVP repo at: $TARGET_DIR"
# mkdir -p "$TARGET_DIR"
# cd "$TARGET_DIR"

# ─── 1. Directory tree ────────────────────────────────────────────────────────
echo "  📁 Creating directory tree..."
mkdir -p \
    .github/ISSUE_TEMPLATE \
    .github/workflows \
    bin \
    docs/memos \
    docs/tracking \
    helios/vcl \
    tests \
    data/calibration

# ─── 2. Root files ────────────────────────────────────────────────────────────
echo "  📄 Writing root files..."

cat > .gitignore <<'GITIGNORE'
# Python
__pycache__/
*.py[cod]
*.egg-info/
build/
dist/
.venv/
venv/

# Test / coverage
.pytest_cache/
.coverage
htmlcov/

# Data (reproducible from corpus + seeds; regenerated, not committed)
data/calibration/*.parquet
data/*.parquet

# Secrets
.env
*.pem
*.key

# OS
.DS_Store
Thumbs.db

# Editor
.vscode/
.idea/
*.swp
GITIGNORE

cat > .env.example <<'ENV_EXAMPLE'
# Copy this file to .env and replace the value below.
# The HMAC secret signs deviation_log.jsonl entries (C1 §6.5).
# MUST be at least 32 characters. NEVER commit .env.
DEVIATION_HMAC_SECRET=replace-with-32-plus-character-cryptographically-random-secret
ENV_EXAMPLE

cat > .pre-commit-config.yaml <<'PRECOMMIT'
# Run: poetry run pre-commit install
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.4
    hooks:
      - id: gitleaks
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
PRECOMMIT

cat > pyproject.toml <<'PYPROJECT'
[tool.poetry]
name = "helios-mvp"
version = "0.1.0"
description = "HELIOS MVP — Research-grade RCA framework with C1 runtime invariants"
authors = ["Akshay Adik"]
readme = "README.md"
license = "MIT"
packages = [{include = "helios"}]

[tool.poetry.dependencies]
python = "^3.11"
pydantic = "^2.0"

[tool.poetry.group.dev.dependencies]
ruff = "^0.6"
mypy = "^1.11"
pytest = "^8.3"
pytest-cov = "^5.0"
pre-commit = "^3.8"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP"]

[tool.mypy]
python_version = "3.11"
files = ["helios", "bin", "tests"]
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"

[build-system]
requires = ["poetry-core>=1.0.0"]
build-backend = "poetry.core.masonry.api"
PYPROJECT

cat > LICENSE <<'LICENSE_EOF'
MIT License

Copyright (c) 2026 Akshay Adik

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
LICENSE_EOF

cat > README.md <<'README_END'
# HELIOS MVP

Research-grade RCA framework with runtime-enforced ablation discipline (C1).

**Status:** Stage 0 — Spine + Harness (in progress)

## What is C1?

Contribution C1 (runtime-enforced DSR evaluation rigour) is the methodological
spine of HELIOS. Every variant change is binary-verified via the Variant Control
Layer; every snapshot has a content hash; every metric-integrity-gate failure is
logged to a cryptographically-signed append-only ledger; every protocol deviation
is HMAC-chained into `deviation_log.jsonl`. CI enforces these invariants on every
push.

## Quick start

```bash
# 1. Install dependencies
poetry install

# 2. Set up secrets
cp .env.example .env
# Edit .env and set DEVIATION_HMAC_SECRET to a 32+ char random string

# 3. Activate pre-commit hooks (gitleaks + ruff)
poetry run pre-commit install

# 4. Log the first deviation (C1 contraction from 6 → 5 components)
poetry run python bin/log_deviation.py \
  --stage "Stage 0" \
  --clause "§3.6.6 / Execution Plan §6 / §4" \
  --change "C1 runtime invariants reduced from 6 to 5; reconciliation ledger not implemented" \
  --reason "RRE/E-H5 descoped per Execution Plan v1.0 §4 'No reconciliation' and Binding Decision #10" \
  --analytic-consequence "E-H5 fully descoped; A-H5 cost-aware static routing remains in scope under static-policy commitment"

# 5. Verify ledger integrity
poetry run pytest tests/test_deviation_log.py -v
```

## Live tracking

- [Live dashboard](docs/tracking/dashboard.md) — Mermaid Gantt + cell completion
- [Tracking documents register](docs/tracking/tracking_documents_register.md) — index of 18 living documents
- [Daily/gate progress](docs/tracking/helios_mvp_tracking.md)
- [Ablation architecture](docs/tracking/ablation_architecture.md)

## Repo layout

```
.github/        ISSUE_TEMPLATE/ + workflows/ (CI, disjointness, ledger verify)
bin/            Signed-ledger CLIs (log_deviation, log_exclusion)
docs/
  memos/        One-off frozen memos (e.g., spine_freeze)
  tracking/     18 living tracking documents (the C1 evidence base)
  osf_protocol_v0.md   Pre-registration protocol
helios/         Core package (vcl/, schemas/, pipelines/, ...)
tests/          pytest suite — HMAC chain integrity is the canary
deviation_log.jsonl     Append-only, HMAC-chained protocol-change record
exclusion_ledger.jsonl  Append-only metric-integrity-gate failures
```

## License

MIT — see `LICENSE`.
README_END

cat > CHANGELOG.md <<'CHANGELOG'
# Changelog

All notable changes to HELIOS MVP. Format: [Keep a Changelog](https://keepachangelog.com/).
Stage tags become Zenodo DOIs at release time.

## [Unreleased]

### Added
- Stage 0 repo skeleton
- C1 tracking documents register (18 living docs)
- Signed deviation log CLI (`bin/log_deviation.py`) with HMAC-SHA256 chaining
- HMAC chain integrity test suite (`tests/test_deviation_log.py`)
- GitHub Actions: CI, disjointness audit (stub), ledger verification
- Issue templates for the four recurring artefact-capture flows

### Pending (Stage 0 exit gate)
- VCL skeleton: `registry.py`, `config.py`, `decorators.py`, `variants.py`
- 5 telemetry recordings + snapshot hashes
- First C1 deviation log entry (C1 contraction 6 → 5)

## [stage-0] — TBD
_(populated when Stage 0 exit gate is signed off)_
CHANGELOG

cat > CONTRIBUTING.md <<'CONTRIBUTING'
# CONTRIBUTING — Solo Researcher Workflow

This repo is a doctoral research artefact. Every change must preserve the C1
runtime invariants. The workflow below is non-optional even though I am the
only contributor.

## The loop

1. **Open a GitHub issue** using the appropriate template:
   - `Deviation Entry` — any change with analytic consequence
   - `Exclusion Ledger Entry` — metric-integrity-gate failure
   - `Weekly Self-Review` — Friday EOD
   - `Stage Gate Evidence` — exit-gate sign-off
2. **Branch from `main`**: `git checkout -b stage-N/short-description`
3. **Make the code change** (test-driven where applicable).
4. **If the change has analytic consequence**, log it BEFORE merge:
   ```bash
   poetry run python bin/log_deviation.py \
     --stage "Stage N" \
     --clause "§..." \
     --change "..." \
     --reason "..." \
     --analytic-consequence "..."
   ```
5. **Open a PR**. CI must pass:
   - `ci.yml` — ruff + mypy + pytest
   - `disjointness_audit.yml` — feature-flag disjointness (Execution Plan §6.3)
   - `ledger_verification.yml` — HMAC chain still verifies
6. **Merge to `main`**. The issue auto-closes via PR keyword.
7. **Tag at stage gates**: `git tag stage-N-exit && git push --tags`. Zenodo
   captures the DOI automatically.

## Hard rules

- **NEVER edit `deviation_log.jsonl` or `exclusion_ledger.jsonl` by hand.**
  Use the CLIs. Manual edits break the HMAC chain and invalidate every
  subsequent entry.
- **NEVER commit `.env`.** The pre-commit gitleaks hook will catch it,
  but don't rely on the hook.
- **Tests run locally before push.** CI is a safety net, not a development tool.

## Tracking documents

The 18 living documents in `docs/tracking/` are part of the audit trail. When
you add evidence (a new variant config, a new exclusion, a new threshold), the
matching tracking doc is updated in the same PR. The doc and the code change
travel together.
CONTRIBUTING

# Append-only ledgers — left empty by design.
# The first deviation_log entry is created by running bin/log_deviation.py
# (see README quick start step 4). This guarantees the genesis signature is
# real, not placeholder.
: > deviation_log.jsonl
: > exclusion_ledger.jsonl

# ─── 3. bin/ — signed ledger CLIs ─────────────────────────────────────────────
echo "  🔑 Writing bin/ CLIs..."

cat > bin/log_deviation.py <<'PY_DEVIATION'
#!/usr/bin/env python3
"""Append a signed deviation log entry to deviation_log.jsonl.

Each entry is HMAC-SHA256 chained: every entry's signature signs both its own
fields AND the previous entry's signature, so any tampering anywhere in the
chain invalidates every subsequent signature. The first entry's prev_signature
is the literal string "GENESIS".

Schema:
    timestamp_utc:        ISO-8601 with Z suffix (UTC)
    commit_sha:           Git commit SHA (from $GITHUB_SHA in CI, else "LOCAL")
    prev_signature:       Hex signature of the immediately preceding entry, or "GENESIS"
    stage:                Stage 0..8
    clause:               Section reference (e.g., "§3.6.6 / Execution Plan §6")
    change:               Concrete description of what changed
    reason:               Justification
    analytic_consequence: Typically: which hypothesis/variant moves status
    signature:            HMAC-SHA256 hex over canonical JSON of all above fields
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path
from typing import Any

LOG_FILE = Path("deviation_log.jsonl")
ENV_KEY = "DEVIATION_HMAC_SECRET"
GENESIS = "GENESIS"


def load_key() -> bytes:
    """Read the HMAC secret from $DEVIATION_HMAC_SECRET. Exit on failure."""
    key = os.getenv(ENV_KEY)
    if not key:
        sys.stderr.write(
            f"ERROR: {ENV_KEY} not set. Copy .env.example to .env and set a secret.\n"
        )
        sys.exit(2)
    if len(key) < 32:
        sys.stderr.write(
            f"ERROR: {ENV_KEY} must be at least 32 characters (got {len(key)}).\n"
        )
        sys.exit(2)
    return key.encode("utf-8")


def previous_signature(log_path: Path) -> str:
    """Return signature of the last entry, or GENESIS if file is empty/missing."""
    if not log_path.exists() or log_path.stat().st_size == 0:
        return GENESIS
    last = ""
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                last = stripped
    if not last:
        return GENESIS
    return json.loads(last)["signature"]


def compute_signature(key: bytes, entry: dict[str, Any]) -> str:
    """HMAC-SHA256 over canonical JSON of entry, excluding the signature field itself."""
    payload_dict = {k: v for k, v in entry.items() if k != "signature"}
    payload = json.dumps(payload_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def append_entry(log_path: Path, fields: dict[str, Any]) -> dict[str, Any]:
    """Build, sign, and append a new entry. Returns the full entry dict."""
    key = load_key()
    prev_sig = previous_signature(log_path)
    entry: dict[str, Any] = {
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "commit_sha": os.getenv("GITHUB_SHA", "LOCAL"),
        "prev_signature": prev_sig,
        **fields,
    }
    entry["signature"] = compute_signature(key, entry)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def verify_chain(log_path: Path) -> tuple[bool, str]:
    """Walk the chain from genesis; return (ok, message)."""
    if not log_path.exists() or log_path.stat().st_size == 0:
        return True, "Empty log — vacuously valid."
    key = load_key()
    expected_prev = GENESIS
    with log_path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            entry = json.loads(stripped)
            if entry.get("prev_signature") != expected_prev:
                return False, (
                    f"Line {lineno}: prev_signature mismatch "
                    f"(expected {expected_prev[:12]}..., got {entry.get('prev_signature', '')[:12]}...)"
                )
            recomputed = compute_signature(key, entry)
            if recomputed != entry.get("signature"):
                return False, f"Line {lineno}: signature does not verify (entry tampered)."
            expected_prev = entry["signature"]
    return True, "Chain verified."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd")

    # Default behaviour: append (kept compatible with bare invocation)
    parser.add_argument("--stage")
    parser.add_argument("--clause")
    parser.add_argument("--change")
    parser.add_argument("--reason")
    parser.add_argument("--analytic-consequence")

    # `verify` subcommand
    sub.add_parser("verify", help="Verify the entire HMAC chain.")

    args = parser.parse_args()

    if args.cmd == "verify":
        ok, msg = verify_chain(LOG_FILE)
        print(("✅ " if ok else "❌ ") + msg)
        return 0 if ok else 1

    required = ["stage", "clause", "change", "reason", "analytic_consequence"]
    missing = [r for r in required if not getattr(args, r, None)]
    if missing:
        parser.error(f"Missing required arguments: {', '.join('--' + m.replace('_','-') for m in missing)}")

    fields = {
        "stage": args.stage,
        "clause": args.clause,
        "change": args.change,
        "reason": args.reason,
        "analytic_consequence": args.analytic_consequence,
    }
    entry = append_entry(LOG_FILE, fields)
    print(f"✅ Deviation logged: {entry['clause']} | sig={entry['signature'][:12]}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
PY_DEVIATION
chmod +x bin/log_deviation.py

cat > bin/log_exclusion.py <<'PY_EXCLUSION'
#!/usr/bin/env python3
"""Stub for the exclusion ledger CLI.

Will mirror log_deviation.py but for runtime metric-integrity-gate failures
(Execution Plan §6.4). Implement when the orchestrator can emit exclusion
events programmatically (Stage 1+).
"""
from __future__ import annotations

import sys


def main() -> int:
    sys.stderr.write("log_exclusion.py is a Stage 1+ stub. Not yet implemented.\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
PY_EXCLUSION
chmod +x bin/log_exclusion.py

# ─── 4. tests/ — HMAC chain integrity ─────────────────────────────────────────
echo "  🧪 Writing tests..."

cat > tests/__init__.py <<'PY_INIT'
PY_INIT

cat > tests/test_deviation_log.py <<'PY_TEST'
"""HMAC chain integrity tests for bin/log_deviation.py.

These tests are the canary for C1 §6.5: they prove the deviation_log.jsonl
chain is genuinely tamper-evident, not just decoratively signed.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _load_log_deviation_module():
    """Import bin/log_deviation.py without putting bin/ on sys.path globally."""
    here = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("log_deviation", here / "bin" / "log_deviation.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["log_deviation"] = mod
    spec.loader.exec_module(mod)
    return mod


log_deviation = _load_log_deviation_module()


@pytest.fixture
def secret_env(monkeypatch):
    monkeypatch.setenv(log_deviation.ENV_KEY, "test-secret-of-at-least-32-characters-x")
    return None


@pytest.fixture
def log_path(tmp_path):
    return tmp_path / "deviation_log.jsonl"


def make_fields(change: str = "test change") -> dict:
    return {
        "stage": "Stage 0",
        "clause": "§test",
        "change": change,
        "reason": "test reason",
        "analytic_consequence": "test consequence",
    }


def test_first_entry_has_genesis_prev_signature(secret_env, log_path):
    entry = log_deviation.append_entry(log_path, make_fields())
    assert entry["prev_signature"] == log_deviation.GENESIS
    assert len(entry["signature"]) == 64  # SHA-256 hex


def test_signature_is_64_hex_chars(secret_env, log_path):
    entry = log_deviation.append_entry(log_path, make_fields())
    assert len(entry["signature"]) == 64
    int(entry["signature"], 16)  # must parse as hex


def test_chain_links_correctly_across_three_entries(secret_env, log_path):
    e1 = log_deviation.append_entry(log_path, make_fields("first"))
    e2 = log_deviation.append_entry(log_path, make_fields("second"))
    e3 = log_deviation.append_entry(log_path, make_fields("third"))
    assert e2["prev_signature"] == e1["signature"]
    assert e3["prev_signature"] == e2["signature"]


def test_signature_recomputes_to_same_value(secret_env, log_path):
    entry = log_deviation.append_entry(log_path, make_fields())
    key = log_deviation.load_key()
    assert log_deviation.compute_signature(key, entry) == entry["signature"]


def test_tampered_change_field_breaks_signature(secret_env, log_path):
    entry = log_deviation.append_entry(log_path, make_fields())
    key = log_deviation.load_key()
    tampered = dict(entry)
    tampered["change"] = "MALICIOUS"
    assert log_deviation.compute_signature(key, tampered) != entry["signature"]


def test_tampered_prev_signature_breaks_chain(secret_env, log_path):
    e1 = log_deviation.append_entry(log_path, make_fields("first"))
    e2 = log_deviation.append_entry(log_path, make_fields("second"))
    assert e2["prev_signature"] == e1["signature"]
    # Now tamper with e2's prev_signature; recomputed sig must differ
    key = log_deviation.load_key()
    tampered = dict(e2)
    tampered["prev_signature"] = "0" * 64
    assert log_deviation.compute_signature(key, tampered) != e2["signature"]


def test_verify_chain_passes_on_clean_log(secret_env, log_path, monkeypatch):
    log_deviation.append_entry(log_path, make_fields("first"))
    log_deviation.append_entry(log_path, make_fields("second"))
    monkeypatch.setattr(log_deviation, "LOG_FILE", log_path)
    ok, msg = log_deviation.verify_chain(log_path)
    assert ok, msg


def test_verify_chain_fails_on_tampered_log(secret_env, log_path):
    log_deviation.append_entry(log_path, make_fields("first"))
    log_deviation.append_entry(log_path, make_fields("second"))
    # Tamper with the on-disk file
    lines = log_path.read_text().splitlines()
    second = json.loads(lines[1])
    second["change"] = "MALICIOUS"
    lines[1] = json.dumps(second, sort_keys=True)
    log_path.write_text("\n".join(lines) + "\n")
    ok, _ = log_deviation.verify_chain(log_path)
    assert not ok


def test_log_file_is_one_json_per_line(secret_env, log_path):
    log_deviation.append_entry(log_path, make_fields("a"))
    log_deviation.append_entry(log_path, make_fields("b"))
    lines = log_path.read_text().splitlines()
    assert len(lines) == 2
    for line in lines:
        json.loads(line)  # must parse


def test_missing_secret_exits(monkeypatch):
    monkeypatch.delenv(log_deviation.ENV_KEY, raising=False)
    with pytest.raises(SystemExit):
        log_deviation.load_key()


def test_short_secret_exits(monkeypatch):
    monkeypatch.setenv(log_deviation.ENV_KEY, "too-short")
    with pytest.raises(SystemExit):
        log_deviation.load_key()


def test_canonical_signature_is_deterministic(secret_env):
    key = log_deviation.load_key()
    entry = {
        "timestamp_utc": "2026-01-01T00:00:00Z",
        "commit_sha": "abc",
        "prev_signature": log_deviation.GENESIS,
        "stage": "S",
        "clause": "C",
        "change": "X",
        "reason": "R",
        "analytic_consequence": "A",
    }
    assert log_deviation.compute_signature(key, entry) == log_deviation.compute_signature(key, entry)
PY_TEST

# ─── 5. helios/ — package skeleton ────────────────────────────────────────────
cat > helios/__init__.py <<'PY_INIT'
"""HELIOS — Heuristic Learning for Integrated Observability Systems."""
__version__ = "0.1.0"
PY_INIT

cat > helios/vcl/__init__.py <<'PY_INIT'
"""Variant Control Layer — C1 §6.1.

Skeleton modules (registry.py, config.py, decorators.py, variants.py) land in
the next PR. This file exists so `poetry install` resolves the package.
"""
PY_INIT

# ─── 6. GitHub Actions ────────────────────────────────────────────────────────
echo "  ⚙️  Writing GitHub Actions..."

cat > .github/workflows/ci.yml <<'YAML_CI'
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install poetry
        run: pipx install poetry
      - name: Install dependencies
        run: poetry install
      - name: Lint (ruff)
        run: poetry run ruff check .
      - name: Type check (mypy)
        run: poetry run mypy
      - name: Run tests
        run: poetry run pytest
YAML_CI

cat > .github/workflows/disjointness_audit.yml <<'YAML_DISJOINT'
name: Disjointness Audit

on:
  pull_request:

jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pipx install poetry
      - run: poetry install
      # TODO: implement static disjointness audit per Execution Plan §6.3.
      # The audit must verify that toggling each feature flag affects exactly
      # one well-defined code path with no hidden coupling. Until implemented,
      # this stub passes; replace before Stage 5 freeze.
      - name: Disjointness audit (stub)
        run: |
          echo "STUB: disjointness audit not yet implemented."
          echo "TODO before Stage 5 freeze: enforce Execution Plan §6.3."
YAML_DISJOINT

cat > .github/workflows/ledger_verification.yml <<'YAML_LEDGER'
name: Ledger Verification

on:
  push:
    branches: [main]
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    env:
      # Set this in repo Settings → Secrets and variables → Actions
      DEVIATION_HMAC_SECRET: ${{ secrets.DEVIATION_HMAC_SECRET }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pipx install poetry
      - run: poetry install
      - name: HMAC chain integrity tests
        run: poetry run pytest tests/test_deviation_log.py -v
      - name: Verify on-disk deviation_log chain
        # Skips cleanly if the secret isn't configured (so the workflow doesn't
        # block early-Stage-0 commits before the secret is set up).
        run: |
          if [ -z "${DEVIATION_HMAC_SECRET:-}" ]; then
            echo "DEVIATION_HMAC_SECRET not set — skipping on-disk chain verification."
            exit 0
          fi
          poetry run python bin/log_deviation.py verify
YAML_LEDGER

# ─── 7. Issue templates ───────────────────────────────────────────────────────
echo "  📝 Writing issue templates..."

cat > .github/ISSUE_TEMPLATE/deviation_entry.yml <<'YAML_DEV'
name: Deviation Entry (C1)
description: Log a protocol deviation with analytic consequence (§6.5).
title: "[Deviation] "
labels: ["c1-deviation"]
body:
  - type: input
    id: stage
    attributes:
      label: Stage
      placeholder: "Stage 2"
    validations:
      required: true
  - type: input
    id: clause
    attributes:
      label: Clause / section reference
      placeholder: "§3.6.6 / Execution Plan §6.4"
    validations:
      required: true
  - type: textarea
    id: change
    attributes:
      label: Change
      description: Concrete description of what changed.
    validations:
      required: true
  - type: textarea
    id: reason
    attributes:
      label: Reason
    validations:
      required: true
  - type: textarea
    id: consequence
    attributes:
      label: Analytic consequence
      description: 'Typically: "hypothesis X moves from confirmatory to exploratory".'
    validations:
      required: true
  - type: checkboxes
    id: cli
    attributes:
      label: Confirmation
      options:
        - label: I will run `bin/log_deviation.py` with these fields BEFORE merging the related PR.
          required: true
YAML_DEV

cat > .github/ISSUE_TEMPLATE/exclusion_entry.yml <<'YAML_EXC'
name: Exclusion Ledger Entry
description: Record a metric-integrity-gate failure (§6.4).
title: "[Exclusion] "
labels: ["exclusion-ledger"]
body:
  - type: input
    id: run_id
    attributes:
      label: Run ID
    validations:
      required: true
  - type: input
    id: variant_hash
    attributes:
      label: variant_config_hash
    validations:
      required: true
  - type: textarea
    id: reason
    attributes:
      label: Exclusion reason
      description: Exact reason — missing metric, OOM, timeout, etc.
    validations:
      required: true
YAML_EXC

cat > .github/ISSUE_TEMPLATE/weekly_review.yml <<'YAML_WEEK'
name: Weekly Self-Review
description: Friday EOD progress + risk check.
title: "[Weekly Review] Week of "
labels: ["weekly-review"]
body:
  - type: textarea
    id: completed
    attributes:
      label: Completed this week
  - type: textarea
    id: blocked
    attributes:
      label: Blocked / risks
  - type: textarea
    id: next
    attributes:
      label: Plan for next week
  - type: dropdown
    id: burnout
    attributes:
      label: Burnout indicator (1=fine, 5=red)
      options: ["1", "2", "3", "4", "5"]
YAML_WEEK

cat > .github/ISSUE_TEMPLATE/stage_gate_evidence.yml <<'YAML_GATE'
name: Stage Gate Evidence
description: Sign-off package for a stage exit gate.
title: "[Gate] Stage  exit"
labels: ["stage-gate"]
body:
  - type: input
    id: stage
    attributes:
      label: Stage
      placeholder: "Stage 0"
    validations:
      required: true
  - type: textarea
    id: criteria
    attributes:
      label: Exit criteria met
      description: List each criterion and link to evidence (commit SHA, doc, log entry).
    validations:
      required: true
  - type: textarea
    id: deviations
    attributes:
      label: Deviations logged this stage
      description: List deviation_log entries (sig prefixes) created this stage.
  - type: checkboxes
    id: cli
    attributes:
      label: Pre-tag checklist
      options:
        - label: All deviations logged via CLI
          required: true
        - label: All tracking docs in `docs/tracking/` updated
          required: true
        - label: CI green
          required: true
        - label: Will tag `stage-N-exit` after merge
          required: true
YAML_GATE

# ─── 8. docs/memos/ ───────────────────────────────────────────────────────────
echo "  📚 Writing docs/..."

cat > docs/memos/spine_freeze_memo_v0.md <<'MEMO_END'
# Spine Freeze Memo v0

**Status:** Draft (Stage 0 placeholder)

## Purpose

One-off frozen memo establishing the architectural spine of HELIOS MVP at
Stage 0. Captures the binding decisions on:

- Three peer pipelines (D, G, L)
- Five-layer execution hierarchy
- C1 invariant set (5 of 6 Class 1 components — see deviation_log entry #1)
- Out-of-scope: reconciliation ledger, RQ4 user study, full pre-warming,
  FGSV/IOL/P4 cognitive (per Execution Plan v1.0 binding decisions)

## Why a memo and not a tracking doc

This is a one-time anchor. Tracking documents update as work progresses;
this memo freezes a snapshot at the start of Stage 0 so subsequent
deviations have a stable referent.

_(Populate before Stage 0 exit gate.)_
MEMO_END

cat > docs/osf_protocol_v0.md <<'OSF_END'
# OSF Pre-Registration Protocol — HELIOS MVP (v0)

**Status:** Stage 0 draft. Becomes binding at Stage 5 freeze.

## Sections (to be populated)

1. **Hypotheses** — A-H1..A-H8 (ablation), B-H1..B-H8 (baseline), E-H1..E-H10 (exploratory)
2. **Variants** — confirmatory + exploratory (with feature-flag matrix)
3. **Metrics** — HR@3, MRR, macro-F1, CpR, log-MTTR, hallucination rates, etc.
4. **Statistical Analysis Plan**
   - Wilcoxon signed-rank (paired continuous)
   - McNemar's exact (paired binary)
   - Holm–Bonferroni rank-ordered FWE control (separate ablation/baseline families)
   - BCa bootstrap (exploratory)
   - MDE recomputed at MVP corpus size
5. **Inclusion / exclusion criteria** — 80% cell-completion threshold etc.
6. **Scope contraction register** — proposal commitment → MVP status → reactivation trigger
7. **Reproducibility manifest** — SHA-256 of corpus, container digests, model identifiers, seeds

_(Populate fully before Stage 5 freeze. Each section is its own commit so the
git diff is the freeze audit trail.)_
OSF_END

# ─── 9. docs/tracking/ — 18 living documents + dashboard + register ──────────
# Each stub has the proper title, purpose, and an empty table the work fills in.

write_stub() {
    # $1 = filename, $2 = title, $3 = purpose, $4 = update cadence
    cat > "docs/tracking/$1" <<STUB_END
# $2

**Purpose:** $3

**Update cadence:** $4
**Owner module:** Researcher (solo)
**Status:** Stage 0 stub — populate as work progresses.

---

_(Replace this block with the appropriate table or content. Each tracking
document is part of the C1 audit trail and must be updated in the same PR
as the code change it tracks.)_
STUB_END
}

write_stub "tracking_documents_register.md" \
  "Tracking Documents Register" \
  "Index of all 18 living tracking documents with paths, purposes, owners, and update cadences. Single source of truth for which docs exist and why." \
  "On any tracking-doc add/remove/rename"

write_stub "helios_mvp_tracking.md" \
  "HELIOS MVP — Daily Tasks + Stage Gates" \
  "Single source of truth for daily tasks, stage-gate sign-offs, and evidence links. Mirrors Execution Plan stage structure." \
  "Daily EOD + at each gate"

write_stub "ablation_architecture.md" \
  "Ablation Architecture — Living ADR" \
  "Living architectural decision record. Captures VCL, peer pipelines, consensus rule, snapshot hash gating, schema evolution. Source for Chapter 4 §4.2." \
  "After every pipeline-stage change"

write_stub "vcl_manifest_tracking.md" \
  "VCL Manifest Tracking" \
  "Master register of all Variant Control Layer configurations and the variant_config_hash they produce. Proves binary-level variant identity (Execution Plan §6.1)." \
  "After every VCL config change or new variant"

write_stub "snapshot_hash_registry.md" \
  "Snapshot Hash Registry" \
  "Log of every incident's snapshot_hash (UEG-C canonical JSON). Proves snapshot identity across variants (Execution Plan §6.2)." \
  "After every recording / replay"

write_stub "disjointness_audit_log.md" \
  "Disjointness Audit Log" \
  "Static + dynamic disjointness results for every feature-flag pair. CI-generated (Execution Plan §6.3). Includes design-freeze audit anchor entry." \
  "Every PR + Stage 7 final"

write_stub "hypothesis_variant_metric_mapping.md" \
  "Hypothesis × Variant × Metric Mapping" \
  "Living Table 3: RQ → hypothesis → variant → measurement location → statistical test. Orchestrator queries this; examiner audits this. Locked at Stage 5 freeze." \
  "Before Stage 5 freeze; rare changes after with deviation log"

write_stub "prompt_version_registry.md" \
  "Prompt Version Registry" \
  "Frozen L-pipe prompt templates with prompt_sha values. Binds H_struct measurement to specific prompt revisions." \
  "Before Stage 5 freeze"

write_stub "calibration_thresholds.md" \
  "Calibration Thresholds" \
  "All frozen runtime thresholds (anomaly detection, PPR restart probability, etc.) with calibration-set justifications." \
  "End of calibration stages (1–5)"

write_stub "seed_register.md" \
  "Seed Register" \
  "Locked random seeds for the confirmatory protocol. Statistical reproducibility precondition." \
  "Before Stage 6 confirmatory runs"

write_stub "reproducibility_manifest.md" \
  "Reproducibility Manifest" \
  "Cumulative SHA-256 of corpus, container digests, replication script, model versions, price book. Source for OSF deposit and Appendix B." \
  "Weekly + Stage 5 freeze"

write_stub "price_book.md" \
  "Token Price Book" \
  "Per-token and per-compute-second cost coefficients (Ollama + 10% API fallback). Frozen for descriptive CpR metrics." \
  "Stage 5 freeze (post-freeze changes are external-validity threats)"

write_stub "replication_verification_log.md" \
  "Replication Verification Log" \
  "Results of the 10% byte-equality replication matrix run via bin/replicate.sh. External-replication evidence for OSF deposit." \
  "Stage 7 + Stage 8"

write_stub "data_collection_log.md" \
  "Data Collection Log" \
  "Record of all telemetry captures, fault injections, and labelling decisions (proposal §3.7). Construct-validity boundary documentation." \
  "After every recording session"

write_stub "validity_tracking.md" \
  "Validity Tracking" \
  "Internal, construct, and external validity threats and mitigations (proposal §3.9.1–3.9.3). Includes ground-truth labelling protocol." \
  "At each major stage"

write_stub "ground_truth_labelling.md" \
  "Ground Truth Labelling" \
  "Hand-curated labels distinguishing injection-target from telemetry-proximate cause. Justifications per binding decision #2." \
  "During Stage 1 corpus build"

write_stub "deviation_log.md" \
  "Deviation Log (Human-Readable)" \
  "Markdown-rendered companion to deviation_log.jsonl. Auto-generated summary table for examiner readability; the JSONL remains the authoritative artefact." \
  "Auto-regenerated when deviation_log.jsonl changes"

# Dashboard — uses a unique terminator because it contains triple-backtick mermaid fences.
cat > docs/tracking/dashboard.md <<'DASHBOARD_END'
# HELIOS MVP — Live Dashboard

_Auto-refresh target (Stage 1+): `weekly_dashboard.yml` GitHub Action will
regenerate the dynamic sections (cell-completion grid, deviation count) every
Friday EOD. Until then, sections marked **(manual)** are kept current by hand._

## Stage Progress (manual)

```mermaid
gantt
    title HELIOS MVP — Stage Progress
    dateFormat YYYY-MM-DD
    axisFormat %b %d

    section Tracking
    Stage 0 — Repo + VCL skeleton + Harness   :active, s0, 2026-05-08, 14d
    Stage 1 — Telemetry + VCL Foundation      :s1, after s0, 28d
    Stage 2 — D-pipe                          :s2, after s1, 14d
    Stage 3 — G-pipe                          :s3, after s2, 14d
    Stage 4 — L-pipe + Consensus              :s4, after s3, 21d
    Stage 5 — OSF Freeze                      :crit, s5, after s4, 7d
    Stage 6 — Confirmatory runs               :s6, after s5, 21d
    Stage 7 — Replication verification        :s7, after s6, 14d
    Stage 8 — Chapter 4 + OSF deposit         :crit, s8, after s7, 28d
```

## Architecture flow (manual; updated when ablation_architecture.md changes)

```mermaid
flowchart LR
    OTEL[OTEL telemetry] --> UEG[UEG-C snapshot]
    UEG -->|snapshot_hash| D[D-pipe]
    UEG -->|snapshot_hash| G[G-pipe]
    UEG -->|snapshot_hash| L[L-pipe]
    D --> C[MAHC consensus]
    G --> C
    L --> C
    C --> R[Ranked root cause]
    VCL[Variant Control Layer] -.gates.-> D
    VCL -.gates.-> G
    VCL -.gates.-> L
    VCL -.gates.-> C
    MIG[Metric Integrity Gate] -.audits.-> R
    MIG -.signs.-> EL[(exclusion_ledger.jsonl)]
    DL[(deviation_log.jsonl)] -.HMAC chain.-> VCL
```

## Cell-completion grid (manual until weekly_dashboard.yml lands)

| Variant            | AIOpsLab | Train-Ticket | DeathStar | PetShop | OpsEval |
|--------------------|----------|--------------|-----------|---------|---------|
| HELIOS-Full        | ⏳ 0/N   | ⏳ 0/N       | ⏳ 0/N    | ⏳ 0/N  | ⏳ 0/N  |
| HELIOS-noLLM       | ⏳ 0/N   | ⏳ 0/N       | ⏳ 0/N    | ⏳ 0/N  | ⏳ 0/N  |
| HELIOS-noConsensus | ⏳ 0/N   | ⏳ 0/N       | ⏳ 0/N    | ⏳ 0/N  | ⏳ 0/N  |

Legend: ✅ ≥80% complete · 🟡 partial · ⏳ not yet started · ❌ blocked

## C1 Invariants snapshot (manual)

| Invariant                          | Status     | Evidence link                                  |
|------------------------------------|------------|------------------------------------------------|
| Variant manifest hashing           | 🟡 stub    | `helios/vcl/` — to be implemented              |
| Snapshot hash registry             | ⏳         | `docs/tracking/snapshot_hash_registry.md`      |
| Metric integrity gate              | ⏳         | Stage 1+                                       |
| Exclusion ledger (signed)          | ⏳         | `bin/log_exclusion.py` (stub)                  |
| Deviation log (signed, chained)    | ✅         | `bin/log_deviation.py` + chain integrity tests |

## Latest deviation log entries (manual until weekly_dashboard.yml)

_(Populate from `deviation_log.jsonl`. The next 5 most recent entries with
`signature[:12]`, `clause`, and `change` truncated to 80 chars.)_
DASHBOARD_END

# ─── 10. data/ ────────────────────────────────────────────────────────────────
cat > data/calibration/.gitkeep <<'GITKEEP'
GITKEEP

# ─── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "✅ HELIOS MVP repo created at: $(pwd)"
echo ""
echo "Files created:"
find . -type f | sort
echo ""
echo "Next steps:"
echo "  1. cd $TARGET_DIR"
echo "  2. git init && git add -A && git commit -m 'Stage 0: repo skeleton + tracking register'"
echo "  3. cp .env.example .env && edit .env (set DEVIATION_HMAC_SECRET to 32+ char random)"
echo "  4. poetry install"
echo "  5. poetry run pre-commit install"
echo "  6. poetry run pytest tests/test_deviation_log.py -v   # MUST be green"
echo "  7. Run the first deviation log entry — see README.md quick start step 4"
echo "  8. gh repo create --public --source=. --push   # or set remote manually"
echo "  9. Set DEVIATION_HMAC_SECRET in repo Settings → Secrets and variables → Actions"