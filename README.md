# HELIOS MVP

Research-grade Root Cause Analysis (RCA) framework with runtime-enforced ablation discipline (Contribution C1).

**Status:** Stage 0 — Spine + Harness (in progress)

---

## What this repo is

HELIOS is the doctoral research artefact for the dissertation _Optimising Software Defect Management, Costs and Operational Efficiency Using AI-Driven Root Cause Analysis and Automated Triage in Microservice Environments_. The MVP implements a contracted scope from the full proposal, organised around five C1 runtime invariants:

1. **Variant Control Layer (VCL)** — binary-level variant identity via content-hashed feature-flag manifest
2. **Snapshot hash registry** — content-addressed UEG-C snapshots
3. **Metric integrity gate** — runtime rejection of incomplete cells
4. **Exclusion ledger** — cryptographically-signed append-only missingness record
5. **Deviation log** — cryptographically-signed append-only protocol-change record

Every protocol change with analytic consequence is logged to `deviation_log.jsonl` via a CLI that HMAC-signs and chains entries. CI verifies the chain on every push.

> **Note:** The full proposal lists six C1 components. The reconciliation ledger is descoped in this MVP — see deviation log entry #1 for justification.

---

## Repository layout

```
.
├── .github/
│   ├── ISSUE_TEMPLATE/         # 4 templates for recurring artefact-capture
│   └── workflows/              # CI, disjointness audit, ledger verification
├── bin/
│   ├── log_deviation.py        # CLI: append signed entries to deviation_log.jsonl
│   └── log_exclusion.py        # Stub (to be implemented Stage 1+)
├── docs/
│   ├── memos/                  # One-off frozen memos
│   ├── tracking/               # 18 living tracking documents (C1 evidence base)
│   └── osf_protocol_v0.md      # Pre-registration protocol (binding at Stage 5)
├── helios/                     # Core package (vcl/, schemas/, pipelines/)
├── tests/                      # pytest suite — HMAC chain integrity is the canary
├── deviation_log.jsonl         # Append-only, HMAC-chained protocol-change record
├── exclusion_ledger.jsonl      # Append-only metric-integrity-gate failures
├── pyproject.toml              # Python 3.11, Poetry-managed
├── .env.example                # HMAC secret placeholder (real .env is gitignored)
├── .pre-commit-config.yaml     # gitleaks + ruff hooks
└── README.md                   # this file
```

---

## First-time setup

You will need: Linux (Ubuntu 22.04+ tested), git, Python 3.11+, Poetry. Setup takes about 15–20 minutes including the Python install.

### Step 1 — Install Python 3.11

If `python3.11 --version` already prints something, skip this step.

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.11 python3.11-venv python3.11-dev
```

Verify:

```bash
python3.11 --version    # should print Python 3.11.x
```

### Step 2 — Install Poetry

```bash
pipx install poetry
# or, if pipx is unavailable:
curl -sSL https://install.python-poetry.org | python3 -
```

### Step 3 — Bootstrap the repo

If you cloned an existing repo, skip the script. If you're starting from scratch in an empty `helios-mvp/` directory:

```bash
cd helios-mvp
./setup_helios_mvp.sh    # populates current directory with all 44 files
```

The script refuses to overwrite existing files unless `--force` is passed.

### Step 4 — Generate the HMAC secret

The deviation log signs every entry with this secret. **It must never be committed.**

```bash
python3 -c "import secrets; print(f'DEVIATION_HMAC_SECRET={secrets.token_urlsafe(32)}')" > .env
chmod 600 .env
cat .env    # verify it looks right
```

> **🔒 Back this secret up in a password manager NOW (1Password, Bitwarden, etc.).**
>
> If you lose it, you cannot verify your existing chain or append new entries. See the [Security model](#security-model) section below for recovery options.

### Step 5 — Install Python dependencies

```bash
poetry env use python3.11
poetry install
```

### Step 6 — Activate the pre-commit hooks

These catch accidental commits of `.env` (gitleaks) and lint violations (ruff).

```bash
poetry run pre-commit install
```

### Step 7 — Verify the HMAC chain test suite passes

```bash
poetry run pytest tests/test_deviation_log.py -v
```

You should see **12 tests pass**. If any fail, do not proceed — fix or report before logging anything to the deviation chain.

### Step 8 — Log the genesis deviation entry

This is the very first entry in your deviation chain. It documents the C1 contraction (6 → 5 components):

```bash
poetry run python bin/log_deviation.py \
  --stage "Stage 0" \
  --clause "§3.6.6 / Execution Plan §6 / §4" \
  --change "C1 runtime invariants reduced from 6 to 5; reconciliation ledger not implemented" \
  --reason "RRE/E-H5 descoped per Execution Plan v1.0 §4 'No reconciliation' and Binding Decision #10" \
  --analytic-consequence "E-H5 fully descoped; A-H5 cost-aware static routing remains in scope under static-policy commitment"
