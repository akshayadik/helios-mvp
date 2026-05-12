# Mutation Blocking + Tamper Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `test_three_mutations` (three independent VCLManifest mutations each rejected by MetricIntegrityGate) and `test_tamper` (middle-entry HMAC chain tamper detected via `TamperDetectedError`).

**Architecture:** Extend `VCLManifest` with two string identity fields (`model_version`, `prompt_template_id`); add `TamperDetectedError` and `verify_hmac_chain()` to `HMACChainedLog`. Tests are written first (TDD). A deviation log entry is required before the final commit because all 8 confirmatory variant hashes change.

**Tech Stack:** Python 3.11, Pydantic v2 (frozen BaseModel), pytest, `helios.vcl.hmac_chain.HMACChainedLog`, `helios.integrity_gate.MetricIntegrityGate`.

---

## File Map

| Action | File | Change |
|---|---|---|
| Modify | `tests/test_vcl.py` | Add `_GateMockLedger` + `test_three_mutations` |
| Modify | `helios/vcl/config.py` | Add `model_version` + `prompt_template_id` fields |
| Modify | `tests/test_deviation_log.py` | Add `TamperDetectedError` import + `test_tamper` |
| Modify | `helios/vcl/hmac_chain.py` | Add `TamperDetectedError`, `verify_hmac_chain()`, `__all__` |
| Append | `deviation_log.jsonl` | Log VCLManifest extension via CLI (required pre-merge) |

No changes needed to `helios/vcl/variants.py` (new VCLManifest fields have defaults), `bin/log_deviation.py` (`verify()` unchanged), or `helios/integrity_gate.py` (existing `check()` covers the gate test).

---

### Task 1: test_three_mutations — write test first, then extend VCLManifest

**Background:**
- `VCLManifest` is at `helios/vcl/config.py`. Its `compute_variant_config_hash()` hashes `self.model_dump()`, so adding new fields changes all existing hashes.
- `VCLManifest.from_flags(**flags: bool | str)` — passing `model_version="..."` is valid (`str` satisfies `bool | str`).
- `MetricIntegrityGate.check(row, incident_id=...)` returns `GateResult(status="FAIL", gate_check="variant_config_hash_match")` when `row["variant_config_hash"] != self._expected`.
- The test writes `test_three_mutations` first. Running it before the VCLManifest fields exist produces `pydantic.ValidationError: Extra inputs are not permitted` — that is the expected RED state.

**Files:**
- Modify: `tests/test_vcl.py`
- Modify: `helios/vcl/config.py`

- [ ] **Step 1: Add import, `_GateMockLedger`, and `test_three_mutations` to `tests/test_vcl.py`**

**1a — Add import** after line 19 (`from helios.vcl.decorators import _current_manifest`):

```python
from helios.integrity_gate import MetricIntegrityGate
```

**1b — Add `_GateMockLedger`** at module level, after the fixtures block (after `yield` on line 31) and before `class TestCanonicalJson`. Insert:

```python
class _GateMockLedger:
    def __init__(self) -> None:
        self.entries: list[dict[str, str]] = []

    def append(self, fields: dict[str, str]) -> None:
        self.entries.append(fields)
```

**1c — Add `test_three_mutations`** as the last method of `TestVCLManifest` (after `test_ingest_mode_invalid_raises`):

```python
    def test_three_mutations(self) -> None:
        """Three manifest mutations each hash-differ and are rejected by MetricIntegrityGate."""
        baseline = VCLManifest.from_flags()
        baseline_hash = baseline.compute_variant_config_hash()

        mutations = [
            VCLManifest.from_flags(lpipe=True),
            VCLManifest.from_flags(model_version="helios-llm-experimental"),
            VCLManifest.from_flags(prompt_template_id="variant-v2"),
        ]

        for mutated in mutations:
            mutated_hash = mutated.compute_variant_config_hash()
            assert mutated_hash != baseline_hash

            ledger = _GateMockLedger()
            gate = MetricIntegrityGate(
                expected_config_hash=baseline_hash,
                ledger=ledger,
                run_id="run-001",
                analytic_consequence="test",
            )
            row = {
                "variant_config_hash": mutated_hash,
                "snapshot_hash": "a" * 64,
                "run_id": "run-001",
            }
            result = gate.check(row, incident_id="INC-001")
            assert result.status == "FAIL"
            assert result.gate_check == "variant_config_hash_match"
            assert len(ledger.entries) == 1
```

- [ ] **Step 2: Run the test — expect RED**

```bash
poetry run pytest tests/test_vcl.py::TestVCLManifest::test_three_mutations -v
```

Expected: `FAILED` with `pydantic_core._pydantic_core.ValidationError: 1 validation error for VCLManifest / model_version / Extra inputs are not permitted`.

- [ ] **Step 3: Add `model_version` and `prompt_template_id` to `helios/vcl/config.py`**

In `helios/vcl/config.py`, after the `ingest_mode` field declaration (line 39) and before the `@field_validator` decorator (line 41), insert:

