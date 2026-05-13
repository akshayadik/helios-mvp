# Stage 1 Infrastructure — disjointness.py + integrity_gate.py

---

## Context

Four features were requested. Exploration confirmed:

- **Feature 3** (test_vcl.py mutation protection): Already implemented — `test_frozen_raises_on_mutation()` at `tests/test_vcl.py:122`. No action needed.
- **Feature 4** (test_deviation_log.py tamper): Already implemented — `test_verify_chain_fails_on_tampered_log()` and related tests exist. No action needed.
- **Feature 2** (`disjointness.py`): Not implemented. CI already expects `DisjointnessRegistry` with `audit()` + `__len__()` — see `ci.yml:270-308`. The `@gated_by` decorator sets `func.__gated_by__ = flag.value` at `decorators.py:46` but does not register anywhere.
- **Feature 1** (`integrity_gate.py`): Not implemented. `ExclusionLedger` exists in `bin/log_exclusion.py`; the gate receives it via a `Protocol` (Dependency Inversion — no bin/ import needed in the helios library layer).

---

## Task 1 — `helios/vcl/disjointness.py` + patch `decorators.py`

### Design

A module-level `_REGISTRY: dict[str, list[str]]` (qualname → list of flag values) holds all `@gated_by` registrations at import time. `decorators.py` calls `register(qualname, flag_value)` after setting `__gated_by__`. `DisjointnessRegistry` snapshots `_REGISTRY` at construction, filters to `helios.*` paths only (test-decorated functions are excluded), and exposes `audit()` + `__len__()`.

**Violation semantics**: same code path gated by more than one distinct flag (§3.9.1 Threat 2).

**Stage 0 behaviour**: no pipeline functions decorated yet → `_REGISTRY` has only test paths → `helios.*` filter yields empty dict → `audit()` returns `[]` → CI prints "Disjointness audit passed: 0 path(s) registered."

### `helios/vcl/disjointness.py` interface contract

```
_REGISTRY: dict[str, list[str]]           # module-level, populated at decoration time
register(qualname: str, flag_value: str)  # appends to _REGISTRY[qualname]

class DisjointnessRegistry:
    __init__()                            # snapshots _REGISTRY, filters to helios.* keys
    audit() -> list[str]                  # returns violation strings (empty = clean)
    __len__() -> int                      # count of helios.* paths in snapshot
```

Violation = any path whose flag-value list has length > 1.

### Patch `helios/vcl/decorators.py`

Two insertions only:
1. Module-level: `from .disjointness import register as _disjointness_register`
2. Inside `decorator(func)` after line 46: `_disjointness_register(f"{func.__module__}.{func.__qualname__}", flag.value)`

No other changes to `decorators.py`.

### `tests/test_disjointness.py` — required tests

Imports: `from helios.vcl.disjointness import DisjointnessRegistry, _REGISTRY, register` and `from helios.vcl.decorators import gated_by` and `from helios.vcl.registry import VCLFlag` (satisfies flag-guard).

| Test name | What it verifies |
|-----------|-----------------|
| `test_no_helios_paths_registered_at_stage0` | `DisjointnessRegistry()` len is zero (no decorated pipeline fns yet) |
| `test_register_increments_len` | After `register("helios.fake.fn", "dpipe")`, len is 1 |
| `test_single_flag_per_path_has_no_violations` | One flag per path → `audit()` returns `[]` |
| `test_double_gating_produces_violation` | Same path registered with two flags → one violation string |
| `test_violation_string_contains_path_and_flags` | Violation message includes qualname and flag list |
| `test_decorator_registers_helios_module_function` | `@gated_by` on a function with `helios.*` module appears in registry |
| `test_test_module_functions_filtered_out` | Paths starting with `tests.` excluded from `_paths` |
| `test_audit_returns_empty_when_all_paths_have_single_flag` | Multiple distinct paths, each with one flag → `[]` |

**Test isolation**: `_REGISTRY` persists across tests. Use unique fake qualnames (e.g. `f"helios.fake.fn_{uuid.uuid4().hex}"`) or a fixture that saves/restores `_REGISTRY`.

---

## Task 2 — `helios/integrity_gate.py` + `tests/test_integrity_gate.py`

### Design

`AppendOnlyLedger` is a `runtime_checkable` `Protocol` with a single `append(fields: dict[str, str]) -> None` method. `MetricIntegrityGate` depends only on this protocol — no `bin/` imports. The `from_manifest` classmethod factory (calls `manifest.compute_variant_config_hash()`) makes `VCLManifest` a natural top-level import, satisfying `flag-guard.py`.

`GateResult` is a `frozen=True` dataclass with `status: Literal["PASS", "FAIL"]`, `reason: str | None`, `gate_check: str | None`.

### `helios/integrity_gate.py` interface contract

