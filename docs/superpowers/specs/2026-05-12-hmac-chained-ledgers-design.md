# Design Spec: HMAC-Chained Audit Ledgers (S0-D2-ENG01 + ENG02)

**Date:** 2026-05-12
**Status:** Approved — ready for implementation
**Tracking tasks:** S0-D2-ENG01 (deviation_log), S0-D2-ENG02 (exclusion_ledger)
**Approach:** B — Shared base in `helios/vcl/`, thin subclasses in `bin/`

---

## 1. Motivation

`bin/log_deviation.py` is implemented but has a hidden I/O dependency: `append_entry()` calls `load_key()` internally, forcing all tests to monkeypatch the environment even for pure chain-logic assertions. The exclusion ledger (`bin/log_exclusion.py`) is a 5-line stub with no schema or tests.

This spec introduces a shared `HMACChainedLog` base class and two concrete ledger types, satisfying SOLID design, eliminating the I/O coupling, and providing full test coverage for both artefacts.

---

## 2. Module Structure

```
helios/vcl/
  hmac_chain.py          ← NEW: HMACChainedLog base class + GENESIS

bin/
  log_deviation.py       ← REFACTORED: DeviationLog(HMACChainedLog) + load_key() + CLI
  log_exclusion.py       ← IMPLEMENTED: ExclusionLedger(HMACChainedLog) + load_key() + CLI

tests/
  test_hmac_chain.py        ← NEW: base class unit tests
  test_deviation_log.py     ← UPDATED: class-based fixtures + test_schema
  test_exclusion_ledger.py  ← NEW: test_append + HMAC chain + test_schema
```

`helios/vcl/hmac_chain.py` is placed in `helios/vcl/` because:
- The directory is flag-guard exempt (VCL is the audit infrastructure)
- HMAC chaining is the tamper-evidence mechanism for all VCL audit artefacts
- `canonical_json` already lives in `helios/vcl/utils.py` — `hmac_chain.py` is a natural companion

`helios/vcl/__init__.py` is **not** updated — `HMACChainedLog` is imported directly from `helios.vcl.hmac_chain` by the bin scripts; it is not part of the public VCL API.

---

## 3. SOLID Mapping

| Principle | Enforcement |
|---|---|
| SRP | `HMACChainedLog` owns chain logic only. `DeviationLog`/`ExclusionLedger` own field schemas only. `load_key()` owns env I/O only. |
| OCP | Add a new ledger type by subclassing — no changes to `HMACChainedLog`. |
| LSP | Both subclasses pass all base-class tests when substituted. |
| ISP | Single `append()` / `verify()` contract — no fat interfaces. |
| DIP | Tests construct `DeviationLog(key=key, path=path)` directly — no env dependency for core logic tests. |

---

## 4. `HMACChainedLog` — Base Class

**File:** `helios/vcl/hmac_chain.py`

```python
GENESIS = "GENESIS"

class HMACChainedLog:
    REQUIRED_FIELDS: tuple[str, ...] = ()

    def __init__(self, key: bytes, log_path: Path) -> None:
        # raises ValueError if len(key) < 32

    def previous_signature(self) -> str:
        # returns GENESIS if file missing/empty, else last entry's signature

    def compute_signature(self, entry: dict[str, Any]) -> str:
        # HMAC-SHA256 over canonical JSON of entry excluding "signature" and "deviation_id"

    def append(self, fields: dict[str, Any]) -> dict[str, Any]:
        # validates REQUIRED_FIELDS, builds envelope, signs, writes JSONL line
        # raises ValueError on missing required field

    def verify(self) -> tuple[bool, str]:
        # walks full chain from GENESIS; returns (ok, message)
```

**Envelope fields added by `append()` (shared by all subclasses):**

| Field | Type | Source |
|---|---|---|
| `timestamp_utc` | ISO-8601 with Z | `datetime.now(UTC)` |
| `commit_sha` | str | `$GITHUB_SHA` or `"LOCAL"` |
| `prev_signature` | str | `GENESIS` or previous entry's hex sig |
| `signature` | 64-char hex | HMAC-SHA256 over all other fields |

`deviation_id` is appended **after** signing — it is a read-convenience field (`signature[:16]`), not part of the signed payload.

---

## 5. `DeviationLog` — Domain Subclass (§B.12)

**File:** `bin/log_deviation.py`

```python
HELIOS_ENABLE_DEVIATION_LOG: bool = True  # always-on C1 audit infrastructure

class DeviationLog(HMACChainedLog):
    REQUIRED_FIELDS = ("stage", "clause", "change", "reason", "analytic_consequence")
```

**Full entry field set:**

| Field | Source |
|---|---|
| `timestamp_utc` | envelope |
| `commit_sha` | envelope |
| `prev_signature` | envelope |
| `stage` | CLI `--stage` |
| `clause` | CLI `--clause` |
| `change` | CLI `--change` |
| `reason` | CLI `--reason` |
| `analytic_consequence` | CLI `--analytic-consequence` |
| `signature` | envelope (signed) |
| `deviation_id` | `signature[:16]` (post-sign, not in payload) |

**CLI:** unchanged from current — all existing `--stage/--clause/...` flags and `verify` subcommand preserved exactly.

---