```python
    # Model identity for C1 hash stability — changing either field invalidates all variant hashes
    model_version: str = "helios-llm-baseline"
    prompt_template_id: str = "baseline-v1"
```

The full field block after the edit (lines 38–42 area):

```python
    # Operational string flag — validated, not a boolean gate
    ingest_mode: str = "recorded"

    # Model identity for C1 hash stability — changing either field invalidates all variant hashes
    model_version: str = "helios-llm-baseline"
    prompt_template_id: str = "baseline-v1"

    @field_validator("ingest_mode")
    @classmethod
    def _validate_ingest_mode(cls, v: str) -> str:
```

- [ ] **Step 4: Run the test — expect GREEN**

```bash
poetry run pytest tests/test_vcl.py::TestVCLManifest::test_three_mutations -v
```

Expected: `PASSED`.

- [ ] **Step 5: Run the full VCL test suite to check for regressions**

```bash
poetry run pytest tests/test_vcl.py -v
```

Expected: all tests pass. The two new VCLManifest fields are additive (defaults provided), so all 8 variant hashes remain unique — they just change value. `test_all_variant_hashes_are_unique` still passes because uniqueness is preserved.

- [ ] **Step 6: Lint and type-check**

```bash
poetry run ruff check helios/ scripts/ tests/ && \
poetry run ruff format --check helios/ scripts/ tests/ && \
poetry run mypy
```

Expected: no errors.

- [ ] **Step 7: Commit Task 1**

```bash
git add tests/test_vcl.py helios/vcl/config.py
git commit -m "$(cat <<'EOF'
feat(vcl): extend VCLManifest with model_version + prompt_template_id; add test_three_mutations

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: test_tamper — write test first, then add TamperDetectedError + verify_hmac_chain

**Background:**
- `HMACChainedLog.verify()` returns `(bool, str)`. It does NOT raise on tamper — it returns `(False, "Line N: ...")`.
- Adding `verify_hmac_chain()` as a thin adapter: it calls `verify()` and raises `TamperDetectedError(msg)` if `ok` is False.
- `TamperDetectedError` must be defined BEFORE `HMACChainedLog` in `hmac_chain.py` because `verify_hmac_chain()` instantiates it at runtime.
- After tampering the middle entry (line 2 of 3), `verify()` catches it at the signature check (not the prev_signature check, because the prev_signature field of line 2 is not tampered — only the `change` field is). The error message is `"Line 2: signature does not verify (entry tampered)."`.
- Post-tamper append works because `previous_signature()` reads the last line from disk (line 3, which is untouched), so `prev_signature` is correctly set for line 4.
- `helios/vcl/` is **exempt** from `flag-guard.py` — adding `class TamperDetectedError` there requires no VCL feature-flag annotation.

**Files:**
- Modify: `tests/test_deviation_log.py`
- Modify: `helios/vcl/hmac_chain.py`

- [ ] **Step 1: Add `TamperDetectedError` import and `test_tamper` to `tests/test_deviation_log.py`**

**1a — Add import** after the existing imports block (after `import pytest` on line 11), before `_HERE = ...`:

```python
from helios.vcl.hmac_chain import TamperDetectedError
```

**1b — Add `test_tamper`** at the end of the file, after `test_canonical_signature_is_deterministic`:

```python
# ── Tamper detection ──────────────────────────────────────────────────────────


def test_tamper(log: Any, log_path: Path) -> None:
    """Middle-entry tamper detected; verify_hmac_chain() raises TamperDetectedError."""
    log.append({**_FIELDS, "change": "first"})
    log.append({**_FIELDS, "change": "second"})
    log.append({**_FIELDS, "change": "third"})

    # Tamper the middle entry (line index 1 = line number 2)
    lines = log_path.read_text(encoding="utf-8").splitlines()
    middle = json.loads(lines[1])
    middle["change"] = "MALICIOUS"
    lines[1] = json.dumps(middle, sort_keys=True)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # verify_hmac_chain() raises on tamper
    with pytest.raises(TamperDetectedError, match="Line 2"):
        log.verify_hmac_chain()

    # verify() backward compat unchanged
    ok, _ = log.verify()
    assert not ok

    # Post-tamper append still works (previous_signature reads last valid line)
    e4 = log.append({**_FIELDS, "change": "fourth"})
    assert e4 is not None

    # File has 4 lines, all valid JSONL
    final_lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(final_lines) == 4
    for line in final_lines:
        json.loads(line)
```

- [ ] **Step 2: Run the test — expect RED**

```bash
poetry run pytest tests/test_deviation_log.py::test_tamper -v
```

Expected: `FAILED` with `AttributeError: 'DeviationLog' object has no attribute 'verify_hmac_chain'`.

- [ ] **Step 3: Add `__all__`, `TamperDetectedError`, and `verify_hmac_chain()` to `helios/vcl/hmac_chain.py`**

**3a — Add `__all__`** after the `TYPE_CHECKING` block (after `from pathlib import Path`) and before `GENESIS`:

```python
__all__ = [
    "GENESIS",
    "HMACChainedLog",
    "TamperDetectedError",
]
```

**3b — Add `TamperDetectedError` class** after `__all__` and before `GENESIS`:

```python

