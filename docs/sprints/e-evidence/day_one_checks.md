# Phase E day-one pool-only checks · results

**Row:** S2-M11-EVAL05 · **Carried from:** S4.8 open item, S5 exit report §5 · **Script:** [`day_one_checks.py`](day_one_checks.py) · **Entries:** 104 (defect and fix), 105 (build-freeze-2)

Two checks that could only run on pool data, so only after the build was frozen. Both read the 240 sealed pool windows through `CaptureReader` (pool gate, window hash, content seal) and print counts only: no case ID, no label file.

## 1. First run · 2026-11-20 · from `build-freeze` (`c4037c0`)

Owner's go for the first pool read on 2026-11-20. All 240 windows read intact.

**Span status codes: defect.** The pool traces carry gRPC status codes, not OTel's:

| Value | Spans | Meaning |
|---|---|---|
| empty | 73,363,325 | not set |
| `0` | 37,309,797 | gRPC OK |
| `14`, `12`, `13`, `9`, `4` | 26,299 | gRPC errors (unavailable, unimplemented, internal, failed precondition, deadline exceeded) |
| `2` | 14,549 | gRPC UNKNOWN |
| `400` | 82 | HTTP error |

HELIOS (`span_features.ERROR_CODES`: `2`, `ERROR`, `STATUS_CODE_ERROR`; G-pipe span features and L-pipe digests) saw span errors in 9 windows. The v2 export (`ERROR`, `STATUS_CODE_ERROR`, HTTP from 400) saw them in 24, so the multi-source baselines' `tracets_err` was nearly empty. The two disagreed in 29 windows.

**Rebuilt series (export v2): pass.** All 240 windows exported all six files, with series wherever the modality exists (239 with logs, 240 with traces), rows equal to the 15-second grid.

**Decision.** The owner chose to fix before E1. Entry 104 records the defect and the shared rule; PR #119 implements it (`helios/telemetry/span_status.py`: OTel `ERROR` text, gRPC codes 2 to 16, HTTP from 400; export v3). Build data carries only `UNSET`, `OK` and `ERROR`, where the new rule equals both old ones, so no build result changed. PR #120 wrote the new freeze record, tag `build-freeze-2` marks it (`a5e7d41`), and entry 105 records the tag.

## 2. Rerun · 2026-11-21 · from `build-freeze-2` (`a5e7d41`)

| Check | Result |
|---|---|
| Windows read, seal intact | 240 of 240 |
| Distinct status values where G-pipe, digests and export disagree | none |
| Windows where HELIOS and export error counts differ | none |
| Windows with span errors, HELIOS / export | 50 / 50 |
| Error spans, HELIOS / export | 40,930 / 40,930 |
| Export v3: all six files | 240 of 240 |
| `logts.csv` with series / with a non-zero error column | 239 / 170 |
| `tracets_err.csv` with series / with a non-zero error column | 240 / 50 |
| `tracets_lat.csv` with series | 240 |
| Every derived file's rows equal the grid | 240 of 240 |
| Failures | none |

Both checks pass. The 50 windows with span errors are the same for HELIOS and the baselines.

## 3. Setup used (phase E worktree)

- `git worktree add --detach ../helios-e build-freeze`, moved to `build-freeze-2` for the rerun; own virtualenv from `poetry.lock` (uv-managed Python 3.11.15); `.env` copied (mode 600).
- Response cache copied with SQLite's backup command: 8,163 rows, identical row digest.
- Pool windows placed at `data/rcaeval/pool/` inside the worktree as an APFS clone (`cp -Rc`): each window manifest names its streams relative to the repository root, so a `--captures` path outside the checkout does not work.
- `bin/build_freeze.py --check` and `--verify` pass in the worktree.
