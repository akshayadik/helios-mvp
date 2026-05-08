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