class TamperDetectedError(RuntimeError):
    """Raised by verify_hmac_chain() when HMAC chain integrity fails."""
```

**3c — Add `verify_hmac_chain()`** as the last method of `HMACChainedLog`, after `verify()` (after line 103):

```python
    def verify_hmac_chain(self) -> None:
        """Raises TamperDetectedError on failure; delegates to verify()."""
        ok, msg = self.verify()
        if not ok:
            raise TamperDetectedError(msg)
```

The full module-level section after the edit:

```python
if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "GENESIS",
    "HMACChainedLog",
    "TamperDetectedError",
]


class TamperDetectedError(RuntimeError):
    """Raised by verify_hmac_chain() when HMAC chain integrity fails."""


GENESIS = "GENESIS"
_UNSIGNED_KEYS: frozenset[str] = frozenset({"signature", "deviation_id"})


class HMACChainedLog:
    # ... all existing methods unchanged ...

    def verify(self) -> tuple[bool, str]:
        # ... unchanged ...

    def verify_hmac_chain(self) -> None:
        """Raises TamperDetectedError on failure; delegates to verify()."""
        ok, msg = self.verify()
        if not ok:
            raise TamperDetectedError(msg)
```

- [ ] **Step 4: Run the test — expect GREEN**

```bash
poetry run pytest tests/test_deviation_log.py::test_tamper -v
```

Expected: `PASSED`.

- [ ] **Step 5: Run the full deviation log test suite to check for regressions**

```bash
poetry run pytest tests/test_deviation_log.py tests/test_hmac_chain.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Lint and type-check**

```bash
poetry run ruff check helios/ scripts/ tests/ && \
poetry run ruff format --check helios/ scripts/ tests/ && \
poetry run mypy
```

Expected: no errors.

- [ ] **Step 7: Commit Task 2**

```bash
git add tests/test_deviation_log.py helios/vcl/hmac_chain.py
git commit -m "$(cat <<'EOF'
feat(hmac): add TamperDetectedError + verify_hmac_chain; add test_tamper

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Deviation log entry + full pre-push gate

**Background:** Extending `VCLManifest` with new fields changes the `compute_variant_config_hash()` output for all 8 confirmatory variants. Per CLAUDE.md §Core Invariants: every protocol change with analytic consequence must be logged to `deviation_log.jsonl` via the CLI before merging. Omitting this entry will cause the `ledger_verification.yml` CI job to flag the log as incomplete.

**Files:**
- Append: `deviation_log.jsonl`

- [ ] **Step 1: Load the HMAC secret and append a deviation log entry**

```bash
set -a; source .env; set +a

poetry run python bin/log_deviation.py \
  --stage "Stage 1" \
  --clause "§6.2" \
  --change "Add model_version and prompt_template_id fields to VCLManifest" \
  --reason "Enable test_three_mutations: three mutation types (flag, model version, prompt template) each produce a distinct variant_config_hash" \
  --analytic-consequence "All 8 confirmatory variant_config_hash values change; update vcl_manifest_tracking.md hash registry after merge"
```

Expected output: `✅ Deviation logged: §6.2 | sig=<12-char hex>...`

- [ ] **Step 2: Verify the HMAC chain is clean**

```bash
set -a; source .env; set +a
poetry run python bin/log_deviation.py verify
```

Expected: `✅ Chain verified.`

- [ ] **Step 3: Run the full test suite**

```bash
poetry run pytest -v
```

Expected: all tests pass, coverage ≥ 90%.

- [ ] **Step 4: Run the full pre-push gate sequence**

```bash
set -a; source .env; set +a && \
  poetry run ruff check helios/ scripts/ tests/ && \
  poetry run ruff format --check helios/ scripts/ tests/ && \
  poetry run mypy && \
  poetry run pytest && \
  poetry run python bin/log_deviation.py verify && \
  make validate-tracking
```

Expected: all steps exit 0.

- [ ] **Step 5: Commit the deviation log entry**

```bash
git add deviation_log.jsonl
git commit -m "$(cat <<'EOF'
chore(deviation-log): log VCLManifest hash-breaking extension §6.2

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review Checklist

**Spec coverage:**
- Part 1 (VCLManifest extension): Task 1, Steps 3 and 4 ✓
- Part 1 (`test_three_mutations` — hash diff + gate rejection): Task 1, Steps 1 and 2 ✓
- Part 2 (`TamperDetectedError` + `verify_hmac_chain()`): Task 2, Steps 3 and 4 ✓
- Part 2 (`test_tamper` — middle entry, backward compat, post-tamper append, JSONL structure): Task 2, Steps 1 and 2 ✓
- Deviation log entry: Task 3 ✓

**No placeholders:** All steps show complete code. ✓

**Type consistency:**
- `_GateMockLedger.append(fields: dict[str, str]) -> None` matches `AppendOnlyLedger` protocol ✓
- `verify_hmac_chain(self) -> None` — raises `TamperDetectedError`, returns nothing ✓
- `TamperDetectedError` defined before `verify_hmac_chain()` uses it ✓