```
Module imports: VCLManifest from helios.vcl.config (satisfies flag-guard)

class AppendOnlyLedger(Protocol, runtime_checkable):
    append(fields: dict[str, str]) -> None

@dataclass(frozen=True)
class GateResult:
    status: Literal["PASS", "FAIL"]
    reason: str | None = None
    gate_check: str | None = None

class MetricIntegrityGate:
    REQUIRED_FIELDS: tuple[str, ...] = (
        "variant_config_hash", "snapshot_hash", "run_id"
    )

    __init__(*, expected_config_hash: str, ledger: AppendOnlyLedger,
             run_id: str, analytic_consequence: str)

    from_manifest(cls, manifest: VCLManifest, *, ledger, run_id,
                  analytic_consequence) -> MetricIntegrityGate
        # calls manifest.compute_variant_config_hash()

    check(row: dict[str, Any], *, incident_id: str) -> GateResult
        # Checks all REQUIRED_FIELDS present (gate_check="required_field_present")
        # Checks row["variant_config_hash"] == self._expected
        #   (gate_check="variant_config_hash_match")
        # On FAIL: calls _fail() which appends to ledger, returns GateResult(FAIL)
        # On PASS: returns GateResult(PASS), no ledger write

    check_consistency(rows: Sequence[dict], *, incident_id: str) -> GateResult
        # Per-row check() first; then cross-row check:
        # All variant_config_hash values equal (gate_check="cross_pipeline_config_hash_match")
        # All snapshot_hash values equal (gate_check="cross_pipeline_snapshot_hash_match")

    _fail(row, incident_id, *, gate_check, reason) -> GateResult
        # Appends 7-field dict to self._ledger matching ExclusionLedger.REQUIRED_FIELDS:
        #   variant_config_hash, snapshot_hash, run_id, incident_id,
        #   gate_check, reason, analytic_consequence
        # Returns GateResult(FAIL, reason, gate_check)
```

### `tests/test_integrity_gate.py` — required tests

Mock ledger (no HMAC, no file I/O): a `_MockLedger` class with `entries: list[dict]` and `append()`.
Imports include `from helios.vcl.config import VCLManifest` (flag-guard compliant).

| Test name | What it verifies |
|-----------|-----------------|
| `test_pass_on_valid_row` | Valid row with all fields + correct config hash → `GateResult(status="PASS")` |
| `test_fail_missing_required_field` | Row missing `run_id` → FAIL, gate_check="required_field_present" |
| `test_fail_missing_snapshot_hash` | Row missing `snapshot_hash` → FAIL |
| `test_fail_config_hash_mismatch` | Wrong `variant_config_hash` → FAIL, gate_check="variant_config_hash_match" |
| `test_fail_writes_all_seven_ledger_fields` | FAIL path → ledger entry contains all 7 ExclusionLedger required fields |
| `test_pass_does_not_write_to_ledger` | PASS → `_MockLedger.entries` remains empty |
| `test_from_manifest_factory_derives_correct_hash` | `from_manifest(full_manifest, ...)` → expected hash matches `full_manifest.compute_variant_config_hash()` |
| `test_check_consistency_pass_on_identical_rows` | Two rows with same hashes → PASS |
| `test_check_consistency_fails_on_config_hash_mismatch` | Two rows with different config hashes → FAIL, gate_check="cross_pipeline_config_hash_match" |
| `test_check_consistency_fails_on_snapshot_hash_mismatch` | Two rows with different snapshot hashes → FAIL, gate_check="cross_pipeline_snapshot_hash_match" |
| `test_gate_result_frozen` | Assigning to `GateResult.status` raises `FrozenInstanceError` |
| `test_appendonly_ledger_protocol_satisfied` | `isinstance(_MockLedger(), AppendOnlyLedger)` is `True` |

---

## Files to Create / Modify

| Action | Path |
|--------|------|
| **Create** | `helios/vcl/disjointness.py` |
| **Modify** | `helios/vcl/decorators.py` — 2 line insertions |
| **Create** | `tests/test_disjointness.py` |
| **Create** | `helios/integrity_gate.py` |
| **Create** | `tests/test_integrity_gate.py` |

No changes to `bin/log_exclusion.py`, `helios/vcl/__init__.py`, or existing test files.

---

## Hooks and Compliance Notes

- `research-compliance.py` blocks specific float and integer literals as word tokens — avoid in all code and docstrings; use integer comparisons (`> 1`, `== 0`) and prose for boundary values.
- `flag-guard.py` exempts `helios/vcl/` entirely. `helios/integrity_gate.py` imports `VCLManifest` at module level — flag-guard compliant.
- Test files import VCL symbols directly — flag-guard compliant.
- No deviation log entry needed: new artefact files, not protocol changes with analytic consequence.

---

## Verification

```bash
# Lint + types + tests
poetry run ruff check helios/ scripts/ tests/ && \
poetry run ruff format --check helios/ scripts/ tests/ && \
poetry run mypy && \
poetry run pytest

# Simulate the CI disjointness job (must exit cleanly)
poetry run python helios/vcl/disjointness.py 2>/dev/null || \
poetry run python - <<'EOF'
from helios.vcl.disjointness import DisjointnessRegistry
r = DisjointnessRegistry()
assert not r.audit(), r.audit()
print(f"Disjointness audit passed: {len(r)} path(s) registered.")
EOF

# Coverage gate
poetry run pytest --cov=helios --cov-report=term-missing
```
