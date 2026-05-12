# Mutation Blocking + Tamper Detection — Design Spec

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `test_three_mutations` (VCLManifest mutation → Integrity Gate rejection) and `test_tamper` (HMAC chain middle-entry tamper + `TamperDetectedError`).

**Architecture:** Extend `VCLManifest` with two new string fields; add `TamperDetectedError` + `verify_hmac_chain()` to `HMACChainedLog`; add two tests.

**Tech Stack:** Python 3.11, Pydantic v2, pytest, HMAC-SHA256 (`helios.vcl.hmac_chain`), `helios.integrity_gate`.

---

## Part 1 — VCLManifest Extension

### New fields in `helios/vcl/config.py`

```python
model_version: str = "helios-llm-baseline"
prompt_template_id: str = "baseline-v1"
```

No `temperature` field — `model_version` covers "model parameter" with zero float-precision complexity.

**Why defaults:** `extra="forbid"` blocks *unknown* keys at construction; new fields with defaults are valid. All 8 confirmatory variants in `variants.py` need no changes.

**Breaking consequence:** All 8 `variant_config_hash` values change (hash covers full `model_dump()`). A deviation log entry is required before merging.

**How to apply:** After merging, run the test suite to observe the new hash values, then update `docs/tracking/vcl_manifest_tracking.md` hash registry.

---

## Part 2 — `test_three_mutations`

**File:** `tests/test_vcl.py`, added to `TestVCLManifest`.

**Imports added:** `MetricIntegrityGate` from `helios.integrity_gate` + an inline `_GateMockLedger` dataclass (not shared with `test_integrity_gate.py` — keeps test files independent).

**Three mutations against a default-flags baseline:**

| Label | Field changed | New value |
|---|---|---|
| A | `lpipe` | `True` (flag toggle) |
| B | `model_version` | `"helios-llm-experimental"` |
| C | `prompt_template_id` | `"variant-v2"` |

**Per-mutation assertions:**
1. `mutated.compute_variant_config_hash() != baseline_hash`
2. `gate.check(row_with_mutated_hash, ...).status == "FAIL"`
3. `gate.check(...).gate_check == "variant_config_hash_match"`
4. Ledger has exactly 1 entry after the call

**Out-of-scope (Stage 0):** "Assert no pipelines executed" — no orchestrator exists at Stage 0. Gate rejection at `check()` satisfies the semantic intent.

---

## Part 3 — `TamperDetectedError` + `verify_hmac_chain()`

**File:** `helios/vcl/hmac_chain.py`

```python
class TamperDetectedError(RuntimeError):
    """Raised by verify_hmac_chain() when HMAC chain integrity fails."""
```

```python
def verify_hmac_chain(self) -> None:
    """Raises TamperDetectedError on failure; delegates to verify()."""
    ok, msg = self.verify()
    if not ok:
        raise TamperDetectedError(msg)
```

**Backward compat:** `verify()` is unchanged. All existing tests and `bin/log_deviation.py verify` command continue to work. `TamperDetectedError` added to `__all__` in `hmac_chain.py`.

**SOLID:** `verify_hmac_chain()` is a thin adapter — zero duplication, Open/Closed principle preserved.

---

## Part 4 — `test_tamper`

**File:** `tests/test_deviation_log.py`

Steps:
1. Append 3 entries to a fresh log
2. Tamper the **middle entry** (line index 1) — overwrite `"change"` field
3. Assert `log.verify_hmac_chain()` raises `TamperDetectedError`; message contains `"Line 2"` (from `verify()`'s `f"Line {lineno}: ..."` format)
4. Assert `log.verify()` returns `(False, ...)` (backward compat confirmed)
5. Append a 4th entry — assert it returns a non-None dict (chain append succeeds regardless of on-disk tamper, since `previous_signature()` reads the last intact line)
6. Assert all 4 lines in the final file are valid JSONL

**Import:** `from helios.vcl.hmac_chain import TamperDetectedError` (direct import, no importlib).

---

## Files Summary

| Action | File | What changes |
|---|---|---|
| Modify | `helios/vcl/config.py` | Add `model_version`, `prompt_template_id` fields |
| Modify | `helios/vcl/hmac_chain.py` | Add `TamperDetectedError`, `verify_hmac_chain()`, update `__all__` |
| Modify | `tests/test_vcl.py` | Add `test_three_mutations` to `TestVCLManifest` |
| Modify | `tests/test_deviation_log.py` | Add `test_tamper` |
| No change | `helios/vcl/variants.py` | New fields have defaults |
| No change | `bin/log_deviation.py` | `verify()` unchanged |
| No change | `helios/integrity_gate.py` | Existing `check()` covers gate test |

**Pre-merge gate:** Deviation log entry + `poetry run pytest` + `make validate-tracking`.