```

Verify the chain:

```bash
poetry run python bin/log_deviation.py verify
# → ✅ Chain verified.
```

### Step 9 — Push to GitHub

```bash
git add -A
git commit -m "Stage 0: repo skeleton + tracking register + genesis deviation"

# Create the public repo and push:
gh repo create helios-mvp --public --source=. --push
# Or set the remote manually:
# git remote add origin git@github.com:<your-username>/helios-mvp.git
# git push -u origin main
```

### Step 10 — Configure GitHub Secrets

In the repo on GitHub: **Settings → Secrets and variables → Actions → New repository secret**.

- **Name:** `DEVIATION_HMAC_SECRET`
- **Value:** the same value as your local `.env`

This lets the `ledger_verification.yml` workflow run the on-disk chain check on every push. Without it, the workflow skips chain verification with a warning (so it doesn't block your initial commits before secrets are configured).

---

## Daily commands

### Pre-push gate — run before every PR

This is the exact sequence CI runs. All steps must be green before opening a PR.

```bash
# Load the HMAC secret (needed for chain verify; harmless for other commands)
set -a; source .env; set +a

poetry run ruff check helios/ scripts/ tests/          # lint
poetry run ruff format --check helios/ scripts/ tests/ # format
poetry run mypy                                        # type check
poetry run pytest                                      # tests
poetry run python bin/log_deviation.py verify          # HMAC chain integrity
make validate-tracking                                 # tracking schema
```

One-liner (fails fast on first error):

```bash
set -a; source .env; set +a && \
  poetry run ruff check helios/ scripts/ tests/ && \
  poetry run ruff format --check helios/ scripts/ tests/ && \
  poetry run mypy && \
  poetry run pytest && \
  poetry run python bin/log_deviation.py verify && \
  make validate-tracking
```

---

### Testing

```bash
# All tests (quiet)
poetry run pytest

# All tests, verbose
poetry run pytest -v

# Single file
poetry run pytest tests/test_deviation_log.py -v
poetry run pytest tests/test_validate_tracking.py -v

# Single test
poetry run pytest tests/test_deviation_log.py::test_verify_chain_passes_on_clean_log -v

# HMAC chain canary (12 tests — run after every deviation log entry)
poetry run pytest tests/test_deviation_log.py -v

# Tracking validator tests via Makefile
make test-tracking
```

---

### Coverage

```bash
# Terminal report showing uncovered lines
poetry run pytest --cov=helios --cov-report=term-missing

# HTML report (open htmlcov/index.html)
poetry run pytest --cov=helios --cov-report=html

# Enforce the CI threshold (90%)
poetry run pytest --cov=helios --cov-fail-under=90
```

`.coverage` and `htmlcov/` are gitignored — local build artefacts only.

---

### Lint and format

```bash
# Lint check (no changes)
poetry run ruff check helios/ scripts/ tests/

# Lint with auto-fix
poetry run ruff check --fix helios/ scripts/ tests/

# Format check (no changes)
poetry run ruff format --check helios/ scripts/ tests/

# Apply formatting
poetry run ruff format helios/ scripts/ tests/
```

---

### Type checking

```bash
poetry run mypy
```

Targets come from `[tool.mypy] files` in `pyproject.toml` (`helios`, `bin`, `tests`).

---

### Tracking document validation

The `docs/tracking/helios_mvp_tracking.md` schema is enforced by a pre-commit hook and replicated in CI to catch `--no-verify` bypasses.

```bash
make validate-tracking   # run the validator (exit 0 = clean, 1 = violations)
make test-tracking       # run the full pytest suite against the validator
make install-hooks       # (once per clone) install the pre-commit hook
```

Violations print to stderr with rule codes R1–R8 (status state machine, immutable columns, DONE-row evidence, deviation refs). Fix flagged rows and re-stage before committing.

---

### Deviation log

When any protocol change has analytic consequence, log it **before merging**:

```bash
set -a; source .env; set +a