## 6. `ExclusionLedger` — Domain Subclass (§3.6.8)

**File:** `bin/log_exclusion.py`

```python
HELIOS_ENABLE_EXCLUSION_LEDGER: bool = True  # always-on C1 audit infrastructure

class ExclusionLedger(HMACChainedLog):
    REQUIRED_FIELDS = (
        "variant_config_hash", "snapshot_hash", "run_id",
        "incident_id", "gate_check", "reason", "analytic_consequence",
    )
```

**Full entry field set:**

| Field | Source |
|---|---|
| `timestamp_utc` | envelope |
| `commit_sha` | envelope |
| `prev_signature` | envelope |
| `variant_config_hash` | CLI `--variant-config-hash` |
| `snapshot_hash` | CLI `--snapshot-hash` |
| `run_id` | CLI `--run-id` |
| `incident_id` | CLI `--incident-id` |
| `gate_check` | CLI `--gate-check` |
| `reason` | CLI `--reason` |
| `analytic_consequence` | CLI `--analytic-consequence` |
| `signature` | envelope (signed) |

**CLI:**
```
poetry run python bin/log_exclusion.py \
  --variant-config-hash <hash> --snapshot-hash <hash> \
  --run-id <id> --incident-id <id> \
  --gate-check <name> --reason <text> --analytic-consequence <text>

poetry run python bin/log_exclusion.py verify
```

---

## 7. Test Plan

### `tests/test_hmac_chain.py` (new — base class)

| Test | Covers |
|---|---|
| `test_genesis_on_empty_log` | `previous_signature()` → GENESIS when file missing |
| `test_genesis_on_empty_file` | `previous_signature()` → GENESIS when file is empty |
| `test_signature_excludes_signature_field` | Signed payload never includes `signature` key |
| `test_short_key_raises_at_construction` | `key` shorter than 32 bytes → `ValueError` |

### `tests/test_deviation_log.py` (updated)

| Test | Covers |
|---|---|
| `test_schema` *(new — tracking ref: S0-D2-ENG01)* | All §B.12 fields present; Z-suffix timestamp; 64-char hex sig; GENESIS prev; `deviation_id == signature[:16]` |
| `test_missing_required_field_raises` *(new)* | `append()` with missing field → `ValueError` |
| `test_first_entry_has_genesis_prev_signature` | Chain start |
| `test_signature_is_64_hex_chars` | SHA-256 output |
| `test_chain_links_correctly_across_three_entries` | Chain linkage |
| `test_signature_recomputes_to_same_value` | Determinism |
| `test_tampered_change_field_breaks_signature` | Field mutation |
| `test_tampered_prev_signature_breaks_chain` | Chain mutation |
| `test_verify_chain_passes_on_clean_log` | `verify()` happy path |
| `test_verify_chain_fails_on_tampered_log` | `verify()` tamper detection |
| `test_log_file_is_one_json_per_line` | JSONL format |
| `test_missing_secret_exits` | `load_key()` no env → `SystemExit` |
| `test_short_secret_exits` | `load_key()` short key → `SystemExit` |
| `test_canonical_signature_is_deterministic` | Determinism |

### `tests/test_exclusion_ledger.py` (new)

| Test | Covers |
|---|---|
| `test_append` *(tracking ref: S0-D2-ENG02)* | Full-field entry written; GENESIS prev; 64-char hex sig; valid JSONL |
| `test_schema` | All §3.6.8 fields present; Z-suffix timestamp; `incident_id` round-trips |
| `test_chain_links_across_two_entries` | `e2.prev_sig == e1.sig` |
| `test_verify_passes_on_clean_log` | `verify()` happy path |
| `test_verify_fails_on_tampered_log` | On-disk tamper detection |
| `test_missing_required_field_raises` | `append()` missing field → `ValueError` |
| `test_short_key_raises` | `ExclusionLedger(key=b"x", ...)` → `ValueError` |

---

## 8. Documentation Fixes

| File | Change |
|---|---|
| `docs/tracking/HELIOS_MVP_Execution_plan_v0.6.md` line 34 | `eval/deviation_log.py` → `bin/log_deviation.py` |
| `docs/tracking/helios_mvp_tracking.md` S0-D2-ENG01 | Clarify filename as `bin/log_deviation.py` |
| `docs/tracking/helios_mvp_tracking.md` S0-D2-ENG02 | Clarify filename as `bin/log_exclusion.py` |
| `CLAUDE.md` (root) | Already correct — no change |
| `README.md` stub comment | Update once `log_exclusion.py` is implemented |

---

## 9. Invariants (Never Violate)

- `deviation_id` and any future convenience fields must **never** be included in the HMAC-signed payload. `compute_signature` excludes both `"signature"` and `"deviation_id"` from the canonical JSON — this is critical for `verify()` correctness, since `deviation_id` is written into the JSONL line after signing and would otherwise cause a hash mismatch on replay.
- `REQUIRED_FIELDS` validation fires inside `append()` — not in the CLI — so programmatic callers get the same protection as the CLI.
- To add a future post-sign convenience field: add its key to the exclusion set in `compute_signature`, document it here, add a `test_verify_passes_with_convenience_field_present` test.

---

*This spec is approved. Implementation plan to follow via `writing-plans` skill.*
