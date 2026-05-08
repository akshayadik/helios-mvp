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