poetry run python bin/log_deviation.py \
  --stage "Stage N" \
  --clause "§..." \
  --change "..." \
  --reason "..." \
  --analytic-consequence "..."
```

Each entry is HMAC-SHA256 signed and chained to the previous entry. The written record looks like:

```json
{
  "timestamp_utc": "2026-05-08T11:32:25.866918Z",
  "commit_sha": "LOCAL or GitHub SHA",
  "prev_signature": "GENESIS or hex-of-previous-entry",
  "stage": "Stage 0",
  "clause": "...",
  "change": "...",
  "reason": "...",
  "analytic_consequence": "...",
  "signature": "64-char hex HMAC-SHA256"
}
```

After every entry, verify the chain and run the HMAC canary:

```bash
poetry run python bin/log_deviation.py verify
poetry run pytest tests/test_deviation_log.py -v
```

**Never edit `deviation_log.jsonl` by hand.** See [Security model](#security-model) for recovery options.

---

### Exclusion ledger (Stage 1+)

`bin/log_exclusion.py` is a stub. When implemented it will sign and append metric-integrity-gate failures to `exclusion_ledger.jsonl` using the same HMAC chain pattern.

---

### Stage gate tagging

At each stage exit, tag the commit and push (Zenodo mints a DOI automatically):

```bash
git tag stage-N-exit
git push origin stage-N-exit
```

---

## Where the data lives

| Artefact | Path | Format | Updated by | Append-only? |
|---|---|---|---|---|
| Deviation log | `deviation_log.jsonl` | JSONL, HMAC-chained | `bin/log_deviation.py` | Yes |
| Exclusion ledger | `exclusion_ledger.jsonl` | JSONL, HMAC-chained | `bin/log_exclusion.py` (Stage 1+) | Yes |
| Tracking documents | `docs/tracking/*.md` | Markdown | You (in PRs) | No (versioned via git) |
| HMAC secret | `.env` (gitignored) | `KEY=value` | You (manually) | N/A |
| GitHub Secrets | Repo Settings | Encrypted at rest by GitHub | You (web UI) | N/A |
| Stage tags | git refs `stage-N-exit` | Git tags | You (`git tag`) | N/A |

**Both `.jsonl` files at the repo root are the canonical C1 audit trail. Do not edit them by hand. Use the CLIs.**

---

## Security model

> This section answers: how does the secret work, what happens if it leaks, what happens if it's deleted, can someone else who downloads the repo tamper with my logs?

### What the HMAC chain proves

Each entry in `deviation_log.jsonl` is signed with HMAC-SHA256 over its own fields *plus* the previous entry's signature. This means:

- ✅ **Tampering with any past entry breaks every subsequent signature.** CI catches this.
- ✅ **Reordering entries breaks the chain.** Each entry's `prev_signature` references the previous entry by its signature value.
- ✅ **Inserting a fake entry requires recomputing all later signatures**, which requires holding the HMAC secret.
- ✅ **Anyone reading the repo can see the deviation log** (it's plain text JSONL) but cannot append valid entries without the secret.

### What it does NOT prove

- ❌ **It does not prove WHO wrote the entry.** Only that whoever wrote it had access to the secret at the time.
- ❌ **It does not prevent rewrites by someone who holds the secret.** If the secret leaks, an attacker (or future-you under deadline pressure) could regenerate the entire chain with different content.
- ❌ **It does not survive force-push to `main`.** This is why branch protection on `main` is mandatory.

### The two-layer integrity model

For research-integrity purposes, the deviation log relies on **two independent integrity layers**:

1. **HMAC chain** (this repo's responsibility): tampering is mathematically detectable.
2. **Git commit history** (GitHub's responsibility): commits are externally timestamped; force-push is blocked by branch protection.

To tamper with the audit trail without leaving evidence, an adversary would need to (a) hold the HMAC secret AND (b) successfully force-push to a protected branch on GitHub. The intersection makes silent tampering impractical.

### FAQ

**Q: Can someone who downloads the repo add fake deviation entries?**

No. Without the HMAC secret (which lives in your `.env` and is gitignored), `bin/log_deviation.py` exits with an error before writing anything. They can read `deviation_log.jsonl` (it's plain text), but any entries they try to append manually won't have valid signatures, so:
- Local `verify` fails immediately
- CI on the next push to your repo fails immediately

**Q: What if I clone the repo on a new machine?**

Restore the secret from your password manager into a new `.env`. The chain continues from where you left off. If you don't have the backup, see "What if I lose the secret entirely" below.

**Q: What if the HMAC secret leaks publicly?**

Rotate it immediately:

```bash
# 1. Generate a new secret
python3 -c "import secrets; print(f'DEVIATION_HMAC_SECRET={secrets.token_urlsafe(32)}')" > .env

# 2. Update GitHub Secrets in repo Settings → Secrets and variables → Actions

# 3. Log the rotation as a deviation
poetry run python bin/log_deviation.py \
  --stage "Stage N" \
  --clause "Security / HMAC secret rotation" \
  --change "Rotated DEVIATION_HMAC_SECRET due to suspected leak" \
  --reason "<describe how leak was detected>" \
  --analytic-consequence "Pre-rotation chain frozen at signature <prefix-of-last-entry>; future entries chain from new secret. Pre-rotation entries verifiable only with old secret."
```

The pre-rotation chain entries are still cryptographically valid — anyone with the *old* secret can still verify them. The git history (with branch protection enabled) provides external timestamping for the rotation event itself.

**Q: What if I lose the secret entirely?**

Two options:

1. **Recovery (preferred):** restore from password manager. This is why backing up is mandatory at setup step 4.
2. **Chain reset:** generate a new secret. New entries chain from the literal string `GENESIS` again. The old entries become "trust by git history alone" — verifiable via GitHub commit timestamps + branch protection but not via HMAC. The new chain's first entry must document this:
   ```
   --change "Chain reset due to lost HMAC secret"
   --analytic-consequence "Pre-reset entries cannot be HMAC-verified; rely on git history. <list any post-mortem>"
   ```

**Q: Why HMAC-SHA256 and not GPG/sigstore?**

GPG or sigstore would prove identity (you signed it) in addition to integrity. For a solo doctoral researcher with a single audit trail, HMAC + branch protection is sufficient and simpler to operate. The full proposal (Appendix B.12) specifies Ed25519 signatures as the binding scheme — the MVP uses HMAC for operational simplicity, and this contraction is itself a deviation log entry to be filed.


---

## CI / GitHub Actions

Three workflows run on every PR and push to `main`:

| Workflow | Trigger | What it checks |
|---|---|---|
| `ci.yml` | push to main, PR | ruff lint, mypy types, pytest |
| `disjointness_audit.yml` | PR | Static feature-flag disjointness (stub until Stage 5) |
| `ledger_verification.yml` | push to main, PR | HMAC chain integrity tests + on-disk chain `verify` |

The on-disk chain check in `ledger_verification.yml` requires `DEVIATION_HMAC_SECRET` to be set in repo Secrets (setup step 10). If unset, the workflow skips with a warning rather than blocking — this is intentional, so you can push the initial commits before configuring secrets.

---

## Stage progression

| Stage | Output | Exit gate |
|---|---|---|
| **Stage 0** | Repo skeleton + VCL stub + first deviation | 18 tracking docs initialised, HMAC chain green, 5 telemetry recordings |
| Stage 1 | Telemetry + VCL Foundation | UEG-C snapshots, snapshot hashes recorded |
| Stage 2 | D-pipe (deterministic anomaly) | D-pipe operational on calibration corpus |
| Stage 3 | G-pipe (graph reasoning) | G-pipe operational on calibration corpus |
| Stage 4 | L-pipe + MAHC consensus | L-pipe + voting operational |
| **Stage 5** | **OSF Pre-registration freeze** | Hypotheses, variants, metrics, SAP locked |
| Stage 6 | Confirmatory runs | All variant×benchmark cells populated |
| Stage 7 | Replication verification | 10% byte-equality matrix run |
| **Stage 8** | **Chapter 4 + OSF deposit** | Final deposit DOI registered |

See [`docs/tracking/dashboard.md`](docs/tracking/dashboard.md) for the live Gantt timeline.

---

## Tracking documents

The 18 living tracking documents in `docs/tracking/` are the C1 evidence base. Full index in [`tracking_documents_register.md`](docs/tracking/tracking_documents_register.md). Highlights:

- [`dashboard.md`](docs/tracking/dashboard.md) — Mermaid timeline + cell-completion grid
- [`helios_mvp_tracking.md`](docs/tracking/helios_mvp_tracking.md) — Daily tasks + stage gates
- [`ablation_architecture.md`](docs/tracking/ablation_architecture.md) — Living architectural decision record
- [`hypothesis_variant_metric_mapping.md`](docs/tracking/hypothesis_variant_metric_mapping.md) — RQ → hypothesis → variant → metric (Stage 5 binding)
- [`vcl_manifest_tracking.md`](docs/tracking/vcl_manifest_tracking.md) — VCL configs and `variant_config_hash` registry
- [`snapshot_hash_registry.md`](docs/tracking/snapshot_hash_registry.md) — Per-incident UEG-C snapshot hashes
- [`reproducibility_manifest.md`](docs/tracking/reproducibility_manifest.md) — SHA-256 of corpus, container digests, model versions

---

## Troubleshooting

**Poetry can't find Python 3.11**

```bash
which python3.11
poetry env use $(which python3.11)
poetry install
```

**`pre-commit install` fails with `command not found`**

```bash
poetry run pre-commit install    # use poetry's environment, not system
```

**Tests fail with `DEVIATION_HMAC_SECRET not set`**

The test suite uses a pytest fixture that sets a test-only secret automatically. If tests still fail with this message, your `tests/test_deviation_log.py` may have been edited or the import path is broken. Restore from git: `git checkout HEAD -- tests/test_deviation_log.py`.

**`bin/log_deviation.py` exits with `DEVIATION_HMAC_SECRET not set`**

You skipped step 4 of setup. Generate the secret:

```bash
python3 -c "import secrets; print(f'DEVIATION_HMAC_SECRET={secrets.token_urlsafe(32)}')" > .env
```

If the env var still isn't picked up, you may need to source it explicitly:

```bash
set -a; source .env; set +a
poetry run python bin/log_deviation.py ...
```

Or (cleaner) install `python-dotenv` and load `.env` at the top of `log_deviation.py` — this is a Stage 1 follow-up.

**`poetry run python bin/log_deviation.py verify` fails after a force-push**

Force-push to `main` is the failure mode this repo is designed to detect. If it was intentional (e.g., recovering from a corrupted commit), document it in `docs/tracking/deviation_log.md` and accept that downstream signatures may need re-validation. If it was unintentional, treat as a security event and rotate the secret.

**I edited `deviation_log.jsonl` by hand and now the chain is broken**

Don't edit it by hand. If you already did, your only honest options are:
1. Restore from a clean git ref: `git checkout HEAD -- deviation_log.jsonl`
2. Document the manual edit and start a chain reset (see Security FAQ above)

**`gh repo create` fails with auth error**

Authenticate the GitHub CLI first: `gh auth login`.

---

## Contributing workflow

This is a solo doctoral project. The workflow in [`CONTRIBUTING.md`](CONTRIBUTING.md) is followed strictly even though I'm the only contributor — it's part of the C1 audit story.

Short version:
1. Open an issue using the appropriate template
2. Branch from `main` (`git checkout -b stage-N/short-description`)
3. Make the code change (test-driven where applicable)
4. If the change has analytic consequence, log it via `bin/log_deviation.py` BEFORE merging
5. Open a PR — CI must pass (ruff, mypy, pytest, disjointness, ledger verification)
6. Merge to `main`
7. At stage gates: `git tag stage-N-exit && git push --tags` (Zenodo captures the DOI automatically)

---

## License

MIT — see [`LICENSE`](LICENSE).

---

## Citations and DOI

When this repo reaches its first stage tag, Zenodo will mint a DOI per release. Add the DOI badge here once available. For now, cite as:

> Adik, Akshay (2026). _HELIOS MVP — Research-grade RCA framework with runtime-enforced ablation discipline._ GitHub repository. Stage 0 in progress.
