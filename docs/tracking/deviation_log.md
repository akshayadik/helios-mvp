# Deviation Log (Human-Readable)

**Purpose:** Markdown-rendered companion to `deviation_log.jsonl`. Human-readable summary table for examiner readability; the JSONL remains the authoritative artefact.

**Schema version:** v1.0 (frozen 2026-05-15)
**Update cadence:** After every `deviation_log.jsonl` append via `bin/log_deviation.py`
**Owner:** AA
**Authoritative source:** `deviation_log.jsonl` (HMAC-SHA256 chained)
**Verify command:** `poetry run python bin/log_deviation.py verify`

---

## Column Definitions

| Column | Meaning |
|---|---|
| `#` | Entry sequence number (1-indexed) |
| `Date` | `timestamp_utc` date component |
| `Stage` | Research stage when change was made |
| `Clause` | Proposal / execution plan clause affected |
| `Change` | Brief description of what changed (truncated to 80 chars) |
| `Analytic_consequence` | Impact on confirmatory analysis validity |
| `sig[:12]` | First 12 hex chars of HMAC-SHA256 signature (tamper indicator) |

---

## Entries

| # | Date | Stage | Clause | Change | Analytic_consequence | sig[:12] |
|---|---|---|---|---|---|---|
| 1 | 2026-05-08 | Stage 0 | Setup / pyproject.toml python constraint | Python pinned to 3.11 via deadsnakes PPA | Reproducibility constraint — Python version mismatch would break all test runs | 7fee47b53a2d |
| 2 | 2026-05-08 | Stage 0 | §3.6.6 / Execution Plan §6 / §4 | C1 runtime invariants reduced from 6 to 5; reconciliation ledger deferred | Deferred sub-artefact implemented at Milestone 1 — no analytic loss | fb8ece84e8a1 |
| 3 | 2026-05-08 | Stage N | §... | Template entry (genesis placeholder — no real change) | None | 539e67a1910f |
| 4 | 2026-05-12 | Stage 1 | §6.2 | Add model_version and prompt_template_id fields to VCLManifest | All variant_config_hashes invalidated and recomputed — hash table in vcl_manifest_tracking.md updated | 0b8fcc0d03d1 |
| 5 | 2026-05-14 | Stage 0 | §B.12 / Execution Plan §10 / Exit Gates EG1–EG6 | Stage 0 spine exit sign-off. All 6 gates satisfied | None (sign-off entry; no protocol change) | a64c18b7f0b9 |

---

## Future Entries

`[PENDING: Stage 1+ — append as protocol deviations occur via bin/log_deviation.py CLI. Each entry requires: --stage, --clause, --change, --reason, --analytic-consequence]`

---

*Last updated: 2026-05-15 from deviation_log.jsonl (5 entries, chain verified)*
