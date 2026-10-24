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
# Ed25519 key for deviation entries from 35 on (D7): restore the
# DEVIATION_ED25519_PRIVATE_KEY line from the password manager into .env.
# The key pair already exists (keys/deviation_log_ed25519.pub.pem); `keygen` is one-time and refuses to replace it.

poetry env use python3.11
poetry install
poetry run pre-commit install
```

### Pre-push gate (run before every PR — exact CI sequence)

```bash
set -a; source .env; set +a && \
  poetry run ruff check helios/ scripts/ tests/ bin/ && \
  poetry run ruff format --check helios/ scripts/ tests/ bin/ && \
  poetry run black --check helios/ scripts/ tests/ bin/ && \
  poetry run mypy && \
  poetry run pytest && \
  poetry run python bin/verify_ledgers.py && \
  poetry run python bin/log_deviation.py verify-public && \
  poetry run python bin/verify_captures.py && \
  poetry run python bin/verify_osf_freeze.py --verify && \
  poetry run make validate-tracking && \
  poetry run jupyter nbconvert --to notebook --execute --ExecutePreprocessor.timeout=120 \
    --output-dir "${TMPDIR:-/tmp}" research/ablation_notebook.ipynb
```

The last step mirrors CI's `ablation-notebook` job, which executes the notebook against the committed `research/osf/` artefacts; a renamed key that only the notebook reads fails nowhere else (S0.7, `loo_cv_cpr`). When renaming a field or key, search `*.ipynb` too.

CI's lint job also runs `black --check` (floating `>=24.0,<27.0`, resolves to black 26). ruff 0.6.9 accepts both styles of multi-line string call (`f("""` hugged or split), but black 26 accepts only the hugged form — so a file can pass `ruff format --check` and still fail CI. `verify_osf_freeze.py --verify` reads `helios/vcl/variants.py` from **HEAD**, so it only reflects an edit after commit; `tests/test_verify_osf_freeze.py::test_variants_py_matches_frozen_vcl_sha` checks the working tree.

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

**Ablation variants:** 8 confirmatory (Ch3 Table 17): HELIOS-Full, noLLM, LLM-only, D, noConsensus, noRouter, G, noStructural; 7 exploratory: noCogni, noACP, noReconcile, HIS3, noFGSV, noIOL, noExpl.

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
- **17 flags** (owner decision D2, 2026-10-23, deviation entry 31): 13 Chapter 3 flags (`l2c_llm`, `p4_cognitive`, `mahc_hierarchical`, `cbr_routing`, `l2b_graph`, `acp_stateful`, `reconcile_terminal`, `fgsv_ks_gate`, `iol_self_telemetry`, `coe_narrative`, `his_tier`, `sampling_regime_tag`, `ueg_structural`) + 3 implementation flags (`dpipe`, `dpipe_propagation`, `gpipe`) + `ingest_mode` (str). The May names `mahc`, `cbr`, `router`, `acp`, `reconcile`, `ueg_c_structural`, `lpipe` no longer exist (`cbr_routing` is Ch3's cost-based routing, ORAR: OFF = uniform routing = HELIOS-noRouter).
- `VCLFlag.bool_flags()` returns the 16 boolean flags, excluding `INGEST_MODE`. Always use this when iterating flags for gating — never iterate `VCLFlag` directly.

**Manifest and hashing (`config.py`, `utils.py`)**
- `VCLManifest` is `frozen=True` + `extra="forbid"`. Hash is exhaustive — adding a field without updating the model breaks hash stability.
- `canonical_json()` pre-normalises floats with `round(o, 6)` **before** passing to `json.dumps`. This is required because `json.dumps` handles `float` natively and never calls the `default` hook for them; a `default`-only approach silently produces un-rounded output.
- `ingest_mode` is validated by `@field_validator` to `"recorded" | "live"` at every construction path (direct, `from_flags`, deserialization).

**Decorator (`decorators.py`)**
- `@gated_by(VCLFlag.X)` raises `TypeError` at **decoration time** (import time) if `X` is not a boolean flag. Do not attempt to gate on `INGEST_MODE`.
- `VCLManifest` is imported under `TYPE_CHECKING` only — with `from __future__ import annotations` all annotations are lazy strings, so this is correct and satisfies `TCH001`.
- Uses `ContextVar` for thread/async safety. Call `set_current_manifest()` before invoking any `@gated_by` component; missing manifest raises `RuntimeError`.

**Variants (`variants.py`)**
- Every variant is built as `_full_except(...)` from HELIOS-Full's flags; Table 17 "passthru" is OFF; flags Table 17 does not name follow Full; each exploratory variant is Full with exactly one flag OFF.
- All 15 variant hashes are unique (enforced by `test_all_fifteen_variant_hashes_are_unique`). Helpers go in `catalog.py`, never `variants.py` (it is fingerprinted by the OSF freeze).

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
| `ledger_verification.yml` | `log_deviation.py verify-public` (Ed25519, public key only, no secret) + HMAC chain integrity + `verify_ledgers.py` (anchors); the HMAC part **fails** if `DEVIATION_HMAC_SECRET` is missing (only fork PRs skip, with a warning) |

### Tracking schema rules (R1–R8)

Enforced by `scripts/validate_tracking.py` as a pre-commit hook (working tree vs HEAD) and in CI with `--range BASE..HEAD`, which validates **every commit** that touched the tracker against its own parent(s). Before 2026-10-22 CI ran the bare form on a checkout, comparing the file with itself, so R4/R5 never fired in CI. Merge commits: a row is reported only if invalid against every parent. Audit a branch locally with `python3 scripts/validate_tracking.py --range origin/main..HEAD`.

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
- The `.env` file is gitignored — back it up in a password manager; losing it breaks chain verification. It holds two secrets: `DEVIATION_HMAC_SECRET` and `DEVIATION_ED25519_PRIVATE_KEY`.
- `DEVIATION_HMAC_SECRET` must also be set in GitHub Secrets for `ledger_verification.yml` to run the on-disk chain check.

### ruff

- `[tool.ruff.lint]` has `preview = true` — preview-stable rules (e.g. `RUF022` `__all__` sort) fire locally, matching CI. Do not remove it.
- ruff is pinned to `>=0.6.9,<0.7` in both `pyproject.toml` and `ci.yml`. To widen the pin: run `ruff format helios/ scripts/ tests/` first to absorb formatting changes, update both files, then regenerate `poetry.lock`.
- `__all__` lists must be sorted in ASCII order (uppercase before lowercase). `ruff check --fix` auto-sorts; the order is: uppercase names first (`A–Z`), then lowercase (`a–z`).

### Poetry / lock file

- After **any** change to `pyproject.toml` dependencies, run `poetry lock` to regenerate `poetry.lock` (Poetry 2.x dropped `--no-update`; plain `poetry lock` re-resolves only what changed).
- Always commit `poetry.lock` in the same commit as the `pyproject.toml` change. A stale lock file breaks every CI job that runs `poetry install`.
- **Never use `poetry install --no-root` in a CI job that runs `bin/` scripts directly.** `--no-root` skips installing the `helios` package itself. `pytest` survives this because `pyproject.toml` injects `pythonpath = ["."]` before test collection; bare `poetry run python bin/<script>.py` does not get that injection and raises `ModuleNotFoundError: No module named 'helios'`. The correct form for any job that imports from `helios` at runtime is `poetry install --no-interaction --with dev` (no `--no-root`).

### Pydantic v2

- `VCLManifest` is `frozen=True` — assignment raises `ValidationError` at runtime. In tests, use `manifest.field = value  # type: ignore[misc]` to suppress the mypy read-only property error (the pydantic plugin detects it correctly).
- If a Pydantic model is used **only in annotations** in a module that has `from __future__ import annotations`, import it under `TYPE_CHECKING` to satisfy `TCH001`. The lazy string evaluation means the import is not needed at runtime.
- Prefer `@field_validator` over factory-method validation — it fires on every construction path (direct instantiation, `from_flags`, Pydantic deserialization), not just one entry point.

### Claude Code hooks

- `research-compliance.py` blocks any Write/Edit containing the literals `0.0`, `1.0`, `0.5`, or `100` as word-bounded tokens **in any file**, including Markdown and plan files. Avoid these literals in documentation; use prose (`"rounds to zero"`, `"full coverage"`) instead.
- `flag-guard.py` exempts the entire `helios/vcl/` path — files there can define classes and functions without a `HELIOS_ENABLE_*` pattern. Everywhere else, new `def`/`class` definitions require a VCL import (`VCLFlag`, `gated_by`, `VCLManifest`) or an `HELIOS_ENABLE_*` reference. `.claude/` (hook tooling) is also exempt.
- For Edit/MultiEdit, `flag-guard.py` checks the file as it will look **after** the edit; `research-compliance.py` checks only the inserted `new_string` text. (Before 2026-10-22 both read only `content`, so Edits were never inspected.)
- Hooks are launched with `python3` (macOS has no bare `python`). A hook command that is not found exits 127, which Claude Code treats as non-blocking — a missing interpreter silently disables the guard. After changing `.claude/settings.json`, review hooks via `/hooks` or restart the session.
- PostToolUse scripts resolve the Poetry venv themselves (`poetry env info -p`); they do not rely on `python`/`ruff` being on PATH.
- `format-and-matrix-update.sh` runs `ruff check --fix` after **every** edit, which deletes imports that are unused *at that moment*. When adding an import and its use in separate edits, add the use first (or both in one edit) — otherwise the import is silently stripped and only `ruff check`/mypy in the gate will notice (F821).

### Secret scanning (gitleaks)

- `.gitleaks.toml` must keep `[extend] useDefault = true`. Without it the custom file **replaces** gitleaks' built-in rules, leaving zero rules — every scan "passes". This was the state from 2026-05-19 (`1e59dc5`) to 2026-10-22.
- Pre-commit only scans staged changes. Full-history scan: the binary pre-commit installs under `~/.cache/pre-commit/*/golangenv-default/bin/gitleaks`, run as `gitleaks detect --source . --config .gitleaks.toml --redact`.
- After every fresh clone: `poetry run pre-commit install` (no hooks run until this is done).

### HMAC-chained log patterns

- **Head anchors.** Each ledger has a signed sibling `<stem>.anchor.json` (entry count, head signature, log kind). A chain alone cannot detect entries removed from the end; the anchor can. `append()` rewrites the anchor and **refuses** to extend a log whose tail no longer matches it (so a truncated log is never silently re-anchored). Commit the `.anchor.json` together with its `.jsonl`.
- `bin/verify_ledgers.py` verifies the deviation, exclusion and reconciliation ledgers; a missing anchor fails even for an empty log. `--init-anchors` is a one-time bootstrap for pre-anchor logs (done 2026-10-22 after checking every committed version of each ledger is a prefix of the current file) and refuses to overwrite.
- `verify()` also checks each entry has its class's `REQUIRED_FIELDS` (all ledgers share one key, so a log of one kind could otherwise pass as another) and, for the deviation log, that `deviation_id == signature[:16]` when present (entries 1–3 predate the field).
- Residual, by design: rolling back a ledger **and** its anchor together to an earlier committed state is consistent from inside the repo. Git history and the OSF deposit are the external record.
- Never hand-edit an `.anchor.json`. If `verify` reports an anchor mismatch, investigate (git log -p on both files) — do not regenerate the anchor.
- **Ed25519 layer (D7, S0.9, deviation entry 35).** From entry `ED25519_FROM_ENTRY = 35` the deviation log is also signed with Ed25519: each entry carries `ed25519_signature` over all its other fields (HMAC `signature` and `prev_signature` included), and the anchor carries `log_sha256` (digest of the whole file) plus `anchor_ed25519_signature`. `poetry run python bin/log_deviation.py verify-public` needs only the committed public key `keys/deviation_log_ed25519.pub.pem` and checks every byte, entries 1–34 included (they stay HMAC-only; their bytes are covered by the signed digest). CI runs it without secrets.
- Appending needs both `DEVIATION_HMAC_SECRET` and `DEVIATION_ED25519_PRIVATE_KEY`; the CLI refuses a private key that does not match the committed public key. `ed25519_signature` is in `_UNSIGNED_KEYS`, so HMAC signatures are unchanged by the layer. The boundary is a code constant: stripping signatures cannot downgrade the log. The exclusion and reconciliation ledgers stay HMAC-only (`ED25519_FROM_ENTRY = None`).
- Losing the Ed25519 private key means no further deviation entries can be appended; rotation would need a new key, a code change and a deviation entry signed by the HMAC chain. Back the key up with the HMAC secret.

### Capture content seal

- `window_hash` covers TelemetryWindow fields (metadata + Parquet **paths**) only; it does not change when Parquet bytes change, and the manifest's `snapshot_hash` is outside it. `data/captures/<id>/content_seal.json` (helios/telemetry/seal.py) signs, with the ledger key, the SHA-256 of the exact `manifest.json` bytes and of every declared Parquet stream, bound to the incident id and the directory name.
- `RunOrchestrator` skips a capture whose seal is missing or mismatched (`gate_check=capture_seal_invalid`). `bin/run_capture.py` seals new captures and refuses to start without the key. Any imported corpus (confirmatory) must be sealed before it can run.
- Seals are write-once. `bin/verify_captures.py --init-seals` seals only captures whose every file is tracked and identical to git HEAD; the 20 exploratory captures were sealed 2026-10-22 after also matching tag `milestone-3-exit` (deviation entry 23).
- Never rewrite a `manifest.json` after sealing (even reformatting changes its bytes).

- **`_UNSIGNED_KEYS` must cover every field that is derived from `signature`.** `HMACChainedLog.compute_signature()` excludes `{"signature", "deviation_id"}` from the signed payload. If you add a new post-sign field (any field set inside `_post_sign_fields()`), add its key to `_UNSIGNED_KEYS` in `helios/vcl/hmac_chain.py` — otherwise `verify()` will always report tampering because it recomputes the hash without that field.
- Post-sign fields belong in `_post_sign_fields()` — the hook is called *after* `compute_signature()` sets `entry["signature"]` but *before* the JSONL line is written. Never set derived fields earlier in `append()`.
- `from helios.vcl.hmac_chain import GENESIS as GENESIS` — the `as GENESIS` form is required in `bin/` files so that `log_deviation.GENESIS` is accessible as a module attribute in tests (ruff F401 would otherwise flag the import as unused).

### VCL consumer patterns

- Annotate every pipeline entry-point with `@gated_by(VCLFlag.X)` where `X` is the flag controlling that component. The decorator registers `__gated_by__` for the static disjointness audit.
- **Never** use `@gated_by(VCLFlag.INGEST_MODE)` — it is a string flag, not boolean, and raises `TypeError` at decoration time. Check `manifest.ingest_mode` directly where needed.
- Call `set_current_manifest(manifest)` before invoking any `@gated_by` component. The `ContextVar` has no default; a missing manifest raises `RuntimeError` at call time.
- When iterating flags for audits or tests, use `VCLFlag.bool_flags()` — not `VCLFlag` directly, which includes `INGEST_MODE`.

### Session knowledge management

- Run `/save-bug-fixes` at the end of any session where a non-obvious bug was diagnosed and fixed. This writes to the project memory at `/home/akshay/.claude/projects/-home-akshay-workspace-helios-mvp/memory/`.
- A bug is worth saving when the root cause required diagnosis (not just "I had a typo"). Canonical examples: tool behaviour that contradicts documentation, version-pinning interactions, Pydantic/ruff/mypy edge cases.
- `/save-bug-fixes` uses Bash heredocs internally to avoid `flag-guard.py` blocking content that contains `def ` or `class `. Do not switch to Write tool for memory file content.
